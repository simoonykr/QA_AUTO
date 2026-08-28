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

1. 실행 생성 후 실제 상태를 조회할 `GET /executions/{executionId}` 계약
2. 실행 중단 `POST /executions/{executionId}/cancel`과 재시도 endpoint
3. 실시간 이벤트 방식 결정: SSE 우선, 불가하면 polling 주기와 종료 상태 정의
4. XLSX/DOCX 업로드·파싱 endpoint 및 파일 크기·확장자 제한
5. 환경·테스트 계정·정책 관리 목록 endpoint
6. 모든 오류 응답이 `{ code, message, requestId, retryable, details? }` 형태인지 확인
7. 로컬 개발 CORS 또는 Vite `/api` proxy 운용 방식 확정

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
