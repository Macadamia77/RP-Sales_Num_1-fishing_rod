"""판정과 결과 파일 · 조회 결과(A·B·NG·NV·C.json)로 건물명·대표번호·대리 연락처를 정하고 엑셀·HTML을 만든다

  common.py           주소 정리, 이름 비교, 관리사무소 판정 등 공통 규칙
  merge.py            판정 → results.json, 다음 단계 대기열
  build_outputs.py    엑셀·HTML 만드는 함수
  export_selected.py  선택된 행만 엑셀·HTML 5종으로 (수식 차단, LibreOffice 재계산)

원래 legacy/ 에서 별도 프로세스로 돌던 원본 판정 코드를 2026-10-08 옮겨 왔다. 판정 로직은 바꾸지 않았다.
"""
