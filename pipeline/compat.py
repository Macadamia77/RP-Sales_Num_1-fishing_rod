"""원본 자바스크립트(collector.js, naver.js)와 문자열·숫자 처리를 똑같이 맞추는 함수

조회 코드는 원래 브라우저 자바스크립트였다. 공백 처리, 반올림, 주소 인코딩, 객체 키 순서가
파이썬 기본 동작과 달라서, 같은 응답에서 같은 결과가 나오도록 여기서 맞춘다.
"""
import math
import re
from decimal import Decimal, ROUND_HALF_UP

# 자바스크립트 \s 가 다루는 공백 문자. 눈에 안 보이는 문자라 코드 번호로 적는다
_WS_CHARS = ('\t\n\x0b\x0c\r   ' + ''.join(chr(c) for c in range(0x2000, 0x200b))
             + '    　﻿')
WS = '[' + re.escape(_WS_CHARS) + ']'          # 자바스크립트 \s
DOT = '[^\n\r  ]'                     # 자바스크립트 .
WS_CHARS = _WS_CHARS


def js_trim(t):
    """String.prototype.trim()"""
    return t.strip(_WS_CHARS)


def num_str(v):
    """String(number). 127.0 → '127'"""
    v = jnum(v)
    return str(v) if isinstance(v, int) else repr(v)


def js_str(v):
    """String(v || '')"""
    if v is None or v is False or v == '' or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0):
        return ''
    if isinstance(v, float):
        return num_str(v)
    return str(v)


def truthy(v):
    """자바스크립트 참·거짓 판정"""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not (isinstance(v, float) and math.isnan(v))
    if isinstance(v, str):
        return len(v) > 0
    return True


def tstr(v):
    """템플릿 문자열 안의 값 `${v}`"""
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        return num_str(v)
    return str(v)


def jor(a, b):
    """a || b"""
    return a if truthy(a) else b


def to_num(v):
    """Number(v). 숫자로 못 바꾸면 None (자바스크립트 NaN은 JSON에서 null)"""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    t = js_trim(str(v))
    if t == '':
        return 0
    try:
        f = float(t)
    except ValueError:
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(f) if f.is_integer() and abs(f) < 1e15 else f


def jnum(v):
    """JSON에 쓸 숫자. 자바스크립트처럼 127.0 은 127"""
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return int(v)
    return v


def fixed6(v):
    """+(+v).toFixed(6)"""
    n = to_num(v)
    if n is None:
        return None
    q = Decimal(float(n)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    return jnum(float(q))


def js_round(v):
    """Math.round"""
    return int(math.floor(v + 0.5))


_UNRES_URI = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' + "-_.!~*'()")
_UNRES_FORM = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' + '*-._')


def enc_uri(s):
    """encodeURIComponent"""
    out = []
    for ch in str(s):
        if ch in _UNRES_URI:
            out.append(ch)
        else:
            out.extend('%%%02X' % b for b in ch.encode('utf-8'))
    return ''.join(out)


def enc_form(pairs):
    """new URLSearchParams(obj).toString()"""
    def e(s):
        out = []
        for ch in str(s):
            if ch in _UNRES_FORM:
                out.append(ch)
            elif ch == ' ':
                out.append('+')
            else:
                out.extend('%%%02X' % b for b in ch.encode('utf-8'))
        return ''.join(out)
    return '&'.join(e(k) + '=' + e(v) for k, v in pairs)


class JSObj(dict):
    """Object.values 순서. 정수 모양 키는 오름차순이 먼저, 나머지는 넣은 순서"""

    def js_values(self):
        idx, other = [], []
        for k in self.keys():
            if re.fullmatch(r'0|[1-9][0-9]*', k) and int(k) < 4294967295:
                idx.append(k)
            else:
                other.append(k)
        idx.sort(key=int)
        return [self[k] for k in idx + other]


def dist(x1, y1, x2, y2):
    """collector.js dist · 경도·위도 차이로 m 거리"""
    if x1 is None or x2 is None:
        return None
    r = math.pi / 180
    return js_round(math.hypot((x2 - x1) * math.cos(y1 * r) * 111320, (y2 - y1) * 110540))
