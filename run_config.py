"""설정 파일로 실행 · 조회설정.toml 하나만 고치고 VS Code F5 메뉴에서 고르면 된다

  python run_config.py 확인     조회 대상만 확인 (API 호출 없음)
  python run_config.py 조회     기본 조회와 결과 파일
  python run_config.py 114      마지막으로 조회한 작업에 114On 추가 조회 (job_id 입력 불필요)
  python run_config.py 상태     마지막 작업의 진행 상황
  옵션 --config <파일>  (기본 조회설정.toml)

  · [["조회"]] 블록을 여러 개 두면 구마다 다른 등급을 한 번에 처리한다 (블록끼리는 합집합, 한 작업)
  · 구·동·등급 이름을 잘못 쓰면 비슷한 이름을 추천한다
  · 키는 .env 파일에 한 번만 적어 두면 된다 (.env.example 참고). 이미 환경변수가 있으면 환경변수가 우선
  · 마지막 작업 ID를 .last_job.json 에 기억해 114 조회에 자동으로 넘긴다

pipeline/ 코드는 고치지 않고 service.run_core(), run_114() 를 그대로 부른다. 기존 python run.py run --gu ... 방식도 그대로 쓸 수 있다.
"""
import argparse
import json
import os
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 이하
    sys.exit('Python 3.11 이상이 필요함 (설정 파일을 읽는 tomllib)')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pipeline import credentials, service  # noqa: E402
from pipeline.cli import guarded  # noqa: E402
from pipeline.errors import UsageError  # noqa: E402
from pipeline.selection import FilterSet  # noqa: E402

LAST = os.path.join(HERE, '.last_job.json')
ALLOWED_TOP = {'src', 'work', 'out', 'workers', 'skip_geo', 'run_tag', 'scope114', '조회', 'query'}
# 블록 항목 · 한글 이름과 영어 이름 모두 받음. TOML 은 한글 키를 따옴표로 감싸야 함 ("구" = [...])
BLOCK_KEYS = {'구': 'gu', 'gu': 'gu', '동': 'dong', 'dong': 'dong', '등급': 'rank', 'rank': 'rank', 'id': 'id'}


def load_env(path):
    return credentials.load_env(path)


def _list(v, name):
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(x, (str, int)) for x in v):
        raise UsageError(f'{name} 는 ["값1", "값2"] 형태의 목록이어야 함')
    return [str(x).strip() for x in v if str(x).strip()]


def load_config(path):
    if not os.path.exists(path):
        raise UsageError(f'설정 파일이 없음 · {path}')
    try:
        with open(path, 'rb') as f:
            c = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        hint = ' · 한글 이름은 따옴표로 감싸야 함: [["조회"]], "구" = ["중구"]' if 'key' in str(e) else ''
        raise UsageError(f'설정 파일 문법 오류 · {e}{hint}')
    unknown = set(c) - ALLOWED_TOP
    if unknown:
        raise UsageError(f'설정 파일에 모르는 항목 · {", ".join(sorted(unknown))} (쓸 수 있는 항목: {", ".join(sorted(ALLOWED_TOP))})')
    src = _list(c.get('src'), 'src')
    if not src:
        raise UsageError('설정 파일에 src (원본 CSV 경로) 가 필요함')
    base = os.path.dirname(os.path.abspath(path))
    src = [s if os.path.isabs(s) else os.path.join(base, s) for s in src]
    raw = [c.get('조회') or [], c.get('query') or []]
    if not all(isinstance(x, list) for x in raw):
        raise UsageError('조회 범위는 [["조회"]] 처럼 대괄호 두 겹으로 적어야 함')
    blocks = raw[0] + raw[1] or [{}]
    if not all(isinstance(b, dict) for b in blocks):
        raise UsageError('[["조회"]] 블록 형식이 다름')
    fss = []
    for n, b in enumerate(blocks, 1):
        unk = set(b) - set(BLOCK_KEYS)
        if unk:
            raise UsageError(f'{n}번째 조회 블록에 모르는 항목 · {", ".join(sorted(unk))} (쓸 수 있는 항목: "구", "동", "등급", id)')
        v = {'gu': [], 'dong': [], 'rank': [], 'id': []}
        for k, val in b.items():
            v[BLOCK_KEYS[k]] += _list(val, k)
        fss.append(FilterSet(gu=v['gu'], dong=v['dong'], rank=[r.upper() for r in v['rank']], id=v['id']))
    scope = c.get('scope114', 'no_rep')
    if scope not in service.SCOPES:
        raise UsageError(f'scope114 는 {", ".join(service.SCOPES)} 중 하나')
    return {'src': src, 'filters': fss, 'work': os.path.join(base, c.get('work', 'work')), 'out': os.path.join(base, c.get('out', 'results')),
            'workers': int(c.get('workers', 4)), 'skip_geo': bool(c.get('skip_geo', False)), 'run_tag': str(c.get('run_tag', '')),
            'scope114': scope}


def remember(job_id, cfg_path):
    tmp = LAST + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'job_id': job_id, 'config': os.path.abspath(cfg_path)}, f, ensure_ascii=False)
    os.replace(tmp, LAST)


def last_job():
    if not os.path.exists(LAST):
        raise UsageError('기억된 작업이 없음. 먼저 「조회」를 실행')
    with open(LAST, encoding='utf-8') as f:
        return json.load(f)['job_id']


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description='조회설정.toml 로 실행')
    ap.add_argument('cmd', choices=['확인', '조회', '114', '상태', 'list', 'run', 'run114', 'status'])
    ap.add_argument('--config', default=os.path.join(HERE, '조회설정.toml'))
    ap.add_argument('--env', default=os.path.join(HERE, '.env'))
    a = ap.parse_args(argv)
    cmd = {'list': '확인', 'run': '조회', 'run114': '114', 'status': '상태'}.get(a.cmd, a.cmd)

    def go():
        load_env(a.env)
        c = load_config(a.config)
        if cmd == '확인':
            plan = service.Plan(c['src'], c['filters'], c['skip_geo'], c['run_tag'])
            service.describe_plan(plan, c['work'])
        elif cmd == '조회':
            r = service.run_core(c['src'], c['filters'], c['skip_geo'], c['run_tag'], c['work'], c['out'], c['workers'])
            remember(r['job_id'], a.config)
            print('\n작업 ID를 기억함 · 114On 추가 조회는 「설정파일로 114On 추가 조회」 메뉴나 python run_config.py 114')
        elif cmd == '114':
            service.run_114(last_job(), c['scope114'], c['work'], c['out'])
        elif cmd == '상태':
            service.status(last_job(), c['work'])
    sys.exit(guarded(go))


if __name__ == '__main__':
    main()
