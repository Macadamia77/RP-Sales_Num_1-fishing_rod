# 공통 규칙 · 인천 콜리스트 건물명·대표번호 공백 채우기
# 주소 정리, 이름 비교, 관리사무소 판정, 대리 연락처 분류, 시설 건물 판정, 정렬 규칙을 한곳에 모음
# 규칙을 바꿀 때는 이 파일만 고치고, 인수인계 문서도 함께 고칠 것
import json, math, os, re

from ..settings import current as settings

SIDO = '인천광역시'
GRADE_ORDER = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}

# ---------- 파일 ----------
def load(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save(path, obj):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)

def s(v):
    if v is None: return ''
    if isinstance(v, float) and math.isnan(v): return ''
    t = str(v).strip()
    return '' if t.lower() == 'nan' else t

# ---------- 주소 ----------
GU_RE = r'인천(?:광역시)?\s*[가-힣]+(?:구|군)\s*'

def road_from_src(v):
    """원본 도로명주소 → '인천광역시 미추홀구 염전로168번길 14'. 앞의 (건물명없음)과 뒤의 (동) 표시 제거"""
    t = s(v)
    t = re.sub(r'^\(건물명없음\)\s*', '', t)
    t = re.sub(r'\s*\([^)]*\)\s*$', '', t).strip()
    return t

def jibun_from_src(v):
    """원본 지번주소 → '인천광역시 미추홀구 도화동 985-2'. 번지 글자 제거. 번지 숫자가 없으면 빈 값"""
    t = s(v)
    if not t or '블록' in t: return ''
    t = re.sub(r'(\d+)\s*번지\s*(\d+)\s*호', r'\1-\2', t)
    t = t.replace('번지', '').strip()
    t = re.sub(r'\s+', ' ', t)
    if not re.search(r'\d+(?:-\d+)?\s*$', t): return ''
    return t

def short_addr(full):
    """'인천광역시 미추홀구 염전로168번길 14' → '염전로168번길 14'"""
    return re.sub('^' + GU_RE, '', s(full)).strip()

def nr(v):
    """비교용 도로명 키. 카카오 코드의 nr과 같은 규칙"""
    t = s(v).replace('인천광역시', '인천')
    t = re.sub(r'\s*\([^)]*\)', ' ', t).split(',')[0]
    return re.sub(r'\s+', ' ', t).strip()

def nj(v):
    """비교용 지번 키. 카카오 코드의 nj와 같은 규칙. 행정동 번호 제거"""
    t = s(v).replace('인천광역시', '인천')
    t = re.sub(r'\s*\([^)]*\)', ' ', t)
    t = re.sub(r'(\d+)\s*번지\s*(\d+)\s*호', r'\1-\2', t).replace('번지', '')
    t = re.sub(r'(\d+)\s*호\s*$', '', t)
    t = re.sub(r'([가-힣]+?)\d+동', r'\1동', t)
    return re.sub(r'\s+', ' ', t).strip()

def dist_m(x1, y1, x2, y2):
    try:
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
    except (TypeError, ValueError):
        return None
    return round(math.hypot((x2 - x1) * math.cos(math.radians(y1)) * 111320, (y2 - y1) * 110540))

# ---------- 이름 ----------
MG_RE = r'관리사무소|관리사무실|관리실|관리단|관리소|관리센터|입주자대표회의'
# 관리사무소처럼 보이는 이름이라도 전기차 충전소 등은 관리사무소가 아님 (예: 입주자대표회의 전기차충전소 1833-xxxx)
NON_OFFICE = r'전기차|충전소|충전기'

def is_mg(n): return bool(re.search(MG_RE, s(n))) and not re.search(NON_OFFICE, s(n))

def strip_mg(n):
    """관리사무소 이름에서 관리사무소, 관리실, 관리단, 관리소, 관리센터, 입주자대표회의 이후를 떼어 냄"""
    return re.sub(r'\s*(' + MG_RE + r').*$', '', s(n)).strip()

def _core(x):
    return re.sub(r'\s+|아파트|오피스텔|빌라|주택|\(.*?\)', '', s(x))

def name_eq(a, b):
    """기존 이름 비교. 공백·아파트·오피스텔·빌라·주택·괄호 제거 후, 같거나 한쪽이 다른 쪽에 들어 있고 길이 비율 0.7 이상"""
    x, y = _core(a), _core(b)
    if len(x) < 2 or len(y) < 2: return False
    if x == y: return True
    sh, lo = (x, y) if len(x) < len(y) else (y, x)
    return sh in lo and len(sh) / len(lo) >= 0.7

LOOSE_DROP = r'\s+|아파트|오피스텔|빌라|주택|\(.*?\)|인천|주상복합|\d+차|\d+단지'

# 동별로 더하는 지역어. 원래는 region_words 안에 「주안동이면 관교」로 적혀 있던 것
# 수집설정.toml [region.extra_words] 에서 읽는다. 항목이 없으면 기본값(주안동 → 관교)
def _extra_words(gu, dong):
    extra = settings().extra_words
    return extra.get(f'{s(gu)} {s(dong)}', []) + extra.get(s(dong), [])

def region_words(gu, dong):
    """지역명 목록. '미추홀구' → '미추홀', '주안동' → '주안', '강화읍 관청리' → '강화', '관청'. 동별로 더하는 지역어(_extra_words)도 넣음"""
    out = set()
    for w in re.split(r'\s+', s(gu) + ' ' + s(dong)):
        w = re.sub(r'\d*(구|군|동|읍|면|리|가)$', '', w)
        if len(w) >= 2: out.add(w)
    for w in _extra_words(gu, dong): out.add(w)
    return sorted(out, key=len, reverse=True)

def _loose(x, words=()):
    t = re.sub(LOOSE_DROP, '', s(x))
    for w in words: t = t.replace(w, '')
    return t

def loose_eq(mg_name, bld_name, words=()):
    """새 규칙 3. 관리사무소 이름을 stripMg 한 뒤, 지역명·차수·흔한 단어까지 지우고 두 글자 이상 겹치면 같은 건물"""
    x, y = _loose(strip_mg(mg_name), words), _loose(bld_name, words)
    if len(x) < 2 or len(y) < 2: return False
    return any(x[i:i + 2] in y for i in range(len(x) - 1))

def exact_core_eq(a, b):
    """새 규칙 2. 주소가 달라도 인정하려면 이름이 완전히 같아야 함"""
    x, y = _core(strip_mg(a)), _core(b)
    return len(x) >= 2 and x == y

OTHER_FACILITY_MG = r'지하상가|지하도상가|시장|주차장|상가번영회|상인회'

def is_bldg_place(cat, name):
    """2순위 건물명 후보: 분류가 부동산으로 시작하는 건물 자체 장소"""
    c = s(cat)
    return c.startswith('부동산') and not re.search(r'부동산서비스|중개|고시원|고시텔|원룸|하숙|셰어|쉐어|숙박', c) and not is_mg(name)

REP_EXCL = r'고시원|고시텔|원룸|숙박'

def clean_kb(n):
    n = re.sub(r'\.+$', '', s(n))
    n = re.sub(r'\.\(', '(', n)
    n = re.sub(r'\((도|고층|저층|신|구|\d+(-\d+)?)\)\s*$', '', n).strip()
    return re.sub(r'\.+$', '', n).strip()

def bad_name(n):
    """건물명으로 쓰지 않는 값"""
    t = s(n)
    if len(re.sub(r'\s+', '', t)) < 2: return True
    if re.match(r'^[가-힣]+\d*(동|리|가)\s*\d', t): return True
    if re.match(r'^(다세대|연립|도시형|아파트|주택|빌라|오피스텔|근린생활시설)\s*(\(.*\))?$', t): return True
    if re.match(r'^(가|나|다|라|[A-Z]|\d+)동$', t): return True
    if re.match(r'^[\d\-\s]+$', t): return True
    return False

def suspicious_name(n):
    """약초동처럼 동네 이름 형태로 끝나는 건물명. 가동, 1동, A동 같은 동 표시는 제외"""
    t = s(n)
    return bool(re.search(r'[가-힣]동$', t)) and not re.search(r'(\d|[A-Za-z]|[가나다라마바사아자차카타파하]|제\d*)동$', t)

# ---------- 대리 연락처 ----------
EXCL = re.compile(r'전기차|충전소|편의점|카페|커피|GS25|CU |^CU|세븐일레븐|이마트24|미니스톱|스타벅스|이디야|메가MGC|빽다방|투썸|컴포즈')

def role(name, cat):
    t = s(cat) + ' ' + s(name)
    if re.search(r'공인중개|부동산중개|부동산', t): return 0, '공인중개사'
    if re.search(r'헬스|피트니스|필라테스|요가|노래|코인노래|PC방|피씨방|당구|스크린골프', t): return 1, '헬스장·노래방·PC방'
    if re.search(r'병원|의원|치과|한의원|약국|학원|교습|어학|공부방|교육', t): return 2, '병원·약국·학원'
    if re.search(r'음식|식당|한식|중식|일식|양식|분식|치킨|피자|고기|족발|보쌈|김밥|국밥|주점|호프|오뎅|레스토랑|횟집|찜|탕|반찬|베이커리|제과|떡|도시락|술집|이자카야|포차', t): return 3, '식당'
    return 4, '기타 점포'

def digits(p): return re.sub(r'\D', '', s(p))

# ---------- 시설 건물 ----------
FAC_RULES = [
    ('유치원·어린이집', r'유아교육|어린이집', r'유치원$|어린이집$'),
    ('학교', r'교육,학문 > 학교', r'(초등|중|고등|대)학교$'),
    ('병원·의원', r'의료,건강 > (병원|의원)', r'병원$|의원$'),
    ('요양·복지시설', r'요양|사회복지|노인복지', r'요양원$|요양병원$|복지관$|경로당$'),
    ('은행', r'금융기관|은행', r'은행$|은행\s*\S*지점$'),
    ('숙박시설', r'^여행 > 숙박', r'모텔$|호텔$|여관$'),
    ('시장', r'> 시장', r'시장$'),
    ('종교시설', r'종교', r'교회$|성당$|사찰$'),
    ('공공기관', r'공공,사회기관|행정기관', r'주민센터$|우체국$|경찰서$|지구대$|소방서$'),
    ('공장·창고', r'공장|창고', r'(?<!아파트형)공장$|창고$'),
    ('주유소', r'주유소', r'주유소$'),
]

def facility(name, places, hh, ho):
    """places: 주소 일치 카카오 장소 dict 목록"""
    name = s(name)
    extra = ' · 세대수 0, 호수 0' if (s(hh) in ('0', '') and s(ho) in ('0', '')) else ''
    for p in places or []:
        if not name or not name_eq(p.get('n'), name): continue
        for lab, rc, _ in FAC_RULES:
            if re.search(rc, s(p.get('c'))):
                return lab, f"카카오맵 장소 {p.get('n')} · {p.get('c')}{extra}", p.get('u', '')
    for lab, _, rn in FAC_RULES:
        if name and re.search(rn, name):
            return lab, f'건물명에 시설 이름이 들어감{extra}', ''
    return '', '', ''

# ---------- 정렬 ----------
def sort_key(row):
    """HTML 목록 정렬 규칙. 사람 확인 필요 먼저, 그다음 등급 S A B C D, 등급 없음 맨 끝, 같은 등급은 idx 순"""
    return (0 if row.get('human') else 1, GRADE_ORDER.get(s(row.get('grade')).upper(), 9), int(row.get('i', 0)))
