# 건물정보 수집기 · 상세 명세 (AI용)

> 대상: 이 로직을 재구현하거나 고치는 개발자의 AI 도우미.
> 기준: main `972ff81`. 줄 번호는 이 커밋 기준이다.
> 사람용 판: `설명서/수집기_상세_설명서.html`. 판정 규칙 전체(순위·단어 목록·이름 비교)는 `설명서/수집기_로직_설명서_AI용.md`, 파일 지도는 `docs/코드구조_설명서_AI용.md`.
> 5장의 추적은 `tests/fakeapi.py`의 가짜 응답으로 실제 코드를 실행해 기록한 것이다.

## 0. 핵심 사실 (자주 틀리는 것)

1. CSV의 `위도`·`경도`, `대표번호 유형`, `대표번호 장소명`, `연락처 수`, `연락처 전체` 열은 **읽지 않는다**. 필수 열은 `시군구, 법정동, 도로명주소, 지번주소, 건물명, 대표번호, 등급, 세대수, 호수, buildingRosterIdx`뿐이다(`pipeline/selection.py:21`). 좌표는 카카오 주소검색에서 받는다.
2. **주소 묶음(R·J)** 은 CSV 주소 + 카카오 **주소검색**(`address.json`) 첫 결과 1건씩의 공식 도로명·지번 + (판정 때) 네이버 지오코딩 주소다. 다른 장소들의 주소는 들어가지 않는다. CSV 주소가 출발점이라, 카카오가 다른 표기를 주지 않으면 R·J는 CSV 주소와 같다(가짜 데이터 5건 중 3건). 101은 다른 지번 `관교동 13-8`, 105는 CSV에 없던 도로명 `주승로 250`이 더해졌다.
3. **장소 풀**은 카카오 **키워드 검색**(`keyword.json`) 결과 중 "주소 일치 또는 건물 좌표에서 200m 이하"만 남긴 것이다. 반경 검색이 아니므로 "200m 안 모든 장소"가 아니다.
4. **건물 내 점포** = 장소 풀 중 주소 일치(`m=1`) 장소. 정규화 주소가 R 또는 J의 원소와 **완전히 같으면** 일치다. 부분 포함은 쓰지 않는다. 200m 이내 "근처 장소"(`m=0`)는 대리 연락처에 쓰지 않는다.
5. **중개업소 8곳**은 번호 대상(`대표번호`가 빈 값 또는 `없음`)이고 좌표가 있으면, 대표번호 판정 **전에** 카카오 단계에서 미리 수집한다. 입력에 대리 번호 열은 없고, 다른 연락처 열도 보지 않는다.
6. 중개업소 목록(`ag`, 분류검색 AG2)과 장소 풀(`P`, 키워드 검색)은 **별개 목록**이다. 건물 안 중개업소는 둘 다에 있을 수 있다. 8곳 한도는 `ag` 안에서만 센다. 최종 주변 부동산 3곳은 건물 내 점포로 뽑힌 **전화번호 숫자**와 같은 것을 건너뛴다.
7. KB·집품의 "이름이 없으면"은 **타겟 건물의 임시 건물명 `pn`이 없을 때**다. `pn` = CSV 원래 이름(이름 대상이면 '') → 카카오 공식 건물명(도로명→지번) → 장소 풀 주소 일치 건물 자체 장소 이름. KB는 이와 별개로 **번호 대상이면 항상** 조회한다.
8. KB·집품으로 새 이름 `nn`이 생기고 번호 대상이며 좌표가 있으면, 카카오를 **새로 검색**(`{nn}`, `{nn} 관리사무소`, 반경 1km)해 장소 풀에 추가한다. 기존 풀만 뒤지지 않는다.
9. 대표번호 판정의 이름 비교에는 `nn`이 아니라 **최종 건물명**(P6 결과, 없으면 CSV 원래 이름)을 쓴다. P6 순서는 카카오 공식 건물명 → 카카오 건물 자체 장소 → 집품 → KB라서, 새 이름 재검색으로 들어온 카카오 장소 이름이 집품 이름보다 먼저 쓰일 수 있다.

## 1. 대상 유형별 실행 표

`nt` = 이름 대상(`건물명`이 `(건물명없음)`으로 시작), `pt` = 번호 대상. 둘 다 0이면 조회하지 않는다.

| 단계 | nt만 | pt만 | 둘 다 | 추가 조건 | 위치 |
|---|---|---|---|---|---|
| 카카오 주소검색 | O | O | O | 도로명·지번 중 있는 것만 | `kakao.py:112-113` |
| 주소로 장소검색 | O | O | O | - | `kakao.py:155-167` |
| 이름으로 재검색 | - | O | O | `pn` 있음, `len(core(pn))>=2` | `kakao.py:179-184` |
| 중개업소 AG2 300m | - | O | O | 좌표 있음 | `kakao.py:187-189` |
| KB부동산 | `pn` 없을 때 | O | O | 1단계 성공 | `secondary.py:54` |
| 집품 | `pn` 없을 때 | - | `pn` 없을 때 | 1단계 성공 | `secondary.py:72` |
| 새 이름 재검색 | - | - | `nn` 있을 때 | 좌표 있음 | `secondary.py:102` |
| 건물명 결정 | O | - | O | - | `merge.py:38` |
| 대표번호 결정 | - | O | O | - | `merge.py:224-227` |
| 대리 연락처 | - | 대표번호 없을 때 | 대표번호 없을 때 | - | `merge.py:230` |
| 네이버 지오코딩 | 이름 못 찾음 | `ph0` 없음 | 둘 중 하나 | `skip_geo` 아님, 미조회 | `merge.py:243` |
| 네이버 지역검색 | - | 보류된 이름 다른 100m 안 관리사무소 | 〃 | - | `merge.py:77-84` |
| 114On | - | `ph0` 없음 | 〃 | `run114`; `no_proxy`면 대리도 없을 때 | `merge.py:245-246` |

`ph0` = 114On 후보를 빼고 한 대표번호 판정 결과(`merge.py:225`).

## 2. 카카오 API 3종

| | 주소검색 `address.json` | 키워드 검색 `keyword.json` | 분류검색 `category.json` |
|---|---|---|---|
| 성격 | 주소 사전 (주소 자체 정보) | 글자 관련 장소 목록 | 좌표 반경 안 분류별 장소 |
| 요청 | `?query=인천광역시 {구} {짧은 주소}` | 주소: `?query={주소}&page={1..3}&size=15` / 이름: `?query={이름}&page=1&size=15&x=&y=&radius=1000` | `?category_group_code=AG2&x=&y=&radius=300&sort=distance` |
| 쓰는 건수 | `documents[0]`만 | 페이지마다 15, `meta.is_end`면 중단 | 첫 응답 전체(최대 15) |
| 쓰는 항목 | `x`, `y`, `road_address.address_name`, `road_address.building_name`, `address.address_name` | `id`, `place_name`, `category_name`, `phone`, `place_url`, `x`, `y`, `road_address_name`, `address_name` | `place_name`, `phone`, `distance`, `place_url` |
| 결과물 | `g`, `bnR`, `bnJ`, `R`, `J` | 장소 풀 `P` | 중개업소 `ag` |

공통: 헤더 `Authorization: KakaoAK {KAKAO_REST_KEY}`. 5xx·네트워크 오류는 `0.6·2^n`초 대기로 최대 6회 시도, 401·403·429·3xx·JSON 아님은 즉시 중단(`transport.interpret`). 응답에 `documents` 목록이 없으면 중단.

## 3. 단계별 데이터

### S1 입력 (`prepare.py`, `common.py:32-51`)

```
row → nt, pt
road  = road_from_src(도로명주소)   # '^\(건물명없음\)\s*' 제거, 끝 '\s*\([^)]*\)\s*$' 제거
jibun = jibun_from_src(지번주소)    # '블록' 포함 → ''; '(\d+)\s*번지\s*(\d+)\s*호'→'\1-\2'; '번지' 제거; 끝이 '\d+(-\d+)?'가 아니면 ''
short_road, short_jib = short_addr(road), short_addr(jibun)    # '^인천(광역시)?\s*[가-힣]+(구|군)\s*' 제거
b = [idx, short_road, short_jib, n0 = ('' if nt else 건물명), nt, pt]
```

### S2 카카오 주소검색 (`kakao.py:105-134`)

```
P = '인천광역시 ' + 구 + ' '
road_q, jib_q = P+short_road (or ''), P+short_jib (or '')
ad_r, ad_j = address(road_q), address(jib_q)
first = ad_r[0] or ad_j[0];  g = (first.x, first.y) or None
bnR = ad_r[0].road_address.building_name;  bnJ = ad_j[0].road_address.building_name
R = {nr(road_q)} ∪ {nr(d.road_address.address_name) | d ∈ {ad_r[0], ad_j[0]}, d.road_address}
J = {nj(jib_q)}  ∪ {nj(d.address.address_name)      | d ∈ {ad_r[0], ad_j[0]}, d.address}
```

정규화(`kakao.py:20-40` = `common.py:53-66`):
- `nr`: `인천광역시`→`인천`(1회), `\s*\([^)]*\)`→공백, 쉼표 앞만, 공백 축약, trim.
- `nj`: `nr`의 앞 두 단계 + `(\d+)\s*번지\s*(\d+)\s*호`→`\1-\2`(1회), `번지` 삭제, 끝 `(\d+)\s*호` 삭제, `([가-힣]+?)\d+동`→`\1동`, 공백 축약, trim.
- 같다고 보는 예: `…주승로 247, 2층`, `…주승로 247 (관교동)`, `…관교동 13번지 11호`, `…관교동 13-11 101호`, `…관교1동 13-11`.
- 다르다고 보는 예: `…관교동 13-1`, `…주승로 247-1`, `…주승로247`(띄어쓰기 차이, 한계).

### S3 장소 풀 (`kakao.py:144-185`)

```
def add(docs, src):
    for d in docs:
        if d.id in P: continue
        m  = nr(d.road_address_name) in R or nj(d.address_name) in J
        dd = dist(g, d.xy) if g else None
        if not m and not (dd is not None and dd <= 200): continue
        P[d.id] = [id, place_name, category_name, phone, place_url, fixed6(x), fixed6(y),
                   road_address_name, address_name, 1 if m else 0, dd, src]

qs = [road_q, jib_q] + [d.address.address_name for d in (ad_r[0], ad_j[0])
                        if d and d.address and nj(d.address.address_name) != nj(jib_q)]
for q in unique(qs): add(keyword(q, pages≤3), 'a')                  # 최대 4개 검색어
if g is None: g = first(p.xy for p in P if p.m)                       # 좌표 대체
pn = n0 or bnR or bnJ or first(p.name for p in P if p.m and is_bldg(p.cat, p.name))
if pt and pn and len(core(pn)) >= 2:
    rad = 1000 if g else None
    add(keyword(pn, g, rad, 1 page) + keyword(pn+' 관리사무소', g, rad, 1 page), 'rs')
```

- `P`는 `JSObj`라 숫자 모양 ID가 오름차순으로 먼저 온다. 판정의 "첫 장소"는 이 순서.
- `is_bldg` = 분류가 `부동산`으로 시작, `부동산서비스|중개|고시원|고시텔|원룸|하숙|셰어|쉐어|숙박` 없음, 관리사무소 아님(카카오 단계용 `is_mg`).

### S4 중개업소 (`kakao.py:186-189`)

```
ag = []
if pt and g:
    docs = [d for d in category('AG2', g, 300) if d.phone][:8]
    ag = [[d.place_name, d.phone, to_num(d.distance), d.place_url] for d in docs]
```

- 정렬은 카카오의 `sort=distance` 순서를 그대로 쓴다.
- `to_num('') == 0` → 거리 빈칸이 0m로 저장된다(알려진 문제).

### S5 KB·집품 (`secondary.py:47-107`)

```
short_a(s) = trim(s 에서 '^인천(광역시)?\s*[가-힣]+(구|군)\s*', 끝 '\s*\(…', 끝 '번지…' 제거)
sq(s) = 공백 전부 제거
if pt or (nt and not pn):
    m = first(x ∈ kb.search(short_jib)          if match(x))         # 'intgraSerch?검색설정명=SRC_NTOTAL&검색키워드=관교동 13-11&출력갯수=10&페이지설정값=1'
    m = m or first(x ∈ kb.search(구+' '+short_road) if match(x))      # '미추홀구 주승로 247'
    # match(x): sq(short_a(x.JUSO_ARNO)) == sq(short_jib) or sq(short_a(x.NEWADDRESS)) == sq(short_road); 목록은 HSCM·VILLA만
    if m and m.COMPLEX_NO: mm = kb.complex_main(m.COMPLEX_NO)       # 'complexMain?단지기본일련번호=7123'
        kb = {no, t, nm: HSCM_NM, addr, road, main_nm: mm.단지명, tel: mm.관리사무소전화번호내용, hh: mm.총세대수}
if nt and not pn:
    z = zippoom.search('인천광역시 '+구+' '+(short_road or short_jib))   # autoComplete?keyword=...
    zm = first(x ∈ z if sq(short_a(x.address))==sq(short_road) or sq(short_a(x.oldAddress))==sq(short_jib))
    zp = {id, nm: zm.buildingName, type, generic: not nm or nm ~ '^[가-힣]+[0-9]*(동|리|가)\s*[0-9]'}
nn = '' if pn else (zp.nm if usable(zp) else clean_kb(kb.main_nm or kb.nm) if usable)
if nn and pt and len(core(nn)) >= 2 and g:
    P += research(nn)    # keyword(nn) + keyword(nn+' 관리사무소'), 반경 1000, 1페이지, add()와 같은 거름, src='rs2'
```

- 요청 사이 0.35초, 재시도 없음, 오류 뒤 3초 대기. 헤더 없음(KB·집품).

### S6 판정 (`legacy/merge.py`)

```
pl = places_of(A.P + B.P)                      # ID 중복 제거
R, J += 네이버 지오코딩 주소(끝 건물명 제거 후 nr/nj)
for p in pl: p.m = nr(p.road) in R or nj(p.jib) in J
matched = [p for p in pl if p.m]
nm   = decide_name(...)   if nt                 # bnR|bnJ → matched 건물 자체 장소 → zp → kb
name = nm.v if nm else n0
ph0  = decide_phone(..., use114=False) if pt
ph   = decide_phone(..., use114=True)  if pt
st, re_ = proxies(matched, C, A) if pt and not ph
```

`proxies`:

```
pool = []
for p in matched (+ C.pool):
    skip if no phone, EXCL.search(category+' '+name), is_mg(name), digits(phone) seen
    pool += (role_rank(name, category), mobile=digits.startswith('01'), p)
st = sorted(pool, key=(role_rank, mobile))[:2]          # 안정 정렬
used = digits of st
re_ = [a for a in A.ag if digits(a.phone) not in used (and not repeated)][:3]
```

`role_rank`(1부터): 1 `공인중개|부동산중개|부동산` · 2 `헬스|피트니스|필라테스|요가|노래|코인노래|PC방|피씨방|당구|스크린골프` · 3 `병원|의원|치과|한의원|약국|학원|교습|어학|공부방|교육` · 4 식당 단어 목록 · 5 기타. 1번의 `부동산`이 카카오 분류 `부동산 > 주거시설 > …`(아파트·오피스텔·경비실)에도 걸리는 문제가 있다.

대표번호 6순위 상세는 `설명서/수집기_로직_설명서_AI용.md` P7 참고.

## 4. 결과 한 건 (`results.json`)의 주요 필드

| 필드 | 뜻 |
|---|---|
| `nm` | `{v, src, st, link}` 건물명 결정 결과 (이름 대상만) |
| `ph` | `{v, name, link, src}` 대표번호 (번호 대상만) |
| `held` | 보류 후보 `[{v, name, link, reason, d}]` |
| `st` | 건물 내 점포 `[{n, p, c, role, pr, src, link, mob}]` 최대 2 |
| `re` | 주변 부동산 `[{n, p, d, link}]` 최대 3 |
| `K` | 주소 일치 장소 전체 `[[이름, 분류, 전화, 링크]]` (엑셀 근거 시트) |
| `flags`, `human` | 검수 사유, 사람 확인 필요 여부 |

## 5. 실행 추적 (가짜 API)

### 건물 101 · nt=1, pt=1, `주승로 247 / 관교동 13-11`

요청 순서:

```
address  인천광역시 미추홀구 주승로 247
address  인천광역시 미추홀구 관교동 13-11
keyword  인천광역시 미추홀구 주승로 247 (p1)
keyword  인천광역시 미추홀구 관교동 13-11 (p1)
keyword  인천 미추홀구 관교동 13-8 (p1)                      # 지번 주소검색이 돌려준 다른 지번
keyword  동부아파트 (x=126.69, y=37.44, r=1000, p1)
keyword  동부아파트 관리사무소 (r=1000, p1)
category AG2 (x=126.69, y=37.44, r=300, sort=distance)
KB       intgraSerch 검색키워드=관교동 13-11                   # pn 있음, pt라서 KB 조회
KB       complexMain 단지기본일련번호=7123
(집품 없음: pn='동부아파트')
```

S2 결과: `g=[126.69, 37.44]`, `bnR=bnJ='동부아파트'`, `R=['인천 미추홀구 주승로 247']`, `J=['인천 미추홀구 관교동 13-11', '인천 미추홀구 관교동 13-8']`.

장소 판단:

| 장소 | 분류 | 전화 | nr∈R | nj∈J | d | 결과 |
|---|---|---|---|---|---|---|
| 동부아파트 관리사무소 | 부동산>주거시설>아파트>관리사무소 | 032-421-0000 | T | T | 2 | m=1 |
| 동부아파트 | 부동산>주거시설>아파트 | - | T | T | 0 | m=1 |
| 정석공인중개사사무소 | …>부동산중개>공인중개사사무소 | 032-875-6060 | T | T | 18 | m=1 |
| (음식점) | 음식점>한식 | 032-111-2222 | T | T | 11 | m=1 |
| 세븐일레븐 관교점 | 가정,생활>편의점 | 032-123-4567 | T | T | 0 | m=1 |
| 동부아파트 경비실 (rs) | 부동산>주거시설>아파트 | 032-421-9999 | T | T(13-8) | 14 | m=1 |
| 먼가게 | 음식점>분식 | 010-1234-5678 | F | F | 88 | m=0, 근처 |
| 아주먼곳 | 음식점 | 032-000-1111 | F | F | 530 | 버림 |

`ag`: 응답 11곳 → 전화 없는 2곳 제외 → 8곳 `[중개1 20, 중개3 0(빈칸), 중개4 80, 중개6 120, 중개7 140, 중개8 160, 중개9 180, 중개10 200]`.
KB: `{no: 7123, main_nm: '동부', tel: '032-421-3360'}`.
판정: `nm='동부아파트'`(1순위), `ph='032-421-0000'`(1순위, `loose_eq` '동부'='동부'), KB 전화는 4순위로 밀림, 대리 연락처 없음.

변형(관리사무소 장소와 KB 전화 제거): `ph=None` → `st=[동부아파트 경비실(rank1, 문제), 정석공인중개사사무소(rank1)]`(음식점 rank4는 3번째라 빠짐, 편의점 제외, 먼가게는 m=0이라 대상 아님) → `re=[중개1 20, 중개3 0, 중개4 80]`.

### 건물 102 · nt=1, pt=1, `인하로411번길 49 / 관교동 316-6`

```
address ×2 → building_name 없음
keyword ×2 → 0건 → P 비어 있음 → pn=''
(이름 재검색 없음)
category AG2 → 0곳
KB intgraSerch 관교동 316-6 → VILLA '다세대(316-6)' 주소 일치 → complexMain V1 → 단지명 '호산빌라.', tel ''
집품 autoComplete '인천광역시 미추홀구 인하로411번길 49' → '호산빌라'(빌라) 주소 일치, generic=False
nn = '호산빌라' (집품 우선)
keyword '호산빌라' r=1000, '호산빌라 관리사무소' r=1000 → 호산빌라 · 부동산>주거시설>빌라 · 032-555-6666 · m=1 → P에 추가(rs2)
판정: nm='호산빌라' (2순위 카카오 건물 자체 장소가 3순위 집품보다 먼저), ph='032-555-6666' (3순위 이름 같은 장소)
```

### 건물 103 · nt=0, pt=1, 원래 이름 `신비마을아파트`, `경원대로 627 / 관교동 500`

```
address 도로명 → 결과 없음; address 지번 → road_address None → R·J = 원본만
keyword 경원대로 627 p1, p2 / 관교동 500 p1
  → 관교프라자 관리단 d=63, 신비마을아파트 관리사무소 d=11, 신비학원 d=9 (모두 m=1)
keyword 신비마을아파트 r=1000, 신비마을아파트 관리사무소 r=1000   # pn = n0
category AG2 → 관교메트로부동산 130, 정석공인중개사사무소 140
KB 관교동 500 → 0건 → 미추홀구 경원대로 627 → 0건; 집품 없음(nt=0)
판정: ph = 신비마을아파트 관리사무소 032-777-8888 (1순위)
      관교프라자 관리단: 이름 다름, KB 아님, d≤100 → 네이버 확인 → 위치 불일치 → held
      flags = ['관리사무소 후보 검수 필요']
```

## 6. 재구현 시 결정해야 할 것

- CSV `위도`·`경도`를 신뢰할 수 있으면 좌표 대체·검증에 쓴다(공식 건물명·주소 묶음 때문에 주소검색은 남는다).
- 주변 중개업소 수집을 대표번호 판정 뒤로 옮기거나 부동산 DB 조회로 바꾼다.
- 건물 키를 건물관리번호(도로명주소 25자리)로 바꾸면 R·J 글자 비교와 정규화 규칙 네 벌이 필요 없어진다.
- `role` 1순위를 `부동산중개` 분류(또는 AG2)로 좁히고, 중개업소 거리 빈칸을 0 대신 None으로 둔다.
- 장소 풀·`ag`·원래 응답을 저장해 규칙이 바뀌어도 재호출 없이 다시 판정할 수 있게 한다.

## 7. 확인 방법

- 추적 재현: `tests/fakeapi.py`의 `FakeTransport`로 `pipeline.providers.kakao.proc_a`, `pipeline.secondary.proc_b`를 직접 호출하면 위 요청 목록과 `A`·`B` 값을 얻는다. 전체 판정은 `service.run_core([sample CSV], transport=FakeTransport())` 후 `work/jobs/*/data/*/results.json`.
- 단위·흐름 시험: `python -m unittest discover -s tests` (40개 중 39개 통과, 실패 1개는 `조회설정.toml` 예시 값 변경 때문).
- 실제 API: 아직 미실행. 환경 네트워크 정책에서 `dapi.kakao.com`, `maps.apigw.ntruss.com`, `naverapihub.apigw.ntruss.com`, `api.kbland.kr`, `live.zippo-om.com`(, `www.114.co.kr`)를 허용해야 한다.
