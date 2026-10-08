# 인천 건물정보 수집기

인천 콜리스트 CSV에서 건물명이 없거나 대표번호가 없는 건물을 골라, 카카오·KB부동산·집품·네이버(필요하면 114On)를 조회해 건물명과 관리사무소 번호를 채운 결과 파일을 만든다.
「인천 건물정보 수집기 설명서」의 구조와 마지막 「옵션 설정 개선안」을 반영해 새로 짠 코드다.

원본 CSV는 읽기만 한다. 결과는 항상 새 폴더에 새 파일로 만든다.

## 1. 준비

```
Python 3.11 이상
pip install -r requirements.txt
LibreOffice (선택) · 엑셀 수식 재계산용. 없으면 재계산만 건너뜀
```

**Windows에서 `python`이 안 잡힐 때** · 「Python was not found; run without arguments to install from the Microsoft Store」가 나오면 PATH의 `python`이 Microsoft Store 바로가기다. 설치된 파이썬을 전체 경로로 부른다(Anaconda 예: `C:\Users\<사용자>\anaconda3\python.exe run_config.py 확인`). VS Code F5는 VS Code에서 고른 인터프리터를 쓴다. 한글 출력이 깨지면 `PYTHONIOENCODING=utf-8`을 준다.

**결과 폴더 이름 바꾸기** · `조회설정.toml`의 `out`(기본 `results`)을 바꾼다. 예: `out = "결과물"`. 기본값이 아닌 폴더를 쓰면 결과 파일이 git에 올라가지 않도록 `.gitignore`에도 추가한다.

키는 루트에 `.env` 파일을 만들어 아래 이름으로 값을 적는다. `.env`는 `.gitignore`에 들어 있다.

```
KAKAO_REST_KEY=
NCP_GEO_ID=
NCP_GEO_SECRET=
NCP_HUB_ID=
NCP_HUB_SECRET=
```

- 키는 환경변수나 `.env`에서만 읽는다. 이미 환경변수가 있으면 환경변수가 우선한다.
- 키는 어떤 파일에도 쓰지 않는다. 화면 출력과 오류 메시지, 응답 기록(traces)에서는 `<KAKAO_REST_KEY>`처럼 가려서 남긴다.
- 조회가 끝나면 결과 폴더(xlsx·zip 내부 포함)에 키 문자열이 들어갔는지 검사한다.
- 필요한 키가 없으면 그 단계 직전에 어떤 이름이 빠졌는지 알려 주고 멈춘다.

## 2. 가장 쉬운 사용법 · 설정 파일 + VS Code F5

1. `조회설정.toml`에서 `src`(원본 CSV 경로)와 `[["조회"]]` 블록만 고친다.
2. VS Code에서 F5를 누르고 메뉴를 고른다.

| F5 메뉴 | 하는 일 |
|---|---|
| 설정파일로 대상 확인 | 조회할 건물 수만 보여 줌. API 호출 없음 |
| 설정파일로 조회 | 기본 조회와 결과 파일. 작업 ID를 `.last_job.json`에 기억 |
| 설정파일로 114On 추가 조회 | 마지막 작업에 114On 조회. 작업 ID 입력 필요 없음 |
| 대상 확인 / 기본 조회 / 114On 추가 조회 | 설정 파일 없이 CSV·구·작업 ID를 입력창에서 받음 |

터미널에서는 이렇게 쓴다.

```
python run_config.py 확인
python run_config.py 조회
python run_config.py 114
python run_config.py 상태
옵션  --config 다른설정.toml   --env 다른.env
```

### 조회설정.toml 쓰는 법

```toml
src = ["C:/data/콜리스트_*.csv"]   # 여러 개, * 패턴 가능. 상대 경로는 이 파일 기준

[["조회"]]              # 블록 하나 = 조회 범위 하나. 블록끼리는 합쳐서 한 작업
"구" = ["중구"]
"동" = ["운서동", "중산동"]
"등급" = ["S", "A"]

[["조회"]]
"구" = ["미추홀구"]      # 동을 생략하면 그 구 전체
"등급" = ["B"]
```

- TOML 문법에서 한글 이름은 따옴표로 감싸야 한다. `[[조회]]`, `구 = [...]`처럼 쓰면 문법 오류가 난다. 영어 이름(`[[query]]`, `gu`, `dong`, `rank`, `id`)도 쓸 수 있다.
- 같은 항목 안의 여러 값은 「또는」, 서로 다른 항목끼리는 「그리고」로 묶인다.
- 구·동·ID 이름이 CSV에 없으면 바로 멈추고 비슷한 이름을 추천한다(예: 「주안1동 → 혹시 주안동」). 동은 CSV에 적힌 법정동 이름 그대로 써야 한다.
- 등급은 S·A·B·C·D만 받는다. CSV에 그 등급 건물이 없어도 실패로 보지 않는다(예: 중구에는 S등급이 없음).
- 그 밖의 항목: `work`, `out`, `workers`(카카오 동시 조회 1~4), `skip_geo`, `run_tag`, `scope114`(`no_rep` 또는 `no_proxy`).

## 3. 수집설정.toml · 조회 규칙에 쓰는 값

조회 범위(`조회설정.toml`)와 달리 평소에는 고칠 일이 없는 값을 모은 파일이다. 배포한 파일의 값은 원본 collector.js·naver.js·common.py의 값과 같다. 항목을 지우면 기본값이 쓰인다.

| 구역 | 항목 | 기본값 | 뜻 |
|---|---|---|---|
| `[region]` | `sido` | 인천광역시 | 검색어와 주소 검사에 쓰는 시도. 판정 규칙이 인천 기준이라 지금은 인천광역시만 가능 |
| `[region.extra_words]` | `"주안동" = ["관교"]` | 원본과 같음 | 동별로 더하는 지역어. 키는 `"동"` 또는 `"구 동"` |
| `[urls]` | kakao, kb, zippoom, naver_geo, naver_hub, one114 | 원본 주소 | 사이트 주소가 바뀌면 여기만 고침 |
| `[timing]` | kb_zippoom_gap 0.35, one114_gap 4.5, naver_geo_gap 0.12, naver_local_gap 0.15 | 원본 값 | 요청 사이 간격(초). 줄이면 실행할 때 주의가 뜸 |
| `[limits]` | max_errors 3, progress_every 20 | 설명서 값 | 일반 오류 몇 건에서 멈출지, 진행 표시 간격 |

- 다른 위치의 파일을 쓰려면 환경변수 `COLLECTOR_SETTINGS`에 경로를 넣는다.
- 값이 잘못되면 조회를 시작하기 전에 어느 항목이 왜 틀렸는지 알려 주고 멈춘다(종료 코드 2).
- 적용된 설정은 `summary.json`의 `settings`에 남는다.
- 설정을 바꿔도 작업 ID는 그대로다. 지역어를 바꾼 뒤에는 `run.py export`로 판정과 결과 파일만 다시 만들면 된다.

## 4. 명령줄 사용법 · run.py

```
python run.py list    --src "C:/data/콜리스트_*.csv" --gu 중구 연수구 --rank S A
python run.py run     --src ... --gu 중구 --dong 운서동 [--skip-geo] [--run-tag 이름] [--workers 4] [--record-traces]
python run.py run114  --job <작업ID 앞부분> [--scope no_rep|no_proxy]
python run.py export  --job <작업ID> [--mode core|114]      # API 호출 없이 결과 파일만 다시 만듦
python run.py status  [--job <작업ID>]                      # 생략하면 작업 목록
```

끝날 때 돌려주는 값: 0 성공, 2 입력 오류(오타·파일 없음·키 없음), 1 조회 실패, 130 Ctrl+C.

## 5. 작업 ID와 이어 돌리기

- 작업 ID = CSV 내용, 조회 범위, `skip_geo`, 코드(`pipeline/*.py`), `run_tag`로 계산한 값(24자).
- 같은 범위를 다시 실행하면 같은 작업으로 이어진다. 성공한 건물은 건너뛰고, 오류가 난 건물만 다시 조회한다.
- 처음부터 새로 조회하고 싶으면 `run_tag`에 새 이름을 적는다.
- 같은 작업을 두 창에서 동시에 돌리면 두 번째 실행은 바로 멈춘다(파일 잠금).

## 6. 멈추는 조건

| 상황 | 동작 |
|---|---|
| 401·403 (키 또는 구독 오류) | 바로 멈춤 |
| 429 (호출 한도 초과) | 바로 멈춤 |
| 리다이렉트, JSON이 아닌 응답 | 바로 멈춤 (사이트 구조가 바뀐 것으로 봄) |
| 114On 차단 화면 | 바로 멈춤. 75분 이상 지난 뒤 다시 실행 |
| 그 밖의 오류 (5xx, 네트워크 끊김 등) | 재시도 후 그 건물만 오류로 기록. 한 단계에서 3건(`max_errors`)이 되면 멈춤 |

멈춘 뒤 같은 명령으로 다시 실행하면 오류 건물부터 이어서 한다.
조회가 끝났는데 오류 건물이 남아 있으면 마지막에 「오류 남음 N」으로 알려 준다. `status`에서도 보인다.

## 7. 결과 파일

```
results/<작업ID>/core/<실행시각>/
  summary.json                                건수, 오류 남은 건수(errors_remaining), 파일 목록
  <구>_<동>/
    콜리스트_<구>_<동>_재검색결과_<날짜>.xlsx   엑셀
    콜리스트_<구>_<동>_재검색결과_<날짜>.csv    77열 (원본 28 + 새 열 49, 링크는 옆 열 _링크)
    <구>_<동>_<종류>_목록_<날짜>.html          확인용 HTML 5종
    results.json                              판정 결과 원본
results/<작업ID>/114/<실행시각>/              114On 추가 조회 결과 (같은 형식)
work/jobs/<작업ID>/                            작업 상태 (지우지 말 것. 이어 돌리기에 씀)
```

- 실행할 때마다 새 시각 폴더에 만든다. 이전 결과를 덮어쓰지 않는다.
- 엑셀에서 `=`로 시작하는 조회 결과 글자(예: 가게 이름)는 수식이 아니라 글자로 저장한다(지표 시트 제외). CSV에는 그런 보호가 없으므로 CSV를 엑셀로 열 때는 주의한다.

## 8. 114On 추가 조회

- 기본 조회가 끝난 작업에만 쓸 수 있다. 기본 조회 뒤 코드가 바뀌었으면 거부한다.
- `no_rep`: 대표번호가 없는 건물 전부. `no_proxy`: 대표번호도 대리 연락처도 없는 건물만.
- 한 번에 1건, 요청 사이 4.5초. 원본은 브라우저의 114.co.kr 화면 안에서 호출했으므로, 파이썬에서 직접 호출하는 방식은 실제 사이트에서 아직 확인하지 않았다. 처음에는 적은 건수로 시험할 것.

## 9. 폴더 구성

```
run.py, run_config.py      실행 입구
조회설정.toml              조회 범위 (매번 고침)
수집설정.toml              조회 규칙 값: 지역어, 사이트 주소, 간격, 오류 한도
pipeline/                  새 코드
  cli.py service.py        명령과 작업 흐름
  selection.py prepare.py  CSV 읽기, 조회 범위, 입력 준비
  stages.py                단계 실행 규칙 (건너뛰기, 재시도, 멈춤)
  transport.py             HTTP, 오류 해석, 응답 기록·재생
  storage.py               SQLite 상태 저장, 잠금, 작업 ID
  credentials.py           키 읽기, 가리기, 결과 폴더 검사
  settings.py              수집설정.toml 읽기와 검사
  providers/               카카오, KB부동산, 집품, 네이버, 114On
  secondary.py compat.py   2단계 조회, 자바스크립트와 같은 동작
  reporting.py csv_export.py 판정 스크립트 호출, CSV 변환
legacy/                    판정·결과 파일 원본 (merge.py, common.py, build_outputs.py)과 연결용 export_selected.py
                           common.py는 주안동 예외를 설정으로 옮긴 한 곳만 고침 (original_hashes.json changes)
tools/check_legacy.py      legacy 파일이 원본과 같은지 확인
tools/replay_check.py      기록한 응답으로 네트워크 없이 다시 돌려 결과 비교
tests/                     가짜 API로 전체 흐름 시험, 원본 JS와 결과 비교
docs/                      코드구조_설명서.html(사람용), 코드구조_설명서_AI용.md(AI 도우미용)
```

## 10. 처음 받았을 때 할 일

1. `python tools/check_legacy.py <원본 merge.py 등이 있는 폴더>`
   legacy 폴더의 세 파일은 프로젝트 문서에서 옮겨 적은 것이다. 일부러 고친 곳(common.py 한 곳)은 반영해서 비교하고, 그 밖에 한 글자라도 다르면 다른 줄을 보여 준다.
2. `python -m unittest discover -s tests` · 39개 시험이 모두 통과해야 한다. 원본 JS 비교 시험에는 Node.js가 필요하다(없으면 그 시험만 건너뜀).
3. 작은 동 하나로 `확인` → `조회`를 해 보고, 결과를 기존 결과와 비교한다.
