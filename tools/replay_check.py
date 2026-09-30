"""기록 재생 검증 · run --record-traces 로 남긴 응답으로 네트워크 없이 다시 돌려 결과가 같은지 확인

  python tools/replay_check.py --src <CSV> [--gu ..] [--dong ..] [--rank ..] --job <기준 작업 ID> [--work work]

기준 작업의 traces 폴더를 재생해 새 작업(run_tag=replay)을 만들고, 두 작업의 마지막 core 결과를 건물별로 비교한다.
코드를 고친 뒤 기존 동작이 바뀌지 않았는지 확인할 때 쓴다. API 키가 필요 없다.
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import replay, service  # noqa: E402
from pipeline.selection import FilterSet  # noqa: E402
from pipeline.storage import read_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', nargs='+', required=True)
    for k in ('gu', 'dong', 'rank', 'id'):
        ap.add_argument('--' + k, nargs='*', default=[])
    ap.add_argument('--skip-geo', action='store_true')
    ap.add_argument('--job', required=True)
    ap.add_argument('--work', default='work')
    a = ap.parse_args()
    base = service.resolve_job(a.work, a.job)
    m = read_json(base.manifest)
    if not os.path.isdir(base.traces):
        sys.exit('기준 작업에 traces 폴더가 없음. run --record-traces 로 만든 작업이어야 함')
    tmp = tempfile.mkdtemp(prefix='replay_')
    fs = [FilterSet(gu=a.gu, dong=a.dong, rank=a.rank, id=a.id)]
    for k in ('KAKAO_REST_KEY', 'NCP_GEO_ID', 'NCP_GEO_SECRET', 'NCP_HUB_ID', 'NCP_HUB_SECRET'):
        os.environ.setdefault(k, f'<{k}>')
    r, t = replay.replay_core(a.src, fs, base.traces, os.path.join(tmp, 'work'), os.path.join(tmp, 'results'), skip_geo=a.skip_geo)
    diffs = replay.compare_results(m['core']['exports'][-1]['dir'], r['dir'])
    print(json.dumps({'요청': t.n, '주소·헤더 불일치': t.bad[:5], '남은 기록': t.leftover(), '결과가 다른 건물': diffs}, ensure_ascii=False, indent=1))
    sys.exit(1 if (diffs or t.bad) else 0)


if __name__ == '__main__':
    main()
