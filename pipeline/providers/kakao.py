"""카카오 로컬 API · collector.js 1단계(procA)를 옮김

건물 1곳마다
  ① 원본 도로명·지번으로 주소검색 → 도로명주소 건물명, 좌표, 표준 주소
  ② 주소로 키워드검색 → 주소가 같거나 200m 안에 있는 장소를 모음 (원본과 다른 카카오 지번도 한 번 더)
  ③ 번호 조회 대상이면 「건물명」, 「건물명 관리사무소」로 반경 1km 재검색
  ④ 번호 조회 대상이면 반경 300m 중개업소(AG2)를 최대 8곳 모음 (대리 연락처 후보)
요청이 실패하면 0.6초부터 두 배씩 늘려 최대 6번 시도한다.
"""
import re

from ..compat import DOT, WS, JSObj, dist, enc_uri, fixed6, jnum, jor, js_str, js_trim, num_str, to_num, truthy
from ..errors import FatalError, RequestError, RetryableError, UnexpectedResponse
from ..settings import current as settings

# 시도 이름과 카카오 주소는 수집설정.toml 에서 읽는다 (기본값 인천광역시, https://dapi.kakao.com/v2/local/search/)


# ---------- 주소·이름 규칙 (collector.js 와 같음) ----------
def nr(s):
    if not truthy(s):
        return ''
    S = settings()
    t = str(s).replace(S.sido, S.sido_short, 1)
    t = re.sub(WS + r'*\([^)]*\)', ' ', t)
    t = t.split(',')[0]
    return js_trim(re.sub(WS + '+', ' ', t))


def nj(s):
    if not truthy(s):
        return ''
    S = settings()
    t = str(s).replace(S.sido, S.sido_short, 1)
    t = re.sub(WS + r'*\([^)]*\)', ' ', t)
    t = re.sub(r'([0-9]+)' + WS + '*번지' + WS + r'*([0-9]+)' + WS + '*호', r'\1-\2', t, count=1)
    t = t.replace('번지', '')
    t = re.sub(r'([0-9]+)' + WS + '*호' + WS + r'*\Z', '', t, count=1)
    t = re.sub(r'([가-힣]+?)[0-9]+동', r'\1동', t)
    return js_trim(re.sub(WS + '+', ' ', t))


def core(s):
    return re.sub(WS + r'+|아파트|오피스텔|빌라|주택|\(' + DOT + r'*?\)', '', js_str(s))


def is_mg(n):
    """collector.js 의 isMg. judge/common.py 의 is_mg 보다 목록이 짧음(관리사무실·전기차 제외 없음) · 원본 그대로 둠"""
    return bool(re.search(r'관리사무소|관리실|관리단|관리소|관리센터|입주자대표회의', js_str(n)))


def is_bldg(c, n):
    return truthy(c) and str(c).startswith('부동산') and not re.search(r'부동산서비스|중개|고시원|고시텔|원룸|하숙|셰어|쉐어|숙박', c) and not is_mg(n)


def place_row(d, m, dd, src):
    """판정기가 읽는 장소 한 줄 · [id, 이름, 분류, 전화, 링크, x, y, 도로명, 지번, 주소일치, 거리, 출처]"""
    return [d.get('id'), d.get('place_name'), d.get('category_name'), d.get('phone'), d.get('place_url'),
            fixed6(d.get('x')), fixed6(d.get('y')), d.get('road_address_name'), d.get('address_name'), 1 if m else 0, dd, src]


class Kakao:
    RETRIES = 6

    def __init__(self, transport, key):
        self.t = transport
        self.headers = {'Authorization': 'KakaoAK ' + key}

    def _get(self, url):
        last = ''
        for n in range(self.RETRIES):
            try:
                j = self.t.get_json(url, self.headers, 10, 'kakao')
            except (FatalError, RequestError):
                raise
            except RetryableError as e:
                last = str(e)
                self.t.sleep(0.6 * (2 ** n))
                continue
            if not isinstance(j, dict) or not isinstance(j.get('documents', []), list):
                raise UnexpectedResponse('kakao · 응답에 documents 목록이 없음')
            return j
        raise RetryableError('kakao fail ' + last)

    def address(self, q):
        return self._get(settings().urls['kakao'] + 'address.json?query=' + enc_uri(q)).get('documents') or []

    def keyword(self, q, x=None, y=None, radius=None, max_page=None):
        out = []
        for p in range(1, (max_page or 3) + 1):
            u = settings().urls['kakao'] + 'keyword.json?query=' + enc_uri(q) + '&page=' + str(p) + '&size=15'
            if truthy(x) and truthy(y) and truthy(radius):
                u += f'&x={num_str(x)}&y={num_str(y)}&radius={num_str(radius)}'
            j = self._get(u)
            out += j.get('documents') or []
            if not j.get('meta') or j['meta'].get('is_end'):
                break
        return out

    def category(self, code, x, y, r):
        u = settings().urls['kakao'] + f'category.json?category_group_code={code}&x={num_str(x)}&y={num_str(y)}&radius={r}&sort=distance'
        return self._get(u).get('documents') or []


def proc_a(kakao, gu, b):
    """1단계 · 건물 1곳. b = [i, 짧은 도로명, 짧은 지번, 원래 건물명, nt, pt]"""
    i, road, jib, n0, nt, pt = b
    P = settings().sido + ' ' + gu + ' '
    road_q = P + road if road else ''
    jib_q = P + jib if jib else ''
    log = []
    ad_r = kakao.address(road_q) if road_q else []
    ad_j = kakao.address(jib_q) if jib_q else []
    first = ad_r[0] if ad_r else (ad_j[0] if ad_j else None)
    gx = to_num(first.get('x')) if first else None
    gy = to_num(first.get('y')) if first else None

    def ra(d):
        return (d or {}).get('road_address')
    bn_r = jor(ra(ad_r[0]).get('building_name'), '') if ad_r and ra(ad_r[0]) else ''
    bn_j = jor(ra(ad_j[0]).get('building_name'), '') if ad_j and ra(ad_j[0]) else ''
    # 주소 묶기 · 원본 도로명·지번, 도로명 검색과 지번 검색이 알려준 도로명·지번
    R, J = {}, {}
    if road_q:
        R[nr(road_q)] = 1
    if jib_q:
        J[nj(jib_q)] = 1
    for d in (ad_r[0] if ad_r else None, ad_j[0] if ad_j else None):
        if not d:
            continue
        if d.get('road_address'):
            R[nr(d['road_address'].get('address_name'))] = 1
        if d.get('address'):
            J[nj(d['address'].get('address_name'))] = 1
    a_r = ('성공' + (', 건물명 ' + bn_r if bn_r else ', 건물명 없음')) if ad_r else ('결과 없음' if road_q else '생략')
    a_j = ('성공' + (', 건물명 ' + bn_j if bn_j else ', 건물명 없음')) if ad_j else ('결과 없음' if jib_q else '생략')
    log.append(f'카카오 주소검색 도로명 {a_r} · 지번 {a_j}')

    def in_b(d):
        return nr(d.get('road_address_name')) in R or nj(d.get('address_name')) in J
    P2 = JSObj()
    G = {'x': gx, 'y': gy}

    def add(docs, src):
        for d in docs:
            did = str(d.get('id'))
            if did in P2:
                continue
            m = in_b(d)
            dd = dist(G['x'], G['y'], to_num(d.get('x')), to_num(d.get('y'))) if truthy(G['x']) else None
            if not m and not (dd is not None and dd <= 200):
                continue
            P2[did] = place_row(d, m, dd, src)
    # 장소 검색 · 원본 도로명, 원본 지번, 그리고 원본과 다른 카카오 지번
    qs = []
    if road_q:
        qs.append(road_q)
    if jib_q:
        qs.append(jib_q)
    for d in (ad_r[0] if ad_r else None, ad_j[0] if ad_j else None):
        if d and d.get('address') and nj(d['address'].get('address_name')) != nj(jib_q):
            qs.append(d['address'].get('address_name'))
    cnt = []
    for q in dict.fromkeys(qs):
        docs = kakao.keyword(q)
        add(docs, 'a')
        cnt.append(f'"{q}" {len(docs)}건')
    places = P2.js_values()
    if not truthy(G['x']) and places:
        m = next((p for p in places if p[9]), None)
        if m:
            G['x'], G['y'] = m[5], m[6]
    log.append(f'카카오 장소검색: {", ".join(cnt)} · 주소 일치 {sum(1 for p in places if p[9])}곳')
    # 임시 건물명 · 원본, 도로명주소 건물명, 건물 장소 순
    bp = next((p for p in places if p[9] and is_bldg(p[2], p[1])), None)
    pn = jor(n0, '') or bn_r or bn_j or (bp[1] if bp else '')
    gx, gy = G['x'], G['y']
    # 건물명 재검색 · 번호 대상이고 이름이 있으면 반경 1km
    if pt and pn and len(core(pn)) >= 2:
        rad = 1000 if truthy(gx) else None
        a1 = kakao.keyword(pn, gx, gy, rad, 1)
        a2 = kakao.keyword(pn + ' 관리사무소', gx, gy, rad, 1)
        add(a1 + a2, 'rs')
        log.append(f'카카오 건물명 재검색 "{pn}": {len(a1) + len(a2)}건')
    # 주변 공인중개사 300m
    ag = []
    if pt and truthy(gx):
        docs = [d for d in kakao.category('AG2', gx, gy, 300) if truthy(d.get('phone'))][:8]
        ag = [[d.get('place_name'), d.get('phone'), to_num(d.get('distance')), d.get('place_url')] for d in docs]
    return {'i': i, 'g': [jnum(gx), jnum(gy)] if truthy(gx) else None, 'bnR': bn_r, 'bnJ': bn_j,
            'R': list(R), 'J': list(J), 'P': P2.js_values(), 'ag': ag, 'pn': pn, 'log': log}


def research(kakao, A, nn):
    """2단계에서 새 이름을 얻었을 때 카카오 재검색 · 주소 일치이거나 200m 안인 장소만"""
    R, J = set(A.get('R') or []), set(A.get('J') or [])
    gx, gy = A['g']
    a1 = kakao.keyword(nn, gx, gy, 1000, 1)
    a2 = kakao.keyword(nn + ' 관리사무소', gx, gy, 1000, 1)
    out = []
    for d in a1 + a2:
        m = nr(d.get('road_address_name')) in R or nj(d.get('address_name')) in J
        dd = dist(gx, gy, to_num(d.get('x')), to_num(d.get('y')))
        if not m and not (dd is not None and dd <= 200):
            continue
        out.append(place_row(d, m, dd, 'rs2'))
    return out, len(a1) + len(a2)
