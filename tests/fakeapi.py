"""가짜 API · 테스트와 원본 JS 대조 검증이 같은 응답을 쓰도록 한곳에 모은 시나리오

주소(URL)가 글자 하나까지 같아야 응답이 나온다. 그래서 요청 주소를 만드는 코드가 원본과 다르면
기본 응답(빈 결과)이 돌아가 결과가 달라지고, 대조 검증에서 드러난다.
실제 사이트의 응답이 아니라, 판정 분기를 골고루 지나가도록 만든 합성 응답이다.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.compat import enc_form, enc_uri  # noqa: E402
from pipeline.transport import _Base  # noqa: E402

K = 'https://dapi.kakao.com/v2/local/search/'
KB = 'https://api.kbland.kr/land-complex/'
ZP = 'https://live.zippo-om.com/api/v1/buildings/search/autoComplete?keyword='
P = '인천광역시 미추홀구 '

DEFAULTS = [
    ('https://dapi.kakao.com/', {'documents': [], 'meta': {'is_end': True}}),
    ('https://api.kbland.kr/', {'dataBody': {'data': {'data': {}}}}),
    ('https://live.zippo-om.com/', {'payload': []}),
    ('/map-geocode/', {'status': 'OK', 'addresses': []}),
    ('/search/v1/local', {'items': []}),
    ('POST 114 ', {'data': {'search': {}}}),
]


def kaddr(q):
    return K + 'address.json?query=' + enc_uri(q)


def kkw(q, page=1, x=None, y=None, r=None):
    u = K + 'keyword.json?query=' + enc_uri(q) + f'&page={page}&size=15'
    if x is not None:
        u += f'&x={x}&y={y}&radius={r}'
    return u


def kcat(x, y):
    return K + f'category.json?category_group_code=AG2&x={x}&y={y}&radius=300&sort=distance'


def kbs(q):
    return KB + 'serch/intgraSerch?' + enc_form([('검색설정명', 'SRC_NTOTAL'), ('검색키워드', q), ('출력갯수', '10'), ('페이지설정값', '1')])


def kbm(no):
    return KB + 'complex/complexMain?' + enc_form([('단지기본일련번호', str(no))])


def place(pid, name, cat, phone, road, addr, x, y):
    return {'id': pid, 'place_name': name, 'category_name': cat, 'phone': phone, 'place_url': f'http://place.map.kakao.com/{pid}',
            'road_address_name': road, 'address_name': addr, 'x': x, 'y': y}


def docs(*d, is_end=True):
    return {'documents': list(d), 'meta': {'is_end': is_end}}


def routes():
    R = {}
    road1, jib1 = '인천 미추홀구 주승로 247', '인천 미추홀구 관교동 13-11'
    # ---- 101 동부아파트 · 이름·번호 모두 대상. 카카오 건물명, 관리사무소, 200m 규칙, 다른 카카오 지번, 재검색, AG2, KB
    R[kaddr(P + '주승로 247')] = docs({'x': '126.6900000', 'y': '37.4400000', 'road_address': {'address_name': road1, 'building_name': '동부아파트'},
                                      'address': {'address_name': jib1}})
    R[kaddr(P + '관교동 13-11')] = docs({'x': '126.6901', 'y': '37.4401', 'road_address': {'address_name': road1, 'building_name': '동부아파트'},
                                        'address': {'address_name': '인천 미추홀구 관교동 13-8'}})
    R[kkw(P + '주승로 247')] = docs(
        place('25817078', '동부아파트 관리사무소', '부동산 > 주거시설 > 아파트 > 관리사무소', '032-421-0000', road1, jib1, '126.69001', '37.44002'),
        place('9692385', '동부아파트', '부동산 > 주거시설 > 아파트', '', road1, jib1, '126.69', '37.44'),
        place('18420435', '정석공인중개사사무소', '부동산 > 부동산서비스 > 부동산중개 > 공인중개사사무소', '032-875-6060', road1, jib1, '126.6902', '37.4400'),
        place('1111', '=HYPERLINK("http://example.invalid","x")', '음식점 > 한식', '032-111-2222', road1, jib1, '126.6900', '37.4401'),
        place('7777', '먼가게', '음식점 > 분식', '010-1234-5678', '인천 미추홀구 다른로 1', '인천 미추홀구 관교동 99', '126.6910', '37.4400'),
        place('8888', '아주먼곳', '음식점', '032-000-1111', '인천 미추홀구 먼로 9', '인천 미추홀구 관교동 900', '126.6960', '37.4400'))
    R[kkw(P + '관교동 13-11')] = docs(
        place('25817078', '동부아파트 관리사무소', '부동산 > 주거시설 > 아파트 > 관리사무소', '032-421-0000', road1, jib1, '126.69001', '37.44002'),
        place('5000', '세븐일레븐 관교점', '가정,생활 > 편의점 > 세븐일레븐', '032-123-4567', road1, jib1, '126.69', '37.44'))
    R[kkw('동부아파트', 1, '126.69', '37.44', 1000)] = docs(
        place('4242', '동부아파트 경비실', '부동산 > 주거시설 > 아파트', '032-421-9999', road1, '인천 미추홀구 관교동 13-8', '126.6901', '37.4401'))
    R[kcat('126.69', '37.44')] = docs(*[
        {'place_name': f'중개{n}', 'phone': ('' if n in (2, 5) else f'032-400-00{n:02d}'), 'distance': ('' if n == 3 else str(20 * n)),
         'place_url': f'http://place.map.kakao.com/9{n}'} for n in range(1, 12)])
    R[kbs('관교동 13-11')] = {'dataBody': {'data': {'data': {'HSCM': {'data': [
        {'COMPLEX_NO': 7123, 'HSCM_NM': '동부', 'JUSO_ARNO': '인천광역시 미추홀구 관교동 13-11', 'NEWADDRESS': '인천광역시 미추홀구 주승로 247'}]},
        'VILLA': {'data': []}}}}}
    R[kbm(7123)] = {'dataBody': {'data': {'단지명': '동부', '관리사무소전화번호내용': '032-421-3360', '총세대수': 420}}}
    # ---- 102 · 카카오에서 이름 없음 → 집품 이름 → 새 이름으로 카카오 재검색 → 건물 대표번호
    road2, jib2 = '인천 미추홀구 인하로411번길 49', '인천 미추홀구 관교동 316-6'
    for q in (P + '인하로411번길 49', P + '관교동 316-6'):
        R[kaddr(q)] = docs({'x': '126.6950', 'y': '37.4450', 'road_address': {'address_name': road2, 'building_name': ''}, 'address': {'address_name': jib2}})
    R[kbs('관교동 316-6')] = {'dataBody': {'data': {'data': {'VILLA': {'data': [
        {'COMPLEX_NO': 'V1', 'HSCM_NM': '다세대(316-6)', 'JUSO_ARNO': '인천광역시 미추홀구 관교동 316-6'}]}}}}}
    R[kbm('V1')] = {'dataBody': {'data': {'단지명': '호산빌라.', '관리사무소전화번호내용': ''}}}
    R[ZP + enc_uri(P + '인하로411번길 49')] = {'payload': [{'buildingDocument': {
        'buildingId': 55, 'buildingName': '호산빌라', 'buildingType': '빌라', 'address': road2, 'oldAddress': jib2}}]}
    R[kkw('호산빌라', 1, '126.695', '37.445', 1000)] = docs(
        place('6060', '호산빌라', '부동산 > 주거시설 > 빌라', '032-555-6666', road2, jib2, '126.6950', '37.4450'))
    # ---- 103 · 기존 이름, 도로명 주소검색 실패·지번만 성공, 장소검색 여러 쪽, 이름 다른 근접 관리단(네이버 확인 대상)
    road3, jib3 = '인천 미추홀구 경원대로 627', '인천 미추홀구 관교동 500'
    R[kaddr(P + '관교동 500')] = docs({'x': '126.7000', 'y': '37.4380', 'road_address': None, 'address': {'address_name': jib3}})
    R[kkw(P + '경원대로 627', 1)] = docs(
        place('300', '신비마을아파트 관리사무소', '부동산 > 주거시설 > 아파트 > 관리사무소', '032-777-8888', road3, jib3, '126.7000', '37.4381'),
        place('20', '관교프라자 관리단', '부동산 > 상가 > 관리사무소', '032-999-0000', road3, jib3, '126.7005', '37.4384'),
        is_end=False)
    R[kkw(P + '경원대로 627', 2)] = docs(
        place('1000', '신비학원', '교육,학문 > 학원', '032-321-0000', road3, jib3, '126.7001', '37.4380'))
    R[kcat('126.7', '37.438')] = docs(
        {'place_name': '관교메트로부동산', 'phone': '032-422-2455', 'distance': '130', 'place_url': 'http://place.map.kakao.com/1901238807'},
        {'place_name': '정석공인중개사사무소', 'phone': '032-875-6060', 'distance': '140', 'place_url': 'http://place.map.kakao.com/18420435'})
    # ---- 104 · 이름만 대상, 카카오 결과 없음 → 집품이 지번만 줌(이름 아님)
    R[ZP + enc_uri(P + '경원대로640번길 6-39')] = {'payload': [{'buildingDocument': {
        'buildingName': '관교동 505-8', 'address': '인천 미추홀구 경원대로640번길 6-39'}}]}
    # ---- 105 · 도로명 없이 지번만
    R[kaddr(P + '관교동 12-3')] = docs({'x': '126.69', 'y': '37.44', 'road_address': {'address_name': '인천 미추홀구 주승로 250', 'building_name': '테스트빌'},
                                       'address': {'address_name': '인천 미추홀구 관교동 12-3'}})
    # ---- 네이버 지오코딩 (상대 경로로 적음 · 원본이 API 화면 안에서 상대 경로로 불렀기 때문)
    R['/map-geocode/v2/geocode?query=' + enc_uri(P + '주승로 247')] = {'status': 'OK', 'addresses': [{
        'roadAddress': '인천광역시 미추홀구 주승로 247 동부아파트', 'jibunAddress': '인천광역시 미추홀구 관교동 13-11 동부아파트',
        'addressElements': [{'types': ['SIDO'], 'longName': '인천광역시'}, {'types': ['BUILDING_NAME'], 'longName': '동부아파트'}],
        'x': '126.6900123', 'y': '37.4400456'}]}
    # ---- 네이버 지역 검색
    R['/search/v1/local?display=5&query=' + enc_uri('동부아파트 관리사무소')] = {'items': [
        {'title': '<b>동부아파트</b> 관리사무소', 'category': '아파트', 'roadAddress': road1, 'address': jib1, 'mapx': '1266900200', 'mapy': '374400300'}]}
    R['/search/v1/local?display=5&query=' + enc_uri('관교프라자 관리사무소')] = {'items': [
        {'title': '관교<b>프라자</b>', 'category': '상가', 'roadAddress': road3, 'mapx': '1267400000', 'mapy': '374380000'}]}
    # ---- 114On (본문의 query 로 찾음)
    R['POST 114 ' + P + '주승로 247'] = {'data': {'search': {
        'dbdata': {'Document': [
            {'Field': {'COMP_KOR_NM': '동부아파트관리사무소', 'DDD': '032', 'TEL': '4213360', 'ROAD_ADDR': '인천 미추홀구 주승로 247',
                       'ADDR': '인천 미추홀구 관교1동 13번지 11호', 'CST_UPJONG_NM': '관리사무소'}},
            {'Field': {'COMP_NM': '동부약국', 'TEL00': '0324210001', 'ROAD_ADDR': '인천 미추홀구 주승로 247', 'ADDR': '', 'CST_UPJONG_NM': '약국'}}]},
        'register': {'Document': [
            {'Field': {'COMP_KOR_NM': '동부약국', 'TEL00': '0324210001', 'ROAD_ADDR': '인천 미추홀구 주승로 247'}},
            {'Field': {'COMP_KOR_NM': '동부원룸', 'TEL00': '01099998888', 'ROAD_ADDR': '인천 미추홀구 주승로 247', 'CST_UPJONG_NM': '원룸'}}]}}}}
    R['POST 114 ' + P + '관교동 500'] = {'data': {'search': {'report': {'Document': [
        {'Field': {'COMP_KOR_NM': '신비학원', 'TEL00': '01011112222', 'ROAD_ADDR': '', 'ADDR': '인천 미추홀구 관교동 500', 'CST_UPJONG_NM': '학원'}}]}}}}
    R['POST 114 신비마을아파트'] = {'data': {'search': {'keynumber': {'Document': [
        {'Field': {'COMP_KOR_NM': '신비마을아파트 관리사무소', 'TEL00': '0327778888', 'ROAD_ADDR': '인천 미추홀구 경원대로', 'ADDR': ''}}]}}}}
    return {k: {'status': 200, 'body': json.dumps(v, ensure_ascii=False)} for k, v in R.items()}


def norm_key(method, url, body=None):
    if method == 'POST':
        return 'POST 114 ' + json.loads(body)['query']
    for host in ('https://maps.apigw.ntruss.com', 'https://naverapihub.apigw.ntruss.com'):
        if url.startswith(host):
            return url[len(host):]
    return url


def lookup(table, key):
    if key in table:
        r = table[key]
        return r['status'], r['body']
    for prefix, body in DEFAULTS:
        if key.startswith(prefix):
            return 200, json.dumps(body, ensure_ascii=False)
    return 404, ''


class FakeTransport(_Base):
    """routes() 응답을 돌려주는 가짜 통신. 요청 주소를 모두 기록"""

    def __init__(self, table=None, overrides=None):
        super().__init__()
        self.table = dict(table or routes())
        self.table.update(overrides or {})
        self.calls = []
        self.slept = 0.0

    def _request(self, method, url, headers, body, timeout, kind):
        self._count(kind)
        key = norm_key(method, url, body)
        with self._lock:
            self.calls.append(key)
        return lookup(self.table, key)

    def sleep(self, sec):
        self.slept += sec


# 테스트용 입력 · [i, 짧은 도로명, 짧은 지번, 원래 건물명, nt, pt]
ROWS_A = [
    [101, '주승로 247', '관교동 13-11', '', 1, 1],
    [102, '인하로411번길 49', '관교동 316-6', '', 1, 1],
    [103, '경원대로 627', '관교동 500', '신비마을아파트', 0, 1],
    [104, '경원대로640번길 6-39', '관교동 505-8', '', 1, 0],
    [105, '', '관교동 12-3', '', 1, 1],
]
GEO_ROWS = [[101, '주승로 247', '관교동 13-11'], [104, '경원대로640번길 6-39', '관교동 505-8']]
VERIFY_ROWS = [['101:25817078', '동부아파트 관리사무소', 126.69001, 37.44002, '미추홀구'],
               ['103:20', '관교프라자 관리단', 126.7005, 37.4384, '미추홀구']]
Q114_ROWS = [[101, '주승로 247', '관교동 13-11', '동부아파트', 37.44, 126.69],
             [103, '경원대로 627', '관교동 500', '신비마을아파트', 37.438, 126.7]]
