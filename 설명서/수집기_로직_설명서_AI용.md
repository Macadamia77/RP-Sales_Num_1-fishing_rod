# 건물정보 수집기 · 수집·정제 로직 명세 (AI용)

> 대상: 이 로직을 회사 시스템(AWS, 버튼 방식)으로 재구현하거나 고치는 개발자의 AI 도우미.
> 기준: main `1a26228` 코드. 줄 번호는 이 커밋 기준이다.
> 사람이 읽는 판은 `설명서/수집기_로직_설명서.html`. 코드 파일 지도와 실행 흐름은 `docs/코드구조_설명서_AI용.md`, 위험 목록은 `검수보고서.md`.
> 이 문서의 값(개수, 거리, 단어 목록)은 코드에 적힌 값을 그대로 옮긴 것이다. 바꾸면 결과가 달라진다.

## 0. 요약

- 입력은 콜리스트 CSV의 한 행(건물)이다. 출력은 건물명, 대표번호, 대리 연락처(최대 5개), 검수 후보, 플래그다.
- **같은 건물 판단은 주소로 한다.** 건물의 여러 주소를 정규화해 집합 R(도로명)·J(지번)로 묶고, 장소의 정규화 주소가 집합에 **같은 값으로** 있으면 "주소 일치"다. 이름이나 부분 포함은 쓰지 않는다.
- 과정은 P1~P9다. 수집은 P2~P5와 P9, 판정은 P6~P8이다. 판정은 `legacy/merge.py`가 하고, P9가 끝날 때마다 다시 돈다.
- 현재 구현은 (구, 동) 단위 배치이고, 단계 사이 데이터는 JSON 파일과 JS 대기열 파일로 넘긴다. 재구현 때는 건물 1곳 단위 함수로 바꾸는 것을 전제로 이 문서를 썼다.

## 1. 용어

| 용어 | 뜻 |
|---|---|
| 이름 대상 `nt` | 원본 `건물명`이 `(건물명없음)`으로 시작 |
| 번호 대상 `pt` | 원본 `대표번호`가 빈 값이거나 `없음` |
| 짧은 주소 | `인천광역시 ○○구 `를 뗀 주소. 예 `주승로 247`, `관교동 13-11` |
| R, J | 주소 묶음. 정규화한 도로명 집합, 정규화한 지번 집합 |
| 장소 풀 `P` | 카카오 장소 중 주소 일치이거나 200m 이내라서 남긴 목록 |
| 주소 일치 `m` | 장소의 `nr(도로명) ∈ R` 또는 `nj(지번) ∈ J` |
| 임시 건물명 `pn` | P3 재검색에 쓰는 이름. 원래 이름 → 공식 건물명 → 건물 장소 이름 |
| 새 이름 `nn` | P5에서 집품·KB로 얻은 이름. `pn`이 없을 때만 만든다 |
| 건물명 `name` | P6 결과, 없으면 원래 이름(`n0`). P7·P8 비교에 쓴다 |
| 보류 `held` | 자동으로 넣지 않은 대표번호 후보. 결과의 `검수_후보번호` 열 |

## 2. 과정별 명세

각 과정은 `조건 → 수집 → 정제 → 선택 → 저장` 순서로 적는다.

### P1 입력과 주소 준비 · `pipeline/prepare.py`, `legacy/common.py:32-51`

```
for row in csv:
    nt = row.건물명.startswith('(건물명없음)')
    pt = strip(row.대표번호) in ('', '없음')
    if not (nt or pt): skip
    road  = road_from_src(row.도로명주소)   # 앞 '(건물명없음) ' 제거, 끝 '(…)' 제거
    jibun = jibun_from_src(row.지번주소)    # 'N번지 M호'→'N-M', '번지' 제거; '블록' 포함 또는 끝이 숫자가 아니면 ''
    short_road, short_jib = short_addr(road), short_addr(jibun)   # 앞 '인천(광역시)? ○○구 ' 제거
    n0 = '' if nt else row.건물명
    emit [idx, short_road, short_jib, n0, nt, pt]
```

### P2 건물 기준 정보 · `pipeline/providers/kakao.py:105-141`

```
P = '인천광역시 ' + 구 + ' '
ad_r = kakao.address(P + short_road) if short_road else []     # GET address.json?query=...
ad_j = kakao.address(P + short_jib)  if short_jib  else []
first = ad_r[0] or ad_j[0]
x, y = first.x, first.y                                        # 없으면 None
bnR = ad_r[0].road_address.building_name or ''
bnJ = ad_j[0].road_address.building_name or ''
R = { nr(P + short_road) } ∪ { nr(d.road_address.address_name) for d in (ad_r[0], ad_j[0]) if d.road_address }
J = { nj(P + short_jib)  } ∪ { nj(d.address.address_name)      for d in (ad_r[0], ad_j[0]) if d.address }
```

- 각 결과의 **첫 문서만** 쓴다.
- 좌표가 없으면 P3 뒤에 "주소 일치인 첫 장소"의 좌표로 대신한다(`kakao.py:169-172`).

정규화 함수 (`kakao.py:20-40`, `common.py:53-66`, 두 벌이 같은 규칙):

```
nr(s): '인천광역시'→'인천' (첫 1회) → '\s*\([^)]*\)'→' ' → ',' 앞부분만 → 공백 하나로 → trim
nj(s): '인천광역시'→'인천' → 괄호 삭제 → '(\d+)\s*번지\s*(\d+)\s*호'→'\1-\2' (1회) → '번지' 삭제
       → 끝 '(\d+)\s*호' 삭제 → '([가-힣]+?)\d+동'→'\1동' (주안1동→주안동) → 공백 하나로 → trim
```

실행 예: `nr('인천광역시 미추홀구 주승로 247 (관교동)') = '인천 미추홀구 주승로 247'`, `nj('인천광역시 미추홀구 관교동 13번지 11호') = '인천 미추홀구 관교동 13-11'`.
한계: `주승로247`과 `주승로 247`은 `nr`로 다르다.

### P3 장소 풀 · `kakao.py:144-185`, `kakao.py:194-207`

```
def add(docs, src):
    for d in docs:
        if d.id in P: continue
        m  = nr(d.road_address_name) in R or nj(d.address_name) in J
        dd = dist(x, y, d.x, d.y) if x else None
        if not m and not (dd is not None and dd <= 200): continue      # 버림
        P[d.id] = [id, place_name, category_name, phone, place_url, x6, y6, road_address_name, address_name, m, dd, src]

# 수집 ① 주소로 장소검색
qs = [P+short_road, P+short_jib] + [d.address.address_name for d in (ad_r[0], ad_j[0])
                                    if d and d.address and nj(d.address.address_name) != nj(P+short_jib)]
for q in unique(qs):                        # 최대 4개, 글자가 같으면 1회
    add(kakao.keyword(q, max_page=3), 'a')   # 15건 × 최대 3페이지, 좌표·반경 없음, meta.is_end면 중단

pn = n0 or bnR or bnJ or first(p.name for p in P if p.m and is_bldg(p.category, p.name))

# 수집 ② 이름 재검색
if pt and pn and len(core(pn)) >= 2:
    rad = 1000 if x else None
    add(kakao.keyword(pn, x, y, rad, max_page=1) + kakao.keyword(pn + ' 관리사무소', x, y, rad, max_page=1), 'rs')
```

- 수집 ③(P5의 새 이름 재검색, `research`)도 같은 거르기로 `src='rs2'` 행을 만든다. 단 `x`가 있어야 하고 반경은 항상 1km다.
- `P`의 순서는 자바스크립트 `Object.values` 규칙을 따른다. 숫자 모양 ID는 오름차순이 먼저 온다(`compat.JSObj`). 판정의 "첫 장소"는 이 순서다.
- 판정(`merge.py:places_of`)은 P3의 `P`와 P5의 `P`(rs2)를 합치고, 네이버 주소를 더한 R·J로 `m`을 다시 계산한다.

### P4 주변 중개업소 · `kakao.py:186-189`

```
ag = []
if pt and x:
    docs = kakao.category('AG2', x, y, 300)          # sort=distance, page·size 지정 없음 → 첫 15곳
    docs = [d for d in docs if d.phone][:8]
    ag = [[d.place_name, d.phone, to_num(d.distance), d.place_url] for d in docs]
```

- 단어 필터는 없다. AG2(중개업소) 분류 코드로 거른다.
- 대표번호를 찾을지와 무관하게 **번호 대상 전부에서 미리** 호출한다. P8에서 쓰는 건 대표번호를 못 찾은 건물뿐이다.
- **문제**: `distance`가 빈 문자열이면 `to_num('')`이 0을 돌려주어 0m로 저장된다.

### P5 KB부동산·집품 · `pipeline/secondary.py:47-107`, `pipeline/providers/kb.py`, `pipeline/providers/zippoom.py`

P2가 성공한 건물만 대상이다(`service.py:303`). 한 건씩 순서대로, 요청 사이 0.35초. 다시 시도하지 않는다.

```
short_a(s) = trim( 앞 '인천(광역시)?\s*[가-힣]+(구|군)\s*' 제거 → 끝 '\s*\(…' 제거 → 끝 '번지…' 제거 )
sq(s)      = 공백 전부 제거
match(x)   = (jib and sq(short_a(x.JUSO_ARNO)) == sq(jib)) or (road and sq(short_a(x.NEWADDRESS)) == sq(road))

if pt or (nt and not pn):                                          # KB
    m = first(match, kb.search(jib)) if jib                           # 검색어 '관교동 13-11' (시도 붙이면 결과 없음)
    if not m and road: m = first(match, kb.search(구 + ' ' + road))    # '미추홀구 주승로 247'
    if m and m.COMPLEX_NO:
        mm = kb.complex_main(m.COMPLEX_NO)
        kb = {no, nm: m.HSCM_NM, main_nm: mm.단지명, tel: mm.관리사무소전화번호내용, hh: mm.총세대수}

if nt and not pn:                                                  # 집품
    z = zippoom.search('인천광역시 ' + 구 + ' ' + (road or jib))
    zm = first(x for x in z if (road and sq(short_a(x.address)) == sq(road)) or (jib and sq(short_a(x.oldAddress)) == sq(jib)))
    if zm: zp = {id, nm: zm.buildingName, type, generic: not nm or re.match('^[가-힣]+[0-9]*(동|리|가)\s*[0-9]', nm)}

nn = ''
if not pn:
    if zp and not zp.generic and not bad_name(zp.nm): nn = zp.nm
    elif kb and not bad_name(clean_kb(kb.main_nm or kb.nm)): nn = clean_kb(...)
if nn and pt and len(core(nn)) >= 2 and x: P += research(nn)      # P3 수집 ③
```

- KB 호출: `GET https://api.kbland.kr/land-complex/serch/intgraSerch?검색설정명=SRC_NTOTAL&검색키워드={q}&출력갯수=10&페이지설정값=1`, 응답 `dataBody.data.data.HSCM.data[]`와 `VILLA.data[]`만 읽음. 단지정보 `GET .../complex/complexMain?단지기본일련번호={no}`, 응답 `dataBody.data`.
- 집품 호출: `GET https://live.zippo-om.com/api/v1/buildings/search/autoComplete?keyword={q}`, 응답 `payload[].buildingDocument`. 도메인이 사이트(`zippoom.com`)와 달라 오타일 수 있다(미확인).
- 둘 다 공식 API가 아니다. 키·쿠키·브라우저 헤더 없이 부른다.

### P6 건물명 · `legacy/merge.py:38-53`

```
if not nt: return None
if bnR or bnJ:                                             return bnR or bnJ          # 1
bp = first(p for p in matched if is_bldg_place(p.c, p.n));  if bp: return bp.n         # 2
if zp and not zp.generic and not bad_name(zp.nm):          return zp.nm               # 3
if kb and not bad_name(clean_kb(kb.main_nm or kb.nm)):    return clean_kb(...)       # 4
return None   → 플래그 '건물명 미해결'
```

- `matched` = 장소 풀 중 `m == 1`.
- 이름을 찾았고 `suspicious_name`이면 '건물명 검수 필요'. 이름을 찾은 경우에만 `facility()`로 시설 건물 판정(`merge.py:235`).

### P7 대표번호 · `legacy/merge.py:62-126`

```
acc, held, pending = [], [], []
kb_tel = digits(kb.tel)
for p in sorted((p for p in matched if p.phone and is_mg(p.n)), key=(p.d is None, p.d or 0)):
    if re.search(OTHER_FACILITY_MG, p.n):          held += (p, '다른 시설 관리사무소로 보임'); continue
    if name and loose_eq(p.n, name, words):         acc += (1, p); continue
    if kb_tel and digits(p.phone) == kb_tel:        acc += (2, p); continue
    if p.d is not None and p.d <= 100:
        v = naver_verdict(NV[f'{i}:{p.id}'])
        if v in ('네이버 교차 확인 일치', '네이버 단지 위치 일치'): acc += (2, p); continue
        if v is None: pending += [key, p.n, p.x, p.y, 구]; held += (p, '네이버 확인 대기'); continue
        held += (p, v); continue
    held += (p, '100m 넘음')
if name:
    for p in matched:
        if p.phone and not is_mg(p.n) and name_eq(p.n, name) and not re.search(REP_EXCL, p.c): acc += (3, p)
if kb_tel: acc += (4, kb)
if name:
    for p in all_places:                               # 주소 불일치 장소
        if p.m or not p.phone or p.d is None or p.d > 100: continue
        if not exact_core_eq(p.n, name) or re.search(REP_EXCL, p.c): continue
        (held if near_same else acc) += (5, p)         # near_same: 같은 동에 같은 이름 키를 가진 다른 건물이 200m 이내
if use114 and C.ph: acc += (6, C.ph)
move (pr in (3,5) and re.match('^(15|16|18)\d{6}$', digits(v))) from acc to held   # 전국 대표번호
ph = min(acc, key=priority)   # 같은 순위는 들어온 순서
remove from held the numbers equal to ph
flags: '관리사무소 후보 검수 필요' if non-national held, '전국 대표번호 검수 필요' if national held, '114On 약한 일치' if ph.weak
```

- 판정은 두 번 한다. `use114=False` 결과(`ph0`)로 네이버 지오코딩·114On 대기열 여부를 정하고, `use114=True` 결과를 최종값으로 쓴다(`merge.py:225-227`).
- `name`이 비면 1·3·5순위는 나오지 않는다.
- `naver_verdict`: 오류·미조회 → None, best 없음 → '네이버 미등록', best.d ≤ 100 → 관리사무소 이름이면 '교차 확인 일치' 아니면 '단지 위치 일치', 그 밖 → '네이버 위치 불일치'.

### P8 대리 연락처 · `legacy/merge.py:128-149`

```
if not (pt and not ph): skip
pool, seen = [], set()
for p in matched:                                        # 건물 내 점포 (카카오)
    if not p.phone or EXCL.search(p.c + ' ' + p.n) or is_mg(p.n): continue
    if digits(p.phone) in seen: continue
    seen.add(...); pool += {p, role(p.n, p.c), mob: digits(p.phone).startswith('01')}
for x in C.pool:                                         # 건물 내 점포 (114On 주소 일치 업체)
    같은 거르기 (업종 = x.up)
pool.sort(key=(role_rank, mob))                          # 안정 정렬. 같은 순위·유무선이면 들어온 순서
st = pool[:2]
re_ = []
for n, p, d, url in ag:                                  # P4 결과
    if digits(p) in used: continue
    used.add(...); re_ += {n, p, d, url}
    if len(re_) >= 3: break
if not st and not re_: flag '대리 연락처도 없음'
```

- 결과 열 `대리1~5_{구분,건물명,번호,출처}`. 구분은 `건물 내 점포 · {업종}` 또는 `주변 부동산 · {d}m`(`build_outputs.proxy_rows`).
- **문제**: `role()`(`common.py:166-172`)의 0순위 정규식 `공인중개|부동산중개|부동산`이 카카오 분류 `부동산 > 주거시설 > 아파트` 등에도 걸린다. 가짜 API 실행에서 `동부아파트 경비실`이 대리1 "공인중개사"로 뽑혔다. 0순위는 분류에 `부동산중개`가 있을 때만으로 고칠 것을 권한다.

### P9 보강 · `pipeline/providers/naver.py`, `pipeline/providers/one114.py`, `legacy/merge.py:240-249`

**네이버 지오코딩 (NG)**
- 대기열 조건: `((pt and not ph0) or (nt and not nm)) and i not in NG`. `skip_geo`면 건너뛴다.
- 수집: `GET {naver_geo}/map-geocode/v2/geocode?query=인천광역시 {구} {짧은 주소}`, 도로명·지번 각 1회, 0.12초 간격. `addresses[0]`의 `roadAddress`, `jibunAddress`, `BUILDING_NAME` 요소, x, y.
- 정제: 주소 끝의 건물명을 떼고 `nr`/`nj`로 R·J에 추가 → 장소 풀의 `m` 재계산. **새 장소를 검색하지 않는다.**

**네이버 지역검색 (NV)**
- 대기열: P7의 `pending` (`[f'{i}:{place_id}', 이름, x, y, 구]`).
- 수집: `GET {naver_hub}/search/v1/local?display=5&query={q}`, `q` ∈ [이름, `{k} 관리사무소`, `인천 {k} 관리사무소`, `{구} {k}`, `{k}`], `k = ncore(이름)`. 0.15초 간격. `ncore`는 HTML 태그, 공백, `관리사무소|관리실|관리단|관리소|관리센터|경비실|방제실|입주자대표회의|아파트|전기차충전소`를 지운다.
- 정제: `c = ncore(결과 이름)`, `len(c) >= 2 and (k in c or c in k)`인 결과만 거리 계산(`mapx/1e7`, `mapy/1e7`).
- 선택: 가장 가까운 것을 `best`로. 500m 미만을 찾으면 남은 검색어는 건너뛴다.

**114On (C)**
- 별도 명령 `run114`. 대기열 조건: `pt and not ph0 and i not in C`, 범위 `no_proxy`면 추가로 `not (st or re_)`.
- 수집: `POST https://www.114.co.kr/action/search`, 본문 `{"query": q, "collection": "ALL", "latitude", "longitude", …}`, 헤더 Origin·Referer. 4.5초 간격. 응답이 `{`로 시작하지 않으면 차단으로 보고 멈춘다.
- 검색어 순서: `인천광역시 {구} {도로명}` → (도로명 결과 중 주소 일치가 0곳이면) `인천광역시 {구} {지번}` → (대표번호 후보가 아직 없고 이름이 2글자 이상이면) 이름.
- 정제:
  - `hit(d)` = `k114R(d.road) == short_road` 또는 `k114J(d.addr) == short_jib`(끝 `-0` 제거).
  - `weak(d)` = 이름 검색에서만, `k114S(d.road) == 도로 이름` and `k114J(d.addr) == ''` and 이름 같음 and 제외 업종 아님.
  - 전화 없음, `이름|전화` 중복, hit도 weak도 아님 → 버림.
- 선택: `ph`가 없고 `weak or is_rep(d)`인 첫 업체가 `ph`(P7 6순위). `is_rep` = (`is_mg(nm)` and (이름 없음 or `name_eq(strip_mg(nm), name)` or hit)) or (이름 있음 and `name_eq(nm, name)` and not `고시원|고시텔|원룸|숙박|상가`). 나머지 hit 업체 → `pool`(P8 건물 내 점포 후보).

## 3. 상수와 단어 목록

| 이름 | 값 | 위치 |
|---|---|---|
| 장소검색 페이지 | 15건 × 최대 3페이지 (재검색은 1페이지) | `kakao.py:88-98` |
| 근처 장소 거리 | ≤ 200m | `kakao.py:151` |
| 이름 재검색 반경 | 1000m | `kakao.py:180`, `194` |
| 중개업소 | AG2, 300m, 첫 15곳 → 전화 있는 8곳 → 최종 3곳 | `kakao.py:188`, `merge.py:148` |
| 건물 내 점포 | 2곳 | `merge.py:143` |
| 관리사무소 이름 불일치 허용 거리 | ≤ 100m (+네이버 일치) | `merge.py:77` |
| 주소 불일치 허용 거리 | ≤ 100m (+이름 완전 일치) | `merge.py:96` |
| 같은 이름 근처 건물 | ≤ 200m | `merge.py:221` |
| 네이버 지역검색 | 중단 < 500m, 일치 ≤ 100m | `naver.py:115`, `merge.py:59` |
| `MG_RE` | `관리사무소\|관리사무실\|관리실\|관리단\|관리소\|관리센터\|입주자대표회의`, 제외 `전기차\|충전소\|충전기` | `common.py:76-80` |
| `is_mg` (카카오·114 단계용) | `관리사무소\|관리실\|관리단\|관리소\|관리센터\|입주자대표회의` (관리사무실·제외 규칙 없음) | `kakao.py:47` |
| `OTHER_FACILITY_MG` | `지하상가\|지하도상가\|시장\|주차장\|상가번영회\|상인회` | `common.py:133` |
| `REP_EXCL` | `고시원\|고시텔\|원룸\|숙박` | `common.py:140` |
| `is_bldg_place` | 분류가 `부동산`으로 시작, `부동산서비스\|중개\|고시원\|고시텔\|원룸\|하숙\|셰어\|쉐어\|숙박` 없음, 관리사무소 아님 | `common.py:135` |
| `EXCL` (대리 제외) | `전기차\|충전소\|편의점\|카페\|커피\|GS25\|CU \|^CU\|세븐일레븐\|이마트24\|미니스톱\|스타벅스\|이디야\|메가MGC\|빽다방\|투썸\|컴포즈` | `common.py:164` |
| `role` 0 | `공인중개\|부동산중개\|부동산` (문제 있음) | `common.py:168` |
| `role` 1 | `헬스\|피트니스\|필라테스\|요가\|노래\|코인노래\|PC방\|피씨방\|당구\|스크린골프` | `common.py:169` |
| `role` 2 | `병원\|의원\|치과\|한의원\|약국\|학원\|교습\|어학\|공부방\|교육` | `common.py:170` |
| `role` 3 | `음식\|식당\|한식\|중식\|일식\|양식\|분식\|치킨\|피자\|고기\|족발\|보쌈\|김밥\|국밥\|주점\|호프\|오뎅\|레스토랑\|횟집\|찜\|탕\|반찬\|베이커리\|제과\|떡\|도시락\|술집\|이자카야\|포차` | `common.py:171` |
| 전국 대표번호 | `^(15\|16\|18)\d{6}$` (숫자만) | `merge.py:108` |
| 휴대폰 | 숫자가 `01`로 시작 | `merge.py:134` |
| 거리 | `round(hypot((x2-x1)·cos(y1)·111320, (y2-y1)·110540))` | `compat.dist`, `common.dist_m` |

### 이름 비교 3종 (`legacy/common.py`)

```
_core(x)          = 공백·아파트·오피스텔·빌라·주택·'(…)' 제거
name_eq(a, b)     = len(_core)≥2 양쪽, 같거나 (짧은 쪽 ⊂ 긴 쪽 and 길이비 ≥ 0.7)          # 3순위, 114
exact_core_eq(a,b)= _core(strip_mg(a)) == _core(b), 길이 ≥ 2                           # 5순위
loose_eq(mg, b, words):                                                                 # 1순위
    x = strip_mg(mg) 에서 LOOSE_DROP(공백·아파트·오피스텔·빌라·주택·괄호·인천·주상복합·N차·N단지)와 words 제거
    y = b 에서 같은 것 제거
    return len≥2 양쪽 and any(x[i:i+2] in y)
words = region_words(구, 동): 구·동 이름에서 끝 '\d*(구|군|동|읍|면|리|가)' 뗀 2글자 이상 + 수집설정.toml extra_words
strip_mg(n) = n 에서 MG_RE 첫 위치부터 끝까지 삭제
bad_name(n) = 공백 뺀 길이<2 | '^[가-힣]+\d*(동|리|가)\s*\d' | '^(다세대|연립|도시형|아파트|주택|빌라|오피스텔|근린생활시설)\s*(\(.*\))?$' | '^(가|나|다|라|[A-Z]|\d+)동$' | '^[\d\-\s]+$'
clean_kb(n) = 끝 점 제거, '.(' → '(', 끝 '(도|고층|저층|신|구|숫자(-숫자)?)' 제거
```

실행 결과 (미추홀구 관교동, words = [미추홀, 관교]):

| 호출 | 결과 |
|---|---|
| `loose_eq('관교동부아파트 관리사무소', '동부아파트')` | True (`동부` vs `동부`) |
| `loose_eq('푸르지오1차 관리사무소', '주안푸르지오2단지')` | True |
| `loose_eq('관교프라자 관리단', '신비마을아파트')` | False |
| `name_eq('동부아파트', '동부')` | True |
| `name_eq('동부아파트 경비실', '동부아파트')` | False |
| `bad_name('관교동 13-11')`, `bad_name('다세대(316-6)')`, `bad_name('A동')` | True |
| `suspicious_name('약초동')` | True |
| `role('동부아파트', '부동산 > 주거시설 > 아파트')` | `(0, '공인중개사')` ← 문제 |

## 4. 예시 · 가짜 API 실행 결과

`tests/fakeapi.py`의 데이터로 `service.run_core`를 실제 실행한 값이다.

**건물 101** (`주승로 247` / `관교동 13-11`, nt=1, pt=1)
- P2: bnR=bnJ=`동부아파트`, g=(126.69, 37.44), R={`인천 미추홀구 주승로 247`}, J={`…관교동 13-11`, `…관교동 13-8`}.
- P3: 검색어 3개(`…주승로 247`, `…관교동 13-11`, `인천 미추홀구 관교동 13-8`). 받은 8건 → ID 중복 1 → 7곳. 그중 `아주먼곳`(주소 다름, 530m)은 버리고 `먼가게`(주소 다름, 88m)는 남김. 재검색 `동부아파트` → `동부아파트 경비실`(지번 13-8 → 주소 일치).
- P4: 11곳 중 전화 없는 2곳 제외 → 8곳 저장.
- P5: KB 단지 `동부`, 관리사무소 `032-421-3360`.
- P6: `동부아파트` (1순위). P7: `동부아파트 관리사무소 032-421-0000` (1순위, loose_eq). P8: 만들지 않음.

**101 변형** (관리사무소 장소와 KB 전화를 지움)
- P7: 결과 없음.
- P8 `st`: [`동부아파트 경비실`(role 0 ← 문제), `정석공인중개사사무소`(role 0)]. 음식점(role 3)은 3번째라 빠지고 편의점은 제외.
- `re`: [`중개1` 20m, `중개3` 0m(거리 빈칸), `중개4` 80m].

**건물 102**: 카카오 건물명 없음 → 집품 `호산빌라` → 재검색으로 `호산빌라`(빌라, 032-555-6666, 주소 일치)가 장소 풀에 들어옴 → P6 2순위(건물 장소)가 3순위(집품)보다 먼저 걸림 → P7 3순위 `032-555-6666`.

**건물 103**: 원래 이름 `신비마을아파트` → P7 1순위 `신비마을아파트 관리사무소`. `관교프라자 관리단`(63m, 이름 다름)은 네이버 위치 불일치로 보류 → 플래그 `관리사무소 후보 검수 필요`.

## 5. 재구현 시 지킬 것과 바꿀 것

지킬 것 (결과를 바꾸지 않으려면):
1. 같은 건물 판단은 정규화 주소의 **완전 일치**다. 부분 포함으로 바꾸면 이웃 번지(`13-1` ⊂ `13-11`)가 섞인다.
2. 수집 단계는 버리는 기준(주소 일치 또는 200m)을 판정보다 먼저 적용한다. 판정은 그 안에서만 고른다.
3. 대표번호는 후보를 전부 모은 뒤 순위로 고른다. 먼저 찾은 것을 바로 쓰지 않는다.
4. 보류(`held`)는 버리지 말고 검수 후보로 남긴다.
5. 응답이 비정상(401·403·429·리다이렉트·JSON 아님·구조 다름)이면 빈 결과로 처리하지 말고 멈춘다(`transport.interpret`). 과거에 요청 제한 응답을 빈 결과로 처리해 756건이 틀어진 적이 있다.

바꾸기를 권하는 것:
1. `role` 0순위를 `부동산중개` 분류(또는 AG2)로 좁힌다.
2. 중개업소 거리 빈칸을 0이 아닌 None으로 두거나 좌표로 다시 계산한다.
3. P4를 대표번호 판정 뒤로 옮기거나, 부동산 DB 조회로 바꾼다. 반경·개수는 설정값으로 둔다.
4. 정규화 규칙 네 벌(`nr/nj` ×2, `short_a+sq`, `k114R/J/S`)과 `is_mg` 두 벌을 하나로 합친다. 가능하면 건물관리번호(도로명주소 25자리)를 건물 키로 쓴다.
5. 장소 풀·중개업소 목록·원래 응답을 저장해, 규칙이 바뀌어도 다시 호출하지 않고 다시 판정할 수 있게 한다.
6. 판정 결과의 출처·사유를 문장 대신 코드(출처, 순위, 거리 숫자)로 저장한다.

## 6. 검증 방법

- `python -m unittest discover -s tests`: 40개 중 39개 통과. 실패 1개(`test_config_union_env_and_last_job`)는 `조회설정.toml` 예시 값을 용현동 시험용으로 바꿔서 생긴 것이다.
- `tests/test_flow.py`의 원본 JS 비교 시험은 Node가 있으면 원본 `collector.js`·`naver.js`와 요청·결과가 같은지 비교한다.
- 재구현 전에 실제 API로 작은 동 하나를 돌려 `results.json`을 정답으로 고정하고, 새 구현과 건물별 `nm`, `ph`, `held`, `st`, `re`를 비교한다.
