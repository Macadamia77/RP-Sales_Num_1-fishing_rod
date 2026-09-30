"""2단계 · KB부동산과 집품 · collector.js procB 를 옮김

  · KB · 번호 조회 대상이거나, 카카오에서 이름을 못 찾은 이름 조회 대상일 때
        지번으로 먼저, 주소 일치가 없으면 도로명으로 검색 → 단지정보에서 단지명·관리사무소 전화
  · 집품 · 카카오에서 이름을 못 찾은 이름 조회 대상일 때 건물명
  · 새 이름이 생기고 번호 조회 대상이면 그 이름으로 카카오 재검색
요청 사이 0.35초.
"""
import re

from .compat import WS, js_str, js_trim, jor, truthy, tstr
from .providers.kakao import core, research
from .settings import current as settings



def short_a(s):
    t = js_str(s)
    t = re.sub('^' + settings().sido_prefix_re() + WS + r'*[가-힣]+(구|군)' + WS + '*', '', t, count=1)
    t = re.sub(WS + r'*\([^\n\r  ]*\Z', '', t, count=1)
    t = re.sub(r'번지[^\n\r  ]*\Z', '', t, count=1)
    return js_trim(t)


def sq(s):
    return re.sub(WS + '+', '', js_str(s))


def bad_nm(n):
    t = js_trim(js_str(n))
    return (len(sq(t)) < 2 or bool(re.search(r'^[가-힣]+[0-9]*(동|리|가)' + WS + '*[0-9]', t))
            or bool(re.search(r'^(다세대|연립|도시형|아파트|주택|빌라|오피스텔|근린생활시설)' + WS + r'*(\([^\n\r  ]*\))?\Z', t))
            or bool(re.search(r'^(가|나|다|라|[A-Z]|[0-9]+)동\Z', t))
            or bool(re.search(r'^[0-9\-' + WS[1:-1] + r']+\Z', t)))


def clean_kb(n):
    t = js_trim(js_str(n))
    t = re.sub(r'\.+\Z', '', t, count=1)
    t = re.sub(r'\.\(', '(', t, count=1)
    t = re.sub(r'\((도|고층|저층|신|구|[0-9]+(-[0-9]+)?)\)' + WS + r'*\Z', '', t, count=1)
    t = js_trim(t)
    t = re.sub(r'\.+\Z', '', t, count=1)
    return js_trim(t)


def proc_b(kakao, kb, zippoom, sleep, gu, b, A):
    """2단계 · 건물 1곳. A는 이 건물의 1단계 결과"""
    i, road, jib, n0, nt, pt = b
    out = {'i': i, 'log': [], 'P': []}

    def is_match(x):
        return bool((jib and sq(short_a(x.get('JUSO_ARNO'))) == sq(jib)) or (road and sq(short_a(x.get('NEWADDRESS'))) == sq(road)))
    need_kb = pt or (nt and not truthy(A.get('pn')))
    m = None
    if need_kb:
        if jib:
            d = kb.search(jib); sleep(settings().kb_zippoom_gap)
            m = next((x for x in d if is_match(x)), None)
            out['log'].append(f'KB부동산 지번검색 "{jib}": {len(d)}건' + (' 주소일치' if m else ''))
        if not m and road:
            d = kb.search(gu + ' ' + road); sleep(settings().kb_zippoom_gap)
            m = next((x for x in d if is_match(x)), None)
            out['log'].append(f'KB부동산 도로명검색 "{gu} {road}": {len(d)}건' + (' 주소일치' if m else ''))
        if m and truthy(m.get('COMPLEX_NO')):
            mm = kb.complex_main(m['COMPLEX_NO']); sleep(settings().kb_zippoom_gap)
            k = {'no': m['COMPLEX_NO'], 't': m.get('t'), 'nm': jor(m.get('HSCM_NM'), ''), 'addr': jor(m.get('JUSO_ARNO'), ''),
                 'road': jor(m.get('NEWADDRESS'), ''), 'main_nm': jor(mm.get('단지명'), ''), 'tel': jor(mm.get('관리사무소전화번호내용'), ''),
                 'hh': jor(mm.get('총세대수'), '')}
            out['kb'] = k
            out['log'].append(f'KB부동산 단지정보: {tstr(k["main_nm"])}, 관리사무소 전화 {tstr(jor(k["tel"], "없음"))}')
    if nt and not truthy(A.get('pn')):
        q = settings().sido + ' ' + gu + ' ' + (road or jib)
        z = zippoom.search(q); sleep(settings().kb_zippoom_gap)
        zm = next((x for x in z if (road and sq(short_a(x.get('address'))) == sq(road)) or (jib and sq(short_a(x.get('oldAddress'))) == sq(jib))), None)
        if zm is not None:
            nm = jor(zm.get('buildingName'), '')
            zp = {}
            if 'buildingId' in zm:
                zp['id'] = zm['buildingId']
            zp['nm'] = nm
            if 'buildingType' in zm:
                zp['type'] = zm['buildingType']
            zp['generic'] = (not truthy(nm)) or bool(re.search(r'^[가-힣]+[0-9]*(동|리|가)' + WS + '*[0-9]', js_str(nm)))
            out['zp'] = zp
            out['log'].append(f'집품 주소검색: 주소일치 {("이름 없음 " + js_str(nm)) if zp["generic"] else js_str(nm)} · {js_str(zm.get("buildingType"))}')
        else:
            out['log'].append(f'집품 주소검색 "{q}": {len(z)}건, 주소일치 없음')
        out['zq'] = q
    # 새 이름 · 집품 이름, 없으면 KB 단지명
    nn = ''
    if not truthy(A.get('pn')):
        zp = out.get('zp')
        if zp and not zp['generic'] and not bad_nm(zp['nm']):
            nn = zp['nm']
        elif out.get('kb'):
            k = clean_kb(jor(out['kb']['main_nm'], out['kb']['nm']))
            if not bad_nm(k):
                nn = k
    out['nn'] = nn
    # 새 이름으로 카카오 재검색
    if nn and pt and len(core(nn)) >= 2 and truthy(A.get('g')):
        rows, n = research(kakao, A, nn)
        out['P'] += rows
        out['log'].append(f'카카오 건물명 재검색 "{nn}": {n}건')
    return out
