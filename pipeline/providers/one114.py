"""114On · collector.js 5단계(procC, o114)를 옮김 · 실접속 미검증

  · 도로명으로 먼저 검색하고, 주소 일치가 없을 때만 지번으로, 대표번호를 못 찾았고 쓸 만한 이름이 있으면 이름으로도 검색
  · 주소가 일치하는 관리사무소나 건물 대표번호만 대표번호 후보(ph). 고시원·고시텔·원룸·숙박·상가는 제외
  · 번지가 가려진 채 도로명·건물명만 맞으면 「번지 비공개」 약한 일치로 표시
  · 나머지 주소 일치 업체는 대리 연락처 후보(pool)
  · 한 번에 1개, 요청 사이 4.5초. 원본은 브라우저의 114.co.kr 화면 안에서 불렀다.
    파이썬에서 부를 때 사이트가 쿠키나 다른 헤더를 요구하면 차단 화면이 오고, 그러면 BlockedError로 멈춘다.
  · 응답이 JSON이 아니면 차단으로 본다 (원본과 같음).
"""
import json
import re

from ..compat import WS, enc_uri, js_str, js_trim, truthy, tstr
from ..errors import BlockedError, UnexpectedResponse
from .kakao import core, is_mg
from ..settings import current as settings



def headers():
    """Origin·Referer 는 수집설정.toml 의 114On 주소에서 만든다 (기본 https://www.114.co.kr)"""
    m = re.match(r'https://[^/]+', settings().urls['one114'])
    origin = m.group(0)
    return {'Content-Type': 'application/json;charset=UTF-8', 'Request-Type': 'action', 'Origin': origin, 'Referer': origin + '/'}
COLLECTIONS = ('dbdata', 'register', 'report', 'keynumber', 'spl')


def strip114(s):
    return js_trim(re.sub('^' + settings().sido_prefix_re() + WS + r'*[가-힣]+(구|군)' + WS + '*', '', js_str(s), count=1))


def k114R(s):
    """도로명 키 · 「인천 미추홀구 주승로 247 …」 → 「주승로 247」"""
    m = re.match(r'([가-힣A-Za-z0-9]+(?:로|길))' + WS + r'*([0-9]+(?:-[0-9]+)?)', strip114(s))
    return m.group(1) + ' ' + m.group(2) if m else ''


def k114J(s):
    """지번 키 · 「주안1동 137번지 2호」 → 「주안동 137-2」, 「항동1가 12」, 「강화읍 관청리 123」"""
    m = re.match(r'(?:([가-힣]+[읍면])' + WS + r'+)?([가-힣]+[0-9]+가|[가-힣]+?[0-9]*동|[가-힣]+리)' + WS + r'*([0-9]+)(?:번지)?'
                 + WS + r'*(?:-([0-9]+)|([0-9]+)호)?', strip114(s))
    if not m:
        return ''
    dong = m.group(2)
    if dong.endswith('동'):
        dong = re.sub(r'[0-9]+동\Z', '동', dong, count=1)
    sub = m.group(4) or m.group(5)
    return ((m.group(1) + ' ') if m.group(1) else '') + dong + ' ' + m.group(3) + (('-' + sub) if sub and sub != '0' else '')


def k114S(s):
    """도로 이름만 있는 주소 · 「주승로」 (번지 비공개)"""
    m = re.match(r'([가-힣A-Za-z0-9]+(?:로|길))' + WS + r'*\Z', strip114(s))
    return m.group(1) if m else ''


def fmt_tel(t):
    d = re.sub(r'[^0-9]', '', js_str(t))
    if not d:
        return ''
    if d.startswith('02'):
        return re.sub(r'^(02)([0-9]{3})([0-9]{4})$', r'\1-\2-\3', d) if len(d) == 9 else re.sub(r'^(02)([0-9]{4})([0-9]{4})$', r'\1-\2-\3', d)
    if re.match(r'^1[5-9][0-9]{2}', d) and len(d) == 8:
        return re.sub(r'^([0-9]{4})([0-9]{4})$', r'\1-\2', d)
    if len(d) == 11:
        return re.sub(r'^([0-9]{3})([0-9]{4})([0-9]{4})$', r'\1-\2-\3', d)
    if len(d) == 10:
        return re.sub(r'^([0-9]{3})([0-9]{3})([0-9]{4})$', r'\1-\2-\3', d)
    return t


def name_eq(a, b):
    x, y = core(a), core(b)
    if len(x) < 2 or len(y) < 2:
        return False
    if x == y:
        return True
    s_, l_ = (x, y) if len(x) < len(y) else (y, x)
    return s_ in l_ and len(s_) / len(l_) >= 0.7


def strip_mg(n):
    return js_trim(re.sub(WS + r'*(관리사무소|관리실|관리단|관리소|관리센터|입주자대표회의)[^\n\r  ]*\Z', '', js_str(n), count=1))


def link(s):
    return 'https://www.114.co.kr/search/result/all?query=' + enc_uri(s)


class One114:
    def __init__(self, transport):
        self.t = transport

    def search(self, q, lat, lng):
        body = {'query': q, 'localcode': '', 'upjongcode': '', 'filter': '', 'localname': '', 'upjongname': '',
                'collection': 'ALL', 'latitude': lat if lat else 37.4639, 'longitude': lng if lng else 126.6798}
        status, tx = self.t.post_text(settings().urls['one114'], headers(), json.dumps(body, ensure_ascii=False, separators=(',', ':')), 20, 'one114')
        if not tx.startswith('{'):
            raise BlockedError(f'114On 차단 또는 오류 화면 (HTTP {status}). 75분 이상 지난 뒤 같은 명령으로 다시 실행')
        try:
            j = json.loads(tx)
        except ValueError:
            raise UnexpectedResponse('114On · JSON을 읽지 못함')
        sr = (j.get('data') or {}).get('search') or {}
        out = []
        for c in COLLECTIONS:
            for d in ((sr.get(c) or {}).get('Document') or []):
                f = d.get('Field') or {}
                tel = f.get('TEL00') or ((tstr(f.get('DDD')) + '-' + tstr(f.get('TEL'))) if (truthy(f.get('DDD')) and truthy(f.get('TEL'))) else f.get('TEL')) or ''
                out.append({'c': c, 'nm': f.get('COMP_KOR_NM') or f.get('COMP_NM') or '', 'tel': tel,
                            'road': f.get('ROAD_ADDR') or '', 'addr': f.get('ADDR') or '', 'up': f.get('CST_UPJONG_NM') or ''})
        return out


def proc_c(one, gu, q, now_ms):
    """114On · 건물 1곳. q = [i, 짧은 도로명, 짧은 지번, 이름, 위도, 경도]"""
    i, road, jib, name, lat, lng = q
    P = settings().sido + ' ' + gu + ' '
    street = (road or '').split(' ')[0] or ''
    jk = re.sub(r'([0-9]+)-0\Z', r'\1', jib, count=1) if jib else ''

    def hit(d):
        return bool((road and k114R(d['road']) == road) or (jk and k114J(d['addr']) == jk))

    def weak(d):
        return bool(street and k114S(d['road']) == street and not k114J(d['addr']))

    def excl(d):
        return bool(re.search(r'고시원|고시텔|원룸|숙박|상가', (d.get('up') or '') + ' ' + (d.get('nm') or '')))
    nm_ok = bool(name) and len(re.sub(WS + '+', '', name)) >= 2

    def is_rep(d):
        return (is_mg(d['nm']) and (not nm_ok or name_eq(strip_mg(d['nm']), name) or hit(d))) or (nm_ok and name_eq(d['nm'], name) and not excl(d))
    out = {'i': i, 'log': [], 'pool': [], 'ph': None}
    seen = set()

    def push(arr, via, s):
        for d in arr:
            if not d['tel']:
                continue
            key = tstr(d['nm']) + '|' + tstr(d['tel'])
            if key in seen:
                continue
            h = hit(d)
            w = (not h) and via == '건물명검색' and weak(d) and nm_ok and name_eq(strip_mg(d['nm']), name) and not excl(d)
            if not h and not w:
                continue
            seen.add(key)
            x = {'nm': d['nm'], 'tel': fmt_tel(d['tel']), 'up': d['up'], 'road': d['road'], 'addr': d['addr'], 'c': d['c'], 'via': via, 'link': link(s)}
            if not out['ph'] and (w or is_rep(d)):
                out['ph'] = {'v': x['tel'], 'src': '114On ' + via + ' ' + ('관리사무소' if is_mg(d['nm']) else '건물 대표번호') + (' · 번지 비공개, 도로명·건물명 일치' if w else ''),
                             'name': d['nm'], 'link': link(s), 'weak': bool(w)}
            elif h:
                out['pool'].append(x)
    n_r = 0
    if road:
        s = P + road
        r = one.search(s, lat, lng); one.t.sleep(settings().one114_gap)
        n_r = sum(1 for d in r if hit(d))
        push(r, '도로명검색', s)
        out['log'].append(f'114On 도로명검색 "{s}": {len(r)}건, 주소일치 {n_r}곳')
    if not n_r and jib:
        s = P + jib
        r = one.search(s, lat, lng); one.t.sleep(settings().one114_gap)
        push(r, '지번검색', s)
        out['log'].append(f'114On 지번검색 "{s}": {len(r)}건, 주소일치 {sum(1 for d in r if hit(d))}곳')
    if not out['ph'] and nm_ok:
        r = one.search(name, lat, lng); one.t.sleep(settings().one114_gap)
        push(r, '건물명검색', name)
        out['log'].append(f'114On 건물명검색 "{name}": {len(r)}건, 주소일치 {sum(1 for d in r if hit(d) or weak(d))}곳')
    if out['ph']:
        out['log'].append('114On 대표번호 후보: ' + out['ph']['v'] + ' / ' + out['ph']['src'] + ' / ' + out['ph']['name'])
    out['t'] = now_ms()
    return out
