"""수집설정.toml 읽기 · 코드에 박혀 있던 값을 한곳에 모음

  [region]   시도 이름, 동별로 더하는 지역어
  [urls]     조회하는 사이트 주소
  [timing]   요청 사이 간격(초)
  [limits]   오류 몇 건에서 멈출지, 진행 표시 간격

파일이 없거나 항목을 생략하면 아래 DEFAULTS 를 쓴다. DEFAULTS 는 원본 collector.js·naver.js·common.py 의 값과 같다.
파일 위치는 환경변수 COLLECTOR_SETTINGS 로 바꿀 수 있다 (기본: 이 폴더 위의 수집설정.toml).
"""
import copy
import hashlib
import json
import os
import re
import threading

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 이하
    tomllib = None

from .errors import UsageError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, '수집설정.toml')

DEFAULTS = {
    'region': {
        'sido': '인천광역시',
        # 지역어: 관리사무소 이름을 비교할 때 지우는 지역 이름. 구·동 이름에서 자동으로 만들고, 여기 적은 것을 더한다
        # 키는 「동」 또는 「구 동」. 원본 common.py 의 「주안동이면 관교를 더함」을 옮긴 것
        'extra_words': {'주안동': ['관교']},
    },
    'urls': {
        'kakao': 'https://dapi.kakao.com/v2/local/search/',
        'kb': 'https://api.kbland.kr/land-complex/',
        'zippoom': 'https://live.zippo-om.com/api/v1/buildings/search/autoComplete?keyword=',
        'naver_geo': 'https://maps.apigw.ntruss.com',
        'naver_hub': 'https://naverapihub.apigw.ntruss.com',
        'one114': 'https://www.114.co.kr/action/search',
    },
    'timing': {
        'kb_zippoom_gap': 0.35,
        'one114_gap': 4.5,
        'naver_geo_gap': 0.12,
        'naver_local_gap': 0.15,
    },
    'limits': {
        'max_errors': 3,
        'progress_every': 20,
    },
}

# 판정 규칙(judge/common.py 등)이 인천 주소 형식을 기준으로 짜여 있어, 지금은 인천만 받는다.
# 다른 시도를 넣으려면 판정 규칙의 주소 정리 부분도 함께 고쳐야 한다 (검수보고서 1-13)
SUPPORTED_SIDO = {'인천광역시': '인천'}


class Settings:
    def __init__(self, data, path):
        self.data = data
        self.path = path
        r, u, t, lim = data['region'], data['urls'], data['timing'], data['limits']
        self.sido = r['sido']
        self.sido_short = SUPPORTED_SIDO[self.sido]
        self.extra_words = r['extra_words']
        self.urls = u
        self.kb_zippoom_gap = t['kb_zippoom_gap']
        self.one114_gap = t['one114_gap']
        self.naver_geo_gap = t['naver_geo_gap']
        self.naver_local_gap = t['naver_local_gap']
        self.max_errors = lim['max_errors']
        self.progress_every = lim['progress_every']
        self.warnings = _warnings(data)

    def sha(self):
        """적용된 값 전체의 지문. 작업 기록과 summary.json 에 남긴다"""
        return hashlib.sha256(json.dumps(self.data, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]

    def sido_prefix_re(self):
        """주소 앞의 「인천광역시 ○○구 」 또는 「인천 ○○구 」 부분 (원본 JS 의 /^인천(광역시)?\\s*[가-힣]+(구|군)\\s*/ 와 같음)"""
        rest = self.sido[len(self.sido_short):]
        return re.escape(self.sido_short) + '(' + re.escape(rest) + ')?'


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate(raw, path):
    name = os.path.basename(path)
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise UsageError(f'{name} · 모르는 구역 [{", ".join(sorted(unknown))}] (쓸 수 있는 구역: {", ".join(DEFAULTS)})')
    out = copy.deepcopy(DEFAULTS)
    for sec, vals in raw.items():
        if not isinstance(vals, dict):
            raise UsageError(f'{name} · [{sec}] 는 구역이어야 함')
        bad = set(vals) - set(DEFAULTS[sec])
        if bad:
            raise UsageError(f'{name} · [{sec}] 에 모르는 항목 {", ".join(sorted(bad))} (쓸 수 있는 항목: {", ".join(DEFAULTS[sec])})')
        out[sec].update(vals)
    r = out['region']
    if r['sido'] not in SUPPORTED_SIDO:
        raise UsageError(f'{name} · sido 는 지금 {", ".join(SUPPORTED_SIDO)} 만 가능 (판정 규칙이 인천 주소 기준). 받은 값 {r["sido"]!r}')
    ew = r['extra_words']
    if not isinstance(ew, dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)
                                           for k, v in ew.items()):
        raise UsageError(f'{name} · [region.extra_words] 는 "동" = ["지역어", ...] 형태여야 함')
    for k in ew:
        parts = k.split()
        if not (1 <= len(parts) <= 2) or not re.search(r'(동|가|리|읍|면)$', parts[-1]):
            raise UsageError(f'{name} · [region.extra_words] 의 키는 "주안동" 이나 "미추홀구 주안동" 형태여야 함 · 받은 값 {k!r}')
    for k, v in out['urls'].items():
        if not isinstance(v, str) or not v.startswith('https://'):
            raise UsageError(f'{name} · [urls] {k} 는 https:// 로 시작하는 주소여야 함')
    for k, v in out['timing'].items():
        if not _is_num(v) or v < 0:
            raise UsageError(f'{name} · [timing] {k} 는 0 이상의 숫자(초)여야 함')
    for k, v in out['limits'].items():
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise UsageError(f'{name} · [limits] {k} 는 1 이상의 정수여야 함')
    return out


def _warnings(data):
    w = []
    for k, v in data['timing'].items():
        base = DEFAULTS['timing'][k]
        if v < base:
            w.append(f'[timing] {k} = {v} 는 원래 값 {base} 보다 짧음. 차단되거나 호출 한도에 걸릴 수 있음')
    if data['urls'] != DEFAULTS['urls']:
        w.append('[urls] 사이트 주소가 기본값과 다름: ' + ', '.join(k for k in data['urls'] if data['urls'][k] != DEFAULTS['urls'][k]))
    return w


def load(path=None):
    """설정 파일을 읽어 Settings 를 만든다. 파일이 없으면 기본값"""
    path = path or os.environ.get('COLLECTOR_SETTINGS') or DEFAULT_PATH
    if not os.path.exists(path):
        if path != DEFAULT_PATH:
            raise UsageError(f'설정 파일이 없음 · {path}')
        return Settings(copy.deepcopy(DEFAULTS), None)
    if tomllib is None:
        raise UsageError('Python 3.11 이상이 필요함 (설정 파일을 읽는 tomllib)')
    try:
        with open(path, 'rb') as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise UsageError(f'{os.path.basename(path)} 문법 오류 · {e} · 한글 키는 따옴표로 감쌀 것: "주안동" = ["관교"]')
    return Settings(_validate(raw, path), path)


_lock = threading.Lock()
_current = None


def current():
    global _current
    with _lock:
        if _current is None:
            _current = load()
        return _current


def use(s):
    """시험이나 다른 코드에서 설정을 직접 정할 때. None 이면 다음 current() 때 파일을 다시 읽음"""
    global _current
    with _lock:
        _current = s


def defaults():
    return Settings(copy.deepcopy(DEFAULTS), None)
