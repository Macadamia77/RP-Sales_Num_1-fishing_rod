"""네이버 · naver.js 를 옮김

  proc_geo    · 네이버 지오코딩. 원본 도로명·지번을 넣어 네이버 기준 도로명·지번·건물명·좌표를 받음 (주소 묶기 보강)
  proc_verify · NAVER API HUB 지역 검색. 이름이 확연히 다른 근접 관리사무소가 정말 그 자리에 있는지 확인.
                이름을 5가지로 바꿔 검색하고, 500m 안에서 찾으면 멈춤
두 API는 값을 채우지 않고 판정에만 쓴다. 지역 검색은 전화번호를 빈칸으로 준다.
"""
import math
import re

from ..compat import WS, enc_uri, jnum, js_round, js_str, to_num
from ..errors import FatalError, RequestError, RetryableError, UnexpectedResponse

from ..settings import current as settings


def ncore(s):
    t = re.sub(r'<[^>]+>', '', js_str(s))
    return re.sub(WS + r'+|관리사무소|관리실|관리단|관리소|관리센터|경비실|방제실|입주자대표회의|아파트|전기차충전소', '', t)


def ndist(x1, y1, x2, y2):
    if None in (x1, y1, x2, y2):
        return None
    r = math.pi / 180
    return js_round(math.hypot((x2 - x1) * math.cos(y1 * r) * 111320, (y2 - y1) * 110540))


def _headers(pair):
    return {'X-NCP-APIGW-API-KEY-ID': pair[0], 'X-NCP-APIGW-API-KEY': pair[1]}


class Naver:
    RETRIES = 4

    def __init__(self, transport, gu, geo_key=None, hub_key=None):
        self.t, self.gu = transport, gu
        self.geo_h = _headers(geo_key) if geo_key else None
        self.hub_h = _headers(hub_key) if hub_key else None

    def _call(self, url, headers, kind):
        last = ''
        for n in range(self.RETRIES):
            try:
                j = self.t.get_json(url, headers, 60, kind)
            except (FatalError, RequestError):
                raise
            except RetryableError as e:
                last = str(e)
                self.t.sleep(0.8 * (n + 1))
                continue
            if not isinstance(j, dict):
                raise UnexpectedResponse(f'{kind} · 응답이 JSON 객체가 아님')
            return j
        raise RetryableError('네이버 호출 실패 ' + last)

    # ---------- 지오코딩 ----------
    def geo(self, addr):
        j = self._call(settings().urls['naver_geo'] + '/map-geocode/v2/geocode?query=' + enc_uri(addr), {**self.geo_h, 'Accept': 'application/json'}, 'naver_geo')
        if 'addresses' not in j:
            raise UnexpectedResponse('naver_geo · 응답에 addresses 가 없음')
        a = (j.get('addresses') or [None])[0]
        if not a:
            return None
        e = next((z for z in a.get('addressElements') or [] if (z.get('types') or [None])[0] == 'BUILDING_NAME'), None)
        return [a.get('roadAddress'), a.get('jibunAddress'), e.get('longName') if e else '', jnum(to_num(a.get('x'))), jnum(to_num(a.get('y')))]

    def proc_geo(self, row):
        """row = [i, 짧은 도로명, 짧은 지번]"""
        i, road, jib = row[0], row[1], row[2]
        P = settings().sido + ' ' + self.gu + ' '
        o = {'i': i}
        if road:
            o['r'] = self.geo(P + road)
            self.t.sleep(settings().naver_geo_gap)
        if jib:
            o['j'] = self.geo(P + jib)
            self.t.sleep(settings().naver_geo_gap)
        return o

    # ---------- 지역 검색 ----------
    def local(self, q):
        j = self._call(settings().urls['naver_hub'] + '/search/v1/local?display=5&query=' + enc_uri(q), dict(self.hub_h), 'naver_local')
        if 'items' not in j:
            raise UnexpectedResponse('naver_local · 응답에 items 가 없음')
        out = []
        for z in j.get('items') or []:
            o = {'n': re.sub(r'<[^>]+>', '', js_str(z.get('title')))}
            for k, src in (('c', 'category'), ('road', 'roadAddress'), ('jib', 'address')):
                if src in z:
                    o[k] = z[src]
            mx, my = to_num(z.get('mapx')), to_num(z.get('mapy'))
            o['x'] = jnum(mx / 1e7) if mx is not None else None
            o['y'] = jnum(my / 1e7) if my is not None else None
            out.append(o)
        return out

    def proc_verify(self, q):
        """q = [키, 관리사무소 이름, 카카오 x, 카카오 y, 구 이름]"""
        key, name, x, y, gu = q
        k = ncore(name)
        best, tried = None, []
        for s in [name, k + ' 관리사무소', settings().sido_short + ' ' + k + ' 관리사무소', gu + ' ' + k, k]:
            items = self.local(s)
            tried.append(f'{s}:{len(items)}')
            self.t.sleep(settings().naver_local_gap)
            for z in items:
                c = ncore(z['n'])
                if len(c) >= 2 and (k in c or c in k):
                    d = ndist(x, y, z['x'], z['y'])
                    if d is None:
                        continue
                    if best is None or d < best['d']:
                        best = {**z, 'd': d}
            if best and best['d'] < 500:
                break
        return {'key': key, 'best': best, 'tried': tried}
