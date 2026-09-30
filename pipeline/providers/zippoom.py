"""집품 주소 자동완성 · 공개 문서가 없는 내부 API

사이트 맨 아래에 「무단 크롤링 금지」가 적혀 있다. 건물명을 못 찾은 건물에만, 한 건씩 0.35초 간격으로 부른다.
호출 주소는 원본 collector.js 에 적힌 그대로다 (사이트 도메인 zippoom.com 과 철자가 다름 · 실접속으로 확인 필요).
"""
from ..compat import enc_uri
from ..errors import UnexpectedResponse

from ..settings import current as settings


class Zippoom:
    def __init__(self, transport):
        self.t = transport

    def search(self, q):
        j = self.t.get_json(settings().urls['zippoom'] + enc_uri(q), {}, 10, 'zippoom')
        if not isinstance(j, dict) or not isinstance(j.get('payload') or [], list):
            raise UnexpectedResponse('zippoom · 응답 구조가 다름 (payload 목록 없음)')
        return [(x.get('buildingDocument') or {}) for x in (j.get('payload') or [])]
