"""판정과 병합 · 조회 결과로 건물명, 대표번호, 대리 연락처, 검수 표시를 정하고 다음 조회 대기열을 만든다

언제든 다시 돌려도 됨. 있는 결과만으로 판정하고, 부족한 단계는 대기열 파일로 알려 줌

사용 예
  python merge.py --work work --gu 미추홀구 --dong 주안동
  python merge.py --work work --gu 미추홀구 --dong 주안동 --scope114 no_proxy

--scope114
  no_rep    대표번호가 없는 건물 전부를 114On 대기열에 넣음. 용현동·주안동 방식. 기본값
  no_proxy  대표번호도 대리 연락처도 없는 건물만
  none      114On 대기열을 만들지 않음

만드는 파일 · 작업 폴더 안
  results.json               건물별 최종 판정
  naver_geo_000.js ...       지오코딩 탭에 주입할 대기열. 주소 묶기 보강용
  naver_verify_000.js ...    지역 검색 탭에 주입할 대기열. 이름이 다른 근접 관리사무소
  q114_000.js ...            114.co.kr 탭에 주입할 114On 대기열
"""
import argparse, json, os, re
from urllib.parse import quote
from common import (load, save, s, nr, nj, short_addr, dist_m, is_mg, strip_mg, name_eq, loose_eq, exact_core_eq,
                    region_words, is_bldg_place, REP_EXCL, OTHER_FACILITY_MG, clean_kb, bad_name, suspicious_name,
                    EXCL, role, digits, facility)

def places_of(A, B):
    out, seen = [], set()
    for src in (A.get('P') or []) + (B.get('P') or []):
        pid = src[0]
        if pid in seen: continue
        seen.add(pid)
        out.append({'id': pid, 'n': src[1], 'c': src[2], 'p': src[3], 'u': src[4], 'x': src[5], 'y': src[6],
                    'road': src[7], 'jib': src[8], 'm0': src[9], 'd': src[10], 'src': src[11]})
    return out

def kmap(q): return 'https://map.kakao.com/?q=' + quote(q)

def decide_name(r, A, B, matched):
    if not r['nt']: return None
    if A.get('bnR') or A.get('bnJ'):
        v = A.get('bnR') or A.get('bnJ')
        return {'v': v, 'src': '카카오 주소검색 도로명주소 건물명', 'st': '카카오 주소검색', 'link': kmap(r['road'] or r['jibun'])}
    bp = next((p for p in matched if is_bldg_place(p['c'], p['n'])), None)
    if bp: return {'v': bp['n'], 'src': '카카오맵 장소 ' + s(bp['c']), 'st': '카카오맵 장소', 'link': bp['u']}
    zp, kb = B.get('zp'), B.get('kb')
    if zp and not zp.get('generic') and not bad_name(zp.get('nm')):
        q = (r['road'] or r['jibun']).replace('인천광역시', '인천')
        return {'v': zp['nm'], 'src': '집품 주소검색 건물명', 'st': '집품', 'link': 'https://zippoom.com/search/' + quote(q) + '?searchWithAddress=false'}
    if kb:
        k = clean_kb(kb.get('main_nm') or kb.get('nm'))
        if not bad_name(k):
            return {'v': k, 'src': 'KB부동산 단지명 ' + s(kb.get('main_nm') or kb.get('nm')), 'st': 'KB부동산', 'link': 'https://kbland.kr/c/' + str(kb['no'])}
    return None

def naver_verdict(v):
    if not v or v.get('err'): return None
    b = v.get('best')
    if not b: return '네이버 미등록'
    if b['d'] <= 100: return '네이버 교차 확인 일치' if is_mg(b['n']) else '네이버 단지 위치 일치'
    return '네이버 위치 불일치'

def decide_phone(r, A, B, C, places, matched, name, words, NV, near_same, use114):
    """대표번호 판정. 반환: (ph, held, pending_naver, flags)"""
    held, pending, flags = [], [], []
    kb = B.get('kb') or {}
    kb_tel = digits(kb.get('tel'))
    acc = []   # (우선순위, ph)
    for p in sorted([p for p in matched if p['p'] and is_mg(p['n'])], key=lambda z: (z['d'] is None, z['d'] or 0)):
        base = '카카오맵 관리사무소' if p['src'] == 'a' else '카카오맵 건물명 재검색 관리사무소'
        ph = {'v': p['p'], 'name': p['n'], 'link': p['u']}
        if re.search(OTHER_FACILITY_MG, p['n']):
            held.append({**ph, 'reason': '다른 시설 관리사무소로 보임', 'd': p['d']}); continue
        if name and loose_eq(p['n'], name, words):
            acc.append((1, {**ph, 'src': base})); continue
        if kb_tel and digits(p['p']) == kb_tel:
            acc.append((2, {**ph, 'src': base + ' · 이름은 다르지만 KB 번호와 일치'})); continue
        if p['d'] is not None and p['d'] <= 100:
            key = f"{r['i']}:{p['id']}"
            vd = naver_verdict(NV.get(key))
            if vd in ('네이버 교차 확인 일치', '네이버 단지 위치 일치'):
                acc.append((2, {**ph, 'src': base + ' · 이름은 다르지만 주소가 같고 거리가 가까움 · ' + vd})); continue
            if vd is None:
                pending.append([key, p['n'], p['x'], p['y'], r['gu']])
                held.append({**ph, 'reason': '관리사무소 이름 불일치 · 네이버 확인 대기', 'd': p['d']}); continue
            held.append({**ph, 'reason': '관리사무소 이름 불일치 · ' + vd, 'd': p['d']}); continue
        held.append({**ph, 'reason': '관리사무소 이름 불일치 · 100m 넘음', 'd': p['d']})
    if name:
        for p in matched:
            if p['p'] and not is_mg(p['n']) and name_eq(p['n'], name) and not re.search(REP_EXCL, s(p['c'])):
                acc.append((3, {'v': p['p'], 'name': p['n'], 'link': p['u'], 'src': '카카오맵 건물 대표번호' if p['src'] == 'a' else '카카오맵 건물명 재검색 건물 대표번호'}))
    if kb_tel:
        acc.append((4, {'v': kb['tel'], 'name': s(kb.get('main_nm') or kb.get('nm')), 'link': 'https://kbland.kr/c/' + str(kb['no']), 'src': 'KB부동산 관리사무소'}))
    if name:
        for p in places:
            if p['m'] or not p['p'] or p['d'] is None or p['d'] > 100: continue
            if not exact_core_eq(p['n'], name) or re.search(REP_EXCL, s(p['c'])): continue
            ph = {'v': p['p'], 'name': p['n'], 'link': p['u']}
            if near_same:
                held.append({**ph, 'reason': '주소 다름 · 근처에 같은 이름 건물이 있어 자동으로 넣지 않음', 'd': p['d']})
            else:
                acc.append((5, {**ph, 'src': '카카오맵 · 주소 다름, 건물명·거리 일치 ' + str(p['d']) + 'm'}))
    if use114 and C and C.get('ph'):
        c = C['ph']
        acc.append((6, {'v': c['v'], 'name': c['name'], 'link': c['link'], 'src': c['src'], 'weak': c.get('weak') or '번지 비공개' in c['src']}))
    # 건물 장소에 붙은 전국 대표번호(15xx·16xx·18xx)는 분양·상담 번호인 경우가 많아 자동으로 넣지 않음
    nat = False; keep = []
    for pr, c in acc:
        if pr in (3, 5) and re.match(r'^(15|16|18)\d{6}$', digits(c['v'])):
            held.append({'v': c['v'], 'name': c['name'], 'link': c['link'], 'reason': '전국 대표번호(15xx·16xx·18xx) · 분양·상담 번호일 수 있어 자동으로 넣지 않음', 'd': None, 'nat': True})
            nat = True
        else:
            keep.append((pr, c))
    acc = keep
    acc.sort(key=lambda z: z[0])
    ph = acc[0][1] if acc else None
    if ph:
        for h in held:
            if digits(h['v']) == digits(ph['v']):
                ph['src'] += ' · 검수 후보와 같은 번호'
                h['reason'] += ' · 확정 번호와 같음'
        if ph.get('weak'): flags.append('114On 약한 일치')
    # 확정 번호와 같은 후보는 검수 대상에서 뺌
    held = [h for h in held if not (ph and digits(h['v']) == digits(ph['v']))]
    if any(not h.get('nat') for h in held): flags.append('관리사무소 후보 검수 필요')
    if any(h.get('nat') for h in held): flags.append('전국 대표번호 검수 필요')
    return ph, held, pending, flags

def proxies(matched, C, A):
    pool, seen = [], set()
    for p in matched:
        if not p['p'] or EXCL.search(s(p['c']) + ' ' + s(p['n'])) or is_mg(p['n']): continue
        d = digits(p['p'])
        if d in seen: continue
        seen.add(d); pr, rl = role(p['n'], p['c'])
        pool.append({'n': p['n'], 'p': p['p'], 'c': s(p['c']), 'role': rl, 'pr': pr, 'src': '카카오맵', 'link': p['u'], 'mob': d.startswith('01')})
    for x in (C or {}).get('pool', []):
        if not x.get('tel') or EXCL.search(s(x.get('up')) + ' ' + s(x['nm'])) or is_mg(x['nm']): continue
        d = digits(x['tel'])
        if d in seen: continue
        seen.add(d); pr, rl = role(x['nm'], x.get('up'))
        pool.append({'n': x['nm'], 'p': x['tel'], 'c': s(x.get('up')), 'role': rl, 'pr': pr, 'src': '114On ' + s(x.get('via')), 'link': x['link'], 'mob': d.startswith('01')})
    pool.sort(key=lambda z: (z['pr'], z['mob']))
    st = pool[:2]
    used = {digits(z['p']) for z in st}; re_ = []
    for n2, p2, dd, url in A.get('ag') or []:
        if digits(p2) in used: continue
        used.add(digits(p2)); re_.append({'n': n2, 'p': p2, 'd': dd, 'link': url})
        if len(re_) >= 3: break
    return st, re_, len(pool)

def write_js(d, prefix, fn, reg, rows, chunk):
    for f in os.listdir(d):
        if f.startswith(prefix) and f.endswith('.js'): os.remove(os.path.join(d, f))
    out = []
    for k in range(0, len(rows), chunk):
        part = rows[k:k + chunk]; name = f'{prefix}{k // chunk:03d}.js'
        with open(os.path.join(d, name), 'w', encoding='utf-8') as f:
            f.write(f"{fn}({json.dumps(reg, ensure_ascii=False)},{json.dumps(part, ensure_ascii=False, separators=(',', ':'))})")
        idsum = sum(x[0] for x in part) if part and isinstance(part[0][0], int) else None
        out.append((name, len(part), idsum))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default='work'); ap.add_argument('--gu', required=True); ap.add_argument('--dong', required=True)
    ap.add_argument('--scope114', default='no_rep', choices=['no_rep', 'no_proxy', 'none'])
    a = ap.parse_args()
    d = os.path.join(a.work, f'{a.gu}_{a.dong}')
    IN = load(os.path.join(d, 'input.json'), [])
    if not IN: raise SystemExit('input.json 이 없음. prepare.py 먼저')
    AA, BB, CC = load(os.path.join(d, 'A.json')), load(os.path.join(d, 'B.json')), load(os.path.join(d, 'C.json'))
    NG, NV = load(os.path.join(d, 'NG.json')), load(os.path.join(d, 'NV.json'))
    words = region_words(a.gu, a.dong)
    reg = {'gu': a.gu, 'dong': a.dong}
    # 1차 · 이름 확정 후 같은 이름 건물 좌표 모음
    pre = {}
    for r in IN:
        i = str(r['i']); A = AA.get(i) or {}; B = BB.get(i) or {}
        if not A or A.get('err'): continue
        R, J = set(A.get('R') or []), set(A.get('J') or [])
        g = NG.get(i) or {}
        for z in (g.get('r'), g.get('j')):
            if z:
                # 네이버 주소 끝에 붙는 건물명(z[2])을 떼야 카카오 주소와 비교됨
                bn = (z[2] or '').strip() if len(z) > 2 else ''
                zr, zj = (z[0] or '').strip(), (z[1] or '').strip()
                if bn:
                    if zr.endswith(bn): zr = zr[:-len(bn)].strip()
                    if zj.endswith(bn): zj = zj[:-len(bn)].strip()
                if zr: R.add(nr(zr))
                if zj: J.add(nj(zj))
        pl = places_of(A, B)
        for p in pl: p['m'] = 1 if (nr(p['road']) in R or nj(p['jib']) in J) else 0
        matched = [p for p in pl if p['m']]
        nm = decide_name(r, A, B if not (B.get('err')) else {}, matched)
        pre[i] = (A, B, pl, matched, nm)
    names = {}
    INd = {str(x['i']): x for x in IN}
    for i, (A, B, pl, matched, nm) in pre.items():
        r0 = INd[i]
        fn = nm['v'] if nm else r0['n0']
        if fn and A.get('g'): names.setdefault(re.sub(r'\s+|아파트|오피스텔|빌라|주택', '', fn), []).append((i, A['g']))
    results, pend_all, geo_q, q114 = [], [], [], []
    for r in IN:
        i = str(r['i']); o = {k: r[k] for k in ('i', 'gu', 'dong', 'grade', 'hh', 'ho', 'road', 'jibun', 'n0', 'nt', 'pt')}
        A = AA.get(i); B = BB.get(i) or {}; C = CC.get(i) if (CC.get(i) and not CC.get(i).get('err')) else None
        flags = []
        if not A or A.get('err'):
            o.update({'nm': None, 'ph': None, 'held': [], 'st': [], 're': [], 'km': 0, 'tm': 0, 'log': [A.get('err')] if A else ['1단계 미조회'],
                      'K': [], 'T': [], 'kb': None, 'zp': None, 'fac': ['', '', ''], 'g': None})
            o['flags'] = ['조회 오류 또는 미조회']; o['human'] = True; results.append(o); continue
        A, B, pl, matched, nm = pre[i]
        if B.get('err'): flags.append('2단계 조회 오류'); B = {}
        name = nm['v'] if nm else r['n0']
        key = re.sub(r'\s+|아파트|오피스텔|빌라|주택', '', name or '')
        near_same = False
        if key and A.get('g'):
            for j, g2 in names.get(key, []):
                if j != i:
                    dd = dist_m(A['g'][0], A['g'][1], g2[0], g2[1])
                    if dd is not None and dd <= 200: near_same = True
        ph, held, pending, f2 = (None, [], [], [])
        ph0 = None
        if r['pt']:
            ph0, _, _, _ = decide_phone(r, A, B, None, pl, matched, name, words, NV, near_same, False)
            ph, held, pending, f2 = decide_phone(r, A, B, C, pl, matched, name, words, NV, near_same, True)
            pend_all += pending
            flags += f2
        st, re_, pooln = ([], [], 0)
        if r['pt'] and not ph:
            st, re_, pooln = proxies(matched, C, A)
        if r['nt'] and not nm: flags.insert(0, '건물명 미해결')
        if r['nt'] and nm and suspicious_name(nm['v']): flags.append('건물명 검수 필요'); nm['src'] += ' · 건물명 검수 필요'
        if r['pt'] and not ph and not (st or re_): flags.append('대리 연락처도 없음')
        fac = facility(nm['v'], matched, r['hh'], r['ho']) if (r['nt'] and nm) else ('', '', '')
        o.update({'g': A.get('g'), 'nm': nm, 'ph': ph, 'held': held, 'st': st, 're': re_, 'pool_n': pooln,
                  'km': len(matched), 'tm': len((C or {}).get('pool', [])), 'flags': flags, 'human': bool(flags),
                  'log': list(A.get('log', [])) + list(B.get('log', [])) + list((C or {}).get('log', [])),
                  'K': [[p['n'], p['c'], p['p'], p['u']] for p in matched], 'T': (C or {}).get('pool', []),
                  'kb': B.get('kb'), 'zp': B.get('zp'), 'zq': B.get('zq'), 'fac': list(fac)})
        results.append(o)
        # 대기열
        if ((r['pt'] and not ph0) or (r['nt'] and not nm)) and i not in NG:
            geo_q.append([r['i'], short_addr(r['road']), short_addr(r['jibun'])])
        if r['pt'] and not ph0 and i not in CC and a.scope114 != 'none':
            if a.scope114 == 'no_rep' or not (st or re_):
                g = A.get('g') or [None, None]
                q114.append([r['i'], short_addr(r['road']), short_addr(r['jibun']), name or '', g[1], g[0]])
    save(os.path.join(d, 'results.json'), results)
    w1 = write_js(d, 'naver_geo_', '__loadGeoQueue', reg, geo_q, 400)
    w2 = write_js(d, 'naver_verify_', '__loadVerifyQueue', reg, pend_all, 200)
    w3 = write_js(d, 'q114_', '__loadQueue114', reg, q114, 400)
    # 요약
    n = len(results); nt = sum(1 for x in results if x['nt']); pt = sum(1 for x in results if x['pt'])
    print(f'{a.gu} {a.dong} · 대상 {n}건')
    print(f"  단계별 결과 A {len(AA)} · B {len(BB)} · 지오코딩 {len(NG)} · 네이버 확인 {len(NV)} · 114On {len(CC)}")
    print(f"  건물명 {sum(1 for x in results if x['nt'] and x['nm'])} / {nt}")
    print(f"  대표번호 {sum(1 for x in results if x['pt'] and x['ph'])} / {pt} · 대리 연락처만 {sum(1 for x in results if x['pt'] and not x['ph'] and (x['st'] or x['re']))}")
    print(f"  사람 확인 필요 {sum(1 for x in results if x['human'])}")
    for label, w in (('네이버 지오코딩 대기열', w1), ('네이버 확인 대기열', w2), ('114On 대기열', w3)):
        tot = sum(z[1] for z in w)
        print(f'  {label} {tot}건' + ('' if not w else ' · ' + ', '.join(f'{z[0]} {z[1]}건' + (f' idx합 {z[2]}' if z[2] is not None else '') for z in w)))

if __name__ == '__main__':
    main()
