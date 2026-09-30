"""API 키 · 환경변수(또는 .env 파일)에서만 읽는다

키는 파일·로그·결과물 어디에도 쓰지 않는다. 오류 메시지에 키가 섞이면 가리고,
결과 폴더에 키 문자열이 들어갔는지 마지막에 검사한다.
"""
import os
import zipfile

from .errors import MissingCredential, UsageError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENV = os.path.join(ROOT, '.env')

GROUPS = {
    'kakao': ['KAKAO_REST_KEY'],
    'naver_geo': ['NCP_GEO_ID', 'NCP_GEO_SECRET'],
    'naver_hub': ['NCP_HUB_ID', 'NCP_HUB_SECRET'],
}
ALL_NAMES = [n for names in GROUPS.values() for n in names]
_HELP = {
    'kakao': '카카오 개발자 콘솔의 REST API 키',
    'naver_geo': '네이버 클라우드 플랫폼 Maps(Geocoding) Application의 Client ID·Secret',
    'naver_hub': 'NAVER API HUB 지역 검색 Application의 Client ID·Secret',
}


def load_env(path=DEFAULT_ENV):
    """KEY=VALUE 형식의 .env 를 환경변수로 올린다. # 주석과 빈 줄은 건너뜀. 이미 있는 환경변수는 덮어쓰지 않음.
    run.py 와 run_config.py 가 모두 부른다. 올린 키 이름 목록을 돌려줌 (값은 돌려주지 않음)"""
    if not os.path.exists(path):
        return []
    loaded = []
    with open(path, encoding='utf-8-sig') as f:
        for n, line in enumerate(f, 1):
            t = line.strip()
            if not t or t.startswith('#'):
                continue
            if '=' not in t:
                raise UsageError(f'.env {n}번째 줄 형식이 다름 (KEY=VALUE)')
            k, v = t.split('=', 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            # 예시 문서의 「(카카오 키)」 형식을 그대로 따라 괄호로 감싼 경우도 받음
            while len(v) >= 2 and (v[0], v[-1]) in (('(', ')'), ('<', '>'), ('[', ']'), ('{', '}')):
                v = v[1:-1].strip()
            if k and v and not os.environ.get(k):
                os.environ[k] = v
                loaded.append(k)
    return loaded


def get(group):
    """키 묶음을 돌려준다. 없으면 어떤 환경변수가 필요한지 알려 주는 오류"""
    names = GROUPS[group]
    vals = [os.environ.get(n, '').strip() for n in names]
    missing = [n for n, v in zip(names, vals) if not v]
    if missing:
        raise MissingCredential(f'환경변수 {", ".join(missing)} 가 없음 ({_HELP[group]}). '
                                f'.env 파일에 적거나 환경변수로 넣은 뒤 같은 명령으로 다시 실행')
    return vals


def secrets():
    """지금 환경에 있는 키 값들 (가리기·검사용)"""
    return [v for v in (os.environ.get(n, '').strip() for n in ALL_NAMES) if len(v) >= 6]


def placeholders():
    """키 값 → 자리 표시 문자열. 응답 기록 파일에 키 대신 이 문자열을 쓴다"""
    out = {}
    for n in ALL_NAMES:
        v = os.environ.get(n, '').strip()
        if len(v) >= 6:
            out[v] = f'<{n}>'
    return out


def mask(text):
    """글 안의 키 값을 *** 로 가림"""
    t = str(text)
    for v in secrets():
        t = t.replace(v, '***')
    return t


def mask_headers(headers):
    rep = placeholders()
    out = {}
    for k, v in (headers or {}).items():
        v2 = str(v)
        for sec, ph in rep.items():
            v2 = v2.replace(sec, ph)
        out[k] = v2
    return out


def scan(folder):
    """결과 폴더에서 키 문자열이 들어간 파일 목록. xlsx·zip은 안쪽 파일까지 본다"""
    bs = [s.encode('utf-8') for s in secrets()]
    if not bs:
        return []
    hits = []
    for root, _, files in os.walk(folder):
        for fn in files:
            p = os.path.join(root, fn)
            try:
                if fn.lower().endswith(('.xlsx', '.zip')):
                    with zipfile.ZipFile(p) as z:
                        blobs = [z.read(n) for n in z.namelist()]
                else:
                    with open(p, 'rb') as f:
                        blobs = [f.read()]
            except (OSError, zipfile.BadZipFile):
                continue
            if any(b in blob for b in bs for blob in blobs):
                hits.append(p)
    return hits
