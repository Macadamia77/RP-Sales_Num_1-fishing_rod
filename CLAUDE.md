코딩할 때는 아래 지침을 따릅니다.
@docs/coding-guidelines.md

## 세션 시작 · 마무리

- 시작하면 `STATE.md`(현재 상태, 최근 실행, 열린 결정)를 먼저 읽는다.
- 사용자가 마무리·최신화를 요청하면 `/wrap-up` 스킬(`.claude/skills/wrap-up/SKILL.md`) 순서대로 문서를 갱신한다.

## 실행

- 설정 파일 방식: `python run_config.py 확인|조회|114|상태` (`조회설정.toml`의 `src`, `out`, `[["조회"]]`)
- 명령줄 방식: `python run.py list|run|run114|export|status ...`
- 이 PC에서는 `python`이 Store 바로가기라 `C:\Users\kimro\anaconda3\python.exe`로 부르고 `PYTHONIOENCODING=utf-8`을 준다.
- `확인`/`list`는 API를 호출하지 않는다. `조회`/`run`은 실제 API를 부르고 오래 걸리므로 백그라운드로 돌린다.
- 시험: `python -m unittest discover -s tests` (인터넷 불필요)

## 규칙

- `.env`의 키 값은 출력하거나 파일에 쓰지 않는다. 있는지만 확인한다.
- `pipeline/` 안의 .py를 고치면 코드 해시가 바뀌어 기존 작업을 이어 돌리거나 114On을 붙일 수 없다. 고치기 전에 사용자에게 알린다.
- `legacy/`는 원본을 옮긴 판정 코드다. 고치면 `original_hashes.json`에 의도한 수정으로 기록하고 `tools/check_legacy.py`로 확인한다.
- 결과 폴더(`results/`, `결과물/`)와 `work/`는 커밋하지 않는다.
- `설명서/` 폴더는 git에서 제외했다(2026-10-08). 사용자가 저장소 밖 다른 폴더에서 관리하므로 여기서는 고치지 않는다. 로직이나 코드가 바뀌어 설명서에 반영할 내용이 생기면 사용자에게 알려 준다.
- `docs/코드구조_설명서*`는 저장소에 남아 있다. 코드 구조가 바뀌면 md와 html을 같이 고친다.
- 명령줄 방식(`run.py`)은 `--work`·`--out`을 절대 경로로 준다. 상대 경로(기본값 `work`)면 판정 단계(legacy를 `legacy/`에서 실행)가 `input.json 이 없음`으로 실패한다. 설정 파일 방식은 절대 경로로 바꿔 넘겨서 괜찮다.

## 설명 방식

- 사용자는 한국어로 묻는다. 로직을 설명할 때는 용어를 섞지 말고(주소 묶음 R·J ≠ 장소 풀 P, 주소검색 `address.json` ≠ 키워드검색 `keyword.json`), 실제 건물 하나를 예로 단계별로 따라가며 설명한다.
