# QA Issue Collector

Android QA 이슈 등록에 필요한 증거 자료를 자동으로 모으기 위한 로컬 도구입니다.

## v0.1 범위

- ADB 경로 설정
- Android 디바이스 검색
- 전체 앱/실행 중인 앱 목록 조회
- 앱 이름을 찾을 수 있으면 `앱 이름 (패키지명)` 형태로 표시
- 이슈 요약, 재현 절차, 실제 결과, 기대 결과 입력
- 심각도 입력은 제거하고 Jira 우선순위로 통합
- 최근 logcat 저장
- 디바이스 스크린샷 저장
- 선택 시 짧은 화면 녹화 저장
- 이슈별 폴더와 메타데이터 생성

## v0.3 Jira 설정

- Jira URL 저장
- 이메일/계정 저장
- API Token 저장
- 연결 테스트
- 접근 가능한 프로젝트 목록 조회
- 선택한 프로젝트의 이슈 타입 조회

## v0.3.5 Jira 생성 필드 조회

- 선택한 프로젝트와 이슈 타입 기준으로 생성 가능한 필드 조회
- 필수 필드 목록 표시
- 필드명, API 키, 타입, 허용값 표시

## v0.4 Jira 이슈 생성

- 선택한 프로젝트와 이슈 타입으로 Jira 이슈 생성
- 담당자 목록 조회 및 선택
- 우선순위 선택
- `Test Environment`(`customfield_10027`) 선택
- `Reproducibility`(`customfield_10028`) 선택
- 요약은 `summary` 필드에 입력
- 재현 절차, 실제 결과, 기대 결과, 앱 정보는 `description` 필드에 입력
- 연결된 디바이스 정보는 `Device Environment`(`customfield_10400`) 필드에 ADF 형식으로 입력
- `Device Environment`에는 제조사, 모델, Android 버전, SDK만 입력
- `labels` 필드가 있으면 `qa-auto`, `android` 라벨 자동 입력

## v0.5 Jira 첨부 업로드

- `증거 수집 후 Jira 등록` 버튼 추가
- 증거 수집 후 Jira 이슈 생성
- 생성된 이슈에 `logcat.txt`, `screenshot.png`, `screenrecord.mp4` 첨부
- 영상 녹화를 선택하지 않은 경우 영상 파일은 건너뜀
- 설정 탭의 단독 Jira 이슈 생성 버튼 제거
- UI 스타일, 여백, 헤더, 액션 버튼 디자인 개선

## 실행

```bat
cd /d "D:\2025 업무\에스엠\qa-issue-collector"
python src\main.py
```

## 생성 파일

수집 결과는 `data\issues` 아래에 이슈별 폴더로 저장됩니다.

```text
data/
  issues/
    2026-05-20_153012_login_crash/
      logcat.txt
      screenshot.png
      screenrecord.mp4
      issue_meta.json
      issue_summary.md
```

## 다음 단계

- 실패한 업로드 재시도 큐 추가
