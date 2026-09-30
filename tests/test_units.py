"""단위 테스트 · 인터넷 불필요

  python -m unittest discover -s tests -v
"""
import http.server
import os
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import fakeapi  # noqa: E402
import sample  # noqa: E402
from pipeline import credentials, reporting, settings, stages, storage  # noqa: E402
from pipeline.errors import (AuthError, BlockedError, MissingCredential, RateLimitError, RequestError, RetryableError,  # noqa: E402
                             StageStopped, UnexpectedResponse, UsageError)
from pipeline.providers.kakao import Kakao  # noqa: E402
from pipeline.providers.one114 import One114, fmt_tel, k114J, k114R, k114S  # noqa: E402
from pipeline.selection import FilterSet, load_sources, select, suggest  # noqa: E402
from pipeline.transport import HttpTransport, ReplayTransport, interpret  # noqa: E402

KEYS = {'KAKAO_REST_KEY': 'kakao-test-key-123', 'NCP_GEO_ID': 'geo-id-123456', 'NCP_GEO_SECRET': 'geo-secret-123',
        'NCP_HUB_ID': 'hub-id-123456', 'NCP_HUB_SECRET': 'hub-secret-123'}


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ic_test_')
        self._env = {k: os.environ.get(k) for k in KEYS}
        os.environ.update(KEYS)
        settings.use(settings.defaults())   # 시험은 항상 원본과 같은 기본값으로

    def tearDown(self):
        settings.use(None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ------------------------------------------------------------------ 선택
class SelectionTest(TmpCase):
    def csv(self, name='a.csv', rows=None, enc='utf-8-sig'):
        return sample.write(os.path.join(self.tmp, name), rows or sample.ROWS, enc)

    def test_multi_csv_glob_and_cp949(self):
        self.csv('콜리스트_1.csv')
        self.csv('콜리스트_2.csv', sample.ROWS_JUNG, 'cp949')
        df = load_sources([os.path.join(self.tmp, '콜리스트_*.csv')])
        self.assertEqual(len(df), len(sample.ROWS) + 1)
        self.assertEqual(set(df['_enc']), {'utf-8-sig', 'cp949'})

    def test_or_within_and_across(self):
        df = load_sources([self.csv(rows=sample.ROWS + sample.ROWS_JUNG)])
        out = select(df, [FilterSet(gu=['미추홀구', '중구'], rank=['A', 'B'])])
        self.assertEqual(sorted(out['buildingRosterIdx']), ['101', '103', '105', '301'])

    def test_union_of_blocks(self):
        df = load_sources([self.csv(rows=sample.ROWS + sample.ROWS_JUNG)])
        out = select(df, [FilterSet(gu=['중구']), FilterSet(gu=['미추홀구'], dong=['학익동'])])
        self.assertEqual(sorted(out['buildingRosterIdx']), ['201', '301'])

    def test_typo_suggests(self):
        df = load_sources([self.csv()])
        with self.assertRaises(UsageError) as c:
            select(df, [FilterSet(dong=['관교1동'])])
        self.assertIn('관교동', str(c.exception))
        with self.assertRaises(UsageError) as c:
            select(df, [FilterSet(gu=['미추홀'])])
        self.assertIn('미추홀구', str(c.exception))
        self.assertIn('주안동', suggest('주안1동', ['주안동', '도화동']))

    def test_dong_in_other_gu(self):
        df = load_sources([self.csv(rows=sample.ROWS + sample.ROWS_JUNG)])
        with self.assertRaises(UsageError) as c:
            select(df, [FilterSet(gu=['미추홀구'], dong=['운서동'])])
        self.assertIn('중구', str(c.exception))

    def test_duplicate_ids_across_files(self):
        self.csv('x1.csv')
        self.csv('x2.csv', sample.ROWS[:1])
        with self.assertRaises(UsageError) as c:
            load_sources([os.path.join(self.tmp, 'x*.csv')])
        self.assertIn('중복', str(c.exception))

    def test_missing_column_and_non_incheon(self):
        p = os.path.join(self.tmp, 'bad.csv')
        with open(p, 'w', encoding='utf-8-sig') as f:
            f.write('시군구,법정동\n미추홀구,관교동\n')
        with self.assertRaises(UsageError):
            load_sources([p])
        r = dict(sample.ROWS[0], 시도='서울특별시', 도로명주소='서울특별시 중구 세종대로 1', 지번주소='서울특별시 중구 태평로1가 31')
        with self.assertRaises(UsageError) as c:
            load_sources([self.csv('seoul.csv', [r])])
        self.assertIn('인천', str(c.exception))

    def test_rank_and_empty_result(self):
        df = load_sources([self.csv()])
        with self.assertRaises(UsageError):
            select(df, [FilterSet(rank=['E'])])
        with self.assertRaises(UsageError):
            select(df, [FilterSet(dong=['학익동'], rank=['S'])])      # 등급 자체는 맞지만 조건에 맞는 행이 없음
        out = select(df, [FilterSet(rank=['S', 'B'])])                  # CSV에 없는 등급이 섞여도 실패하지 않음
        self.assertEqual(sorted(out['buildingRosterIdx']), ['101', '103', '106'])


# ------------------------------------------------------------------ 단계 실행기
class _NullT:
    def begin(self, *a): pass
    def end(self): pass
    def sleep(self, s): pass


class StageTest(TmpCase):
    def store(self):
        return storage.Store(os.path.join(self.tmp, 's.sqlite3'))

    def test_resume_skips_done_and_retries_errors(self):
        st = self.store()
        seen, fail = [], {'on': True}

        def fn(x):
            seen.append(x)
            if x == 2 and fail['on']:
                raise RuntimeError('일시 오류')
            return {'i': x}
        stages.run_stage('A', 'g', [1, 2, 3], lambda x: x, fn, st, _NullT(), 't', log=lambda *a: None)
        self.assertEqual(st.counts('A', 'g'), (2, 1))
        seen.clear()
        fail['on'] = False
        stages.run_stage('A', 'g', [1, 2, 3], lambda x: x, fn, st, _NullT(), 't', log=lambda *a: None)
        self.assertEqual(seen, [2])
        self.assertEqual(st.counts('A', 'g'), (3, 0))

    def test_three_errors_stop(self):
        st = self.store()
        with self.assertRaises(StageStopped) as c:
            stages.run_stage('B', 'g', list(range(10)), lambda x: x, lambda x: 1 / 0, st, _NullT(), 't', log=lambda *a: None)
        self.assertFalse(c.exception.fatal)
        self.assertEqual(st.counts('B', 'g'), (0, 3))

    def test_fatal_stops_immediately(self):
        st = self.store()

        def fn(x):
            if x == 1:
                raise AuthError('401')
            return x
        with self.assertRaises(StageStopped) as c:
            stages.run_stage('A', 'g', [0, 1, 2, 3], lambda x: x, fn, st, _NullT(), 't', log=lambda *a: None)
        self.assertTrue(c.exception.fatal)
        self.assertEqual(st.counts('A', 'g'), (1, 1))

    def test_workers(self):
        st = self.store()
        stages.run_stage('A', 'g', list(range(50)), lambda x: x, lambda x: {'v': x}, st, _NullT(), 't', workers=4, log=lambda *a: None)
        self.assertEqual(st.counts('A', 'g'), (50, 0))

    def test_lock(self):
        p = os.path.join(self.tmp, 'job', '.lock')
        with storage.JobLock(p):
            if os.name != 'nt':
                import subprocess
                code = ('import sys; sys.path.insert(0, %r)\nfrom pipeline.storage import JobLock\n'
                        'try:\n  JobLock(%r).__enter__(); print("got")\nexcept Exception as e: print(type(e).__name__)') % (ROOT, p)
                out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True).stdout.strip()
                self.assertEqual(out, 'JobLocked')
        with storage.JobLock(p):
            pass


# ------------------------------------------------------------------ 통신
class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        code = int(self.path.split('/')[1])
        self.send_response(code)
        if 300 <= code < 400:
            self.send_header('Location', '/200')
        self.end_headers()
        self.wfile.write(b'{"documents": []}' if code == 200 else b'<html>no</html>')


class TransportTest(TmpCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_status_mapping(self):
        t = HttpTransport()
        self.assertEqual(t.get_json(self.base + '/200', {}, 5, 'x'), {'documents': []})
        for code, exc in ((401, AuthError), (403, AuthError), (429, RateLimitError), (302, UnexpectedResponse),
                          (404, RequestError), (500, RetryableError)):
            with self.assertRaises(exc, msg=code):
                t.get_json(self.base + f'/{code}', {}, 5, 'x')

    def test_non_json_is_unexpected(self):
        with self.assertRaises(UnexpectedResponse):
            interpret(200, '<html>', 'u', 'x')

    def test_record_and_replay_masks_key(self):
        tr = os.path.join(self.tmp, 'traces')
        t = HttpTransport(trace_dir=tr)
        t.begin('A', 7)
        t.get_json(self.base + '/200', {'Authorization': 'KakaoAK ' + KEYS['KAKAO_REST_KEY']}, 5, 'kakao')
        t.end()
        with open(os.path.join(tr, 'A_7.json'), encoding='utf-8') as f:
            raw = f.read()
        self.assertNotIn(KEYS['KAKAO_REST_KEY'], raw)
        self.assertIn('<KAKAO_REST_KEY>', raw)
        r = ReplayTransport(tr)
        r.begin('A', 7)
        self.assertEqual(r.get_json(self.base + '/200', {'Authorization': 'KakaoAK ' + KEYS['KAKAO_REST_KEY']}, 5, 'kakao'), {'documents': []})
        self.assertEqual(r.bad, [])


# ------------------------------------------------------------------ 키
class CredentialTest(TmpCase):
    def test_missing(self):
        os.environ.pop('NCP_HUB_SECRET')
        with self.assertRaises(MissingCredential) as c:
            credentials.get('naver_hub')
        self.assertIn('NCP_HUB_SECRET', str(c.exception))

    def test_mask_and_scan(self):
        self.assertNotIn(KEYS['KAKAO_REST_KEY'], credentials.mask('오류 ' + KEYS['KAKAO_REST_KEY']))
        d = os.path.join(self.tmp, 'out')
        os.makedirs(d)
        with zipfile.ZipFile(os.path.join(d, 'a.xlsx'), 'w') as z:
            z.writestr('xl/sheet1.xml', 'x ' + KEYS['NCP_GEO_SECRET'])
        with open(os.path.join(d, 'b.html'), 'w') as f:
            f.write('clean')
        self.assertEqual([os.path.basename(p) for p in credentials.scan(d)], ['a.xlsx'])


# ------------------------------------------------------------------ 조회 모듈
class ProviderTest(TmpCase):
    def test_kakao_retries_5xx_then_ok(self):
        url = fakeapi.kaddr('인천광역시 미추홀구 주승로 247')
        t = fakeapi.FakeTransport()
        real = t.table[url]
        seq = [{'status': 502, 'body': ''}, {'status': 503, 'body': ''}, real]

        def req(method, u, h, b, to, kind):
            t._count(kind)
            if u == url:
                r = seq.pop(0)
                return r['status'], r['body']
            return fakeapi.lookup(t.table, fakeapi.norm_key(method, u, b))
        t._request = req
        docs = Kakao(t, 'k').address('인천광역시 미추홀구 주승로 247')
        self.assertEqual(docs[0]['road_address']['building_name'], '동부아파트')
        self.assertAlmostEqual(t.slept, 0.6 + 1.2)

    def test_kakao_401_is_fatal_and_bad_shape(self):
        url = fakeapi.kaddr('x')
        with self.assertRaises(AuthError):
            Kakao(fakeapi.FakeTransport(overrides={url: {'status': 401, 'body': ''}}), 'k').address('x')
        with self.assertRaises(UnexpectedResponse):
            Kakao(fakeapi.FakeTransport(overrides={url: {'status': 200, 'body': '{"documents": 3}'}}), 'k').address('x')

    def test_114_block(self):
        t = fakeapi.FakeTransport(overrides={'POST 114 x': {'status': 200, 'body': '<html>차단</html>'}})
        with self.assertRaises(BlockedError):
            One114(t).search('x', 37.4, 126.6)

    def test_114_keys(self):
        self.assertEqual(k114J('인천 미추홀구 주안1동 137번지 2호'), '주안동 137-2')
        self.assertEqual(k114J('인천 중구 항동1가 12'), '항동1가 12')
        self.assertEqual(k114J('인천 강화군 강화읍 관청리 123'), '강화읍 관청리 123')
        self.assertEqual(k114R('인천광역시 미추홀구 주승로 247 동부'), '주승로 247')
        self.assertEqual(k114S('인천 미추홀구 주승로'), '주승로')
        self.assertEqual([fmt_tel(x) for x in ('0324213360', '0212345678', '15771234', '01012345678')],
                         ['032-421-3360', '02-1234-5678', '1577-1234', '010-1234-5678'])


# ------------------------------------------------------------------ 수집설정.toml
class SettingsTest(TmpCase):
    def write(self, text):
        p = os.path.join(self.tmp, 's.toml')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return p

    def test_shipped_file_equals_original_values(self):
        s = settings.load(os.path.join(ROOT, '수집설정.toml'))
        self.assertEqual(s.data, settings.DEFAULTS)
        self.assertEqual(s.warnings, [])

    def test_partial_file_keeps_defaults(self):
        s = settings.load(self.write('[timing]\none114_gap = 6\n[region.extra_words]\n"연수구 송도동" = ["송도국제"]\n'))
        self.assertEqual(s.one114_gap, 6)
        self.assertEqual(s.kb_zippoom_gap, 0.35)
        self.assertEqual(s.extra_words, {'연수구 송도동': ['송도국제']})
        self.assertEqual(s.urls, settings.DEFAULTS['urls'])

    def test_bad_values_are_rejected(self):
        for text in ('[timing]\nkb_gap = 1\n', '[region]\nsido = "서울특별시"\n', '[timing]\none114_gap = -1\n',
                     '[urls]\nkb = "http://api.kbland.kr/"\n', '[limits]\nmax_errors = 0\n', '[other]\nx = 1\n',
                     '[region.extra_words]\n"관교" = ["x"]\n', '[region.extra_words]\n"주안동" = "관교"\n', '[region]\n주안동 = 1\n'):
            with self.subTest(text=text), self.assertRaises(UsageError):
                settings.load(self.write(text))

    def test_shorter_gap_warns(self):
        s = settings.load(self.write('[timing]\none114_gap = 1.0\n'))
        self.assertTrue(any('one114_gap' in w for w in s.warnings))

    def test_values_reach_code(self):
        settings.use(settings.load(self.write('[urls]\none114 = "https://m.114.co.kr/api/search"\nkakao = "https://kakao.example/v2/"\n'
                                              '[limits]\nmax_errors = 5\n')))
        t = fakeapi.FakeTransport()
        with self.assertRaises(RequestError):   # 가짜 API 에 없는 주소라 404. 요청 주소만 확인
            Kakao(t, 'k').address('주소')
        self.assertTrue(t.calls[0].startswith('https://kakao.example/v2/address.json'))
        from pipeline.providers.one114 import headers
        self.assertEqual(headers()['Origin'], 'https://m.114.co.kr')
        self.assertEqual(settings.current().max_errors, 5)

    def test_extra_words_reach_legacy_judge(self):
        """판정 코드(legacy/common.py)는 별도 프로세스라 환경변수로 받는다. 설정이 없으면 원래 값(주안동 → 관교)"""
        import importlib.util
        spec = importlib.util.spec_from_file_location('legacy_common', os.path.join(ROOT, 'legacy', 'common.py'))
        common = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(common)
        old = os.environ.pop('COLLECTOR_REGION_EXTRA', None)
        try:
            self.assertIn('관교', common.region_words('미추홀구', '주안동'))
            self.assertNotIn('관교', common.region_words('미추홀구', '학익동'))
            settings.use(settings.load(self.write('[region.extra_words]\n"미추홀구 학익동" = ["인하"]\n')))
            os.environ['COLLECTOR_REGION_EXTRA'] = reporting._env()['COLLECTOR_REGION_EXTRA']
            self.assertIn('인하', common.region_words('미추홀구', '학익동'))
            self.assertNotIn('인하', common.region_words('연수구', '학익동'))
            self.assertNotIn('관교', common.region_words('미추홀구', '주안동'))
        finally:
            os.environ.pop('COLLECTOR_REGION_EXTRA', None)
            if old is not None:
                os.environ['COLLECTOR_REGION_EXTRA'] = old


if __name__ == '__main__':
    unittest.main()
