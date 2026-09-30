"""기록 재생 · run --record-traces 로 남긴 응답을 네트워크 없이 다시 돌려, 코드를 고친 뒤에도 같은 결과가 나오는지 확인

사용 예 (tools/replay_check.py 가 이 함수를 부름)
  기준 작업의 traces 폴더와 같은 CSV·같은 조회 범위로 새 작업 폴더에서 run_core 를 돌리고,
  두 작업의 results.json 을 건물별로 비교한다.
"""
import json
import os

from . import service
from .storage import read_json
from .transport import ReplayTransport


def replay_core(src, filter_sets, traces, work, out, skip_geo=False, run_tag='replay', log=print):
    t = ReplayTransport(traces)
    r = service.run_core(src, filter_sets, skip_geo=skip_geo, run_tag=run_tag, work=work, out=out, workers=1, transport=t, log=log)
    return r, t


def compare_results(dir_a, dir_b):
    """두 결과 폴더(core/<시각>)의 results.json 을 건물별로 비교. 다른 건물 ID 목록"""
    diffs = {}
    for g in sorted(os.listdir(dir_a)):
        pa, pb = os.path.join(dir_a, g, 'results.json'), os.path.join(dir_b, g, 'results.json')
        if not os.path.exists(pa):
            continue
        ra = {str(x['i']): x for x in read_json(pa, [])}
        rb = {str(x['i']): x for x in read_json(pb, [])} if os.path.exists(pb) else {}
        bad = [k for k in sorted(set(ra) | set(rb)) if json.dumps(ra.get(k), sort_keys=True, ensure_ascii=False) != json.dumps(rb.get(k), sort_keys=True, ensure_ascii=False)]
        if bad:
            diffs[g] = bad
    return diffs
