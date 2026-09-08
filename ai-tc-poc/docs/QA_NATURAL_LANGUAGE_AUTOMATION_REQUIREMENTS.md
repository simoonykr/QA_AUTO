# QA 자연어 TC 기반 AI 자동화 요구사항

작성일: 2026-09-03

## 기본 원칙

QA는 기획서·디자인·정책 명세를 바탕으로 기존 방식대로 자연어 TC를 작성한다. QA에게 CSS selector, Playwright action, assertionType, operator, timeout, DOM 구조 등 실행 엔진 내부 명세를 직접 작성하도록 요구하지 않는다.

AI와 Playwright가 자연어 TC를 해석하고 실제 화면에서 검증하여 실행 명세를 생성한다.

## 현재 확인된 문제

`KakaoGames_AI_Automation.xlsx`에는 `KG-WEB-001~021`의 독립된 TC 21건이 있다. 가져오기에서는 메타데이터 9행 제외와 TC 21건 감지가 정상적으로 표시됐지만 이후 구조화·실행 계획에서 다음 문제가 발생했다.

- 여러 TC가 하나의 ExecutionPlan으로 합쳐짐
- `Not Test`, `Source:` 등 결과·보고용 값이 ASSERT 단계로 생성됨
- 원문과 대상 환경에 없는 `http://demo-target`이 NAVIGATE 단계에 추가됨
- TC 제목, URL, 기대 결과가 잘못 분리됨
- 실행 불가능한 계획이 `READY`로 판정됨
- 잘못된 계획을 Worker가 실행한 뒤 실패

## 2026-09-08 방향 변경: 페이지 우선 시나리오 생성

자연어 TC를 먼저 완전한 Playwright 실행 명세로 변환하는 방식은 TC 형식과 표현 편차에 지나치게 의존한다. TC ID·제목·보고용 메타데이터가 실행 단계가 되거나, 행동과 기대 결과가 잘못 분리되고, 실제 화면에 없는 selector·URL이 생성되는 문제가 반복됐다. 잘못된 구조화 결과를 QA가 모두 수정·삭제하는 것도 실사용 흐름으로 적합하지 않다.

따라서 다음 구현부터 **실제 페이지에서 검증 가능한 기본 시나리오를 먼저 생성하고 자연어 TC는 테스트 목적과 누락 검증을 보강하는 자료로 사용**한다. 자연어 TC는 실행 명세의 단일 진실 공급원이 아니며, 실제 페이지 분석 결과도 TC의 업무 의도를 임의로 대체하지 않는다. 두 입력의 차이를 QA가 검토·승인한다.

```text
실행 환경·시작 URL 선택
→ Playwright 읽기 전용 페이지 탐색
→ 화면 요소·이동 흐름·검증 가능한 상태 수집
→ AI가 검증된 요소만 사용해 기본 테스트 시나리오 작성
→ 자연어 TC에서 대상·행동·기대 결과만 단순 추출
→ 페이지 시나리오와 TC 비교
→ 누락·불일치·자동화 불가 항목 제안
→ QA가 추가·제외·수정
→ 승인된 revision만 Worker 실행
```

단계 출처는 다음 값으로 구분한다.

- `PAGE_DISCOVERY`: 실제 페이지와 Playwright 검증 근거
- `TEST_CASE`: 자연어 TC 원문 근거
- `AI_SUGGESTION`: AI가 제안한 보강 단계
- `MANUAL`: QA가 직접 추가하거나 수정한 단계

### 백엔드 작업과 변경 이유

백엔드는 자연어 문장을 action 키워드로 직접 치환하는 정확도 개선보다 페이지 기반 시나리오 생성 경로를 우선 구현한다. 이 방식은 selector와 URL을 실제 페이지에서 검증할 수 있고, 자연어 해석 실패가 전체 실행 계획을 오염시키는 범위를 줄인다.

1. 페이지 분석 결과로 기본 시나리오를 만드는 API 계약을 추가한다. 후보 endpoint는 `POST /api/v1/page-discoveries/{discoveryId}/scenarios`이며 선택적인 `testCaseVersionId`와 `maxAiCalls`를 받는다.
2. 응답에는 scenario ID, revision, 목적, 탐색 페이지, 단계, 검증된 selector, assertion, 자동화 가능성, 단계별 출처·근거, warnings, `aiUsage`를 포함한다.
3. 페이지 분석은 URL·제목·role·accessible name·label·placeholder·표시 텍스트·안정 ID/name·링크 URL·visible/enabled·iframe·Shadow DOM·클릭 전후 비교 가능한 상태만 수집한다. 전체 HTML, 입력값, 쿠키, 비밀번호, 토큰과 개인정보는 저장하거나 AI에 전달하지 않는다.
4. AI는 서버가 부여하고 Playwright가 검증한 element ID만 선택한다. 임의 selector·허용 범위 밖 URL을 만들 수 없으며, TC·시나리오당 최대 1회와 기존 일일 예산·비용 원장·캐시를 유지한다.
5. 자연어 TC 분석은 우선 `target`, `actions[]`, `expectedResults[]` 추출로 단순화한다. TC ID, Result, BTS ID, Comment, Source와 보고서 값은 실행 입력에서 제외한다.
6. TC와 페이지 시나리오 비교 결과는 `MATCHED | TC_ONLY | PAGE_ONLY | CONFLICT | NOT_AUTOMATABLE`로 반환한다. `TC_ONLY`, `CONFLICT`, `AI_SUGGESTION`은 QA 선택 없이 실행 계획에 자동 편입하지 않는다.
7. 단계 추가·제외·순서 변경·assertion 수정·후보 선택·제안 채택은 새 revision과 감사 로그로 기록하고 승인된 revision만 Worker가 읽는다.
8. 미검증 selector, stale fingerprint, 허용 도메인 밖 URL, 근거 없는 단계, 미확인 충돌, 자동화 불가능한 필수 assertion이 남으면 `executable=false`로 승인·실행을 차단한다.

### 프론트엔드 작업

1. 작성 시작 순서를 `환경 선택 → 시작 URL → 선택적 TC 업로드 → 페이지 분석 → AI 시나리오 생성`으로 변경한다.
2. 페이지 접속, 요소 수집, 후보 검증, 흐름 분석, AI 시나리오 작성, TC 비교 상태를 표시한다.
3. 단계별 행동·대상·검증 selector·기대 결과·자동화 가능성·출처·근거·warning을 검토 화면에 표시한다.
4. 비교 결과별로 `시나리오에 추가`, `이번 실행에서 제외`, `수동 검증`, `문구 수정`, `무시`를 제공한다.
5. 분석·재생성 시작 시 이전 client 승인 versionId, 실행 계획, discovery, 후보 선택, 편집 상태와 실행 설정 연결을 초기화한다. 서버의 과거 READY 버전과 실행 이력은 삭제하지 않는다.
6. 분석 중 환경·URL·TC 변경과 중복 클릭을 막고 요청 ID 또는 AbortController로 늦은 응답을 무시한다.
7. 구조화·승인 후 TC 목록을 새로고침하며 동일 externalId는 하나의 TestCase 행으로 유지하고 버전·실행 이력은 상세에서 구분한다.

### 변경 후 구현 우선순위

1. 페이지 분석 결과 기반 기본 시나리오 생성 API와 저장 모델
2. 프론트의 환경·URL 우선 시작 흐름
3. 단계별 근거·출처 계약과 검토 UI
4. 자연어 TC 단순 추출
5. TC와 페이지 시나리오 비교 및 보강 제안
6. QA 선택·revision·승인·Worker 실행 연결
7. 요청 경쟁 방지와 실제 페이지 통합 회귀

아래 기존 요구사항은 XLSX 파싱, selector 검증, 잘못된 계획 방어, 실행 이력에 계속 적용한다. 단, 기존의 `TC 분석 → 페이지 탐색` 순서는 위 페이지 우선 흐름으로 대체한다.

## 기존 상세 요구 흐름 (페이지 우선 순서로 적용)

```text
XLSX 업로드
→ 보고서 영역과 TC 테이블 분리
→ TC별 독립 데이터로 파싱
→ 사용자가 분석할 TC 선택
→ AI가 TC별 목적·전제조건·절차·기대 결과 분석
→ 실제 대상 페이지 탐색
→ AI가 TC와 화면 요소를 의미적으로 매핑
→ Playwright가 selector 후보 검증
→ TC별 실행 예정 시나리오 생성
→ QA 검토·승인
→ Worker 실행
→ 실행 이력·단계 결과·증적 저장
```

## 1. XLSX TC별 파싱

가져오기 API는 단일 `rawText`뿐 아니라 TC별 객체를 반환해야 한다.

```json
{
  "detectedTestCaseCount": 21,
  "testCases": [
    {
      "externalId": "KG-WEB-019",
      "depth1": "전체게임",
      "depth2": "필터",
      "depth3": "PC 선택",
      "precondition": "전체게임 영역 노출",
      "steps": ["#PC 클릭", "목록 갱신 확인"],
      "expected": "#PC가 활성화되고 PC 대상 게임만 남으며 중복이나 빈 카드가 없다",
      "sourceUrl": "https://kakaogames.com/"
    }
  ]
}
```

아래 열은 원본·감사 목적으로 보관할 수 있지만 AI 시나리오 생성 입력에서는 제외한다.

- Result(AOS), Result(IOS)
- BTS ID
- Comment
- `Not Test`
- `Source:` 및 확인일

각 TC는 별도의 TestCase와 TestCaseVersion으로 저장한다. 여러 TC ID를 하나의 Version으로 구조화하지 않는다.

## 2. AI 시나리오 설계

AI는 문장을 action 키워드로 단순 치환하지 않고 테스트 목적과 검증 전략을 설계한다.

예: `KG-WEB-019`

```text
목적: 전체게임의 PC 필터 동작 검증
사전 상태: 카카오게임즈 메인 페이지 접속, 전체게임 영역 표시
예상 시나리오:
1. 메인 페이지 접속
2. 전체게임 영역 탐색
3. #PC 필터 버튼 후보 탐색
4. 클릭 가능한 단일 후보인지 검증
5. 버튼 클릭
6. #PC 활성 상태 확인
7. PC 게임 목록만 표시되는지 확인
```

기대 결과의 자동화 가능성을 다음 상태로 구분한다.

- `AUTOMATABLE`
- `PARTIALLY_AUTOMATABLE`
- `MANUAL_REVIEW_REQUIRED`
- `UNSUPPORTED`

검증하기 어려운 기대 결과를 임의 selector나 단순 text assertion으로 만들지 않는다.

## 3. 구조화 명세

AI는 처음부터 CSS selector를 추측해 확정하지 않고 대상 의도를 저장한다.

```json
{
  "id": "step-2",
  "actionIntent": "click",
  "targetDescription": "전체게임 영역의 #PC 필터 버튼",
  "selectorHint": { "role": "button", "name": "#PC", "text": "#PC" },
  "selector": null,
  "resolutionStatus": "UNRESOLVED"
}
```

selector resolution 상태는 `UNRESOLVED | RESOLVING | RESOLVED | AMBIGUOUS | NOT_FOUND | STALE`을 사용한다.

## 4. 실제 페이지 기반 의미 매핑

AI가 원문만 보고 계획을 만드는 것으로 끝내지 않는다.

```text
AI 자연어 의도 분석
→ Playwright 읽기 전용 페이지 접속
→ DOM·접근성 트리·표시 텍스트 수집
→ 관련 요소만 AI에 제공
→ AI 의미 매핑
→ Playwright 후보 검증
```

수집 범위는 URL, 페이지 제목, role·accessible name, label, placeholder, 표시 텍스트, 안정적인 data-testid/id/name, 링크 URL, visible/enabled, iframe·shadow DOM 정보로 제한한다. 전체 HTML, 입력값, 쿠키, 비밀번호, 토큰과 개인정보는 저장하거나 AI에 전달하지 않는다.

현재 1차 구현은 `maxAiCalls=0` 규칙 기반 후보와 Playwright 검증을 유지한다. 실제 AI 의미 매핑은 TC당 최대 1회와 일일 예산 제한을 적용해 후속 활성화한다. 상세 selector 탐색 계약은 `AI_PAGE_DISCOVERY_REQUIREMENTS.md`를 따른다.

## 5. Selector 후보 검증

우선순위는 data-testid → role+name → label → placeholder → 안정적인 id/name → 링크 URL → 표시 텍스트 → CSS 구조 순서다.

Playwright가 matchCount, visible, enabled, click/fill 가능 여부와 기대 role·text 일치를 검증한다.

- 유효 후보 1개: `RESOLVED`
- 후보 없음: `NOT_FOUND`
- 유효 후보 복수: `AMBIGUOUS`
- 페이지 fingerprint 변경: `STALE`

미해결 단계가 하나라도 있으면 `executable=false`로 반환하고 승인을 차단한다.

## 6. 잘못된 계획 방어

다음 조건은 승인할 수 없어야 한다.

- 서로 다른 TC ID가 하나의 Version에 포함됨
- `Not Test`, `Source:`, 결과 집계가 action/assertion으로 생성됨
- 원문과 환경에 없는 `demo-target` URL 생성
- 허용 도메인 밖 URL
- click/fill/assert 대상 미해결
- 검증 불가능한 기대 결과를 임의 assertion으로 변환
- 빈 실행 계획 또는 서로 모순되는 단계

이 경우 구체적인 `warnings`와 함께 `executable=false`를 반환한다.

## 7. 실행 이력

현재 DB에는 Execution이 저장되지만 `GET /test-cases`는 `passRate=0`, `lastExecutedAt="실행 기록 없음"`을 고정 반환하며, 전체 실행 이력 목록 API가 없다.

필요 API:

```http
GET /api/v1/executions
GET /api/v1/test-cases/{testCaseId}/executions
GET /api/v1/executions/{executionId}/details
```

실행 목록에는 execution ID, TC ID·제목, version ID, status, errorCode, 계획/완료 단계 수, 시작·종료 시각, duration, artifact 수와 재시도 부모 ID를 포함한다. `GET /test-cases`도 실제 Execution 집계로 성공률과 마지막 실행 시각을 반환한다.

## 8. 프론트엔드 후속 작업

백엔드 계약 확정 후 다음을 구현한다.

- 감지된 TC 목록과 원문 미리보기
- 분석 대상 개별·복수 선택
- `선택한 TC AI 분석`
- 분석 대기, 페이지 분석 필요, 검토 필요, 실행 가능, 자동화 불가 상태
- TC별 예상 수행 시나리오와 자동화 가능성 검토
- 페이지 분석, 후보 선택, 실행 계획 적용
- 개별·일괄 승인
- TC별 최근 결과·성공률·마지막 실행
- 실행 이력 목록과 상태 필터
- 실패 단계·오류 코드·selector·assertion·PNG 증적 상세
- 재시도와 원본 실행 관계

## 기존 구현 우선순위 (2026-09-08 이후 상위 우선순위로 대체)

1. 다중 TC의 단일 계획 생성 차단
2. XLSX를 TC별 객체로 분리
3. 선택 TC 한 건의 AI 시나리오 설계
4. 페이지 분석과 selector resolution 연결
5. 실행 가능성 검증 강화
6. TC별 저장·승인·실행
7. 실행 이력 목록·상세 API와 프론트 UI
8. 단일 TC 전체 흐름 검증 후 일괄 분석 확대
