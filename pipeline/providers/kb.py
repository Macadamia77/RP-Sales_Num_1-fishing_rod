"""KB부동산 · 공개 문서가 없는 내부 API라 예고 없이 바뀔 수 있음

  통합검색   https://api.kbland.kr/land-complex/serch/intgraSerch   (serch 철자는 원래 그대로)
  단지정보   https://api.kbland.kr/land-complex/complex/complexMain
검색어는 「주안동 573-7」이나 「미추홀구 아암대로 15」 형태. 「인천광역시」를 붙이면 결과가 안 나옴.
"""
from ..compat import enc_form, js_str, truthy
from ..errors import UnexpectedResponse

from ..settings import current as settings


class KB:
    def __init__(self, transport):
        self.t = transport

    def _get(self, url):
        j = self.t.get_json(url, {}, 10, 'kb')
        if not isinstance(j, dict):
            raise UnexpectedResponse('kb · 응답이 JSON 객체가 아님')
        return j

    def search(self, q):
        """아파트(HSCM)와 빌라(VILLA) 단지 목록"""
        u = settings().urls['kb'] + 'serch/intgraSerch?' + enc_form([('검색설정명', 'SRC_NTOTAL'), ('검색키워드', q), ('출력갯수', '10'), ('페이지설정값', '1')])
        j = self._get(u)
        d = (j.get('dataBody') or {}).get('data') if truthy(j.get('dataBody')) else None
        d = (d.get('data') if truthy(d) else None) or {}
        hs = (d.get('HSCM') or {}).get('data') if truthy(d.get('HSCM')) else None
        vl = (d.get('VILLA') or {}).get('data') if truthy(d.get('VILLA')) else None
        return [{'t': 'HSCM', **x} for x in (hs or [])] + [{'t': 'VILLA', **x} for x in (vl or [])]

    def complex_main(self, no):
        """단지 기본정보 · 단지명, 관리사무소전화번호내용, 총세대수"""
        j = self._get(settings().urls['kb'] + 'complex/complexMain?' + enc_form([('단지기본일련번호', no if isinstance(no, str) else js_str(no))]))
        db = j.get('dataBody') if truthy(j.get('dataBody')) else None
        return (db.get('data') if db else None) or {}
