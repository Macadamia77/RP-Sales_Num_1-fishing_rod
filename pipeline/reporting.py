"""legacy 스크립트 실행 어댑터 · 판정(merge.py)과 결과 파일(export_selected.py)

legacy 스크립트는 원본 그대로 두고 별도 프로세스로 실행한다. 자식 프로세스에는 API 키 환경변수를 넘기지 않는다.
출력은 작업 폴더의 logs/ 에 남기고, 실패하면 마지막 몇 줄을 오류 메시지에 담는다.
"""
import os
import subprocess
import sys

from . import credentials
from .settings import current as settings
from .csv_export import xlsx_to_csv
from .errors import PipelineError
from .storage import LEGACY_DIR


def _env():
    e = {k: v for k, v in os.environ.items() if k not in credentials.ALL_NAMES}
    e['PYTHONIOENCODING'] = 'utf-8'
    e['PYTHONUTF8'] = '1'
    # 판정 코드(common.region_words)가 쓰는 동별 추가 지역어. 수집설정.toml [region.extra_words]
    e['COLLECTOR_REGION_EXTRA'] = settings().extra_words_json()
    return e


def _run(script, args, log_path):
    cmd = [sys.executable, os.path.join(LEGACY_DIR, script), *args]
    r = subprocess.run(cmd, env=_env(), cwd=LEGACY_DIR, capture_output=True, text=True, encoding='utf-8', errors='replace')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f'$ {script} {" ".join(args)}\n{r.stdout}{r.stderr}\n')
    if r.returncode != 0:
        tail = '\n'.join((r.stdout + r.stderr).strip().splitlines()[-6:])
        raise PipelineError(f'{script} 실행 실패 (코드 {r.returncode})\n{credentials.mask(tail)}')
    return r.stdout


def merge(data_root, gu, dong, scope114, log_path):
    return _run('merge.py', ['--work', data_root, '--gu', gu, '--dong', dong, '--scope114', scope114], log_path)


def export_group(data_root, gu, dong, out_dir, date, log_path):
    """엑셀·HTML 5종·CSV를 out_dir 에 만든다. 만든 파일 경로를 돌려줌"""
    _run('export_selected.py', ['--work', data_root, '--gu', gu, '--dong', dong, '--out', out_dir, '--date', date], log_path)
    xlsx = os.path.join(out_dir, f'콜리스트_{gu}_{dong}_재검색결과_{date}.xlsx')
    csv_path, n = xlsx_to_csv(xlsx, dong)
    return {'xlsx': xlsx, 'csv': csv_path, 'rows': n}
