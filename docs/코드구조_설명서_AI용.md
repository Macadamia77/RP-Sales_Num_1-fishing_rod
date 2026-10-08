# incheon_collector · 코드 구조 명세 (AI용)

> 대상: 이 코드를 고치거나 ERS에 이식할 개발자의 AI 도우미.
> 기준: 2026-09-30판. 파이썬 파일 약 3,400줄, 시험 39개.
> 2026-10-08 갱신: `legacy/` 판정 코드를 `pipeline/judge/`로 옮겨 별도 프로세스 대신 함수로 부르게 바꿨다(판정 로직은 그대로, 용현동 926건 결과가 전과 글자 단위로 같음). 원본 대조 도구(`tools/check_legacy.py`, `original_hashes.json`)와 `.env.example`은 삭제. 시험 41개. 아래 줄 수는 옛 기준이다.
> 사람이 읽는 설명서는 `코드구조_설명서.html`, 검수 결과와 위험 목록은 `검수보고서.md`에 있다.

## 0. 요약 (먼저 읽을 것)

- **하는 일**
  - 인천 콜리스트 CSV에서 조회 대상 건물을 고른다. 대상은 건물명이 `(건물명없음)`이거나 대표번호가 비어 있거나 `없음`인 건물이다.
  - 카카오 → KB부동산·집품 → 네이버(선택으로 114On)를 조회해 건물명과 관리사무소 번호 후보를 모은다.
  - 판정 코드(`pipeline/judge/`)로 확정값을 정한다.
  - 엑셀·CSV(77열)·HTML 5종·summary.json을 만든다.
- **입구는 2개이고, 둘 다 같은 총괄 함수를 부른다.**
  - `run_config.py`: 설정 파일로 실행한다. VS Code F5가 이것을 쓴다.
  - `run.py` → `pipeline/cli.py`: 명령줄 인자로 실행한다.
- **총괄 파일은 `pipeline/service.py`다.**
  - `run_core`: 기본 조회
  - `run_114`: 114On 추가 조회
  - `export`: API 호출 없이 판정과 결과 파일만 다시 만든다
  - `status`: 진행 상황
  - 작업(job) 단위로 상태를 관리한다.
- **층 구조**: 입구 → service(흐름) → stages(단계 실행 규칙) → providers(사이트별 조회) → transport(HTTP·오류 분류).
  - 판정과 결과 파일은 `reporting.py`가 `judge/merge.py`·`judge/export_selected.py`의 `run()`을 불러 만든다.
- **설정은 두 파일이다.**
  - `조회설정.toml`: 조회 범위. 매번 고친다.
  - `수집설정.toml`: 지역어, 사이트 주소, 간격, 오류 한도. 평소에는 고치지 않는다.
  - 키는 `.env` 또는 환경변수에서만 읽는다.

## 1. 파일 지도

줄 수는 2026-09-30 기준이다.

### 1-1. 입구와 총괄

| 파일 | 줄 | 책임 | 주요 이름 |
|---|---|---|---|
| `run.py` | 4 | 명령줄 입구. `pipeline.cli.main()`만 부른다 | — |
| `run_config.py` | 155 | 설정 파일 입구. 조회설정.toml과 .env를 읽고 service를 부른다. 마지막 작업 ID를 `.last_job.json`에 기억한다 | `load_env`, `load_config`, `remember`, `last_job`, `main` |
| `pipeline/cli.py` | 119 | 하위 명령 5개(list·run·run114·export·status)와 종료 코드(0·1·2·130) | `build_parser`, `dispatch`, `guarded`, `main` |
| `pipeline/service.py` | 462 | 전체 흐름. 작업 ID, 작업 폴더, 단계 순서, 판정 호출, 결과 내보내기, 114 조건 검사 | `Plan`, `JobPaths`, `run_core`, `_run_core_group`, `run_114`, `export`, `status`, `_export_ok_only`, `_export_all` |

### 1-2. 입력

| 파일 | 줄 | 책임 | 주요 이름 |
|---|---|---|---|
| `pipeline/selection.py` | 171 | CSV 읽기(UTF-8 → CP949), 필수 열·ID·시도 검사, 조회 범위 선택, 오타 추천 | `FilterSet`, `load_sources`, `validate`, `select`, `suggest` |
| `pipeline/prepare.py` | 69 | 조회 대상 표시(nt·pt), 구·동별 묶기, 판정기 입력 `input.json`과 `source.csv` 쓰기 | `flags`, `groups`, `write_group`, `compact` |

### 1-3. 조회

| 파일 | 줄 | 책임 | 주요 이름 |
|---|---|---|---|
| `pipeline/providers/kakao.py` | 207 | 1단계(A). collector.js procA를 옮김. 주소검색, 키워드검색, 이름 재검색, 중개업소 | `Kakao`, `proc_a`, `research`, `nr`, `nj`, `is_mg` |
| `pipeline/secondary.py` | 106 | 2단계(B). collector.js procB를 옮김. KB 단지정보와 집품 건물명, 새 이름으로 카카오 재검색 | `proc_b`, `clean_kb`, `bad_nm` |
| `pipeline/providers/kb.py` | 37 | KB부동산 내부 API(통합검색, 단지정보) | `KB.search`, `KB.complex_main` |
| `pipeline/providers/zippoom.py` | 20 | 집품 주소 자동완성 내부 API | `Zippoom.search` |
| `pipeline/providers/naver.py` | 117 | naver.js를 옮김. NG: 지오코딩, NV: 지역 검색 교차 확인 | `Naver`, `proc_geo`, `proc_verify` |
| `pipeline/providers/one114.py` | 175 | 5단계(C). collector.js procC·o114를 옮김. 114On. 실제 접속은 확인하지 않음 | `One114`, `proc_c`, `headers`, `k114R`/`J`/`S` |
| `pipeline/compat.py` | 157 | JS와 같은 문자열·숫자 처리 (`\s`, trim, toFixed, encodeURIComponent, Object.values 순서) | `js_trim`, `truthy`, `enc_uri`, `JSObj`, `fixed6`, `dist` |

### 1-4. 실행 규칙과 기반

| 파일 | 줄 | 책임 | 주요 이름 |
|---|---|---|---|
| `pipeline/stages.py` | 104 | 단계 실행기. 성공 건 건너뛰기, 건마다 저장, 멈춤 규칙, 동시 실행(카카오 최대 4), 진행 표시 | `run_stage` |
| `pipeline/transport.py` | 166 | HTTP. 상태 코드를 오류 종류로 바꾸고, 응답 기록·재생을 맡는다. 리다이렉트는 따라가지 않는다. 세션 기본 User-Agent를 브라우저 값으로 둔다(2026-10-07 PR #6, +2줄. KB·114On이 `python-requests` UA를 끊음) | `interpret`, `HttpTransport`, `ReplayTransport` |
| `pipeline/errors.py` | 57 | 오류 종류. FatalError는 즉시 멈춤, 나머지는 건 단위 실패 | `UsageError`, `FatalError`(Auth, RateLimit, Blocked, UnexpectedResponse), `RetryableError`, `RequestError`, `StageStopped` |
| `pipeline/storage.py` | 141 | SQLite 저장소, OS 파일 잠금, 코드 해시, 원자적 JSON 쓰기 | `Store`, `JobLock`, `code_hash`, `write_json` |
| `pipeline/credentials.py` | 89 | 키를 환경변수에서만 읽음. 키 가리기, 결과 폴더(xlsx·zip 내부 포함) 키 검사 | `get`, `mask`, `mask_headers`, `scan` |
| `pipeline/settings.py` | 178 | 수집설정.toml 읽기·검사·기본값(= 원본 값) | `load`, `current`, `use`, `defaults`, `DEFAULTS`, `SUPPORTED_SIDO` |

### 1-5. 판정·결과 연결

| 파일 | 줄 | 책임 | 주요 이름 |
|---|---|---|---|
| `pipeline/reporting.py` | 44 | 판정(`judge.merge.run`)과 결과 파일(`judge.export_selected.run`)을 부른다. print 출력은 `logs/judge.log`에 모으고 실패하면 마지막 줄을 오류에 담는다 | `merge`, `export_group` |
| `pipeline/csv_export.py` | 39 | 엑셀 결과 시트 → CSV. 하이퍼링크는 옆 `_링크` 열로 옮긴다 | `xlsx_to_csv` |
| `pipeline/replay.py` | 33 | 기록한 응답으로 다시 돌려 결과 비교 | `replay_core`, `compare_results` |

### 1-6. judge (판정 코드 · 원래 legacy/)

| 파일 | 줄 | 책임 | 비고 |
|---|---|---|---|
| `pipeline/judge/merge.py` | 261 | 판정. A·B·NG·NV·C.json → results.json과 다음 단계 대기열(`naver_geo_*.js`, `naver_verify_*.js`, `q114_*.js`). 입구 `run(work, gu, dong, scope114)` | 원본 로직 그대로. 명령줄 `main` → `run` |
| `pipeline/judge/common.py` | 207 | 주소 정리, 이름 비교, 관리사무소 판정, 지역어 | 주안동 예외 → `settings().extra_words`(수집설정.toml) |
| `pipeline/judge/build_outputs.py` | 342 | 엑셀·HTML 생성 함수 | 원본 그대로. 단독 실행용 `main` 삭제, HTML 카드에 KB부동산 버튼(2026-10-08) |
| `pipeline/judge/export_selected.py` | 112 | 선택한 행만 엑셀과 HTML 5종으로 만든다. 수식 차단, LibreOffice 재계산. 입구 `run(work, gu, dong, out, date)` | 원본 아님 |

### 1-7. 설정·도구·시험

| 파일 | 책임 |
|---|---|
| `조회설정.toml` | 조회 범위. `src`, `[["조회"]]` 블록(`"구"`, `"동"`, `"등급"`, `id`), workers, skip_geo, run_tag, scope114 |
| `수집설정.toml` | `[region]` sido·extra_words, `[urls]`, `[timing]`, `[limits]` |
| `.env` | 키 5개 (KAKAO_REST_KEY, NCP_GEO_ID, NCP_GEO_SECRET, NCP_HUB_ID, NCP_HUB_SECRET). git에 올리지 않음 |
| `tools/replay_check.py` | 기록 재생으로 결과 비교 |
| `tests/fakeapi.py`, `tests/sample.py` | 가짜 API 응답과 시험용 CSV |
| `tests/test_units.py` | 단위 시험 (선택, 오류 분류, 키, 저장소, 114 규칙, 설정) |
| `tests/test_flow.py` | 전체 흐름, 이어 돌리기, 114 조건, 종료 코드, 설정 파일, 원본 JS 비교(Node 필요) |
| `tests/reference/` | 원본 collector.js·naver.js와 Node 실행기 |

## 2. 실행 흐름

### 2-1. run_core (기본 조회)

```
Plan(src, filter_sets, skip_geo, run_tag)
  load_sources → select → prepare.groups         # 검사 실패 시 UsageError(종료 코드 2), API 호출 전
  job_id = sha256(CSV 해시들, 정규화 필터, skip_geo, code_hash, run_tag)[:24]
JobLock(work/jobs/<id>/.lock)
for (구, 동) in groups:                          # _run_core_group
  prepare.write_group → data/<구>_<동>/input.json, source.csv
  run_stage A (카카오, workers ≤4) → Store → A.json(실패 행 포함)
  run_stage B (KB·집품, 순차, 간격 0.35s, 오류 뒤 3s 쉼) → B.json(실패 행 포함)
  NG.json, NV.json ← 성공 행만
  reporting.merge(scope114='none') → results.json, naver_geo_*.js, naver_verify_*.js
  [skip_geo 아니면] 대기열 NG → run_stage NG → NG.json(성공만) → merge
  대기열 NV → run_stage NV → NV.json(성공만) → merge
_export_all → results/<id>/core/<실행시각>/<구>_<동>/{xlsx, csv, html×5, results.json} + summary.json
credentials.scan(결과 폴더) → 키가 발견되면 PipelineError
```

### 2-2. run_114

```
조건: core.complete == True, code_hash 같음 (다르면 UsageError)
for 그룹:
  data/<그룹>/ 의 CORE_FILES(input.json, source.csv, A, B, NG, NV)를 data114/<그룹>/ 로 복사
  C.json ← 성공 행만 → merge(scope114=no_rep|no_proxy) → q114_*.js
  run_stage C (순차, 요청 간격 4.5s) → C.json → merge
_export_all(mode='114') → results/<id>/114/<실행시각>/...
```

### 2-3. export

API를 부르지 않는다. 저장된 조회 결과로 merge와 결과 파일만 다시 만든다. 지역어 설정을 바꾼 뒤에 쓴다.

## 3. 지켜야 할 규칙

코드를 고칠 때 깨면 안 되는 것들이다.

1. **NG·NV·C 파일에는 성공 행만 넣는다(`_export_ok_only`).** merge.py는 파일에 키가 있으면 「조회함」으로 보고 대기열에서 뺀다(merge.py 243·245줄). A·B는 원본 형식대로 실패 행을 넣는다. merge가 실패 행을 「조회 오류」로 표시하기 때문이다.
2. **FatalError는 1건에서 즉시 멈춘다.** 401·403 → AuthError, 429 → RateLimitError, 3xx → UnexpectedResponse, 2xx인데 JSON이 아니거나 구조가 다른 경우 → UnexpectedResponse, 114 차단 화면 → BlockedError.
3. **나머지 4xx(RequestError)는 다시 시도하지 않는다.** 5xx·네트워크 오류(RetryableError)는 사이트 모듈이 다시 시도한다. 카카오는 6번(0.6·2^n초), 네이버는 4번. 그래도 실패하면 그 건만 실패로 기록하고, 한 단계에서 `max_errors`(기본 3)건이 되면 멈춘다.
4. **Store에는 건마다 바로 쓴다.** 행 = (stage, grp, key, ok, value, updated). ok=0 행은 다음 실행에서 다시 조회한다.
5. **키는 파일에 쓰지 않는다.**
   - 로그·오류·traces는 `mask`로 가린다.
   - 결과 폴더는 마지막에 `scan`으로 검사한다.
6. **원본 CSV는 읽기만 한다.** 결과는 항상 새 실행시각 폴더에 쓴다(이전 결과를 덮어쓰지 않음).
7. **작업 ID는 `pipeline/**/*.py`의 코드 해시를 포함한다.**
   - pipeline 코드(판정 코드 `judge/` 포함, 2026-10-08부터)를 고치면 새 작업이 되어 처음부터 다시 조회하고, 이전 작업에는 114를 붙일 수 없다. 이미 받은 작업은 `export`로 판정만 다시 돌릴 수 있다(`export`는 코드 해시를 검사하지 않음).
   - 수집설정.toml은 작업 ID에 들어가지 않는다. 대신 `summary.json.settings`(파일, sha, extra_words)에 남는다.
8. **조회 모듈은 원본 JS와 같은 요청·같은 결과를 내야 한다.** 시험 `test_same_as_original_js`가 원본 JS를 Node에서 가짜 API로 돌려 요청 목록과 결과를 비교한다. JS와 다른 파이썬 기본 동작(공백, 반올림, 인코딩, 키 순서)은 `compat.py`를 거친다.
9. **엑셀은 수식을 차단한다.** 지표 시트를 뺀 모든 시트에서 `=`로 시작하는 값을 글자로 바꾼다. CSV는 ERS가 원래 글자를 그대로 가져가야 하므로 바꾸지 않는다.

## 4. 데이터 형식

- **작업 폴더** `<work>/jobs/<job_id>/`
  - `job.json`: params, groups, core·c114의 complete, exports, errors_remaining, code_hash
  - `state.sqlite3`
  - `data/`, `data114/`
  - `logs/judge.log`, `traces/`(선택)
- **판정기 입력** `input.json`: 행 = `{i, gu, dong, road, jibun, n0, nt, pt, grade, hh, ho}`
  - 조회 모듈에 넘기는 줄인 형태는 `[i, 짧은 도로명, 짧은 지번, n0, nt, pt]`이다.
- **대기열 파일**: `__loadXxx({...},[[...],...])` 형태의 JS. `service.read_queue`가 `'},['` 뒤를 JSON으로 읽는다. 형식이 다르면 PipelineError.
- **summary.json**
  - `job_id`, `mode`, `date`
  - `errors_remaining`
  - `params`, `settings`
  - `groups[]`: 구, 동, 대상, 채움 건수, `조회_A/B/NG/NV(/C)` 성공·오류
  - `files[]`
- **CSV**: 77열(원본 28 + 새 열 49). 링크가 있는 열은 바로 옆에 `<열>_링크` 열이 붙는다. ERS 연결 키는 `buildingRosterIdx`.

## 5. 고칠 때 어디를 보나

| 하고 싶은 일 | 고칠 곳 | 같이 할 일 |
|---|---|---|
| 사이트 주소가 바뀜 | `수집설정.toml [urls]` | 없음 (코드 수정 불필요) |
| 요청 간격, 멈춤 기준 조정 | `수집설정.toml [timing]`, `[limits]` | 원래 값보다 줄이면 실행 시 주의가 뜸 |
| 특정 동의 지역어 추가 | `수집설정.toml [region.extra_words]` (`"동"` 또는 `"구 동"`) | 기존 작업은 `run.py export`로 판정만 다시 |
| 사이트 응답 구조가 바뀜 | `pipeline/providers/<사이트>.py` | 시험의 가짜 응답(`tests/fakeapi.py`)도 수정. 코드 해시가 바뀌어 새 작업이 됨 |
| 판정 규칙 변경 | `pipeline/judge/common.py` 또는 `merge.py` | 코드 해시가 바뀜. 기존 작업에 `export`로 판정을 다시 돌려 전후 `results.json`을 비교 |
| 결과 열 추가(예: 출처 코드, 거리) | `pipeline/judge/build_outputs.py`, `pipeline/csv_export.py` | CSV 77열을 확인하는 시험(`test_full_run_outputs`) 수정 |
| 다른 시도 지원 | 판정 주소 규칙(judge/common.py `GU_RE`, `LOOSE_DROP`, `replace('인천광역시','인천')` 등) → `settings.SUPPORTED_SIDO`에 추가 | 지금은 인천광역시만 허용 |
| 새 사이트 추가 | `providers/` 새 파일 + `service`에 단계 추가 + merge.py가 읽을 JSON | `run_stage` 규칙(건너뛰기, 멈춤)을 그대로 씀 |

## 6. 알려진 한계

자세한 내용은 `검수보고서.md`에 있다.

- 2026-10-07 미추홀구 용현동 926건을 실제 API로 돌렸다(오류 0). 그 밖에는 가짜 API와 원본 JS 비교로 확인했다.
- 114On을 파이썬에서 직접 부르는 방식은 확인하지 않았다. 원본은 브라우저 화면 안에서 호출했다.
- 판정 코드는 프로젝트 문서의 2026-09-28판을 옮겨 적은 것이다(원래 legacy/). 원본 대조 도구는 2026-10-08 이식 때 삭제했고, 옛 파일은 git 기록에 있다.
- 집품 조회 도메인(`live.zippo-om.com`)과 링크 도메인(`zippoom.com`)이 다르다. 어느 쪽이 맞는지 확인이 필요하다.
- 호출 제한은 작업 하나 안에서만 지킨다. 작업 여러 개를 동시에 돌리면 같은 키로 호출이 겹친다.
- 상태를 SQLite 파일에 저장한다. 서버 한 대의 고정 디스크에서 돌려야 한다. Lambda처럼 매번 새로 뜨는 환경이나 여러 대가 함께 쓰는 네트워크 디스크는 맞지 않는다.
