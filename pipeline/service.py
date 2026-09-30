"""전체 흐름 조정 · 작업(job) 단위로 조회, 판정, 결과 파일을 관리한다

작업 ID = CSV 내용, 조회 범위, skip_geo, 코드 해시, run_tag 를 해시한 값의 앞 24자리.
  조건이 같으면 같은 작업으로 이어서 실행하고, 하나라도 다르면 새 작업이 된다.
  (pipeline/ 의 .py 를 고치면 코드 해시가 바뀌어 새 작업이 된다. 이전 작업에 114를 붙일 수도 없게 된다)

작업 폴더 · <work>/jobs/<job_id>/
  job.json        조건과 진행 상태
  state.sqlite3   조회 결과 (한 건마다 저장)
  data/<구>_<동>/     판정기 입력·출력 (input.json, source.csv, A.json, B.json, NG.json, NV.json, results.json, 대기열)
  data114/<구>_<동>/  114On을 붙인 판정용 사본 (+ C.json)
  logs/, traces/(선택)
결과 폴더 · <out>/<job_id>/core/<시각>/ , <out>/<job_id>/114/<시각>/  · 이전 결과를 덮어쓰지 않는다
"""
import datetime
import glob
import hashlib
import json
import os
import shutil
import time

from . import credentials, prepare, reporting
from .errors import PipelineError, StageStopped, UsageError
from .providers.kakao import Kakao, proc_a
from .providers.kb import KB
from .providers.naver import Naver
from .providers.one114 import One114, proc_c
from .providers.zippoom import Zippoom
from .secondary import proc_b
from .selection import FilterSet, load_sources, select
from .stages import run_stage
from . import settings
from .storage import JobLock, Store, code_hash, file_sha256, now_iso, read_json, write_json
from .transport import HttpTransport

SCOPES = ('no_rep', 'no_proxy')
CORE_FILES = ('input.json', 'source.csv', 'A.json', 'B.json', 'NG.json', 'NV.json')


# ---------------------------------------------------------------- 작업 폴더
class JobPaths:
    def __init__(self, work, job_id):
        self.job_id = job_id
        self.dir = os.path.join(work, 'jobs', job_id)
        self.data = os.path.join(self.dir, 'data')
        self.data114 = os.path.join(self.dir, 'data114')
        self.db = os.path.join(self.dir, 'state.sqlite3')
        self.manifest = os.path.join(self.dir, 'job.json')
        self.lock = os.path.join(self.dir, '.lock')
        self.logs = os.path.join(self.dir, 'logs')
        self.traces = os.path.join(self.dir, 'traces')

    def merge_log(self):
        return os.path.join(self.logs, 'legacy.log')


def resolve_job(work, job):
    """24자리 전체나 앞부분(겹치지 않으면)으로 작업을 찾는다"""
    root = os.path.join(work, 'jobs')
    job = (job or '').strip()
    if not job:
        raise UsageError('--job 에 작업 ID가 필요함. run 결과나 status 에서 확인')
    cands = [d for d in (os.listdir(root) if os.path.isdir(root) else []) if d.startswith(job)]
    if not cands:
        raise UsageError(f'작업을 찾지 못함 · {job} (작업 폴더 {root})')
    if len(cands) > 1:
        raise UsageError(f'작업 ID 앞부분이 여러 작업과 겹침 · {", ".join(sorted(cands))}')
    return JobPaths(work, cands[0])


# ---------------------------------------------------------------- 계획
class Plan:
    def __init__(self, src, filter_sets, skip_geo, run_tag):
        self.df_all = load_sources(src)
        self.filter_sets = [fs for fs in (filter_sets or [])] or [FilterSet()]
        self.df = select(self.df_all, self.filter_sets)
        self.groups = prepare.groups(self.df)
        self.files = sorted({p for p in self.df_all['_src']})
        self.file_info = [{'path': p, 'sha256': file_sha256(p), 'rows': int((self.df_all['_src'] == p).sum())} for p in self.files]
        self.skip_geo = bool(skip_geo)
        self.run_tag = (run_tag or '').strip()
        self.code = code_hash()
        self.job_id = job_id_for([f['sha256'] for f in self.file_info], self.filter_sets, self.skip_geo, self.code, self.run_tag)


def job_id_for(csv_shas, filter_sets, skip_geo, code, run_tag):
    filters = sorted(json.dumps(fs.normalized(), ensure_ascii=False, sort_keys=True) for fs in filter_sets)
    key = json.dumps({'csv': sorted(csv_shas), 'filters': filters, 'skip_geo': bool(skip_geo), 'code': code, 'run_tag': run_tag or ''},
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]


def _group_counts(part):
    return {'rows': int(len(part)), 'nt': int(part['_nt'].sum()), 'pt': int(part['_pt'].sum())}


def describe_plan(plan, work, log=print):
    """list 명령 · API를 부르지 않고 조회 대상만 보여 줌"""
    log(f'CSV {len(plan.files)}개 · 전체 {len(plan.df_all):,}행 · 선택 {len(plan.df):,}행')
    for fs in plan.filter_sets:
        log(f'  조회 범위 · {fs.describe()}')
    log('')
    tot = {'sel': 0, 'rows': 0, 'nt': 0, 'pt': 0}
    sel_by = plan.df.groupby(['시군구', '법정동']).size().to_dict()
    for (gu, dong), n_sel in sorted(sel_by.items()):
        part = plan.groups.get((gu, dong))
        c = _group_counts(part) if part is not None else {'rows': 0, 'nt': 0, 'pt': 0}
        grades = part['등급'].value_counts().to_dict() if part is not None else {}
        g = ' '.join(f'{k}{grades[k]}' for k in ['S', 'A', 'B', 'C', 'D'] if k in grades)
        log(f'  {gu} {dong} · 선택 {n_sel} · 조회 대상 {c["rows"]} (이름 {c["nt"]}, 번호 {c["pt"]})' + (f' · 등급 {g}' if g else ''))
        tot['sel'] += n_sel
        for k in ('rows', 'nt', 'pt'):
            tot[k] += c[k]
    log(f'  합계 · 동 {len(sel_by)}곳 · 선택 {tot["sel"]:,} · 조회 대상 {tot["rows"]:,} (이름 {tot["nt"]:,}, 번호 {tot["pt"]:,})')
    jp = JobPaths(work, plan.job_id)
    m = read_json(jp.manifest)
    state = '새 작업' if not m else ('기본 조회 완료' if m['core']['complete'] else '기본 조회 진행 중 · run 으로 이어서 실행')
    log(f'\n작업 ID {plan.job_id} · {state}')
    return tot


# ---------------------------------------------------------------- 공통
def read_queue(group_dir, prefix):
    """merge.py 가 만든 대기열 파일(__loadXxx({...},[...]))에서 행 목록을 읽는다"""
    rows, seen = [], set()
    for f in sorted(glob.glob(os.path.join(group_dir, prefix + '*.js'))):
        with open(f, encoding='utf-8') as fh:
            t = fh.read()
        try:
            k = t.index('},[') + 2
            part = json.loads(t[k:t.rindex(')')])
        except ValueError:
            raise PipelineError(f'대기열 파일 형식이 예상과 다름 · {f}')
        for r in part:
            if str(r[0]) not in seen:
                seen.add(str(r[0]))
                rows.append(r)
    return rows


def _export_ok_only(store, stage, grp, path):
    """성공한 행만 내보냄. merge.py 는 파일에 있는 키를 「이미 조회함」으로 보아 대기열에서 빼기 때문에,
    실패 행을 넣으면 다시 조회되지 않는다"""
    write_json(path, {k: v for k, v in store.all(stage, grp).items() if not (isinstance(v, dict) and v.get('err'))})


class _Clients:
    """키가 실제로 필요한 단계에서만 키를 요구한다"""

    def __init__(self, transport):
        self.t = transport
        self._kakao = None

    def kakao(self):
        if not self._kakao:
            self._kakao = Kakao(self.t, credentials.get('kakao')[0])
        return self._kakao

    def naver_geo(self, gu):
        return Naver(self.t, gu, geo_key=credentials.get('naver_geo'))

    def naver_hub(self, gu):
        return Naver(self.t, gu, hub_key=credentials.get('naver_hub'))


def _new_manifest(plan):
    return {
        'job_id': plan.job_id, 'created': now_iso(), 'updated': now_iso(), 'code_hash': plan.code,
        'params': {'src': plan.file_info, 'filters': [fs.normalized() for fs in plan.filter_sets],
                   'skip_geo': plan.skip_geo, 'run_tag': plan.run_tag},
        'groups': [{'gu': gu, 'dong': dong, 'name': prepare.group_name(gu, dong), **_group_counts(part)}
                   for (gu, dong), part in sorted(plan.groups.items())],
        'core': {'complete': False, 'finished': None, 'exports': []},
        'c114': {'scope': None, 'complete': False, 'finished': None, 'exports': []},
    }


def _save_manifest(jp, m):
    m['updated'] = now_iso()
    write_json(jp.manifest, m)


def _summaries(data_root, groups, store, include_c):
    out = []
    for g in groups:
        res = read_json(os.path.join(data_root, g['name'], 'results.json'), []) or []
        s = {'구': g['gu'], '동': g['dong'], '대상': len(res),
             '이름_대상': sum(1 for x in res if x['nt']), '번호_대상': sum(1 for x in res if x['pt']),
             '건물명_채움': sum(1 for x in res if x['nt'] and x.get('nm')),
             '대표번호_채움': sum(1 for x in res if x['pt'] and x.get('ph')),
             '대리_연락처만': sum(1 for x in res if x['pt'] and not x.get('ph') and (x.get('st') or x.get('re'))),
             '대리_연락처도_없음': sum(1 for x in res if x['pt'] and not x.get('ph') and not (x.get('st') or x.get('re'))),
             '건물명_미해결': sum(1 for x in res if x['nt'] and not x.get('nm')),
             '사람확인필요': sum(1 for x in res if x.get('human'))}
        for st in (('A', 'B', 'NG', 'NV', 'C') if include_c else ('A', 'B', 'NG', 'NV')):
            ok, err = store.counts(st, g['name'])
            s[f'조회_{st}'] = {'성공': ok, '오류': err}
        out.append(s)
    return out


def _export_all(jp, m, data_root, mode, out, store, date, log):
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    base = os.path.join(out, jp.job_id, mode, stamp)
    n = 1
    while os.path.exists(base):
        n += 1
        base = os.path.join(out, jp.job_id, mode, f'{stamp}-{n}')
    files = []
    for g in m['groups']:
        gdir = os.path.join(base, g['name'])
        r = reporting.export_group(data_root, g['gu'], g['dong'], gdir, date, jp.merge_log())
        files.append({'group': g['name'], **{k: os.path.relpath(v, base) if isinstance(v, str) else v for k, v in r.items()},
                      'results_json': os.path.join(g['name'], 'results.json')})
        shutil.copyfile(os.path.join(data_root, g['name'], 'results.json'), os.path.join(gdir, 'results.json'))
        log(f'  결과 · {g["name"]} · {r["rows"]}행 → {gdir}')
    groups = _summaries(data_root, m['groups'], store, mode == '114')
    errors = sum(v['오류'] for g in groups for k, v in g.items() if k.startswith('조회_'))
    summary = {'job_id': jp.job_id, 'mode': mode, 'created': now_iso(), 'date': date, 'errors_remaining': errors,
               'params': m['params'], 'settings': _settings_info(), 'groups': groups, 'files': files}
    if mode == '114':
        summary['scope114'] = m['c114']['scope']
    write_json(os.path.join(base, 'summary.json'), summary)
    hits = credentials.scan(base)
    if hits:
        raise PipelineError(f'결과 파일에서 API 키 문자열이 발견됨 · {hits}. 이 폴더를 공유하지 말 것')
    return base, summary


def _settings_info():
    S = settings.current()
    return {'file': S.path, 'sha': S.sha(), 'extra_words': S.extra_words}


def _settings_note(log):
    """수집설정.toml 을 먼저 읽어 오류를 조회 전에 알리고, 원래 값과 다른 설정이 있으면 주의를 출력"""
    S = settings.current()
    for w in S.warnings:
        log(f'  주의 · {w}')
    return S


# ---------------------------------------------------------------- 기본 조회
def run_core(src, filter_sets=None, skip_geo=False, run_tag='', work='work', out='results', workers=4,
             record_traces=False, transport=None, date=None, log=print):
    if not 1 <= int(workers) <= 4:
        raise UsageError('--workers 는 1~4')
    _settings_note(log)
    plan = Plan(src, filter_sets, skip_geo, run_tag)
    if not plan.groups:
        raise UsageError('선택한 행 중 조회 대상(건물명이나 대표번호가 빈 행)이 없음')
    jp = JobPaths(work, plan.job_id)
    date = date or datetime.date.today().isoformat()
    with JobLock(jp.lock):
        m = read_json(jp.manifest) or _new_manifest(plan)
        _save_manifest(jp, m)
        log(f'작업 ID {plan.job_id} · 동 {len(plan.groups)}곳 · 대상 {sum(len(p) for p in plan.groups.values()):,}건')
        t = transport or HttpTransport(trace_dir=jp.traces if record_traces else None)
        store = Store(jp.db)
        cl = _Clients(t)
        try:
            for (gu, dong), part in sorted(plan.groups.items()):
                _run_core_group(jp, store, t, cl, gu, dong, part, plan.skip_geo, int(workers), log)
            m['core']['complete'] = True
            m['core']['finished'] = now_iso()
            _save_manifest(jp, m)
            log('\n결과 파일 만드는 중')
            base, summary = _export_all(jp, m, jp.data, 'core', out, store, date, log)
            m['core']['exports'].append({'at': now_iso(), 'dir': base})
            m['core']['errors_remaining'] = summary['errors_remaining']
            _save_manifest(jp, m)
        except StageStopped:
            m['core']['complete'] = False
            _save_manifest(jp, m)
            raise
        finally:
            store.close()
    _print_summary(summary, log)
    if summary['errors_remaining']:
        log(f'\n주의 · 조회 오류가 남은 건물 {summary["errors_remaining"]}건. 결과 파일에는 「조회 오류 또는 미조회」로 표시됨. '
            f'같은 명령으로 다시 실행하면 그 건물만 다시 조회함')
    log(f'\n작업 ID {plan.job_id} · 결과 폴더 {base}')
    return {'job_id': plan.job_id, 'dir': base, 'summary': summary, 'requests': dict(t.count)}


def _run_core_group(jp, store, t, cl, gu, dong, part, skip_geo, workers, log):
    name = prepare.group_name(gu, dong)
    gdir = os.path.join(jp.data, name)
    rows_full = prepare.write_group(gdir, part)
    rows = prepare.compact(rows_full)
    log(f'\n■ {gu} {dong} · 대상 {len(rows)}건')
    key0 = lambda b: b[0]  # noqa: E731
    have_a = store.ok_keys('A', name)
    have_b = store.ok_keys('B', name)
    if any(str(b[0]) not in have_a or str(b[0]) not in have_b for b in rows):
        kakao = cl.kakao()
    else:
        kakao = None
    run_stage('A', name, rows, key0, lambda b: proc_a(kakao, gu, b), store, t, '카카오', workers=workers, log=log)
    store.export('A', name, os.path.join(gdir, 'A.json'))
    A = store.all('A', name)
    rows_b = [b for b in rows if str(b[0]) in store.ok_keys('A', name)]
    kb, zp = KB(t), Zippoom(t)
    run_stage('B', name, rows_b, key0, lambda b: proc_b(kakao, kb, zp, t.sleep, gu, b, A[str(b[0])]), store, t,
              'KB부동산·집품', after_error_sleep=3.0, log=log)
    store.export('B', name, os.path.join(gdir, 'B.json'))
    _export_ok_only(store, 'NG', name, os.path.join(gdir, 'NG.json'))
    _export_ok_only(store, 'NV', name, os.path.join(gdir, 'NV.json'))
    reporting.merge(jp.data, gu, dong, 'none', jp.merge_log())
    if not skip_geo:
        gq = read_queue(gdir, 'naver_geo_')
        if [q for q in gq if str(q[0]) not in store.ok_keys('NG', name)]:
            nv = cl.naver_geo(gu)
            run_stage('NG', name, gq, key0, nv.proc_geo, store, t, '네이버 지오코딩', log=log)
            _export_ok_only(store, 'NG', name, os.path.join(gdir, 'NG.json'))
            reporting.merge(jp.data, gu, dong, 'none', jp.merge_log())
    vq = read_queue(gdir, 'naver_verify_')
    if [q for q in vq if str(q[0]) not in store.ok_keys('NV', name)]:
        nv = cl.naver_hub(gu)
        run_stage('NV', name, vq, key0, nv.proc_verify, store, t, '네이버 교차 확인', log=log)
        _export_ok_only(store, 'NV', name, os.path.join(gdir, 'NV.json'))
        reporting.merge(jp.data, gu, dong, 'none', jp.merge_log())
    ea, eb = store.counts('A', name)[1], store.counts('B', name)[1]
    if ea or eb:
        log(f'  조회 오류가 남은 건물 · 카카오 {ea}, KB부동산·집품 {eb}. 같은 명령으로 다시 실행하면 그 건물만 다시 조회')


# ---------------------------------------------------------------- 114On
def run_114(job, scope='no_rep', work='work', out='results', transport=None, date=None, log=print):
    if scope not in SCOPES:
        raise UsageError(f'--scope 는 {", ".join(SCOPES)} 중 하나')
    _settings_note(log)
    jp = resolve_job(work, job)
    date = date or datetime.date.today().isoformat()
    with JobLock(jp.lock):
        m = read_json(jp.manifest)
        if not m or not m['core']['complete']:
            raise UsageError('기본 조회(run)가 끝난 작업에만 114On을 붙일 수 있음. 먼저 같은 조건으로 run 을 끝까지 실행')
        if m['code_hash'] != code_hash():
            raise UsageError('이 작업을 만든 뒤 pipeline/ 코드가 바뀌어 이어서 실행할 수 없음. 같은 조건으로 run 을 다시 실행해 새 작업을 만든 뒤 114를 붙일 것')
        if m['core'].get('errors_remaining'):
            log(f'  주의 · 기본 조회 오류가 남은 건물 {m["core"]["errors_remaining"]}건은 114 대기열에서 빠짐. 먼저 run 을 다시 실행해 오류를 줄이는 것을 권함')
        if m['c114']['scope'] and m['c114']['scope'] != scope:
            log(f'  주의 · 이전 114 범위 {m["c114"]["scope"]} → 이번 {scope}. 이미 조회한 건물은 다시 조회하지 않음')
        m['c114']['scope'] = scope
        m['c114']['complete'] = False
        _save_manifest(jp, m)
        t = transport or HttpTransport()
        store = Store(jp.db)
        one = One114(t)
        try:
            for g in m['groups']:
                name, gu, dong = g['name'], g['gu'], g['dong']
                src_dir, gdir = os.path.join(jp.data, name), os.path.join(jp.data114, name)
                os.makedirs(gdir, exist_ok=True)
                for f in CORE_FILES:
                    if os.path.exists(os.path.join(src_dir, f)):
                        shutil.copyfile(os.path.join(src_dir, f), os.path.join(gdir, f))
                _export_ok_only(store, 'C', name, os.path.join(gdir, 'C.json'))
                reporting.merge(jp.data114, gu, dong, scope, jp.merge_log())
                q = read_queue(gdir, 'q114_')
                todo = [x for x in q if str(x[0]) not in store.ok_keys('C', name)]
                log(f'\n■ {gu} {dong} · 114On 대기 {len(todo)}건 (건당 약 5~14초)')
                run_stage('C', name, q, lambda x: x[0], lambda x: proc_c(one, gu, x, lambda: int(time.time() * 1000)),
                          store, t, '114On', log=log)
                _export_ok_only(store, 'C', name, os.path.join(gdir, 'C.json'))
                reporting.merge(jp.data114, gu, dong, scope, jp.merge_log())
            m['c114']['complete'] = True
            m['c114']['finished'] = now_iso()
            _save_manifest(jp, m)
            log('\n결과 파일 만드는 중')
            base, summary = _export_all(jp, m, jp.data114, '114', out, store, date, log)
            m['c114']['exports'].append({'at': now_iso(), 'dir': base})
            m['c114']['errors_remaining'] = summary['errors_remaining']
            _save_manifest(jp, m)
        finally:
            store.close()
    _print_summary(summary, log)
    return {'job_id': jp.job_id, 'dir': base, 'summary': summary, 'requests': dict(t.count)}


# ---------------------------------------------------------------- 결과 다시 만들기·상태
def export(job, mode='core', work='work', out='results', date=None, log=print):
    """API를 부르지 않고 저장된 조회 결과로 판정과 결과 파일을 다시 만든다"""
    if mode not in ('core', '114'):
        raise UsageError('--mode 는 core 또는 114')
    _settings_note(log)
    jp = resolve_job(work, job)
    date = date or datetime.date.today().isoformat()
    with JobLock(jp.lock):
        m = read_json(jp.manifest)
        key = 'core' if mode == 'core' else 'c114'
        if not m[key]['complete']:
            raise UsageError(f'{mode} 조회가 끝나지 않은 작업 · 먼저 {"run" if mode == "core" else "run114"} 를 끝까지 실행')
        store = Store(jp.db)
        try:
            root = jp.data if mode == 'core' else jp.data114
            scope = 'none' if mode == 'core' else m['c114']['scope']
            for g in m['groups']:
                reporting.merge(root, g['gu'], g['dong'], scope, jp.merge_log())
            base, summary = _export_all(jp, m, root, mode, out, store, date, log)
            m[key]['exports'].append({'at': now_iso(), 'dir': base})
            _save_manifest(jp, m)
        finally:
            store.close()
    _print_summary(summary, log)
    return {'job_id': jp.job_id, 'dir': base, 'summary': summary}


def status(job=None, work='work', log=print):
    root = os.path.join(work, 'jobs')
    if not job:
        ids = sorted(os.listdir(root)) if os.path.isdir(root) else []
        if not ids:
            log(f'작업이 없음 · {root}')
            return []
        rows = []
        for j in ids:
            m = read_json(os.path.join(root, j, 'job.json'))
            if not m:
                continue
            rows.append(m)
        rows.sort(key=lambda x: x['updated'], reverse=True)
        for m in rows:
            groups = ', '.join(g['name'] for g in m['groups'][:4]) + (' 외' if len(m['groups']) > 4 else '')
            st = '완료' if m['core']['complete'] else '진행 중'
            if m['core'].get('errors_remaining'):
                st += f' (오류 남음 {m["core"]["errors_remaining"]})'
            s114 = f' · 114 {m["c114"]["scope"]} {"완료" if m["c114"]["complete"] else "진행 중"}' if m['c114']['scope'] else ''
            log(f'{m["job_id"]} · {m["updated"]} · 기본 조회 {st}{s114} · {groups}')
        return rows
    jp = resolve_job(work, job)
    m = read_json(jp.manifest)
    log(f'작업 ID {m["job_id"]} · 만든 때 {m["created"]} · 마지막 {m["updated"]}')
    log('CSV · ' + ', '.join(os.path.basename(f['path']) for f in m['params']['src']))
    for f in m['params']['filters']:
        log('조회 범위 · ' + FilterSet(**f).describe())
    log(f'skip_geo {m["params"]["skip_geo"]} · run_tag {m["params"]["run_tag"] or "-"} · 코드 {"같음" if m["code_hash"] == code_hash() else "바뀜 (이어서 실행 불가)"}')
    store = Store(jp.db)
    try:
        for g in m['groups']:
            parts = []
            for st in ('A', 'B', 'NG', 'NV', 'C'):
                ok, err = store.counts(st, g['name'])
                if ok or err:
                    parts.append(f'{st} {ok}' + (f'(오류 {err})' if err else ''))
            log(f'  {g["name"]} · 대상 {g["rows"]} · ' + (' · '.join(parts) or '아직 조회 전'))
    finally:
        store.close()
    err_txt = f' · 오류 남음 {m["core"]["errors_remaining"]}건 (run 다시 실행)' if m['core'].get('errors_remaining') else ''
    log(f'기본 조회 {"완료" if m["core"]["complete"] else "진행 중"}{err_txt}' + (f' · 마지막 결과 {m["core"]["exports"][-1]["dir"]}' if m['core']['exports'] else ''))
    if m['c114']['scope']:
        log(f'114On {m["c114"]["scope"]} {"완료" if m["c114"]["complete"] else "진행 중"}' + (f' · 마지막 결과 {m["c114"]["exports"][-1]["dir"]}' if m['c114']['exports'] else ''))
    return m


def _print_summary(summary, log):
    log('')
    for s in summary['groups']:
        log(f'  {s["구"]} {s["동"]} · 대상 {s["대상"]} · 건물명 {s["건물명_채움"]}/{s["이름_대상"]} · 대표번호 {s["대표번호_채움"]}/{s["번호_대상"]}'
            f' · 대리만 {s["대리_연락처만"]} · 사람 확인 {s["사람확인필요"]}')
