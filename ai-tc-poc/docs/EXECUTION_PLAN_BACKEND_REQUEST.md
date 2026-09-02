# 실행 예정 시나리오 및 Worker 계획 일치 검증 요청

작성일: 2026-09-02

## 문제

사용자가 구조화·승인한 TC와 Worker가 실제 수행한 단계가 일치하는지 실행 전에 확인할 수 없다. 실제 화면에서는 기대한 전체 시나리오 대신 `assert` 한 단계만 실행된 사례가 확인됐다. 프론트 실행 모니터에도 고정 로그인 데모 화면이 남아 있어 실제 수행 내용으로 오인될 수 있다.

## 백엔드 요청

1. 승인 전에 구조화 명세를 실행 가능한 계획으로 검증한다.
2. 단계별로 `stepNo`, `id`, `title`, `action`, `url`, `selector`, 마스킹된 `value`, `operator`, `expected`, `timeoutMs`를 제공한다.
3. `navigate`의 대상 URL, `fill`의 selector와 value/secret reference, `click`의 selector, `assert`의 selector·operator·expected가 없으면 승인 또는 실행을 차단한다.
4. 권장 오류 코드는 `EXECUTION_PLAN_INVALID`, `STEP_PARAMETER_MISSING`, `UNSUPPORTED_ACTION`, `TARGET_URL_NOT_ALLOWED`다.
5. 다음 조회 계약을 제공한다.

```http
GET /api/v1/test-case-versions/{versionId}/execution-plan
```

```json
{
  "versionId": "uuid",
  "status": "READY",
  "environment": { "id": "uuid", "name": "Staging", "baseUrl": "https://example.test" },
  "steps": [],
  "warnings": [],
  "executable": true,
  "source": "AI"
}
```

6. 비밀번호·토큰·실제 secret 값은 반환하지 않고 `***` 또는 secret alias만 제공한다.
7. 실행 상세에 사용한 `testCaseVersionId`, 계획 hash/revision, 환경 ID·base URL, 계획 단계 수, 실제 수행 단계 수, 계획 단계와 step run의 연결 ID를 포함한다.
8. Worker는 요청된 승인 UUID의 `structured_spec.steps`만 실행하며 Seed, demo-target, 고정 샘플 fallback을 사용하지 않는다.
9. 계획이 비었거나 단계 수가 달라지거나 필수 파라미터가 없으면 Worker 시작 전에 차단한다.

## 통합 수용 기준

구조화 저장 → 계획 조회 → 승인 → 실행 생성 → 동일 UUID와 동일 단계 수 로드 → 모든 단계 결과 저장 → 계획/실제 비교 조회가 하나의 테스트로 검증돼야 한다. 계약과 검증 결과는 `FRONTEND_BACKEND_SYNC.md`와 `WORKSTREAM_STATUS.md`에 반영한다.

## 프론트 선반영

백엔드 계획 API 전까지는 현재 구조화 응답을 이용해 실행 전 예상 시나리오를 표시한다. 필수 파라미터가 누락된 계획은 실행을 차단하며, 계획 API가 제공되면 서버의 `executable`과 `warnings`를 단일 기준으로 전환한다.
