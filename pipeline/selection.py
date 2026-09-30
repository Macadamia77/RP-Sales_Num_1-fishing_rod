"""CSV 읽기와 조회 범위 선택

  · --src 는 여러 개, *.csv 패턴 가능. UTF-8로 읽다가 실패하면 CP949로 다시 읽는다
  · 필수 열, buildingRosterIdx 형식·중복, 시도(수집설정.toml, 기본 인천광역시) 주소 여부를 검사한다
  · 필터: 같은 옵션 안의 여러 값은 OR, 서로 다른 옵션끼리는 AND
      --gu 중구 연수구 --rank S A  →  (중구 또는 연수구) 이면서 (S 또는 A)
  · 조회 묶음(FilterSet)을 여러 개 주면 합집합. 설정 파일의 [[조회]] 블록마다 하나
  · 값은 글자가 정확히 같아야 한다. CSV에 없는 값은 오타로 보고 실패하며, 비슷한 값을 추천한다
"""
import difflib
import glob
import os
import re
from dataclasses import dataclass, field

import pandas as pd

from .errors import UsageError
from .settings import current as settings

REQUIRED = ['시군구', '법정동', '도로명주소', '지번주소', '건물명', '대표번호', '등급', '세대수', '호수', 'buildingRosterIdx']
RANKS = ['S', 'A', 'B', 'C', 'D']


@dataclass
class FilterSet:
    gu: list = field(default_factory=list)
    dong: list = field(default_factory=list)
    rank: list = field(default_factory=list)
    id: list = field(default_factory=list)

    def normalized(self):
        """작업 ID 계산용. 순서와 중복을 없앤 형태"""
        return {k: sorted({str(v).strip() for v in getattr(self, k) if str(v).strip()}) for k in ('gu', 'dong', 'rank', 'id')}

    def describe(self):
        n = self.normalized()
        parts = [f'{lab} {", ".join(n[k])}' for k, lab in (('gu', '구'), ('dong', '동'), ('rank', '등급'), ('id', 'ID')) if n[k]]
        return ' · '.join(parts) or '전체'


def expand_sources(patterns):
    files = []
    for p in patterns:
        p = os.path.expanduser(str(p))
        hits = sorted(glob.glob(p)) if any(ch in p for ch in '*?[') else ([p] if os.path.exists(p) else [])
        if not hits:
            raise UsageError(f'CSV를 찾지 못함 · {p}')
        files += hits
    out = []
    for f in files:
        a = os.path.abspath(f)
        if a not in out:
            out.append(a)
    if not out:
        raise UsageError('--src 로 CSV를 지정해야 함')
    return out


def read_csv(path):
    """문자 그대로 읽는다 (숫자·빈칸 자동 변환 없음). 인코딩 UTF-8 → CP949 순서"""
    last = None
    for enc in ('utf-8-sig', 'cp949'):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False), enc
        except UnicodeDecodeError as e:
            last = e
    raise UsageError(f'CSV 인코딩을 읽지 못함 (UTF-8, CP949 모두 실패) · {path} · {last}')


def load_sources(patterns):
    """CSV 여러 개를 읽어 하나로 합친다. 검사에 걸리면 UsageError"""
    frames = []
    for path in expand_sources(patterns):
        df, enc = read_csv(path)
        miss = [c for c in REQUIRED if c not in df.columns]
        if miss:
            raise UsageError(f'필수 열이 없음 · {os.path.basename(path)} · {", ".join(miss)}')
        df = df.copy()
        df['_src'] = path
        df['_enc'] = enc
        frames.append(df)
    cols0 = [c for c in frames[0].columns if not c.startswith('_')]
    for df in frames[1:]:
        cols = [c for c in df.columns if not c.startswith('_')]
        if cols != cols0:
            raise UsageError(f'CSV끼리 열 구성이 다름 · {os.path.basename(df["_src"].iloc[0])}. 같은 형식의 콜리스트만 함께 읽을 수 있음')
    df = pd.concat(frames, ignore_index=True)
    for c in REQUIRED:
        df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
    bad = df[~df['buildingRosterIdx'].str.fullmatch(r'\d+')]
    if len(bad):
        raise UsageError(f'buildingRosterIdx 가 숫자가 아닌 행 {len(bad)}개 · 예 {bad["buildingRosterIdx"].head(3).tolist()}')
    dup = df[df['buildingRosterIdx'].duplicated(keep=False)]
    if len(dup):
        ex = dup.groupby('buildingRosterIdx')['_src'].apply(lambda s: sorted({os.path.basename(x) for x in s})).head(3)
        raise UsageError(f'buildingRosterIdx 중복 {dup["buildingRosterIdx"].nunique()}개 · 예 ' +
                         '; '.join(f'{k} ({", ".join(v)})' for k, v in ex.items()) + '. 같은 건물이 두 CSV에 들어 있으면 하나만 넣을 것')
    S = settings()
    in_addr = df['도로명주소'].str.contains(S.sido_short, regex=False) | df['지번주소'].str.contains(S.sido_short, regex=False)
    not_ic = df[~in_addr]
    if '시도' in df.columns:
        not_ic = df[(df['시도'] != S.sido) & ~in_addr]
    if len(not_ic):
        raise UsageError(f'{S.sido} 주소가 아닌 행 {len(not_ic)}개 · 예 {not_ic["도로명주소"].head(2).tolist()}. 이 프로그램은 {S.sido} 주소만 조회함')
    return df


def suggest(value, choices, n=3):
    """비슷한 값 추천. 행정동(주안1동)을 넣으면 법정동(주안동)도 후보로"""
    cands = list(dict.fromkeys(difflib.get_close_matches(value, choices, n=n, cutoff=0.5)))
    legal = re.sub(r'\d+동$', '동', value)
    if legal != value and legal in choices and legal not in cands:
        cands.insert(0, legal)
    return cands[:n]


def _check_values(kind, values, choices):
    bad = []
    for v in values:
        if v not in choices:
            s = suggest(v, sorted(choices))
            bad.append(f'「{v}」' + (f' → 혹시 {", ".join(s)}' if s else ''))
    if bad:
        raise UsageError(f'CSV에 없는 {kind} · ' + '; '.join(bad))


def validate(df, fs):
    n = fs.normalized()
    _check_values('시군구', n['gu'], set(df['시군구']))
    dongs = set(df['법정동']) if not n['gu'] else set(df.loc[df['시군구'].isin(n['gu']), '법정동'])
    missing = [d for d in n['dong'] if d not in dongs]
    if missing:
        where = f'{", ".join(n["gu"])} 안' if n['gu'] else 'CSV'
        bad = []
        for v in missing:
            s = suggest(v, sorted(dongs))
            other = sorted(set(df.loc[df['법정동'] == v, '시군구']))
            hint = f' → 혹시 {", ".join(s)}' if s else ''
            if other:
                hint = f' → 이 동은 {", ".join(other)}에 있음'
            bad.append(f'「{v}」{hint}')
        raise UsageError(f'{where}에 없는 법정동 · ' + '; '.join(bad) + ' · 법정동 이름을 CSV에 적힌 그대로 써야 함 (행정동은 인식하지 않음)')
    wrong_rank = [r for r in n['rank'] if r not in RANKS]
    if wrong_rank:
        raise UsageError(f'등급은 S, A, B, C, D 중에서 · 받은 값 {", ".join(wrong_rank)}')
    # 등급은 오타가 날 수 없는 다섯 글자라, CSV에 그 등급 건물이 없어도 실패로 보지 않는다 (예: 중구에 S등급이 없음)
    _check_values('buildingRosterIdx', n['id'], set(df['buildingRosterIdx']))


def select(df, filter_sets):
    """조회 묶음들의 합집합. 각 묶음 안에서는 옵션끼리 AND, 값끼리 OR"""
    if not filter_sets:
        filter_sets = [FilterSet()]
    mask = pd.Series(False, index=df.index)
    for fs in filter_sets:
        validate(df, fs)
        n = fs.normalized()
        m = pd.Series(True, index=df.index)
        if n['gu']:
            m &= df['시군구'].isin(n['gu'])
        if n['dong']:
            m &= df['법정동'].isin(n['dong'])
        if n['rank']:
            m &= df['등급'].isin(n['rank'])
        if n['id']:
            m &= df['buildingRosterIdx'].isin(n['id'])
        if not m.any():
            raise UsageError(f'조건에 맞는 행이 없음 · {fs.describe()}')
        mask |= m
    return df[mask].copy()
