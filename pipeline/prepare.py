"""조회 대상 정하기

  nt · 이름 조회 대상 · 원본 건물명이 「(건물명없음)」으로 시작
  pt · 번호 조회 대상 · 원본 대표번호가 빈 값이거나 「없음」
  둘 중 하나라도 해당하면 조회 대상. 둘 다 해당하면 이름과 번호를 모두 찾는다

(시군구, 법정동)별로 묶어 작업 폴더에 input.json(판정기 입력)과 source.csv(선택된 원본 행)를 쓴다.
주소 정리 규칙은 judge/common.py 를 그대로 쓴다.
"""
import os

from .judge.common import jibun_from_src, road_from_src, s, short_addr
from .storage import write_json


def flags(df):
    nt = df['건물명'].astype(str).str.startswith('(건물명없음)')
    ph = df['대표번호'].map(s)
    pt = (ph == '') | (ph == '없음')
    return nt, pt


def groups(df):
    """{(구, 동): 조회 대상 행 DataFrame}. 대상이 없는 동은 빠짐"""
    nt, pt = flags(df)
    df = df.assign(_nt=nt, _pt=pt)
    df = df[df['_nt'] | df['_pt']]
    out = {}
    for (gu, dong), part in df.groupby(['시군구', '법정동'], sort=True):
        out[(gu, dong)] = part
    return out


def input_rows(part):
    rows = []
    for _, r in part.iterrows():
        a, b = bool(r['_nt']), bool(r['_pt'])
        rows.append({
            'i': int(r['buildingRosterIdx']), 'gu': s(r['시군구']), 'dong': s(r['법정동']),
            'road': road_from_src(r['도로명주소']), 'jibun': jibun_from_src(r['지번주소']),
            'n0': '' if a else s(r['건물명']), 'nt': int(a), 'pt': int(b), 'grade': s(r['등급']),
            'hh': s(r['세대수']), 'ho': s(r['호수']),
        })
    return rows


def compact(rows):
    """조회 모듈 입력 · [i, 짧은 도로명, 짧은 지번, 원래 건물명, nt, pt]"""
    return [[x['i'], short_addr(x['road']), short_addr(x['jibun']), x['n0'], x['nt'], x['pt']] for x in rows]


def write_group(group_dir, part):
    """input.json 과 source.csv 를 쓴다. 원본 열만, 원래 순서대로"""
    os.makedirs(group_dir, exist_ok=True)
    rows = input_rows(part)
    write_json(os.path.join(group_dir, 'input.json'), rows)
    cols = [c for c in part.columns if not c.startswith('_')]
    tmp = os.path.join(group_dir, 'source.csv.tmp')
    part[cols].to_csv(tmp, index=False, encoding='utf-8-sig')
    os.replace(tmp, os.path.join(group_dir, 'source.csv'))
    return rows


def group_name(gu, dong):
    return f'{gu}_{dong}'
