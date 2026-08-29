# 프론트엔드 ↔ 백엔드 연동 메모

작성일: 2026-08-28

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
