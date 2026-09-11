# 프론트엔드·백엔드 공용 작업 현황

마지막 갱신: 2026-09-11

## 2026-09-11 재검증 피드백 2차 반영

- 두 분석 화면: 요청 시작 안내, POST 수락 직후 QUEUED 패널, 30초 요청 timeout, 닫기 전까지 유지되는 공통 알림을 적용했다. 기존 2.2초 자동 소멸 알림만으로 오류를 놓치는 문제를 보완했다. 페이지 우선 polling 오류 후 시작 버튼이 잠기지 않도록 상태 해제.
- 시작 URL 초기/환경 변경 시 자동 입력을 제거했다. QA가 명시한 URL만 사용한다.
- `단계 1: 1.` 등 importer 래퍼를 벗긴 후 빈 번호를 제거한다. 연속 동일 URL navigate를 중복 생성하지 않는다. 로딩 대기는 wait/domcontentloaded로 처리하며 selector를 요구하지 않는다(비동기 API·SPA 데이터 로딩까지 보장하지 않음).
- selector 미해결 단계가 있으면 구조화 응답은 MANUAL_REVIEW_REQUIRED/페이지 분석 필요로 반환한다. 기존 저장 버전은 재구조화가 필요하다.
- 전체 백엔드 102 passed/경고 4건, TypeScript 및 frontend Docker 빌드 통과, AI 0회. 지정 public compose로 배포 완료.
- 실제 Chromium UI: 시작 URL 공란, 허용 도메인 오류 지속 표시, AI 시나리오 분석 완료 패널, TC 구조화 검토 분석 결과 패널 모두 확인. 합성 TC 사용; 사용자 XLSX 자체 재업로드 검증은 이번 테스트에서 수행하지 않았다.
- 재실행 스크립트 `backend/scripts/validate_discovery_ui_local.py` 추가. localhost 전용 데모 로그인, 비밀값 출력 없음, 합성 분석 이력 생성.

## 2026-09-11 DISCOVERY_FAILED 수정 및 대상 URL 방어

- 실제 Worker 로그의 반복 NameError(hashlib import 누락)를 수정했다. 합성 TC의 기존 discovery 경로가 실배포에서 COMPLETED로 완료됨을 확인했다.
- 기존 TC discovery는 raw_text의 단일 명시 URL을 선택하고 환경 allowlist와 검증한다. URL 누락/복수/허용 범위 위반이면 422로 차단하며 환경 기본 demo-target으로 대체하지 않는다. Worker에서도 재검증한다. 실행 계획·미리보기에서도 URL 없는 navigate의 환경 기본값 자동 삽입을 제거했다.
- 규칙 기반 구조화에서 TC ID·제목·전제조건·독립 단계 번호 제외, 번호 접두어 정리, 명시적인 기대 결과/이동 확인 문장 assertion 우선 분류. 마지막 행동을 임의 assertion으로 변경하지 않는다. 규칙 기반이므로 복잡한 자유 문장의 의미 분류 전체 해결은 아니다.
- 오류 분류와 안전한 warning 메시지 추가, 원본 브라우저 예외/URL을 로그에 노출하지 않는다. 미해결 요소는 NEEDS_REVIEW/executable=false이며 빈 검증 목록도 실행 가능으로 표시하지 않는다.
- 정식 전체 **100 passed**, 기존 경고 4건, TypeScript 통과, AI 0회. `.env.public` + `compose.public-demo.yml` 배포. 페이지 우선 PASS 3단계, 기존 discovery COMPLETED, 의도적 FAIL 및 MinIO PNG 다운로드 200 검증.
- 프론트 요청: 오류 계약의 code/message 표시, 대상 URL·환경 사전 표시, 파일 가져오기/TC 선택을 페이지 우선 흐름에 연결. 구조화 automationStatus를 실행 가능으로 간주하지 않고 discovery/plan executable을 확인한다. 좁은 화면 레이아웃은 프론트 후속.
- 과거 저장된 잘못된 구조화 버전은 변경하지 않았다. 수정 전 데이터는 원문 URL을 명시하고 새 버전으로 재구조화/재분석한다.

## 2026-09-09 Docker 복구·로컬 배포 통합 검증 완료

- Docker Desktop 시작 실패 원인은 접근 불가 runtime 소켓(sailor-ingest.sock, engine.sock). Desktop 프로세스 종료 후 소켓 전용 폴더를 백업 이름으로 이동해 재생성하여 엔진 running 복구. DB·볼륨 삭제/초기화 없음.
- `.env.public` + `compose.public-demo.yml`로 최신 main 빌드·배포 및 migration 성공. 프로세스 환경에서 AI_ENABLED=false, AI_MAX_CALLS_PER_RUN=0을 override했고 실행 중 API에서도 확인했다. 향후 재배포도 이 override를 유지해야 한다(.env.public 자체는 수정하지 않음).
- 로컬 `http://localhost:8080`, health 200, 미인증 API 401, 기존 데모 자격증명 로그인 성공. PostgreSQL·Redis outbox·Playwright Worker 실제 페이지 우선 3단계 PASS: `6c0b1b66-2e7b-4997-b685-756ab86a7784`.
- 합성 TC 의도적 실패 `bef8ec0a-fb51-4fa3-ab25-217cd2bddaee`는 FAIL, MinIO 증적 다운로드 200·PNG signature 검증 완료. 테스트 레코드는 추적을 위해 보존했다.
- `backend/scripts/validate_page_first_local.py` 추가: localhost 고정, 로컬 env에서 자격증명 읽기, 비밀값 출력 없음. AI 비활성 배포 확인 후 실행하며 실제 DB에 합성 테스트 이력을 추가한다. DB 동시성 부하 검증은 이번 범위 아님.
- 전체 정식 테스트 89 passed/경고 4건, 실제 AI 0회. frontend Docker 빌드 성공. DB/Redis/MinIO host port 미공개 확인.
- 외부 HTTPS quick tunnel 생성은 보안 검토에서 공개 노출 승인 부족으로 차단됨. 우회하지 않았으며 사용자 외부 공개 승인 후 진행한다. 현재 전달 가능한 실제 통합 페이지는 해당 PC의 localhost뿐이다.

## 2026-09-09 실제 Chromium 컴포넌트 검증

- 최신 main 확인 후 실제 Chromium 회귀 테스트 추가. 합성 HTML만 사용하며 브라우저 외부 요청을 전부 차단한다. 요소 수집(중복·비밀 필드 제외), 숨김 요소의 시나리오 제외, 검토 선택, Worker 표시 assertion 수행, DOM 변경 후 DISCOVERY_STALE 차단을 검증했다.
- 실행: `RUN_BROWSER_TESTS=1`, `AI_ENABLED=false`, `AI_MAX_CALLS_PER_RUN=0`, 빈 OPENAI_API_KEY로 정식 테스트 5개 파일 실행 → **89 passed**, 경고 4건. TypeScript 통과, 실제 AI 0회. 브라우저 테스트는 기본 비활성이고 `python -m playwright install chromium` 후 명시적으로 활성화한다.
- Docker Desktop 재기동 요청 후에도 Linux 엔진 연결 불가. PostgreSQL migration·동시성, Redis 큐, MinIO 증적을 포함한 전체 Worker 통합 및 Temporary Staging 배포는 미완료다. 컨테이너 재생성·포트 변경·DB 변경 없음.
- API/공유 타입 변경 없음. 사용자 OneDrive 충돌 복사본 보존. 다음은 Docker 엔진 복구 후 `.env.public` + `compose.public-demo.yml` 환경의 통합 검증이다.

## 21:17 백엔드 정기 확인: 4a14a45 계약 회귀

- 프론트 `4a14a45` 반영 확인. 초기 페이지 검토 행·Mock 승인 방어·승인 환경 고정·늦은 응답 방어의 이전 요청이 반영됐다.
- 실제 FastAPI 앱 경로를 이용한 비교 → 검토 저장 → 오래된 revision 409 → 최신 GET 응답 회귀 테스트와 신규 네 경로의 미인증 401 테스트를 추가했다. DB는 테스트 대역이며 PostgreSQL 통합 검증을 대체하지 않는다.
- 전체 정식 백엔드 88 passed/기존 경고 4건, TypeScript 통과, 실제 AI 호출 0회. API·타입 변경 및 배포 없음. 사용자 충돌 복사본 보존.

## 20:55 정기 main 확인: 1c15256 프론트 반영

- 새 시나리오의 초기 PAGE_ONLY/PENDING 행을 Mock에도 추가하고, 빈 실행·미검토 승인 차단, 승인 멱등성, 근거 없는 ADD/IGNORE 차단을 백엔드와 맞췄다.
- 승인 응답 `environmentId`를 실행 설정에 전달해 해당 환경으로 고정하고, 다른 환경 선택을 막는다. 일반 TC 승인 흐름은 기존처럼 환경을 선택할 수 있다.
- 검토·승인 비동기 응답에도 requestGeneration 검사를 적용해 입력 변경 이후 늦은 응답이 과거 상태를 복구하지 않도록 보완했다.
- 검증: TypeScript 5.9 타입 검사와 `git diff --check` 통과. Vite 번들은 기존 Windows 접근 위반 제약을 따른다.

## 20:47 정기 main 확인: b381700 연동 보완

- 프론트 `b381700`을 fast-forward 반영했다. TC 선택 입력 없이 생성한 초안에 comparisons가 없어 승인할 수 없는 백엔드 연동 문제를 수정했다.
- 새 초안은 검증된 단계마다 PAGE_ONLY/PENDING 검토 행을 반환한다. TC 비교 없이도 명시적으로 검토·저장 후 승인 가능하며 자동 승인하지 않는다. TC 비교를 실행하면 기존처럼 행과 선택을 재생성한다.
- 검증: 백엔드 정식 전체 86 passed, 경고 4건, TypeScript 검사 통과, 실제 AI 호출 0회. 배포 작업은 하지 않았다.
- 프론트 후속 요청: Mock 생성도 동일한 초기 PAGE_ONLY 행을 반환하도록 맞추고, 승인 Mock의 빈 실행 차단·멱등성·근거 없는 ADD/IGNORE 차단을 서버와 맞춘다. 승인 응답 environmentId를 실행 설정에 전달/고정한다(서버는 다른 환경 실행을 거절한다). 검토·승인 응답에도 기존 requestGeneration 검사를 적용하여 입력 변경 뒤 늦은 응답이 과거 상태를 복구하지 않게 한다.

## 페이지 우선 백엔드 2차: TC 비교 → 검토 저장 → 승인·Worker 연결

- 프론트 `a35df71`을 fast-forward 반영하고 기존 Mock UX를 보존했다.
- TC 단순 추출, 시나리오 비교, 선택·문구 저장, 서버 revision 충돌 방지, 승인 API 구현. 승인 시 READY TC 버전과 감사 snapshot을 같은 트랜잭션으로 저장한다.
- 승인된 versionId는 기존 실행 계획 조회·실행 생성 API에 연결한다. Worker는 접속 후 실제 요소 fingerprint를 비교하고 변경되면 DISCOVERY_STALE로 중단한다.
- 자동 실행 범위는 기존 1페이지 data-testid 표시 assertion에 한정된다. AI 의미 분석·클릭·입력·iframe 탐색은 미구현이며, 미확인 TC는 수동/제외 선택만 가능하다. 문구 변경은 실행 의미를 바꾸지 않는다.
- 백엔드 정식 전체 테스트 **84 passed**, 기존 경고 4건, 실제 OpenAI 호출 **0회**. OneDrive 충돌 복사본 테스트는 제외하고 사용자 파일은 보존했다.
- 공유 타입 갱신 후 `npm run typecheck` 통과. 로컬 누락 의존성만 복구했으며 package/lock 파일은 변경하지 않았다.
- 프론트 요청: FRONTEND_BACKEND_SYNC.md의 2차 계약에 따라 Mock 비교·로컬 revision을 서버 응답으로 교체하고 승인 응답 versionId/environmentId로 기존 실행 API를 연결한다. 전체 선택 검토, 수동·제외 범위 표시와 409 재조회 UX를 유지한다.
- Docker Linux 엔진 연결 불가로 실제 DB migration·브라우저 E2E·Temporary Staging 배포 검증은 미완료. 배포 시 `.env.public` + `compose.public-demo.yml`만 사용하며 이번 작업에서는 컨테이너를 변경하지 않았다.
- 다음 백엔드: role/label·iframe·action 가능성 검증, 실제 AI 시나리오/의미 비교(별도 승인 전 호출 금지), DB·Worker 통합 검증.

## 페이지 우선 백엔드 1차 진행 상황 (이력, 2차 내용 우선)

- 정식 백엔드 테스트 전체 `73 passed`, 경고 4건, 실제 OpenAI 호출 0회. URL 제한·입력 제한·검증 요소 선택·조직 범위·미완료 분석 차단 회귀 포함.

- TC 없는 페이지 분석 시작·조회, Worker outbox 처리, 검증 요소 기반 시나리오 초안 생성·조회와 저장 모델 추가.
- 현재 범위는 1페이지 data-testid 기반 읽기 전용 표시 검증, PAGE_DISCOVERY 근거, RULE_BASED/0회, executable=false이다. AI 시나리오 생성 전체 완료가 아니다.
- 새 API 계약과 프론트 공통 타입을 FRONTEND_BACKEND_SYNC.md와 src/api/types.ts에 반영했다.
- 다음: role/label 후보와 iframe 수집 확대, AI 생성·TC 비교·검토 revision·승인·실행 연결. 전체 페이지 우선 백엔드 완성 전까지 프론트는 초안 조회까지만 연결 가능하다.
- Docker Linux 엔진 미실행으로 migration·브라우저·실제 API 통합 검증/배포는 대기 상태다.

이 문서는 두 담당 에이전트의 공용 전달판이다. 각 담당자는 작업 시작 전에 읽고, 작업 완료 커밋에서 자기 영역을 직접 갱신한다.

## 현재 공동 목표

Firebase UI 데모를 실제 FastAPI·PostgreSQL·Redis·MinIO·Playwright Worker와 연결된 로그인 가능 통합 데모로 전환한다. 실제 AI API 호출은 통합 구조가 안정될 때까지 사용하지 않는다.

자연어 TC를 실행 가능한 계획으로 만들기 위한 다음 설계는 [`AI_PAGE_DISCOVERY_REQUIREMENTS.md`](AI_PAGE_DISCOVERY_REQUIREMENTS.md)를 기준으로 한다. QA에게 selector 작성을 요구하지 않고 AI 구조화와 Playwright 페이지 탐색·후보 검증을 분리한다.

QA의 실제 자연어 TC 작성 방식, XLSX TC별 분리, AI 시나리오 설계, 잘못된 계획 방어와 실행 이력 요구사항은 [`QA_NATURAL_LANGUAGE_AUTOMATION_REQUIREMENTS.md`](QA_NATURAL_LANGUAGE_AUTOMATION_REQUIREMENTS.md)를 공통 기준으로 사용한다.

2026-09-08 합의 방향: 자연어 TC를 먼저 완전한 실행 명세로 변환하는 흐름의 정확도 한계를 줄이기 위해 **페이지 우선 시나리오 생성**으로 전환한다. Playwright가 실제 페이지의 검증 가능한 요소·흐름을 수집하고 AI가 기본 시나리오를 작성한 뒤, 자연어 TC는 대상·행동·기대 결과와 누락 검증을 보강하는 입력으로 사용한다. 단계별 `PAGE_DISCOVERY | TEST_CASE | AI_SUGGESTION | MANUAL` 출처와 TC 비교 결과를 QA가 검토·승인한다.

## 환경 운영 합의

- `Local`: 현재 개발 PC의 Docker 통합 환경이다. `http://localhost:8080`은 해당 PC에서만 사용한다.
- `UI Staging (Mock)`: 현재 Firebase에 배포된 `https://tracepilot-demo.web.app`이다. 프론트 화면 검수용이며 Mock API를 사용하므로 실제 FastAPI·DB·Redis·MinIO·Playwright 실행과 연결된 통합 스테이징은 아니다.
- `Temporary Staging`: 회사·관계자 검수를 위한 임시 HTTPS 터널이다. 현재 PC의 `localhost:8080`으로 연결하며 PC, Docker Desktop, 터널 프로세스가 모두 실행 중이어야 한다.
- `Staging`: 향후 별도 서버와 고정 HTTPS 주소로 운영한다. 가입·승인, 자동화, API 통합을 라이브 반영 전에 검증한다.
- `Production`: 실제 사용자용 정식 도메인과 별도 DB·비밀정보를 사용하는 라이브 환경이다.

현재 UI Staging은 이미 운영 중이다. 백엔드의 다음 단계는 Temporary Staging 주소를 열어 Firebase Mock 화면과 별도로 실제 API·Worker가 연결된 통합 데모를 회사에서 확인하는 것이다. 회사 외부 접속 공인 IP 후보는 `59.13.192.250`, `59.12.234.2`이며, 고정 Staging에서는 이 주소를 접근 허용 정책에 사용할 수 있다. 임시 터널 단계는 데모 로그인으로 보호하고, IP 제한은 고정 터널·도메인 구성 시 적용한다.

환경별 DB, 세션 서명 키, 계정, API 키는 공유하지 않는다. 실제 AI는 로컬 TC 구조화 검증에만 예산·캐시·1회 제한을 적용해 활성화했으며 Playwright 실행은 `maxAiCalls=0`을 유지한다.

## 프론트엔드 현황

완료:

- 로그인·로그아웃·세션 복구 및 승인 상태 UX
- 실행 환경·테스트 계정·실행 정책 API 연결
- 서버 정책에 따른 실행 선택 제한
- 실행 SSE, polling fallback 및 증적 표시
- AI 호출 기본값 `0`
- Firebase Mock 데모 빌드
- Firebase 최신 main 재배포 및 공개 화면 회귀 테스트
- AI 토큰 없이 규칙 기반 TC 구조화·검토·실행 흐름 명시
- 실행 정책의 `maxAiCalls`에 따라 AI 호출 선택지를 `0회` 또는 `0회/1회`로 제한하고, 기본 실행 요청과 Mock 정책을 `0`으로 유지
- Firebase Mock 실행 완료 시 `navigate/fill/click/assert` 4단계 상세가 결과 화면에 표시되도록 공개 데모 회귀 보완
- 테스트 케이스 TXT/CSV/XLSX/DOCX 가져오기 UI를 실제 `/test-cases/import` multipart API에 연결하고 10MB·확장자 검증, 로딩·경고·오류 표시 반영
- 구조화 API의 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED`를 전용 분할 검토 상태로 표시하고 감지 TC 수·원문 길이 안내 및 승인·실행 차단
- 새 TC 시작·파일 교체·승인 후 원문 편집 시 이전 승인 `versionId`를 즉시 무효화해 과거 구조화 결과 실행 방지
- 실행 설정과 생성 사이에 예상 시나리오·UUID·구조화 출처·필수 파라미터 검증 화면을 추가하고, 실행 모니터의 고정 로그인 데모 화면 제거
- 실제 동일 출처 배포에서 상태 확인이 `/api/v1/health`로 잘못 조합되던 문제를 수정하고 `/health` 직접 호출로 통일
- 구조화 검토 화면에서 실행 환경별 계획을 조회하고 warning의 `stepNo`·`stepId`·`missingFields`로 오류 단계를 강조
- 승인 전 selector·URL·operator·expected·value·secretRef·assertionType 부분 편집을 PATCH API에 연결하고 반환된 revision·plan hash·warnings·executable을 즉시 반영
- 서버 실행 계획의 `executable=true`일 때만 검토 승인 버튼을 활성화하고, 마스킹된 value는 사용자가 직접 변경하지 않는 한 PATCH body에서 제외
- 구조화 검토 단계와 편집 패널에 삭제 버튼·확인 절차·중복 요청 방지를 추가하고 DELETE 응답의 재번호된 단계, revision, plan hash, warnings, executable을 즉시 반영
- 단계 삭제의 `TC_STEP_NOT_FOUND`는 계획 새로고침으로 복구하고 `TC_VERSION_NOT_REVIEWABLE`은 승인 완료 버전 수정 불가로 구분 안내하며, Mock도 버전·환경별 연속 삭제와 전체 삭제 차단 상태를 재현
- 구조화 검토 화면에 페이지 분석 시작, 상태 polling, 탐색 페이지 fingerprint, 단계별 selector 후보·검증 결과·신뢰도, 복수 후보 선택과 결과 적용 UI를 연결
- 페이지 분석 요청은 현재 `maxPages=1`, `maxAiCalls=0`으로 고정하고 적용 응답의 steps·revision·planHash·warnings·executable을 승인 기준에 즉시 반영하며 Mock에도 동일 흐름을 구현
- XLSX 가져오기 응답의 21개 TC를 목록으로 표시하고 사용자가 선택한 한 건만 독립 구조화하는 UI/API 연결
- 구조화 결과에 자동화 가능성 상태와 사유를 표시하고 실제 실행 이력 API로 대시보드 최근 실행·집계를 표시
- 실행 이력 전용 화면을 실제 `/executions` API에 연결하고 상태·TC ID 필터, 20건 페이지 이동, 단계·오류·증적 요약 및 실행 상세 진입 구현
- 페이지 우선 `AI 시나리오` 화면과 Mock UX 추가: 환경·시작 URL·선택적 TC 입력, 읽기 전용 분석 polling, 검증 요소·페이지 fingerprint, PAGE_DISCOVERY 단계 초안과 TC 보강 미리보기 표시
- 백엔드 1차 `/page-discoveries`·`/page-discoveries/{id}`·`/page-discoveries/{id}/scenarios` 계약 연결. 현재 미지원인 TC 비교·승인 액션은 비활성화하고 AI 0회·실행 불가 초안임을 명시
- TC 비교·편집 Mock UX 추가: `MATCHED | TC_ONLY | CONFLICT | NOT_AUTOMATABLE` 상태, 추가·제외·수동 검증·문구 수정 선택, 로컬 revision 증가와 미결정 건수 표시. 분석 입력 변경 시 과거 discovery·scenario·편집 상태를 폐기하고 늦은 응답을 무시하며, 서버 revision·승인·실행은 계약 전까지 차단
- 백엔드 2차 시나리오 비교·검토·승인 API 연결: 서버 `comparisons` 전체 상태와 `PAGE_ONLY` 표시, 선택별 PATCH 저장, 서버 revision 기준 갱신, `SCENARIO_REVISION_CONFLICT` 발생 시 최신 상태 조회 후 수동 재검토, 승인 응답 `versionId`를 기존 실행 설정·계획·Worker 흐름에 전달
- Mock API도 비교·선택·revision·승인 흐름을 동일하게 재현하며 근거 없는 ADD를 UI에서 차단. 수동·제외 항목은 실행 통과 범위가 아님을 유지하고 실제 AI 호출은 0회

백엔드에 요청:

- 외부 FastAPI HTTPS 주소와 `/api/**` 연결 방식
- 운영 쿠키·CORS·SSE 인증 확인
- 가입·승인 API 계약

다음 작업:

- 페이지 우선 승인 후 실제 DB·Playwright Worker 통합 회귀 및 `DISCOVERY_STALE` 재분석 UX 검증
- 백엔드가 제공하는 후속 단계 편집·순서 변경·AI 보강 제안 계약 연결
- 가입 신청·승인 대기·거절 화면을 백엔드 계약에 맞춰 연결
- 다중 TC 자동 분리 API가 확정되면 선택·분리·일괄 저장 UX 연결

## 백엔드 현황

완료:

- 테스트 케이스·구조화·실행 생성·조회·중단·재시도 API
- 실행 환경·테스트 계정·실행 정책 API
- SSE 실행 이벤트와 PNG 증적 API
- PostgreSQL·Redis outbox·MinIO·Playwright Worker 로컬 구성
- 공용 데모 세션 인증
- 운영 Cookie Secure·SameSite·Domain 설정 및 안전성 검증
- health endpoint와 표준 오류 envelope
- TXT·CSV·XLSX·DOCX 테스트 케이스 업로드·텍스트 추출 API
- Windows Docker Desktop 로컬 통합 환경 실행
- 로그인 → 실행 생성 → Redis → Playwright Worker → `PASS` 전체 흐름 검증 (`maxAiCalls=0`)
- OpenAI 서버 환경변수와 실행당·일일 예산 설정 추가; 키가 없으면 정책을 `maxAiCalls=0`으로 강제하는 fail-closed 보호 적용
- OpenAI 키는 로컬 비밀파일에 입력 완료했으나 실제 Gateway·비용 원장·예산 차단은 아직 미구현이므로 API 호출은 시작하지 않음
- 최신 main 로컬 Compose에서 실제 Chromium 성공·실패 TC 통합 검증 완료
- 실패 assertion용 재현 가능한 migration `0005_seed_worker_failure` 추가
- `.env.public`의 DB·MinIO·데모 인증·세션 비밀값을 실행 중 컨테이너에서 노출 없이 복구
- 필수 비밀값 누락 시 Compose 실행 전 중단하는 PowerShell 시작 검증 추가
- TC 구조화 전용 OpenAI Gateway와 요청당 최대 1회 제한 구현
- 토큰·비용 원장, UTC 일일 `$1` 예산 선차단, 조직·모델·동일 입력 캐시 구현
- 구조화 응답 `aiUsage` 및 표준 AI 오류 계약 문서화
- API 컨테이너 재생성 후에도 Nginx가 Docker DNS를 갱신하도록 reverse proxy `502` 복구 보완
- AI 비활성 구조화가 원문과 무관한 고정 로그인 예제를 반환하던 문제 수정
- 구조화 요청의 9,613자 원문 무손실 전달 및 다중 TC 102건 감지 회귀 테스트 추가
- 다중 TC를 단일 성공 결과로 축약하지 않고 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED` 검토 오류로 반환
- 구조화 요청마다 실제 TestCase와 고유 UUID TestCaseVersion을 생성하고 `raw_text`, `structured_spec`, `REVIEW_REQUIRED` 상태 저장
- `POST /api/v1/test-case-versions/{versionId}/approve` 추가 및 승인 후 `READY` 전환
- 실행 생성 시 실제 UUID 버전의 조직·프로젝트·READY 상태 검증, `tcv-new-v1` alias 제거
- Worker가 execution의 동일 조직·프로젝트 버전과 저장된 `structured_spec.steps`만 조회·실행하도록 강화
- 프론트 검토 승인 버튼을 실제 승인 API에 연결하고 반환 `versionId`를 실행 설정·생성 요청까지 전달
- 실행 계획 조회 API, action별 필수 파라미터·URL allowlist·지원 action 서버 검증 추가
- 승인과 실행 생성을 잘못된 계획에서 차단하고 입력값을 계획 응답에서 마스킹
- 실행 생성 시 plan hash/revision/환경/단계 수 snapshot 저장, Worker 시작 전 DB 계획과 재검증
- 실행 상세에 계획 UUID·hash·revision·환경·계획/실제 단계 수와 단계별 `planStepId` 추가
- 프론트 실행 예정 시나리오를 서버 `executable`, `warnings` 단일 기준으로 전환
- XLSX 구조화 요청 전 결과 집계·보고서 메타데이터 영역을 제외하고 실제 TC 헤더부터 전송하며 제외 행 수를 UI에 표시 (`Expected Result` 유지)
- 최신 `main` `3ec9900`을 기존 Cloudflare Quick Tunnel에 공개용 Compose로 재배포하고, 파일 업로드부터 실제 Worker 성공·실패까지 재현 가능한 HTTPS 검증 스크립트 추가
- 실행 계획 오류에 `stepNo`·`stepId`·`missingFields`를 추가하고 URL assertion은 selector 없이, text/element assertion은 selector 필수로 분리 검증
- 승인 전 `PATCH /test-case-versions/{versionId}/steps/{stepId}`로 selector·URL·operator·expected·value/secretRef를 수정하고 revision/hash를 재계산하는 API 추가
- 원문에 없는 AI selector를 제거하고 `assumptions`에 검토 사유를 남기는 selector grounding 보호 추가
- XLSX TC 헤더 이전 결과 집계·보고서 메타데이터를 제외하고 Expected Result를 보존하며 제외 행 수·감지 TC 수 warning 반환
- 승인 전 `DELETE /test-case-versions/{versionId}/steps/{stepId}`로 불필요한 구조화 단계를 삭제하고 단계 번호·revision·plan hash를 재계산하는 API 추가
- XLSX 구조화 입력에서 TC 헤더, 숫자만 있는 행, 반복 `Not Test/Source` 보고 행을 제외하고 실제 필터 결과를 기준으로 TC 수를 계산
- XLSX 정상 행의 TC ID 또는 Step·Expected Result를 우선 판별해 Result=`Not Test`, Comment=`Source:`가 있어도 보존하도록 보완
- 자연어 구조화 단계에 `targetDescription`·`selectorHint`·selector 해결 상태를 추가하고 원문 근거 없는 selector를 `UNRESOLVED`로 유지
- 페이지 분석 작업·상태·결과를 저장하는 `page_discoveries` migration과 조직·프로젝트 범위 API 추가
- 승인 전 `discover → 상태 조회 → 후보 선택/apply` API를 추가하고 적용 시 revision·plan hash·fingerprint·감사 로그 갱신
- Playwright Worker가 허용 환경 URL을 읽기 전용으로 탐색하고 정제된 접근성·상호작용 요소만 수집하여 selector 후보의 개수·표시·활성 상태를 실제 검증
- `UNRESOLVED`·`AMBIGUOUS`·`NOT_FOUND`·`STALE` 단계가 남으면 실행 계획과 승인을 차단하도록 서버 검증 강화
- XLSX 셀 reference를 기준으로 빈 셀을 보존하며 헤더별 필드를 파싱하고 `testCases[]` 독립 객체 반환
- KakaoGames 원본 21건을 `KG-WEB-001~021`로 분리하고 Result·BTS·Comment는 감사 필드에만 보관하여 AI 입력에서 제외
- 선택 TC 구조화 API로 외부 TC ID와 계층·출처·감사 데이터를 TestCaseVersion에 연결
- 자동화 가능성을 4개 상태로 판정하고 위험 업무 변경은 `UNSUPPORTED`로 승인·실행 차단
- 페이지 분석 `maxPages` 범위의 허용 도메인 GET 탐색, iframe·Shadow DOM 메타데이터, fingerprint 변경 시 이전 분석 `STALE` 처리 추가
- 전체/TC별 실행 이력 API와 실제 TC 성공률·마지막 실행 집계 추가
- OpenAI 화면 요소 의미 매핑 Gateway와 비용 원장·fingerprint 입력 캐시를 구현하고, AI가 서버가 부여한 element ID만 선택하도록 응답을 제한
- AI 의미 매핑 입력을 action·targetDescription·selectorHint와 정제된 요소 메타데이터로 한정하고 selector·입력값·HTML·비밀정보를 전달하지 않도록 보호
- AI가 반환한 알 수 없는 step/element ID를 폐기하는 화이트리스트 검증과 AI 비활성 시 네트워크 0회 fail-closed 회귀 테스트 추가
- 동일 프로젝트의 imported externalId를 다시 구조화하면 기존 TestCase를 행 잠금으로 재사용하고 다음 versionNo의 REVIEW_REQUIRED 버전을 생성하도록 중복 저장 오류 수정

프론트엔드에 요청:

- 모든 실제 API 요청에서 `credentials: 'include'` 유지
- 설정 API 실패 시 실행 차단
- `AUTH_REQUIRED`와 승인 상태별 화면 유지
- SSE 실패 시 2초 polling fallback 유지
- 실제 AI 연동 전 `maxAiCalls=0` 유지
- 배포 빌드는 동일 출처 `/api/v1`을 사용하고 임시·고정 Staging 주소를 소스 코드에 하드코딩하지 않음
- Local·Staging·Production 표시가 필요한 경우 비밀정보가 아닌 빌드 환경명만 사용
- AI 정책이 `1`일 때 선택지를 `0회`, `1회`로 제한하고 키·달러 예산 환경변수는 프론트에서 참조하지 않음
- 단계 편집 화면에서 DELETE API를 연결하고 확인창·중복 클릭 방지·반환 계획 즉시 반영·마지막 단계 삭제 시 승인 차단 처리

다음 작업:

- 페이지 분석 결과 기반 기본 시나리오 생성 API·저장 모델·revision 계약
- TC 단순 추출(`target`, `actions`, `expectedResults`)과 페이지 시나리오 비교 계약
- 검증된 element ID만 사용하는 AI 생성, 단계별 출처·근거, 미확인 충돌 승인 차단
- Cloudflare 임시 HTTPS 터널로 Temporary Staging 구성 및 회사 네트워크 접속 확인
- 프론트에서 구조화 결과의 `aiUsage.source`, 호출 수, 토큰·비용 표시 여부 결정
- 확인 후 고정 Staging 서버·도메인·회사 IP 접근 제한 결정
- PostgreSQL·Redis·MinIO·Worker 외부 통합 배포
- Firebase와 실제 API 연결 후 인증·SSE·증적 통합 검증
- 가입·승인·사용자 역할 API
- 다중 TC 파일의 서버 자동 분리 API/UX 설계(현재는 명확한 검토 상태 반환)
- 프론트에서 검증 Execution/Artifact를 사용해 단계 상세·실패 PNG 화면 교차 확인
- OpenAI 의미 매핑의 Worker 자동 호출은 비활성 상태로 유지하며, 별도 통합 승인 후 명시적 기능 플래그·TC당 최대 1회·일일 예산 내에서 연결
- 다중 선택·일괄 구조화/승인은 단일 TC 전체 흐름 실환경 검증 후 확장

## 최근 검증

- 페이지 우선 프론트 Mock/API 연결: TypeScript 5.9 타입 검사 및 `git diff --check` 통과. 저장소 Vite 8은 기존 Windows 접근 위반, Vite 6 임시 검증은 pnpm store의 `picomatch` 누락으로 번들 검증 대기
- 페이지 우선 2차 비교·검토·승인 연동: TypeScript 5.9 타입 검사와 `git diff --check` 통과. `pnpm run build`는 기존과 동일하게 Vite 프로세스가 Windows 접근 위반(`3221225477`)으로 종료되어 환경 정상화 후 번들 재확인 필요

- 2026-09-08 imported TC 재구조화 수정: 정식 백엔드 테스트 `63 passed`, 의존성/수집 경고 4건, 실제 OpenAI 호출 0회. 기존 TC 재사용 및 최초 생성 경쟁 재시도·최종 충돌 처리를 검증했다. 이전 `71 passed` 집계에는 OneDrive 테스트 복사본이 포함되어 이번에는 정식 `test_api.py`, `test_ai.py`만 실행했다.
- Temporary Staging 배포·DB 연동 재검증 대기: 현재 PC의 Docker Desktop이 `sailor-ingest.sock` 접근 오류로 엔진 시작에 실패한다. 복구 후 `.env.public`과 `compose.public-demo.yml`로 API를 반영하고 KG-WEB-001 반복 구조화를 확인해야 한다.

- KG-WEB-001 반복 구조화 저장 회귀: 기존 TestCase 재사용, versionNo 3→4, 신규 TestCase 0건 확인

- OpenAI 화면 요소 의미 매핑 포함 백엔드 전체 테스트 `60 passed` (`3 warnings`); Fake Gateway만 사용하여 실제 OpenAI 호출 `0회`
- 프론트 실행 이력 UI: `git diff --check` 통과. TypeScript·Vite 프로세스가 현재 Windows 환경에서 접근 위반(`3221225477`)으로 종료되어 타입 검사와 프로덕션 번들 검증은 환경 정상화 후 재확인 필요

- 최신 자연어 QA 요구사항 회귀: 백엔드 `57 passed`, 프론트 실제 API 프로덕션 Docker 빌드 통과, AI 호출 0
- 실제 `KakaoGames_AI_Automation.xlsx`: 21건, 첫 ID `KG-WEB-001`, 마지막 ID `KG-WEB-021`; AI 입력에 `Not Test`/`Source:` 없음, 감사 필드 보존 확인

- 페이지 분석 API·구조화/실행 차단·민감정보 마스킹 회귀 포함 백엔드 단위 테스트 `55 passed` (Docker 일회성 테스트 컨테이너, AI 호출 0)

- 백엔드: `48 passed` (`3 warnings`), 프론트 배포 Dockerfile 프로덕션 빌드 통과
- 백엔드 단계 삭제·XLSX 오탐 회귀: `51 passed` (`3 warnings`)
- 실제 `KakaoGames_AI_Automation.xlsx` 검증: 메타데이터 9행 제외, `KG-WEB-001`~`KG-WEB-021` 고유 TC 21건 보존, `XLSX_TEST_CASES_DETECTED:21`
- 구조화 회귀: 정확히 9,613자 원문 보존, 102건 다중 TC 감지, AI 호출 전 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED` 차단 확인
- AI 사용량 계약: 실제 Gateway 결과 `AI/1`, 캐시 `CACHE/0`, AI 비활성 원문 기반 결과 `RULE_BASED/0`
- 영속 버전 통합: Version `787dc8b2-cecf-4ae4-b438-9786a7a65e2f`, 승인 전 `TC_NOT_READY`(409), 승인 `READY`
- 실제 Worker 통합 Execution `f322af6c-c3f5-4b93-99ee-8fd0f5d6a24b`: 저장된 navigate/fill/click/assert 4단계 전체 `PASS`, AI 호출 `0`
- 계획 검증 Version `5ea8101f-8ca9-4e19-ab83-d7fa5b3adc38`, Execution `bbf2ac81-84e7-42ef-9529-bee62826ca48`: 계획 hash 64자·revision 1·마스킹 확인, 4개 `planStepId`와 실제 단계 모두 일치, 최종 `PASS`, AI 호출 `0`
- Temporary Staging 최신 재배포: 기존 Quick Tunnel URL 유지, `/health` 200, 미인증 API 401, 데모 로그인 200, 공개 호스트 포트는 frontend `8080`만 노출
- 파일 기반 성공 Version `ec034696-6bd6-46c7-b7fb-cad261de0892`, Execution `930d4547-5bb4-4472-b250-dd7e039e3718`: `executable=true`, revision 1, plan hash `fa3f083e83d203ec695bd00545363ab32d5bb6de1f8ba315acc4e22fcf3daeab`, 계획/실제 각 4단계, `stepCountMatches=true`, `step-1..4` 모두 `planStepId` 및 action·selector·expected 일치, 최종 `PASS`
- 의도적 실패 Version `647eae19-34df-4722-a40d-dd87ead60db2`, Execution `5d35f1e2-09b2-49d5-96ec-bb976ef7ea2b`: 4번 assert 실패, `ASSERTION_FAILED`, PNG Artifact `bdbbd9da-f54d-490c-8704-b69c96eb1af2` 다운로드 및 PNG signature 확인
- 필수값 누락 Version `f7361da1-8887-4b8f-9fb8-1c0b6f2b88d2`: 계획 `executable=false`, `STEP_PARAMETER_MISSING`, 승인 HTTP 422로 실행 차단
- 단계 수정 API 실환경 검증 Version `bb4afc1a-7f9d-4cc2-9ee3-626a47a0f8d8`: 누락 warning에 step 2/`step-2`/`value,secretRef`, PATCH 후 revision `1→2→3` 및 hash 변경, selector 없는 URL assertion `executable=true`, 승인 200
- assert selector 누락 실환경 검증 Version `a1be9190-3a62-4e73-aa62-b67a9cb047e7`: `assumptions` 검토 안내, 계획·승인 오류 모두 step 4/`step-4`/`missingFields=[selector]`, 승인 422 확인
- 위 성공·실패 실행은 모두 `maxAiCalls=0`, 구조화 `RULE_BASED/0회/$0`; API·Outbox·Worker 로그에서 비밀값, OpenAI 네트워크, 고정 Seed UUID, `tcv-new-v1`/fallback 표식 미검출
- 검증 중 최초 fixture의 `#email/#submit/#welcome` selector가 실제 대상 DOM과 달라 실패한 문제를 발견했고, 파일 fixture를 대상의 `data-testid` 계약에 맞춰 수정하여 재검증 완료. `demo-target`은 선택된 테스트 환경으로만 사용됐으며 고정 Seed·로그인 샘플 fallback은 사용하지 않음
- 필수 파라미터 누락 계획은 승인 시 `STEP_PARAMETER_MISSING`으로 차단 확인
- Docker 통합: PostgreSQL·Redis·MinIO·API·Outbox·Playwright Worker·Frontend 정상 실행
- 실제 Worker smoke execution: `PASS`, AI 호출 `0`
- 성공 Execution `201c45fc-c846-4cce-b847-1a9fd01c3202`: navigate/fill/click/assert 전체 `PASS`
- 실패 Execution `0a5c5cf4-2179-464e-8504-7df5cb78084c`: 최종 `FAIL`, `ASSERTION_FAILED`, 4단계 `STEP_FAILED`
- 실패 Artifact `8c980f7a-d1e9-4b83-a569-40ba6f6e4ad6`: MinIO PNG 및 API 다운로드 확인
- API·Outbox·Worker 로그 비밀값 미검출, AI 호출 `0회`, 관찰 비용 `$0`
- OpenAI 최초 구조화: 실제 호출 `1회`, 입력 `275`, 출력 `173` 토큰, 비용 `$0.00014505`
- 동일 구조화 재요청: `CACHE`, OpenAI 호출 `0회`, 추가 비용 `$0`
- AI 독립 Playwright Execution `fbc2e998-9600-41ff-8364-bd4a8ac4d3a4`: 4단계 전체 `PASS`, 원장·비용 변화 없음
- 프론트엔드: 타입 검사 및 Firebase 데모 빌드 통과
- 프론트 AI 정책 UI: 서버 정책 `0/1`에 따른 선택 제한 및 요청값 상한 적용 검증
- 프론트 구조화 단계 편집: TypeScript 검사, 실제 API 프로덕션 빌드, Firebase Mock 빌드 통과
- 프론트 구조화 단계 삭제: TypeScript 검사, 실제 API 프로덕션 빌드, Firebase Mock 빌드 통과
- 프론트 페이지 분석·selector resolution: TypeScript 검사, 실제 API 프로덕션 빌드, Firebase Mock 빌드 통과
- 최신 `main` `4b516d9` Temporary Staging 재배포: 프론트 Docker 프로덕션 빌드 통과, `/health` 200, 미인증 API 401, 기존 Quick Tunnel 유지, 외부 공개 포트는 frontend `8080`만 사용
- HTTPS 성공 검증 Version `f0869071-9fdb-4f25-be56-3580f65c67bd`, Execution `8e61b8d7-d612-406d-9aca-545c8b5e12a0`: plan hash `613541ba457b545e9003f2654247a87c07df58283295642129289c98d0387694`, 계획/실제 4단계 및 `planStepId` 일치, 최종 `PASS`
- HTTPS 실패 검증 Execution `8fb52bc6-207b-44ba-b63b-c4441387e9ea`: 최종 `FAIL`, `ASSERTION_FAILED`, 실패 PNG Artifact `8ca2274f-7dff-459e-9ceb-c6e249361139` 및 PNG signature 확인
- HTTPS 단계 편집 검증 Version `32ab90d3-1c61-4cc4-9c9a-0f029661944e`: PATCH 전 `executable=false`, `missingFields=[value,secretRef]`; 저장 후 revision `1→2`, plan hash 재계산, `executable=true`, 승인 200
- 위 HTTPS 재검증은 API `AI_ENABLED=false`, 실행 `maxAiCalls=0`, 구조화 `RULE_BASED/0회/$0` 상태로 수행
- HTTPS 단계 삭제 검증 Version `476ca1df-2b55-4123-bf7e-acb33cde1e75`: 4단계 중 1개 삭제 후 revision `1→2`, plan hash 변경, 남은 `stepNo=1,2,3`; 전체 삭제 후 revision 5, `steps=[]`, `executable=false`, `EXECUTION_PLAN_INVALID` 확인
- Firebase UI: `https://tracepilot-demo.web.app`
- Firebase 공개 회귀: 대시보드·주요 메뉴·Mock PASS 실행 확인
- OpenAI 설정 변경: 정적 diff 검사 통과. Docker Desktop 엔진 미실행으로 백엔드 테스트는 다음 작업에서 재검증 필요

## 차단 사항

- 실제 백엔드 공개에는 서버 제공 방식과 비용 정책 결정이 필요하다.
- 외부 공개 전 Gateway 서버의 고정 배포 방식과 Secret Manager 적용이 필요하다.

상세 통합 검증 기록은 `docs/LOCAL_PLAYWRIGHT_VALIDATION.md`를 기준으로 한다.
