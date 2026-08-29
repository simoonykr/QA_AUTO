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

1. SSE 도입 여부와 단계별 진행률·증적 event 계약
2. XLSX/DOCX 업로드·파싱 endpoint 및 파일 크기·확장자 제한
3. 환경·테스트 계정·정책 관리 목록 endpoint
4. 로컬 개발 CORS에 `http://127.0.0.1:5174` 추가 또는 프론트 포트를 5173으로 고정

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
