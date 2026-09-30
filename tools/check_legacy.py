"""legacy/ 판정 코드가 원본과 같은지 확인

legacy/merge.py, common.py, build_outputs.py 는 프로젝트 문서의 2026-09-28판을 옮겨 적은 것이다.
그중 일부러 고친 곳(original_hashes.json 의 changes)은 따로 적어 두었다. 지금은 common.py 한 곳:
주안동 → 관교 하드코딩을 수집설정.toml 로 옮김.

  python tools/check_legacy.py                 이 폴더의 legacy 파일이 기록과 같은지 (옮겨 적은 원본 + 일부러 고친 곳)
  python tools/check_legacy.py <원본 폴더>      가지고 있는 원본 파일과 비교.
                                               원본에 기록된 수정만 더했을 때 지금 파일과 같으면 「같음 (수정 N곳 반영)」
줄바꿈 방식(CRLF/LF) 차이는 무시한다. 다르면 종료 코드 1.
"""
import difflib
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ['merge.py', 'common.py', 'build_outputs.py']


def text(path):
    with open(path, 'rb') as f:
        return f.read().replace(b'\r\n', b'\n').decode('utf-8')


def sha(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def apply_changes(t, edits):
    for e in edits:
        if t.count(e['old']) != 1:
            return None
        t = t.replace(e['old'], e['new'])
    return t


def main():
    with open(os.path.join(ROOT, 'original_hashes.json'), encoding='utf-8') as f:
        rec = json.load(f)
    changes = rec.get('changes', {})
    bad = 0
    other = sys.argv[1] if len(sys.argv) > 1 else None
    for f in FILES:
        here = text(os.path.join(ROOT, 'legacy', f))
        ch = changes.get(f)
        if other is None:
            want = ch['sha256_after'] if ch else rec['sha256'][f]
            ok = sha(here) == want
            print(f'{f} · {"같음" if ok else "다름"}' + (f' (일부러 고친 곳 {len(ch["edits"])}곳 포함)' if ch and ok else ''))
        else:
            p = os.path.join(other, f)
            if not os.path.exists(p):
                print(f'{f} · 원본 폴더에 없음')
                continue
            orig = text(p)
            expect = apply_changes(orig, ch['edits']) if ch else orig
            ok = expect is not None and sha(expect) == sha(here)
            if ok:
                print(f'{f} · 같음' + (f' (기록된 수정 {len(ch["edits"])}곳 반영)' if ch else ''))
            else:
                print(f'{f} · 다름')
                base = expect if expect is not None else orig
                diff = list(difflib.unified_diff(base.splitlines(), here.splitlines(), '원본' + (' + 기록된 수정' if ch else ''), 'legacy', lineterm='', n=1))
                print('\n'.join(diff[:40]) + ('\n  … (이하 생략)' if len(diff) > 40 else ''))
        bad += not ok
    print(f'기준 · {other or "original_hashes.json"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
