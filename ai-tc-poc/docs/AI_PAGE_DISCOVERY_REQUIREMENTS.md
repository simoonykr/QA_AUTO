# AI 페이지 탐색·Selector Resolution 요구사항

작성일: 2026-09-03

## 목적

QA는 기획서·디자인 명세를 바탕으로 기존 방식대로 자연어 TC를 작성한다. QA에게 CSS selector, action, assertionType 등 실행 엔진 내부 명세 작성을 요구하지 않는다.

시스템이 자연어 TC를 실행 가능한 계획으로 변환하고 실제 페이지에서 대상 요소를 검증한다.

```text
자연어 TC
→ AI 의도·시나리오 구조화
→ Playwright 읽기 전용 페이지 탐색
→ DOM·접근성 정보 수집
→ AI 기반 화면 요소 매핑
→ selector 후보 실제 검증
→ 실행 예정 시나리오 생성
→ QA 검토·승인
→ Worker 실행
```

## 1. 자연어 구조화 모델 확장

구조화 단계에서 selector를 추측해 확정하지 않고 사용자의 대상 의도를 먼저 저장한다.

```json
{
  "id": "step-2",
  "action": "click",
  "title": "PC 필터 선택",
  "targetDescription": "전체게임 영역의 PC 필터 버튼",
  "selectorHint": { "role": "button", "name": "#PC", "text": "#PC" },
  "expected": "PC 게임만 표시되고 PC 필터가 선택 상태가 된다",
  "selector": null,
  "resolutionStatus": "UNRESOLVED"
}
```

`resolutionStatus`:

- `UNRESOLVED`: 아직 탐색하지 않음
- `RESOLVING`: 후보 탐색·검증 중
- `RESOLVED`: 유일하고 실행 가능한 요소로 확정
- `AMBIGUOUS`: 유효 후보가 복수
- `NOT_FOUND`: 유효 후보 없음
- `STALE`: 페이지 변경으로 기존 결과 재검증 필요

원문에 근거가 없는 CSS selector는 AI가 임의로 저장하지 않는다.

## 2. Playwright 페이지 탐색

승인 전에 선택된 테스트 환경의 실제 URL에 접속하여 다음 정보를 수집한다.

- 현재 URL과 페이지 제목
- 접근성 role·name
- label·placeholder·표시 텍스트
- 버튼·링크·입력 등 상호작용 요소
- 안정적인 `data-testid`, `id`, `name`, 링크 URL
- iframe·shadow DOM 여부
- visible·enabled·editable 상태
- selector 후보별 매칭 개수

전체 HTML을 AI에 전달하지 않고 관련 요소만 정제한다. 쿠키, 비밀번호, 토큰, 입력값과 개인정보는 수집·전달하지 않는다.

## 3. Selector 후보 생성·검증

후보 우선순위:

1. `data-testid`
2. 접근성 role + name
3. label
4. placeholder
5. 안정적인 `id`·`name`
6. 링크 URL
7. 표시 텍스트
8. CSS 구조 selector

Playwright가 후보별 존재 여부, matchCount, visible, enabled, 클릭·입력 가능 여부와 예상 role/text 일치를 검증한다.

- 유효 요소 1개: `RESOLVED`
- 유효 요소 0개: `NOT_FOUND`
- 유효 요소 2개 이상: `AMBIGUOUS`
- 페이지 fingerprint 변경: `STALE`

`NOT_FOUND`, `AMBIGUOUS`, `STALE` 단계가 하나라도 있으면 `executable=false`로 반환하고 승인을 차단한다.

## 4. API 초안

### 탐색 시작

```http
POST /api/v1/test-case-versions/{versionId}/discover
```

```json
{ "environmentId": "uuid", "maxPages": 3, "maxAiCalls": 1 }
```

응답: `{ "discoveryId": "uuid", "status": "QUEUED" }`

### 탐색 상태·결과 조회

```http
GET /api/v1/test-case-versions/{versionId}/discoveries/{discoveryId}
```

상태: `QUEUED | PROVISIONING | SCANNING | MAPPING | VALIDATING | COMPLETED | NEEDS_REVIEW | FAILED | CANCELLED`

결과에는 탐색 페이지, 단계별 `targetDescription`, `resolutionStatus`, selector 후보, 선택 후보, matchCount, visible, enabled, confidence, warnings, executable을 포함한다.

### 탐색 결과 적용

```http
POST /api/v1/test-case-versions/{versionId}/discoveries/{discoveryId}/apply
```

복수 후보는 사용자가 선택한 `candidateId`를 전달한다. 적용 성공 시 갱신된 `ExecutionPlanResponse`를 반환한다.

## 5. 실행 계획 반영

탐색 결과 적용 시 다음을 보장한다.

- 선택된 selector를 `structured_spec.steps`에 저장
- `planRevision` 증가 및 `planHash` 재계산
- 탐색 URL·시각·페이지 fingerprint 저장
- AI model·prompt version·사용량 기록
- 감사 로그 기록
- 갱신된 steps, warnings, executable을 반환

Worker는 적용된 동일 revision과 plan hash만 실행한다.

## 6. 안전·비용 제한

- 최초 탐색은 읽기 전용
- 환경 allowlist 밖 이동 차단
- 결제·삭제·가입·게시·파일 업로드 등 파괴적·외부 변경 행동 금지
- DOM 크기, 요소 수, 페이지 수와 탐색 시간 제한
- TC당 AI 호출 최대 1회 및 일일 예산 적용
- 동일 페이지 fingerprint 캐시
- AI 실패 시 규칙 기반 후보까지만 제공
- 사용자 승인 전 실제 업무 행동 실행 금지

## 7. 프론트엔드 작업

백엔드 계약 확정 후 구조화 검토 화면에 다음을 연결한다.

- `페이지 분석 시작`과 분석 환경·대상 URL 표시
- 탐색 진행 상태와 단계별 매핑 결과
- `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `STALE` 강조
- selector 후보의 전략·일치 개수·신뢰도 표시
- 복수 후보 선택 및 찾지 못한 단계의 기존 수동 편집 제공
- 결과 적용 후 steps, revision, planHash, warnings, executable 갱신
- 모든 필수 단계가 해결되고 `executable=true`일 때만 승인
- fingerprint 변경, 시간 초과, AI 예산 초과 오류 안내
- Mock API에 성공·복수 후보·실패 흐름 구현

## 역할 구분

- AI: 자연어 TC 의미와 실제 화면 요소 후보 연결
- Playwright: 페이지 탐색과 후보의 실행 가능성 검증
- 백엔드: 보안, 상태, 비용, revision, plan hash 관리
- 프론트엔드: 진행 상황, 후보 검토·선택, 최종 승인 UX
- QA: 자연어 TC 작성과 실행 예정 시나리오 최종 검토

