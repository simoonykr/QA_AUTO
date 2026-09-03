# 프론트엔드 ↔ 백엔드 연동 메모

작성일: 2026-08-28

## 프론트 담당자 다음 요구사항 (2026-08-30)

현재 `main`의 `01d29f6`까지 반영된 실행 환경·테스트 계정·실행 정책 연동을 기준으로 다음 조건을 유지한다.

1. 실제 AI API를 연결하기 전까지 모든 실행 요청의 `maxAiCalls` 기본값은 `0`으로 유지한다.
2. 서버 정책의 `maxAiCalls`가 `0`이면 AI 호출 횟수를 늘릴 수 없도록 선택지를 비활성화한다. API 키나 데모 계정 비밀번호는 프론트 코드, 브라우저 저장소, `VITE_*` 환경변수에 저장하지 않는다.
3. 환경·계정·실행 정책 중 하나라도 로딩에 실패하면 실행 생성 버튼을 차단하고, 어떤 설정을 불러오지 못했는지 사용자에게 표시한다.
4. 실제 배포에서는 `VITE_USE_MOCK_API=false`, `VITE_API_BASE_URL=/api/v1`을 사용한다. 인증 요청을 포함한 모든 API 요청은 `credentials: 'include'`를 유지한다.
5. HTTP 401 `AUTH_REQUIRED`를 받으면 로그인 화면으로 이동한다. `approvalStatus=PENDING`은 승인 대기 화면, `REJECTED`는 거절 안내 화면으로 분리할 수 있는 구조를 유지한다.
6. 실행 설정 선택지는 서버 정책을 넘지 않아야 한다. 지원 브라우저, 최대 실행 시간, 최대 재시도, 위험 행동 승인 여부를 프론트에서 임의로 확대하지 않는다.
7. 실행 상태는 SSE를 우선 사용하되 연결 실패 시 기존 2초 polling으로 전환하고, 종료 상태에서는 SSE와 polling을 모두 중지한다.
8. Firebase Mock 배포는 화면 시연 전용으로 유지한다. 실제 데이터 입력이 가능한 것처럼 보이지 않도록 상단의 `Mock API 사용 중` 표시를 제거하지 않는다.

## OpenAI 연동 상태 (2026-09-01)

백엔드에 서버 전용 OpenAI 설정과 fail-closed 정책을 추가했다. API 키는 로컬 `.env.public`에만 저장하며 Git, 프론트 코드, 브라우저 저장소, 응답 payload에 포함하지 않는다.

- `AI_ENABLED`, `AI_MAX_CALLS_PER_RUN`, `AI_DAILY_BUDGET_USD`는 백엔드 전용 환경변수다.
- API 키가 없거나 AI가 비활성화된 경우 `GET /api/v1/execution-policies/current`의 `maxAiCalls`는 `0`이다.
- 키와 한도·예산 설정이 모두 유효한 경우에만 서버 정책의 `maxAiCalls`가 설정값을 반환한다. 현재 로컬 목표값은 실행당 `1`이다.
- OpenAI Gateway, 토큰·비용 원장, 일일 예산 선차단, 동일 입력 캐시를 구현했다.
- 실제 호출은 TC 구조화 endpoint에서만 최대 1회 발생한다. 실행 API와 Playwright Worker는 AI와 독립적이다.
- 구조화 응답에 `aiUsage`가 추가된다. 기존 필드는 변경되지 않았다. 상세 계약은 `AI_GATEWAY_CONTRACT.md`를 기준으로 한다.
- 프론트는 AI 키나 달러 예산을 입력·표시·저장하지 않고, 기존처럼 서버가 반환한 `maxAiCalls` 범위 안에서만 선택지를 제공한다.
- 프론트 기본 실행 요청값은 계속 `maxAiCalls: 0`을 유지한다. 현재 AI 호출은 구조화 요청에만 서버 정책으로 적용되며 실행 설정값과 분리되어 있다.

프론트 확인 요청:

1. 정책값이 `0`이면 AI 호출 선택지가 `0회`로 고정되고 실행 버튼의 기존 비활성·토큰 미사용 설명이 유지되는지 확인한다.
2. 향후 정책값이 `1`이면 `0회`, `1회`만 선택 가능하도록 현재 고정 선택지 `0/10/20/30/50`을 정책 기반 정수 범위로 변경한다.
3. UI에서 `AI_ENABLED`, `AI_DAILY_BUDGET_USD`, `OPENAI_API_KEY`를 직접 참조하지 않는다.

프론트 완료 확인 기준:

- Mock 빌드와 실제 API 빌드 모두 타입 검사 통과
- 미로그인, 세션 만료, 설정 API 실패, 실행 생성 중복 클릭 시나리오 확인
- 서버 정책 `maxAiCalls=0`에서 AI 토큰을 사용하는 요청이 생성되지 않음
- 브라우저 저장소와 생성된 JavaScript에 비밀번호·API 키가 포함되지 않음

## 오늘 프론트 반영 내용

- `GET /api/v1/test-cases` 로딩·오류 상태 처리
- `POST /api/v1/test-case-versions/current/structure` 응답을 구조화 검토 화면에 실제 반영
- `POST /api/v1/executions` 요청 중 중복 클릭 방지 및 표준 오류 메시지 처리
- 실행 설정 화면의 환경·브라우저·viewport·locale·계정·한도·승인 값을 `CreateExecutionRequest`에 실제 반영
- Mock/Backend API 연결 상태를 상단에 표시
- JSON이 아닌 오류 응답과 네트워크 오류를 `ApiError`로 정규화

## 현재 합의된 계약

프론트 타입과 FastAPI Pydantic schema의 필드명·enum은 현재 일치한다.

- TC 목록: `TestCaseSummary[]`
- 구조화 요청: `{ title, rawText }`
- 구조화 응답: `versionId`, `status`, `preconditions`, `steps`, `assertions`, `assumptions`, `confidence`, `aiUsage`
- 실행 생성: `Idempotency-Key` 필수, 성공 시 HTTP 202와 `ExecutionResponse`

### 구조화 → 승인 → 실행 계약 (2026-09-02)

1. `POST /api/v1/test-case-versions/current/structure`
   - 요청: `{ title, rawText }`
   - 서버는 새 `test_cases`와 `test_case_versions` row를 만들고 원문과 구조화 결과를 저장한다.
   - 응답의 `versionId`는 매 요청마다 생성되는 UUID이며 `status`는 `REVIEW_REQUIRED`다.
   - `structured_spec`에는 Worker가 읽을 `schemaVersion`, `steps`, 전제조건, assertion, 가정, confidence가 저장된다.
2. 승인 전 단계 수정이 필요한 경우:
   - `PATCH /api/v1/test-case-versions/{versionId}/steps/{stepId}?environmentId={environmentId}`
   - body에서 `selector`, `url`, `operator`, `expected`, `value`, `secretRef`, `assertionType`(`url|text|element`)을 부분 수정한다.
   - `REVIEW_REQUIRED` 버전만 수정 가능하며 성공 시 revision을 1 증가시키고 새 plan hash를 계산한 `ExecutionPlanResponse`를 반환한다.
   - 불필요한 단계 삭제는 `DELETE /api/v1/test-case-versions/{versionId}/steps/{stepId}?environmentId={environmentId}`를 사용한다.
   - 삭제 성공도 갱신된 `ExecutionPlanResponse`를 반환한다. 남은 단계의 `stepNo`는 1부터 연속으로 재정렬되고 revision과 plan hash가 다시 계산된다.
   - 모든 단계를 삭제할 수 있으며 이때 `steps=[]`, `executable=false`, `planHash=null`, `EXECUTION_PLAN_INVALID` warning을 반환한다.
3. `POST /api/v1/test-case-versions/{versionId}/approve`
   - 요청 body 없음
   - 응답: `{ "versionId": "<uuid>", "status": "READY" }`
   - 이미 READY인 버전의 재승인은 같은 응답을 반환한다.
4. `POST /api/v1/executions`
   - 구조화 응답에서 받은 동일 `versionId`를 `testCaseVersionId`로 보낸다.
   - 서버는 해당 UUID가 현재 조직·프로젝트에 실제 존재하고 `READY`인지 확인한다.
   - Worker는 execution이 가리키는 동일 버전의 DB `structured_spec.steps`만 실행한다. 빈 명세나 고정 Seed fallback은 사용하지 않는다.

버전 상태 enum: `DRAFT | REVIEW_REQUIRED | READY | ARCHIVED`. 현재 새 구조화 버전은 `REVIEW_REQUIRED`, 승인 성공 후 `READY`다.

| HTTP | code | 프론트 처리 |
|---|---|---|
| 404 | `TC_VERSION_NOT_FOUND` | 존재하지 않거나 다른 조직·프로젝트의 버전으로 동일하게 안내 |
| 409 | `TC_VERSION_NOT_REVIEWABLE` | 검토 대기 버전이 아니므로 승인 불가 |
| 409 | `TC_NOT_READY` | 승인 전 실행 차단 후 구조화 검토 화면으로 이동 |
| 400 | `INVALID_RESOURCE_ID` | UUID가 아닌 과거 `tcv-new-v1` 등 alias 사용 중단 |
| 404 | `TC_STEP_NOT_FOUND` | 이미 삭제됐거나 현재 버전에 없는 단계이므로 목록 새로고침 |
| 409 | `TC_VERSION_NOT_REVIEWABLE` | READY 등 승인 후 버전은 수정·삭제 불가 |

프론트는 구조화 응답의 `versionId`를 보관하고 승인 성공 후에만 실행 설정으로 이동하며, 실행 생성 요청에 해당 값을 그대로 사용한다. 환경·계정은 목록 API가 반환한 UUID를 사용한다.

### 실행 계획 조회·일치 검증 계약 (2026-09-02)

```http
GET /api/v1/test-case-versions/{versionId}/execution-plan?environmentId={environmentId}
```

응답 필드:

- `versionId`, `status`, `revision`, `planHash`
- `environment`: `id`, `name`, `baseUrl`
- `steps`: `stepNo`, `id`, `title`, `action`, `url`, `selector`, 마스킹된 `value`, `secretRef`, `operator`, `expected`, `assertionType`, `timeoutMs`
- `warnings`: `code`, `message`, `stepNo?`, `stepId?`, `missingFields[]`
- `executable`, `source`

조회 API는 잘못된 계획도 HTTP 200으로 반환하며 `executable=false`, `planHash=null`, `warnings`로 검토 사유를 제공한다. 승인과 실행 생성은 같은 서버 검증기를 사용하고 잘못된 계획을 HTTP 422로 차단한다.

- `STEP_PARAMETER_MISSING`: action별 필수 값 누락
- `UNSUPPORTED_ACTION`: 현재 Worker가 지원하지 않는 action
- `TARGET_URL_NOT_ALLOWED`: 환경 allowlist 밖의 navigate URL
- `EXECUTION_PLAN_INVALID`: 빈 계획, 잘못된 단계 형식 또는 실행 생성 후 계획 불일치

assertion 검증 규칙:

- `assertionType=url`: `url`, `operator`, `expected` 필수. selector 없이 실행 가능하며 URL은 환경 allowlist를 통과해야 한다.
- `assertionType=text|element`: `selector`, `operator`, `expected` 필수.
- 과거 데이터는 assert 단계에 URL이 있고 selector가 없으면 `url`, 그 외에는 `text`로 호환 추론한다.
- 승인 HTTP 422 오류의 `details`에도 `stepNo`, `stepId`, `missingFields`가 동일하게 포함된다.

실행 생성 시 서버는 검증된 계획의 SHA-256 hash, revision, 환경 ID·base URL과 계획 단계 수를 execution 설정 snapshot에 저장한다. Worker는 실행 직전에 DB 명세로 hash를 다시 계산하고 snapshot과 하나라도 다르면 브라우저를 시작하지 않는다.

`GET /api/v1/executions/{executionId}/details`에는 다음이 추가된다.

- 각 `steps[]`: `planStepId`
- `plan`: `testCaseVersionId`, `planHash`, `planRevision`, `environmentId`, `baseUrl`, `plannedStepCount`, `actualStepCount`, `stepCountMatches`

프론트 실행 전 화면은 로컬 구조화 결과가 아니라 이 API의 `executable`을 최종 기준으로 사용한다. `fill.value`는 실제 값이 있어도 항상 `***`로 반환한다.

## 백엔드 담당자 확인 요청

## 페이지 분석·selector 해결 계약

- 구조화 단계는 `targetDescription`, `selectorHint`, `resolutionStatus`를 반환한다. 원문 근거가 없는 selector는 저장하지 않으며 초기 상태는 `UNRESOLVED`이다.
- `POST /api/v1/test-case-versions/{versionId}/discover`: `{ environmentId, maxPages: 1..3, maxAiCalls: 0..1 }`, HTTP 202 `{ discoveryId, status: "QUEUED" }`
- `GET /api/v1/test-case-versions/{versionId}/discoveries/{discoveryId}`: `QUEUED → PROVISIONING → SCANNING → MAPPING → VALIDATING → COMPLETED|NEEDS_REVIEW|FAILED` 상태와 페이지 fingerprint, 단계별 후보를 반환한다.
- 후보는 `DATA_TESTID`, `ROLE_NAME`, `LABEL`, `PLACEHOLDER`, `ID_NAME`, `LINK_URL`, `VISIBLE_TEXT`, `CSS` 전략과 `matchCount`, `visible`, `enabled`, `confidence`를 포함한다.
- 단계 상태는 `UNRESOLVED`, `RESOLVING`, `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `STALE`이다. 모든 실행 대상 단계가 `RESOLVED`가 아니면 `executable=false`이며 승인을 차단한다.
- `POST /api/v1/test-case-versions/{versionId}/discoveries/{discoveryId}/apply`: `{ selections: [{ stepId, candidateId }] }`; 선택된 실제 검증 selector를 저장하고 revision·planHash를 재계산한 `ExecutionPlanResponse`를 반환한다.
- 페이지 수집 데이터는 상호작용 요소의 접근성 이름·label·placeholder·안정 ID 등으로 제한하며 input 값, 쿠키, 비밀번호, 토큰, 개인정보와 전체 HTML은 저장하거나 AI에 전달하지 않는다.
- 현재 통합 검증 기본값은 `maxAiCalls=0`이며 규칙 기반 후보를 Playwright로 검증한다. AI 기반 의미 매핑을 활성화할 때도 TC당 최대 1회와 일일 예산 원장을 그대로 적용한다.

완료된 연동:

- `GET /executions/{executionId}`: 프론트 2초 polling 연결
- `POST /executions/{executionId}/cancel`: 실행 모니터 중단 버튼 연결
- `POST /executions/{executionId}/retry`: 결과 화면 재시도 연결
- 확장 상태: `PROVISIONING`, `CANCEL_REQUESTED`, `NEEDS_REVIEW`, `SYSTEM_ERROR` 포함
- 표준 validation 및 서버 오류 envelope 반영

남은 확인 요청:

- 없음. XLSX/DOCX 업로드·파싱 계약은 아래와 같이 확정됨.

파일 가져오기 계약:

- `POST /api/v1/test-cases/import`
- 요청: `multipart/form-data`의 `file` 필드
- 확장자: `.txt`, `.csv`, `.xlsx`, `.docx`
- 파일 크기: 최대 10MB
- 응답: `{ fileName, format, title, rawText, warnings, detectedTestCaseCount, testCases }`
- XLSX의 `testCases[]` 항목: `externalId`, `title`, `depth1~3`, `precondition`, `steps[]`, `expected`, `sourceUrl`, `rawText`, `auditFields`
- `rawText`와 각 항목의 `rawText`에는 구조화에 필요한 ID·계층·전제조건·Step·Expected Result·대상 URL만 포함한다.
- Result(AOS/IOS), BTS ID, Comment, `Not Test`, `Source:` 원문은 `auditFields`에만 보관하고 AI 구조화 입력에서는 제외한다.
- `POST /api/v1/test-case-versions/imported/structure`: `{ testCase: testCases[n] }`를 받아 선택한 TC 하나만 독립 TestCase·TestCaseVersion으로 저장하고 구조화 결과를 반환한다.
- 구조화·계획 응답은 `automationStatus`(`AUTOMATABLE|PARTIALLY_AUTOMATABLE|MANUAL_REVIEW_REQUIRED|UNSUPPORTED`)와 `automationReason`을 반환한다. `UNSUPPORTED`는 승인·실행할 수 없다.
- 프론트는 응답의 `title`, `rawText`를 편집기에 반영한 뒤 기존 구조화 API를 호출
- 오류 코드: `UNSUPPORTED_FILE_TYPE`(415), `FILE_TOO_LARGE`(413), `EMPTY_TEST_CASE_FILE`(422), `UNSUPPORTED_TEXT_ENCODING`(422), `INVALID_DOCUMENT`(422), `EXTRACTED_TEXT_TOO_LARGE`(413)
- 파싱은 서버에서 결정적으로 수행하며 AI API를 호출하지 않음
- 가져온 `rawText`는 구조화 요청에서 최대 50,000자까지 그대로 전송한다.
- 여러 TC가 감지되면 구조화 API는 HTTP 422 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED`와 `details.reviewStatus=REVIEW_REQUIRED`, 감지 건수, 원문 길이, `aiCallCount=0`을 반환한다. 프론트는 이를 일반 분석 성공으로 처리하지 않고 TC별 분리가 필요한 검토 상태로 안내한다.
- AI 비활성 상태의 단일 TC는 원문 기반 `RULE_BASED`, `callCount=0` 결과를 반환하며 고정 로그인 예제를 반환하지 않는다.
- XLSX는 `TC ID/Test Steps/Expected Result` 또는 `단계/기대결과` 헤더를 TC 테이블 시작으로 탐지하고 그 이전 결과 집계·보고서 메타데이터 행을 `rawText`에서 제외한다. 개별 TC의 `Expected Result` 열은 유지한다.
- XLSX 응답 `warnings`에는 `XLSX_METADATA_ROWS_EXCLUDED:{행수}`, `XLSX_TEST_CASES_DETECTED:{건수}`가 포함된다.
- TC 테이블 내부에서 헤더가 반복되거나 숫자만 있는 행, `Not Test`와 `Source:`가 함께 있는 보고 행을 제외하면 `XLSX_NON_TC_ROWS_EXCLUDED:{행수}` warning을 추가한다.
- 단, 정상 TC ID가 있거나 Step과 Expected Result 데이터가 존재하는 행은 Result=`Not Test`, Comment=`Source:`를 포함해도 TC 원문으로 보존한다. 보고 행 제외는 상태·출처 문자열만으로 결정하지 않는다.
- 구조화 selector는 원문에 정확한 근거가 있을 때만 유지한다. 원문에 없는 AI selector는 제거되고 `assumptions`에 승인 전 수정 필요 사유가 추가된다.
- 실제 OpenAI 응답인 경우에만 `aiUsage.source=AI`, `callCount=1`이다. 캐시는 `CACHE/0`, AI 비활성 규칙 기반은 `RULE_BASED/0`이다.

새 상세 조회 계약:

- `GET /api/v1/executions/{executionId}/details`
- 응답: `{ execution, result, errorCode, steps, artifacts }`
- `steps`: `stepNo`, `status`, `action`, `assertion`, `errorCode`, 시작·종료 시각
- `artifacts`: 증적 종류, MinIO object key, SHA-256, 크기, 생성 시각
- 프론트는 기존 상태 polling을 유지하면서 실행 모니터/결과 화면에서 상세 endpoint를 추가 호출할 수 있음
- `GET /api/v1/executions?status=&testCaseId=&limit=&offset=`: 실행 이력 `{ items, total }` 반환
- `GET /api/v1/test-cases/{testCaseId}/executions`: 해당 TC 실행 이력 반환
- 이력 항목은 TC ID·제목, version ID, 상태·오류, 계획/실제 단계 수, 시각·duration, 증적 수, 재시도 부모 ID를 포함한다.
- `GET /api/v1/test-cases`의 `passRate`, `lastExecutedAt`은 실제 종료 Execution 집계를 사용한다.

실시간·증적 계약:

- `GET /api/v1/executions/{executionId}/events`: SSE 연결
- 이벤트 `execution.updated`: 상태 또는 단계/증적 목록이 변경될 때 상세 응답 전체 전달
- 이벤트 `execution.completed`: 종료 상태에서 마지막으로 전달한 뒤 서버가 연결 종료
- 종료 상태: `PASS`, `FAIL`, `BLOCKED`, `NEEDS_REVIEW`, `CANCELLED`, `SYSTEM_ERROR`
- `GET /api/v1/executions/{executionId}/artifacts/{artifactId}`: 권한 범위가 확인된 PNG 증적 반환
- SSE 연결이 불가능한 환경에서는 기존 2초 polling을 fallback으로 유지

실행 설정 리소스 계약:

- `GET /api/v1/environments`: 환경 ID, 이름, base URL, 허용 도메인, 기본 viewport
- `GET /api/v1/test-accounts`: 계정 ID, 별칭, 사용 상태만 반환 (`secret_ref`는 반환 금지)
- `GET /api/v1/execution-policies/current`: 허용 action, 지원 브라우저, 최대 시간·AI 호출·재시도 및 위험 승인 정책

## 데모 로그인 계약

- `POST /api/v1/auth/login`: `{ username, password }`를 받아 HttpOnly 세션 쿠키 발급
- `GET /api/v1/auth/me`: 현재 사용자 `{ id, displayName, role, approvalStatus }` 반환
- `POST /api/v1/auth/logout`: 세션 쿠키 삭제, HTTP 204
- 미로그인 상태에서 `/api/v1/**` 호출 시 HTTP 401 `AUTH_REQUIRED`
- 프론트의 모든 실제 API 요청은 `credentials: 'include'` 사용
- 프론트와 API는 배포 시 동일 사이트의 `/`와 `/api`로 reverse proxy하는 구성을 우선 사용
- 데모 계정 값과 서명 secret은 서버 환경변수로만 주입하며 Git에 저장하지 않음

향후 가입·승인 방식에서도 위 응답을 유지하고 `approvalStatus`를 `PENDING`, `APPROVED`, `REJECTED`로 확장한다. `PENDING` 사용자는 승인 대기 화면만 접근하며, `role`은 `OWNER`, `QA`, `VIEWER`로 구분한다.

## Playwright Worker 반영

- Redis Stream의 `execution.requested` 작업 소비
- Chromium으로 허용된 환경 URL 실제 접속
- 실행 상태 `QUEUED → PROVISIONING → RUNNING → PASS/FAIL` 반영
- 1차 navigation 단계 결과를 `step_runs`에 저장
- 승인된 구조화 명세의 `navigate`·`fill`·`click`·`assert` 단계 실행
- 각 단계 결과를 `step_runs`에 저장하고 실패 화면을 MinIO `tracepilot-artifacts` 버킷에 보관
- `CANCEL_REQUESTED` 확인 후 `CANCELLED` 처리
- 로컬 통합 검증용 `demo-target` 서비스 추가

프론트는 기존 `GET /executions/{executionId}` 2초 polling을 유지하면 실제 Worker 상태가 화면에 반영된다. 단계별 결과와 증적을 조회하는 API/SSE 계약은 다음 작업 범위다.

## 로컬 연동 방법

```env
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

백엔드 미실행 상태에서는 `.env` 기본값에 따라 Mock API가 사용된다.

## 충돌 방지

- 프론트 담당 범위: `src/**`, 프론트 설정과 UI 문서
- 백엔드 담당 범위: `backend/**`, DB migration, worker/API 구현
- 공통 계약 변경 시 `src/api/types.ts`와 `backend/app/schemas/**`를 같은 커밋 또는 연속 커밋으로 맞춘다.
