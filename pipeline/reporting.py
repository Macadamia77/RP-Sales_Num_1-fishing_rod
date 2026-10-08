"""판정(judge/merge.py)과 결과 파일(judge/export_selected.py) 실행

판정 코드가 print 로 남기는 요약은 작업 폴더의 logs/judge.log 에 모으고, 실패하면 마지막 몇 줄을 오류 메시지에 담는다.
"""
import io
import os
import traceback
from contextlib import redirect_stdout

from . import credentials
from .csv_export import xlsx_to_csv
from .errors import PipelineError
from .judge import export_selected
from .judge import merge as judge


def _run(name, fn, args, log_path):
    buf = io.StringIO()
    err = None
    try:
        with redirect_stdout(buf):
            fn(*args)
    except (Exception, SystemExit) as e:   # 판정 코드는 입력이 없으면 SystemExit 을 던짐
        err = e
        buf.write(traceback.format_exc() if isinstance(e, Exception) else f'{e}\n')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f'$ {name} {" ".join(map(str, args))}\n{buf.getvalue()}\n')
    if err is not None:
        tail = '\n'.join(buf.getvalue().strip().splitlines()[-6:])
        raise PipelineError(f'{name} 실행 실패\n{credentials.mask(tail)}') from err
    return buf.getvalue()


def merge(data_root, gu, dong, scope114, log_path):
    return _run('merge', judge.run, (data_root, gu, dong, scope114), log_path)


def export_group(data_root, gu, dong, out_dir, date, log_path):
    """엑셀·HTML 5종·CSV를 out_dir 에 만든다. 만든 파일 경로를 돌려줌"""
    _run('export_selected', export_selected.run, (data_root, gu, dong, out_dir, date), log_path)
    xlsx = os.path.join(out_dir, f'콜리스트_{gu}_{dong}_재검색결과_{date}.xlsx')
    csv_path, n = xlsx_to_csv(xlsx, dong)
    return {'xlsx': xlsx, 'csv': csv_path, 'rows': n}
