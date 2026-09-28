# 지표 로그 검수

어드민 로그 조회 화면의 지표 로그를 크롤링해서 **로그정의서(검수 엑셀) 기준으로 자동 검증**하고, 결과를 정의서 사본의 AOS/IOS 결과 칸에 기입하는 GUI 도구입니다.

- 기존 검수: 로그가 찍혔는지, 내용/수치 값이 정의서대로인지 확인
- 추가 검수: 액션 이후 **수치 변동이 정확히 적용됐는지** (이전 ± 변동 = 최종, 직전 로그와의 연속성)

## 실행

```bat
pip install -r requirements.txt
python crawl_log_check_gui.py
```

- Python 3.10 이상, Chrome 설치 필요
- 처음 **Start Browser** 시 어드민 로그 조회 페이지 주소를 한 번 입력하면 `crawl_log_check_config.json`에 저장됩니다.

## 사용 순서

1. **Start Browser** → 어드민 로그인, 이용자(playerId) 검색 조건 입력 후 조회 (로그인/검색은 수동)
2. **로그정의서 로드** → 검수 엑셀 선택 (`writeResourceLog` / `writeItemLog` / `writeActionLog` 시트 사용)
3. **전체 페이지 크롤링** → 모든 페이지 수집 후 자동 검증
   - 페이지 이동 버튼을 못 찾으면 현재 페이지만 수집합니다. 이 경우 **누적** 체크 후 페이지를 직접 넘기며 **현재 페이지 크롤링**을 반복하세요.
4. **정의서에 결과 기입** → `원본명_자동검수_날짜.xlsx` 사본 생성 (원본은 수정하지 않음)
   - 정의서 각 행의 AOS/IOS 칸: Pass / Fail
   - 시트 맨 오른쪽 `자동검수 상세` 컬럼: 로그 건수, 실패 사유
   - `자동검수_로그` 시트: 크롤링한 전체 로그 + 판정 (정의서에 없는 로그 포함)

표에서 행을 더블클릭하면 파싱된 필드, 매칭된 정의서 행, **같은 `log_tx`로 묶인 로그**(한 액션으로 발생한 로그 묶음)를 볼 수 있습니다.

## 검증 항목

| 판정 | 내용 |
| --- | --- |
| 미정의 | 정의서에 없는 로그 (원인 힌트 표시: 재화 매핑 없음, 같은 action 의 정의 reason 등) |
| Fail | 정의서에 설명이 있는 필드가 로그에 비어 있음 / category·label·action 불일치 / 계산 불일치 / 연속성 끊김 / 정의서상 `삭제` 로그 발생 |
| 경고 | 정의서 로그 분류와 실제 로그타입 불일치 (예: CashItemLog ↔ resource) |
| 대상아님 | checkAuth, idpLogin 등 정의서 대상이 아닌 로그타입 |

수치 검증 규칙

| 로그타입 | 계산 | 연속성 기준 |
| --- | --- | --- |
| item | `quantityBefore ± quantity = quantityAfter` (modType add/sub) | 플레이어 + itemId |
| cashitem / resource | `amountBefore + delta = amount`, modType과 delta 부호 일치 | 플레이어 + rCurrency |
| action | `valueNoBefore + valueNo = valueNoAfter` (설정의 `action_value_reasons` 에 있는 reason만) | - |

연속성은 같은 그룹의 로그를 `modTime` 순으로 정렬해 **직전 로그의 최종값 = 이번 로그의 이전값**인지 확인합니다. 조회 범위 중간의 로그가 빠지면(기간/로그타입으로 일부만 조회) 끊김으로 잡힐 수 있으니 전체 로그로 조회하는 것을 권장합니다.

## 설정 (`crawl_log_check_config.json`)

게임마다 다른 값은 설정 파일로 관리합니다. 파일이 없으면 기본값으로 자동 생성되며, 예시는 `crawl_log_check_config.example.json` 입니다. 로컬 설정 파일은 Git에 올리지 않습니다.

| 키 | 설명 |
| --- | --- |
| `admin_url` | Start Browser 시 여는 어드민 로그 조회 페이지 |
| `currency_map` | 로그의 `rCurrency` → 정의서 재화명 (예: `FREE_GOLD` → `골드`). GUI의 **재화 매핑 설정**에서 수정 가능 |
| `action_value_reasons` | 수치 계산을 검증할 action reason 목록 |
| `ignore_missing_fields` | 필드 누락 검사에서 제외할 필드 (기본: `itemName`, `itemGrade`) |

## 파일

| 파일 | 역할 |
| --- | --- |
| `crawl_log_check_gui.py` | GUI, 크롤링(Selenium), 필터/저장 |
| `log_verifier.py` | 로그 파싱, 정의서 로드/매칭, 검증, 정의서 사본 기입 |
