"""명령줄 · 하위 명령 5개

  list    조회 대상만 확인 (API 호출 없음, 키 불필요)
  run     기본 조회 · 카카오 → KB·집품 → 판정 → 네이버 → 판정 → 결과 파일
  run114  기본 조회가 끝난 작업에 114On 추가 조회
  export  저장된 조회 결과로 판정과 결과 파일만 다시 만들기
  status  작업 목록 또는 한 작업의 진행 상황

종료 코드 · 성공 0, 실패 1, 사용법 오류 2, 취소(Ctrl+C) 130
"""
import argparse
import sys

from . import credentials, service
from .errors import JobLocked, PipelineError, StageStopped, UsageError
from .selection import FilterSet

EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_CANCEL = 0, 1, 2, 130


def _split(values):
    """「중구,연수구」처럼 쉼표로 붙여 넣은 값도 나눈다 (VS Code 입력창 대응). 공백은 이름의 일부일 수 있어 나누지 않음"""
    out = []
    for v in values or []:
        out += [x.strip() for x in str(v).split(',') if x.strip()]
    return out


def _filters(a):
    return [FilterSet(gu=_split(a.gu), dong=_split(a.dong), rank=[r.upper() for r in _split(a.rank)], id=_split(a.id))]


def _add_range(p):
    p.add_argument('--src', nargs='+', required=True, help='CSV 경로나 패턴. 여러 개 가능 (예: "C:/data/콜리스트_*.csv")')
    p.add_argument('--gu', nargs='*', default=[], help='시군구. 생략하면 전체')
    p.add_argument('--dong', nargs='*', default=[], help='법정동. CSV에 적힌 이름 그대로')
    p.add_argument('--rank', nargs='*', default=[], help='등급 S A B C D')
    p.add_argument('--id', nargs='*', default=[], help='buildingRosterIdx')
    p.add_argument('--skip-geo', action='store_true', help='네이버 지오코딩만 건너뜀')
    p.add_argument('--run-tag', default='', help='같은 범위를 새로 다시 조회할 때 붙이는 이름')
    p.add_argument('--work', default='work', help='작업 상태 폴더')


def build_parser():
    ap = argparse.ArgumentParser(prog='run.py', description='인천 건물정보 수집기 · 콜리스트의 빈 건물명·대표번호 채우기')
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('list', help='조회 대상만 확인 (API 호출 없음)')
    _add_range(p)
    p = sp.add_parser('run', help='기본 조회와 결과 파일')
    _add_range(p)
    p.add_argument('--out', default='results', help='결과 폴더')
    p.add_argument('--workers', type=int, default=4, help='카카오 동시 조회 수 1~4')
    p.add_argument('--record-traces', action='store_true', help='응답을 기록해 두기 (나중에 네트워크 없이 재생 검증용)')
    p = sp.add_parser('run114', help='114On 추가 조회')
    p.add_argument('--job', required=True)
    p.add_argument('--scope', default='no_rep', choices=list(service.SCOPES),
                   help='no_rep: 대표번호가 없는 행 · no_proxy: 대표번호도 대리 연락처도 없는 행')
    p.add_argument('--work', default='work')
    p.add_argument('--out', default='results')
    p = sp.add_parser('export', help='결과 파일 다시 만들기 (API 호출 없음)')
    p.add_argument('--job', required=True)
    p.add_argument('--mode', default='core', choices=['core', '114'])
    p.add_argument('--work', default='work')
    p.add_argument('--out', default='results')
    p = sp.add_parser('status', help='작업 상태')
    p.add_argument('--job', default='')
    p.add_argument('--work', default='work')
    return ap


def dispatch(a, log=print):
    if a.cmd == 'list':
        plan = service.Plan(a.src, _filters(a), a.skip_geo, a.run_tag)
        return service.describe_plan(plan, a.work, log)
    if a.cmd == 'run':
        return service.run_core(a.src, _filters(a), a.skip_geo, a.run_tag, a.work, a.out, a.workers, a.record_traces, log=log)
    if a.cmd == 'run114':
        return service.run_114(a.job, a.scope, a.work, a.out, log=log)
    if a.cmd == 'export':
        return service.export(a.job, a.mode, a.work, a.out, log=log)
    if a.cmd == 'status':
        return service.status(a.job, a.work, log)
    raise UsageError(f'알 수 없는 명령 {a.cmd}')


def guarded(fn, log=print, err=None):
    """오류 종류별 종료 코드와 안내. 메시지에 섞인 키는 가림"""
    err = err or (lambda s: print(s, file=sys.stderr))
    try:
        fn()
        return EXIT_OK
    except KeyboardInterrupt:
        err('\n취소함. 끝난 건물은 저장되어 있어 같은 명령으로 다시 실행하면 이어서 함')
        return EXIT_CANCEL
    except UsageError as e:
        err(f'사용법 오류 · {credentials.mask(e)}')
        return EXIT_USAGE
    except StageStopped as e:
        err(f'\n멈춤 · {credentials.mask(e)}\n끝난 건물은 저장되어 있음. 원인을 해결한 뒤 같은 명령으로 다시 실행하면 이어서 함')
        return EXIT_FAIL
    except JobLocked as e:
        err(str(e))
        return EXIT_FAIL
    except PipelineError as e:
        err(f'실패 · {credentials.mask(e)}')
        return EXIT_FAIL
    except Exception as e:  # noqa: BLE001
        err(f'예상하지 못한 오류 · {type(e).__name__}: {credentials.mask(e)}')
        return EXIT_FAIL


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)   # 잘못된 옵션은 argparse 가 종료 코드 2로 끝냄

    def go():
        credentials.load_env(credentials.DEFAULT_ENV)   # run.py 옆의 .env (없으면 건너뜀). 이미 있는 환경변수가 우선
        return dispatch(a)
    sys.exit(guarded(go))
