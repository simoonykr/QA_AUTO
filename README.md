# QA_AUTO

QA 업무를 자동화하기 위한 개인 도구 모음입니다. Android 증거 수집, Jira 리포트, 이미지/OCR 기반 테스트, 반복 체크리스트, Excel 비교 등 실무에서 반복되는 작업을 빠르게 처리하는 스크립트와 앱을 모아둔 저장소입니다.

## 도구 목록

| 폴더 | 목적 |
| --- | --- |
| `qa-issue-collector` | Android 로그, 스크린샷, 선택 영상 수집 후 Jira 이슈 생성 및 첨부 |
| `지라 리포트 자동화` | Jira JQL 결과를 Excel 리포트로 집계 |
| `AOS 성능테스트` | Android 앱 성능 모니터링 및 로그 저장 |
| `Scrcpy기반 다중 자동화` | scrcpy 기반 화면 제어 및 이미지 자동화 |
| `OCR 이미지 매칭 테스트` | Tesseract OCR과 Excel 기준값을 이용한 화면 매칭 |
| `이미지 캡쳐 및 이미지 기반 테스트` | 화면 캡처와 이미지 기반 테스트 실험 |
| `이미지 경로 자동화 및 폴더 이미지 비교` | 이미지 경로 처리 및 폴더 단위 이미지 비교 |
| `엑셀 파일 비교` | Excel 데이터 비교 자동화 |
| `반복 체크리스트 작성` | 반복 체크리스트 작성 보조 |
| `모니터링 자동화 테스트` | 화면/로그 모니터링 자동화 실험 |
| `텍스트 추출 테스트` | 화면 또는 파일 기반 텍스트 추출 실험 |
| `AI를 이용한 TestCase_리뷰및보완작업` | 테스트케이스 리뷰/보완 실험 |

## 빠른 시작

가장 최근에 정리 중인 앱은 `qa-issue-collector`입니다.

```bat
cd qa-issue-collector
python src\main.py
```

실행 전 확인할 항목:

- Python 3.10 이상
- Android SDK Platform Tools (`adb.exe`)
- Jira Cloud API Token
- 각 도구에서 사용하는 외부 프로그램: Tesseract, scrcpy, Excel 등

## 설정 파일

실제 계정, API Token, 로컬 경로는 Git에 올리지 않습니다.

- `qa-issue-collector/config/settings.example.json`을 참고해 로컬 `settings.json`을 만듭니다.
- `settings.json`, `config.json`, `*.env`, `jira_config.json`은 `.gitignore` 대상입니다.
- 저장소에 있는 샘플 파일에는 실제 토큰을 넣지 않습니다.

## 리뷰 노트

전체 저장소 개선 항목은 [docs/repository-review.md](docs/repository-review.md)에 정리했습니다.

멀티 플랫폼 증적 수집 도구 요구사항은 [docs/platform-collector-requirements.md](docs/platform-collector-requirements.md)에 정리했습니다.
