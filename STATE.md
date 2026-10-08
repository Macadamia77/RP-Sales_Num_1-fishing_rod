# STATE · 현재 작업 상태

> 세션을 시작하면 이 파일부터 읽는다. 세션을 마칠 때 `/wrap-up`으로 갱신한다.
> 마지막 갱신: 2026-10-08

## 1. 코드 기준

- main `230c6a3` (PR #6 · HTTP 세션 기본 User-Agent를 브라우저 값으로)
- 작업 브랜치 `claude/kb-button-state` · main에 머지 대기 (PR 생성은 웹에서. 이 PC에는 `gh` 없음)
  - HTML 카드 링크 버튼에 KB부동산 추가 (`legacy/build_outputs.py`, `original_hashes.json`에 의도한 수정으로 기록, `tools/check_legacy.py` 통과)
  - `설명서/` 폴더 git 관리에서 제외 + `.gitignore` (사용자가 저장소 밖에서 관리. 로컬 파일은 남아 있음)
  - `.env.example` 삭제 (사용자 결정. README 안내도 `.env` 직접 만들기로 고침)
  - `결과물/` ignore, `조회설정.toml`(src·out), README 실행 메모, docs 코드구조 설명서 PR #6 반영
  - `STATE.md`, `CLAUDE.md`, `.claude/skills/wrap-up/SKILL.md`
- 원격에 main에 안 들어간 브랜치 2개 · 손대지 않음
  - `claude/cowork-context-sharing-3pf8t6` (`9689f2b`) · 조회설정.toml 내용에 묶인 시험을 풀고 문서의 시험 개수를 40개로 맞춤
  - `claude/brave-carson-g1hwz1` (`e122b3d`) · 조회설정.toml 기본 조회 범위를 시험 기대값(중구·미추홀구)에 맞춤
- 시험: 40개 중 38 통과, 1 실패(`test_config_union_env_and_last_job`, 조회설정.toml 값에 묶인 시험. 위 첫 브랜치가 고침), 1 건너뜀(Node.js 없음)

## 2. 이 PC 실행 환경

- `python` 명령은 Microsoft Store 바로가기라 안 됨 → `C:\Users\kimro\anaconda3\python.exe` (3.14, pandas·openpyxl·requests 설치됨)
- 한글 출력: `PYTHONIOENCODING=utf-8`
- git은 HTTPS로 GitHub에 연결됨(pull·push 가능). `gh`(GitHub CLI)는 설치 안 됨
- `.env` 있음, 키 5개 모두 채워짐 (값은 출력하지 말 것)

## 3. 최근 실행

| 날짜 | 범위 | 작업 ID | 결과 |
|---|---|---|---|
| 2026-10-07 | 미추홀구 용현동, 등급 전체 (`원본 csv/콜리스트_인천광역시_미추홀구_2026-09-23.csv`) | `6fd8ee93db0689325f189220` | 926건 오류 0 · 건물명 300/356 · 대표번호 9/924 · 대리만 914 · 대리도 없음 1 · 사람 확인 58 |
| 2026-10-08 | 위 작업 `export` (API 호출 없음, KB 버튼 확인용) | 같음 | 숫자 같음 · KB 버튼 활성 719, 흐림 206 |

- 최신 결과: `결과물/6fd8ee93db0689325f189220/core/20261008-100446/미추홀구_용현동/` (이전: `…/20261007-145605/`)
- 작업 상태: `work/jobs/6fd8ee93db0689325f189220/` (지우지 말 것. 정답 데이터·114On에 필요)
- `.last_job.json`에 기억됨 → `run_config.py 114`로 바로 114On을 붙일 수 있음 (아직 안 함)
- 대표번호가 적은 이유: KB 720건 매칭(빌라 644) 중 관리사무소 전화가 있는 곳 9

## 4. 알려진 문제

- **명령줄 `run.py`의 상대 경로 버그** (2026-10-08 발견): `--work` 기본값 `work`(상대 경로)를 그대로 legacy에 넘기는데, legacy는 `legacy/` 폴더에서 실행돼 `input.json 이 없음`으로 판정 단계가 실패한다. `run`·`export`·`run114` 모두 해당. 시험은 임시 폴더 절대 경로를 써서 못 잡음. 지금은 `--work`, `--out`을 절대 경로로 주면 됨. 고치려면 `pipeline/cli.py`(또는 `service.py`)에서 절대 경로로 바꿔야 하는데, 그러면 코드 해시가 바뀌어 기존 작업에 114On을 붙일 수 없음
- `run_config.py` 도움말 주석과 `docs/코드구조_설명서_AI용.md`에 `.env.example` 언급이 남아 있음
- 로직: 주소가 다르고 200m를 넘는 단지 밖 관리사무소는 장소 풀에서 버려짐(`kakao.py:151`). `role` 0순위가 `부동산` 분류 전체를 중개사로 봄

## 5. 열린 결정 · 할 일

- [ ] 브랜치 `claude/kb-button-state` PR 만들고 머지
- [ ] `run.py` 상대 경로 버그 고칠지 (용현동 114On을 먼저 붙인 뒤 고치는 게 안전)
- [ ] 용현동에 114On 추가 조회 돌릴지 (915건 × 4.5초 ≈ 1시간+, one114.py 실접속 미검증)
- [ ] 미병합 브랜치 2개 처리
- [ ] 저장소 밖 설명서에 반영할 것: 2026-10-07 로컬 `설명서/`에 고친 내용(로직 설명서 PR #6 반영, 용현동 실행 결과, Q&A 11장). 로컬 파일에 그대로 있음
