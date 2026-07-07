# Repository Review

2026-05-26 기준 저장소 전체 검토 메모입니다.

## 요약

전체 Python 파일은 컴파일 기준으로는 통과했습니다. 다만 여러 도구가 실험 단계에서 만들어진 형태라, 실행 PC가 바뀌면 바로 막힐 수 있는 하드코딩 경로와 도구별 실행 문서 부족이 가장 큰 개선 포인트입니다.

## 우선순위 1: 안전하게 바로 적용할 개선

- 루트 README를 도구 목록 중심으로 정리
- `qa-issue-collector` README를 현재 기능 기준으로 갱신
- 실제 토큰/로컬 설정 파일이 Git에 올라가지 않도록 `.gitignore` 보강
- 저장소 공통 인코딩 규칙 추가

## 우선순위 2: 기능 테스트 후 적용할 개선

- 하드코딩된 로컬 경로를 설정 파일 또는 스크립트 기준 상대 경로로 변경
- 도구별 의존성 정리: `jira`, `openpyxl`, `pandas`, `pillow`, `pyautogui`, `pytesseract`, `pynput` 등
- `지라 리포트 자동화`는 `qa-issue-collector`와 Jira 인증/설정 로직을 공통화
- OCR/이미지 자동화 결과물(`screenshot_*.png`, `extracted_text_*.txt`)은 실행 결과 폴더로 분리

## 우선순위 3: 장기 구조 개선

- 공통 패키지 분리: Jira Client, ADB Client, Excel Exporter, 설정 로더
- 각 도구별 README 추가: 목적, 실행 방법, 필요한 외부 프로그램, 입력/출력 파일
- 샘플 데이터와 실제 업무 데이터 분리
- GUI 도구는 실행 파일 패키징 후보로 관리

## 발견한 주의점

- `AOS 성능테스트/config.py`는 ADB와 저장 경로가 특정 PC 경로로 고정되어 있습니다.
- `OCR 이미지 매칭 테스트/testocr.py`는 Excel 입력 파일 경로가 특정 사용자 폴더로 고정되어 있습니다.
- `지라 리포트 자동화/QA_Daily_Report_Status.py`는 Jira URL이 코드에 고정되어 있고, 로컬 `jira_config.json`에 계정 정보를 저장합니다.
- 기존 대용량 바이너리와 이미지 파일은 scrcpy 및 테스트 자산으로 보이며, 삭제 여부는 별도 판단이 필요합니다.

## 권장 적용 순서

1. 문서와 설정 보호부터 정리
2. `qa-issue-collector`를 기준 도구로 안정화
3. Jira 인증/필드 조회 로직을 공통 모듈화
4. 기존 Jira 리포트 자동화를 새 공통 모듈에 맞춰 정리
5. OCR/이미지/성능 테스트 도구의 하드코딩 경로 제거
