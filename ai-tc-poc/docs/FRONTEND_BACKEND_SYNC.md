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
- 구조화 응답: `versionId`, `preconditions`, `steps`, `assertions`, `assumptions`, `confidence`
- 실행 생성: `Idempotency-Key` 필수, 성공 시 HTTP 202와 `ExecutionResponse`

## 백엔드 담당자 확인 요청

완료된 연동:

- `GET /executions/{executionId}`: 프론트 2초 polling 연결
- `POST /executions/{executionId}/cancel`: 실행 모니터 중단 버튼 연결
- `POST /executions/{executionId}/retry`: 결과 화면 재시도 연결
- 확장 상태: `PROVISIONING`, `CANCEL_REQUESTED`, `NEEDS_REVIEW`, `SYSTEM_ERROR` 포함
- 표준 validation 및 서버 오류 envelope 반영

남은 확인 요청:

1. XLSX/DOCX 업로드·파싱 endpoint 및 파일 크기·확장자 제한

새 상세 조회 계약:

- `GET /api/v1/executions/{executionId}/details`
- 응답: `{ execution, result, errorCode, steps, artifacts }`
- `steps`: `stepNo`, `status`, `action`, `assertion`, `errorCode`, 시작·종료 시각
- `artifacts`: 증적 종류, MinIO object key, SHA-256, 크기, 생성 시각
- 프론트는 기존 상태 polling을 유지하면서 실행 모니터/결과 화면에서 상세 endpoint를 추가 호출할 수 있음

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
