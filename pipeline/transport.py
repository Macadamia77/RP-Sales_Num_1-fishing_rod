"""HTTP 통신 계층

규칙
  401·403        → AuthError (즉시 중단)
  429            → RateLimitError (즉시 중단)
  3xx 리다이렉트  → UnexpectedResponse (즉시 중단)
  그 밖의 4xx     → RequestError (그 건만 실패)
  5xx·네트워크 오류 → RetryableError (조회 모듈이 다시 시도)
  2xx인데 JSON이 아니거나 구조가 다름 → UnexpectedResponse (즉시 중단)

「결과 없음」과 「응답이 이상함」을 구분하는 것이 이 파일의 목적이다. 요청 제한에 걸린 응답을
빈 결과로 처리하면 틀린 결과가 조용히 쌓인다 (주안동 첫 실행 때 756건이 그렇게 됐음).

기록 모드 · trace_dir을 주면 요청마다 주소, 헤더(키는 <이름>으로 가림), 상태, 본문을
<단계>_<건물ID>.json 에 남긴다. ReplayTransport가 이 기록으로 네트워크 없이 똑같이 재생한다.
"""
import glob
import json
import os
import threading
import time
from collections import deque

from . import credentials
from .errors import AuthError, RateLimitError, RequestError, RetryableError, UnexpectedResponse


def interpret(status, body, url, kind, want_json=True):
    """상태 코드와 본문을 규칙에 따라 해석한다"""
    if status in (401, 403):
        raise AuthError(f'{kind} {status} · 키 또는 구독 오류')
    if status == 429:
        raise RateLimitError(f'{kind} 429 · 호출 한도 초과')
    if 300 <= status < 400:
        raise UnexpectedResponse(f'{kind} {status} · 리다이렉트 응답')
    if 400 <= status < 500:
        raise RequestError(f'{kind} {status}')
    if status >= 500 or status == 0:
        raise RetryableError(f'{kind} {status}')
    if not want_json:
        return body
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        raise UnexpectedResponse(f'{kind} · JSON이 아닌 응답 ({str(body)[:60]!r})')


class _Base:
    def __init__(self):
        self.tl = threading.local()
        self.count = {}
        self._lock = threading.Lock()

    def begin(self, stage, key):
        """한 건 조회 시작. 기록·재생이 어느 건물의 요청인지 알게 함"""
        self.tl.key = (stage, str(key))

    def end(self):
        pass

    def _count(self, kind):
        with self._lock:
            self.count[kind] = self.count.get(kind, 0) + 1

    def get_json(self, url, headers, timeout, kind):
        status, body = self._request('GET', url, headers, None, timeout, kind)
        return interpret(status, body, url, kind)

    def post_text(self, url, headers, body, timeout, kind):
        """114On처럼 본문을 직접 보고 판단해야 하는 경우. 401·403·429·리다이렉트만 여기서 처리"""
        status, text = self._request('POST', url, headers, body, timeout, kind)
        if status in (401, 403, 429) or 300 <= status < 400:
            interpret(status, text, url, kind)
        if status >= 500 or status == 0:
            raise RetryableError(f'{kind} {status}')
        return status, text


class HttpTransport(_Base):
    """실제 요청"""

    def __init__(self, trace_dir=None):
        super().__init__()
        import requests
        self.requests = requests
        self.trace_dir = trace_dir
        if trace_dir:
            os.makedirs(trace_dir, exist_ok=True)

    def _session(self):
        if not hasattr(self.tl, 's'):
            self.tl.s = self.requests.Session()
        return self.tl.s

    def begin(self, stage, key):
        super().begin(stage, key)
        self.tl.trace = []

    def end(self):
        tr = getattr(self.tl, 'trace', None)
        if self.trace_dir and tr:
            st, k = self.tl.key
            path = os.path.join(self.trace_dir, f'{st}_{k}.json')
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(tr, f, ensure_ascii=False)
            os.replace(tmp, path)
        self.tl.trace = []

    def _request(self, method, url, headers, body, timeout, kind):
        self._count(kind)
        try:
            if method == 'GET':
                r = self._session().get(url, headers=headers, timeout=timeout, allow_redirects=False)
            else:
                r = self._session().post(url, headers=headers, data=body.encode('utf-8'), timeout=timeout, allow_redirects=False)
        except self.requests.RequestException as e:
            raise RetryableError(credentials.mask(f'{kind} 요청 실패 · {type(e).__name__}'))
        text = r.content.decode('utf-8', errors='replace')
        if self.trace_dir and hasattr(self.tl, 'trace'):
            rec = {'method': method, 'url': url, 'headers': credentials.mask_headers(headers), 'status': r.status_code, 'body': text}
            if body is not None:
                rec['req_body'] = body
            self.tl.trace.append(rec)
        return r.status_code, text

    def sleep(self, sec):
        time.sleep(sec)


class ReplayTransport(_Base):
    """기록된 응답을 순서대로 돌려준다. 요청 주소·헤더가 기록과 다르면 bad 에 남긴다"""

    def __init__(self, trace_dir):
        super().__init__()
        self.q = {}
        for f in glob.glob(os.path.join(trace_dir, '*.json')):
            stage, key = os.path.basename(f)[:-5].split('_', 1)
            with open(f, encoding='utf-8') as fh:
                self.q[(stage, key)] = deque(json.load(fh))
        self.bad = []
        self.n = 0

    def _request(self, method, url, headers, body, timeout, kind):
        self._count(kind)
        self.n += 1
        key = getattr(self.tl, 'key', None)
        q = self.q.get(key)
        if not q:
            self.bad.append({'at': key, 'url': url, 'why': '기록에 없는 요청'})
            return 599, ''
        rec = q.popleft()
        if rec['url'] != url:
            self.bad.append({'at': key, 'url': url, 'want': rec['url'], 'why': '주소 다름'})
        want_h = rec.get('headers') or {}
        if want_h != credentials.mask_headers(headers) and want_h != headers:
            self.bad.append({'at': key, 'why': '헤더 다름', 'got': credentials.mask_headers(headers), 'want': want_h})
        if body is not None and rec.get('req_body') not in (None, body):
            self.bad.append({'at': key, 'why': '요청 본문 다름'})
        return rec['status'], rec['body']

    def leftover(self):
        return {f'{k[0]}_{k[1]}': len(v) for k, v in self.q.items() if v}

    def sleep(self, sec):
        pass
