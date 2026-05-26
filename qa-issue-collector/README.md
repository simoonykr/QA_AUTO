# QA Issue Collector

Android QA 이슈 등록에 필요한 증거 자료를 수집하고 Jira 이슈 생성까지 이어주는 로컬 GUI 도구입니다.

## 현재 기능

- ADB 경로 설정
- 연결된 Android 디바이스 조회
- 설치/실행 중인 앱 목록 조회
- 앱 이름 표시 및 패키지명 보관
- 이슈 요약, 재현 절차, 실제 결과, 기대 결과 입력
- 이슈별 우선순위, Test Environment, Reproducibility 선택
- 프로젝트별 담당자 선택
- Jira 프로젝트, 이슈 타입, 생성 필드 조회
- 필수 필드 목록 표시
- Device Environment 필드 자동 입력
- logcat, 스크린샷, 선택 영상 수집
- Jira 이슈 생성 후 수집 파일 첨부

## Jira 필드 매핑

| Jira 필드 | API 키 | 입력 방식 |
| --- | --- | --- |
| 요약 | `summary` | 화면 입력 |
| 설명 | `description` | 재현 절차/실제 결과/기대 결과/App 정보 |
| 프로젝트 | `project` | Jira 설정 탭에서 선택 |
| 이슈 유형 | `issuetype` | Jira 설정 탭에서 선택 |
| 담당자 | `assignee` | Jira 설정 탭에서 선택 |
| 우선순위 | `priority` | 증거 수집 탭의 이슈 정보에서 선택 |
| Device Environment | `customfield_10400` | 연결된 디바이스 정보 자동 입력 |
| Test Environment | `customfield_10027` | 증거 수집 탭의 이슈 정보에서 선택 |
| Reproducibility | `customfield_10028` | 증거 수집 탭의 이슈 정보에서 선택 |
| 레이블 | `labels` | `qa-auto`, `android` 자동 입력 |

Device Environment에는 제조사, 모델, Android 버전, SDK 버전만 넣습니다.

## 첨부 파일

Jira에는 아래 파일만 첨부합니다.

- `logcat.txt`
- `screenshot.png`
- `screenrecord.mp4` 선택 시

## 실행

```bat
cd qa-issue-collector
python src\main.py
```

## 설정

`config/settings.example.json`을 참고해 로컬 설정 파일을 만듭니다.

```json
{
  "adb_path": "C:\\path\\to\\adb.exe",
  "aapt_path": "C:\\path\\to\\aapt.exe",
  "jira": {
    "url": "https://your-company.atlassian.net",
    "email": "your-email@example.com",
    "api_token": "DO_NOT_COMMIT_REAL_TOKEN"
  }
}
```

실제 `settings.json`은 Git에 올리지 않습니다.

## 생성 파일

수집 결과는 `data/issues` 아래에 이슈별 폴더로 저장됩니다.

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

## 다음 개선 후보

- 첨부 업로드 실패 시 재시도/부분 실패 표시
- Jira 필드가 프로젝트마다 다를 때 커스텀 필드 매핑 UI 제공
- 설정값 검증 메시지 개선
- 실행 파일 패키징
