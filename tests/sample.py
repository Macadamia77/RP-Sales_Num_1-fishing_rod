"""테스트용 콜리스트 CSV · 실제 콜리스트와 같은 28열 형식 (값은 합성)"""
import csv

COLS = ['등급', '총점', '단계', '유형', '연차', '세그먼트', '게이트', '구분', '건물명', '시도', '시군구', '법정동', '도로명주소', '지번주소',
        '위도', '경도', '세대수', '호수', '세대+호', '사용승인일', '기 관리단', '연락처 수', '대표번호', '대표번호 유형', '대표번호 장소명',
        '연락처 전체', '수신거부 수', 'buildingRosterIdx']


def row(idx, gu, dong, road, jib, name='', phone='', grade='C'):
    r = {c: '' for c in COLS}
    r.update({'등급': grade, '총점': '120', '단계': '잠정', '구분': '아파트', '시도': '인천광역시', '시군구': gu, '법정동': dong,
              '건물명': name or f'(건물명없음) 인천광역시 {gu} {jib}번지',
              '도로명주소': (f'인천광역시 {gu} {road} ({dong})' if road else ''), '지번주소': f'인천광역시 {gu} {jib}번지',
              '세대수': '8', '호수': '0', '세대+호': '8', '연락처 수': '0', '대표번호': phone, '수신거부 수': '0', 'buildingRosterIdx': str(idx)})
    return r


ROWS = [
    row(101, '미추홀구', '관교동', '주승로 247', '관교동 13-11', grade='B'),
    row(102, '미추홀구', '관교동', '인하로411번길 49', '관교동 316-6'),
    row(103, '미추홀구', '관교동', '경원대로 627', '관교동 500', name='신비마을아파트', grade='B'),
    row(104, '미추홀구', '관교동', '경원대로640번길 6-39', '관교동 505-8', phone='032-000-0000', grade='D'),
    row(105, '미추홀구', '관교동', '', '관교동 12-3', grade='A'),
    row(106, '미추홀구', '관교동', '주승로 1', '관교동 1', name='기존빌딩', phone='032-111-1111', grade='S'),
    row(201, '미추홀구', '학익동', '학익로 10', '학익동 100', name='학익빌라', grade='C'),
]
ROWS_JUNG = [row(301, '중구', '운서동', '영종대로 178', '운서동 3087-7', name='영종빌라', grade='A')]


def write(path, rows=ROWS, encoding='utf-8-sig'):
    with open(path, 'w', encoding=encoding, newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path
