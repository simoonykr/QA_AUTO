# OpenAI Gateway·사용량 계약

작성일: 2026-09-01

## 적용 범위

- 실제 OpenAI 호출은 `POST /api/v1/test-case-versions/current/structure`에서만 발생한다.
- 모델은 서버 설정 `OPENAI_MODEL`로 관리하며 기본값은 `gpt-4o-mini`다.
- 한 HTTP 요청에서 Gateway 호출은 최대 1회이며 자동 재시도하지 않는다.
- 실행 생성·Redis·Playwright Worker 경로는 AI Gateway를 참조하지 않는다. `maxAiCalls=0` 실행은 계속 독립 수행된다.
- API 키, 원문, 인증값은 원장·로그·응답에 저장하지 않는다.

## 구조화 응답

기존 `StructuredTestCase` 필드는 유지되고 다음 `aiUsage`가 추가된다.

```json
{
  "aiUsage": {
    "source": "AI | CACHE | RULE_BASED",
    "callCount": 0,
    "inputTokens": 0,
    "outputTokens": 0,
    "costUsd": "0.00000000",
    "dailySpentUsd": "0.00000000",
    "dailyBudgetUsd": "1.00000000"
  }
}
```

- `AI`: 이번 요청에서 실제 호출 1회가 발생했다.
- `CACHE`: 같은 조직·모델·정규화 입력 결과를 재사용했으며 이번 호출과 비용은 0이다.
- `RULE_BASED`: AI가 비활성화됐거나 준비되지 않아 기존 규칙 기반 결과를 반환했으며 호출과 비용은 0이다.
- 금액은 부동소수 오차를 피하기 위해 소수점 8자리 문자열로 반환한다.

## 원장·예산·캐시

- `ai_usage_ledger`: 요청 해시, 모델, 상태, 입력·출력 토큰, 예약 비용, 실제 비용, upstream request ID와 오류 코드만 기록한다.
- `ai_structure_cache`: 조직·요청 해시·모델별 구조화 결과를 기록한다. 원문과 API 키는 저장하지 않는다.
- UTC 일자 기준 완료 비용 합계와 최대 예상 비용을 DB advisory lock 안에서 비교한다.
- 최대 예상 비용까지 포함해 `AI_DAILY_BUDGET_USD`를 넘으면 외부 호출 전에 차단한다.
- 기본 공식 단가는 `gpt-4o-mini` 입력 `$0.15/1M`, 출력 `$0.60/1M`이며 서버 설정으로 변경할 수 있다.

## 오류 계약

모든 오류는 기존 `{ code, message, requestId, retryable, details? }` envelope를 사용한다.

| HTTP | code | 의미 | retryable |
|---|---|---|---|
| 429 | `AI_DAILY_BUDGET_EXCEEDED` | 일일 예산과 예약 비용을 합산하면 한도 초과 | false |
| 502 | `AI_UPSTREAM_ERROR` | OpenAI HTTP/연결 오류 | upstream 5xx 또는 연결 오류만 true |
| 502 | `AI_RESPONSE_INVALID` | JSON schema 결과 또는 사용량 응답 검증 실패 | false |
| 502 | `AI_USAGE_LIMIT_ERROR` | 실제 사용 비용이 선예약 상한 초과 | false |
| 504 | `AI_TIMEOUT` | 설정된 Gateway 제한시간 초과 | true |
| 500 | `AI_INTERNAL_ERROR` | 원장·캐시 저장 중 내부 오류 | true |

## 로컬 안전 시작

```powershell
# 실행 중인 기존 컨테이너에서 비어 있는 로컬 비밀값 복구(값은 출력하지 않음)
.\backend\scripts\recover_public_env.ps1

# 비밀값과 Compose 보간만 검증
.\backend\scripts\start_public_demo.ps1 -Action config

# 검증 성공 시에만 빌드·실행
.\backend\scripts\start_public_demo.ps1 -Action up
```

`.env.public`은 Git에서 제외된다. 필수 DB·MinIO·데모 인증·세션 값이 비었거나 placeholder이면 시작 스크립트가 Compose 실행 전에 중단한다. AI가 활성화된 경우 키·예산과 `AI_MAX_CALLS_PER_RUN=1`도 검증한다.
