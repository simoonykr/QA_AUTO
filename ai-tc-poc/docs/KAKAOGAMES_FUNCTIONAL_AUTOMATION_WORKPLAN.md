# KakaoGames 기능 자동화 전환 작업 계획

작성일: 2026-09-16

## 1. 검증 결과와 현재 한계

Temporary Staging에서 `https://kakaogames.com/`을 직접 분석하고 승인·Worker 실행까지 검증했다.

- 현재 페이지 분석: `COMPLETED`
- 수집 요소 29개, 화면 영역 7개, 상호작용 후보 25개
- 실제 관찰 상태 변화 0개
- 내부 링크 포함, 깊이 1, 최대 3페이지 요청에도 방문 페이지는 1개
- 생성된 29개 시나리오는 모두 요소 `visible` assertion
- `#모바일` 하나를 채택한 최종 실행 계획은 `NAVIGATE → ASSERT visible` 2단계
- Worker는 2/2 PASS와 스크린샷 1개를 저장했지만 버튼 클릭과 목록 변경은 실행하지 않음

따라서 현재 PASS는 KakaoGames 필터 기능 성공이 아니라 페이지 접속과 `#모바일` 버튼 표시만 의미한다. 목표 흐름은 다음과 같다.

```text
KakaoGames 접속
→ 전체게임 영역 확인
→ #모바일 클릭
→ 선택 상태와 모바일 게임 목록 변경 확인
→ #전체 클릭
→ 전체 목록 복원 확인
→ TC와 비교
→ 누락 TC 제안
→ 승인한 기능 단계만 Worker 실행
```

## 2. 작업 순서와 담당 선행 관계

기능 자동화의 주 선행 작업은 **백엔드 계약과 Worker 확장**이다. 프론트는 백엔드의 기능 후보·coverage·실행 단계 응답이 있어야 실제 기능 검토 화면을 연결할 수 있다.

다만 프론트의 TC 행 선택 오류는 API 확장과 무관한 P0이므로 즉시 병행한다.

1. 프론트 P0: TC 목록 행별 version 선택과 이전 실행 상태 초기화
2. 백엔드 P0: 기능 후보·상태 변화·coverage 계약 확정
3. 백엔드 P0: 안전한 필터 버튼 클릭과 목록 변화 관찰
4. 백엔드 P0: `click → assertion` 실행 계획과 Worker 연결
5. 프론트 P1: 기능 후보 검토·TC 보강·실행 계획 UI 연결
6. KakaoGames KG-WEB-021 실제 E2E 회귀

## 3. 프론트엔드 작업

### P0. TC 행별 실행 연결 수정

현재 `Cases`의 모든 행 실행 버튼은 행 정보를 넘기지 않고 동일한 전역 `onRun`을 호출한다. 이 때문에 KG-WEB-021을 눌러도 직전에 승인한 page scenario의 `activeVersionId`가 재사용된다.

- `onRun(testCaseId)` 또는 `onRun(testCase)` 형태로 변경
- 선택 TC의 최신 version과 상태를 서버에서 조회
- `READY`는 해당 `versionId`로 실행 설정 이동
- `REVIEW_REQUIRED`는 해당 TC의 구조화 검토 화면으로 이동
- 새 행 선택 전에 `activeVersionId`, `activeEnvironmentId`, `activeStructured`, `pendingExecution` 초기화
- 요청 중 중복 클릭 차단 및 빠른 행 전환 시 이전 응답 무시
- 동일 externalId는 한 목록 행으로 유지하고 버전은 상세에서 구분

완료 조건은 KG-WEB-021 클릭 시 KG-WEB-021만 열리고 이전 page scenario가 다시 열리지 않는 것이다.

### P0. 실행 대상 식별 정보 표시

실행 설정과 계획 상단에 TC ID, 제목, versionNo, versionId, 생성 출처, 대상 URL, 환경, 승인 revision을 표시한다. 임시 `TC-NEW` 표현이나 전역 선택값을 실제 실행 대상으로 오인하지 않게 한다.

### P1. 기능 후보 검토 UI

백엔드 `scenarioCandidates`를 영역별 카드로 표시한다.

- 기능 영역과 목적
- 사전 조건
- click/assert 단계
- 클릭 전후 상태와 변경된 영역
- 근거 element/interaction/state-change ID
- confidence와 automationStatus
- 단순 표시 검증/기능 검증/수동 검증/위험 행동 구분

### P1. 기능 단위 TC coverage와 즉시 보강

요소 29개를 각각 TC 누락으로 표시하지 않고 기능 후보 단위로 다음 enum을 표시한다.

- `COVERED`: TC로 충분히 검증
- `PARTIAL`: 단계 또는 기대 결과 일부 누락
- `MISSING_IN_TC`: 페이지 기능은 있으나 TC에 없음
- `TC_ONLY`: TC는 있으나 페이지 근거 없음
- `NOT_AUTOMATABLE`: 수동 검증 필요

`MISSING_IN_TC`는 기능 영역, 목적, 단계, 기대 결과, 페이지 근거와 자동화 가능성을 포함한다. `TC 보강 초안에 추가`, 문구 수정, 수동 검증, 제외를 서버 revision에 즉시 저장한다. 영역별 일괄 수동·제외 기능도 제공해 29개를 하나씩 처리하는 현재 UX를 개선한다.

### P1. 실행 계획과 모니터

실행 계획에는 실제 동작 순서를 표시한다.

```text
1. NAVIGATE  https://kakaogames.com/
2. CLICK     #모바일
3. ASSERT    #모바일 selected=true
4. ASSERT    게임 목록 변경
5. CLICK     #전체
6. ASSERT    전체 목록 복원
```

모니터는 클릭 전후 스크린샷, selector, 선택 상태, 목록 개수/signature, 실패 코드를 단계별로 보여준다. 제외·수동 항목은 PASS 범위에서 제외됐음을 명시한다.

### P2. 지표 정합성

- 사이드바의 TC 24, 실행 모니터 3 고정 badge 제거
- 실제 API 집계 사용
- Imported TC와 Page scenario 필터 제공
- 표시 확인 PASS와 기능 동작 PASS를 구분

## 4. 백엔드 작업

### P0. 기능 후보 계약

discovery의 `areas`, `interactions`, `stateChanges`를 결합해 `scenarioCandidates`를 반환한다.

```json
{
  "id": "candidate-game-filter-mobile",
  "areaId": "area-game-filter",
  "purpose": "모바일 필터 선택 시 게임 목록 변경 확인",
  "preconditions": ["전체게임 영역이 표시됨"],
  "steps": [
    {"action": "click", "interactionId": "interaction-mobile-filter"},
    {"action": "assert", "assertion": {"type": "selected_state", "expected": true}},
    {"action": "assert", "assertion": {"type": "list_changed"}}
  ],
  "evidence": {
    "elementIds": [],
    "interactionIds": [],
    "stateChangeIds": []
  },
  "automationStatus": "AUTOMATABLE",
  "confidence": 1
}
```

서버가 관찰하지 않은 기능 이름, selector 또는 기대 결과를 생성하지 않는다.

### P0. 안전한 일반 버튼 클릭 관찰

현재 checkbox/radio/tab 또는 명시적 ARIA 토글만 클릭하므로 `#모바일`, `#PC`, `#전체`은 상태 변화 대상에서 제외된다. 폼 외부이고 위험 행동·외부 전송·다운로드가 아니며 고유 selector가 검증된 버튼만 제한적으로 관찰한다.

클릭 전후 수집 대상:

- URL
- `aria-pressed`, `aria-selected`, checked
- 정규화된 선택 상태
- 연결 영역의 item count
- 안전한 element ID signature
- 표시 요소 집합과 영역 fingerprint

전체 HTML, 입력값, 쿠키와 개인정보는 저장하지 않는다. 최대 클릭 수를 제한하고 원상 복구 실패는 `MANUAL_REVIEW_REQUIRED`로 처리한다.

### P0. 클릭 대상과 변경 영역 연결

1. 클릭 전 영역별 fingerprint 저장
2. 안전 버튼 클릭 및 렌더 안정화
3. 클릭 후 영역별 fingerprint 비교
4. 변경 영역이 하나면 기능 후보 생성
5. 여러 영역이 바뀌거나 근거가 불명확하면 수동 검토
6. 원래 상태 복원 후 다음 후보 관찰

버튼 속성이 변하지 않아도 게임 목록 fingerprint가 변하면 기능 근거로 인정한다.

### P0. 시나리오·승인·Worker 확장

페이지 우선 시나리오 단계에 `navigate`, `click`, `wait`, `assert`를 허용한다. 승인 시 selector 단일 일치, discovery fingerprint, interaction/state-change 동일 출처, 클릭 후 기대 상태 재현과 위험 정책을 재검증한다.

Worker는 승인 순서대로 클릭 전 증적 저장 → 클릭 → 안정화 → 상태/목록 assertion → 클릭 후 증적 저장을 수행한다.

권장 오류 코드:

- `INTERACTION_TARGET_NOT_FOUND`
- `INTERACTION_TARGET_AMBIGUOUS`
- `EXPECTED_STATE_NOT_CHANGED`
- `LIST_CHANGE_NOT_OBSERVED`
- `PAGE_FINGERPRINT_STALE`
- `UNSAFE_ACTION_BLOCKED`
- `RESTORE_STATE_FAILED`

### P1. 자연어 TC와 기능 후보 비교

`#모바일 클릭`의 `#모바일`을 CSS ID로 해석하지 않고 visible text/accessible name으로 처리해 `role=button[name="#모바일"]`과 연결한다. 클릭 행동, 선택 상태 유지, 목록 갱신 기대 결과를 기능 후보 근거와 각각 비교해 coverage를 계산한다.

### P1. 다중 페이지 탐색

현재 동일 도메인의 query/fragment 없는 실제 `<a href>`만 탐색해 KakaoGames는 1/3페이지만 방문했다. 링크 role, 상대 경로, JS 버튼 이동 후보를 안전 정책 안에서 분리하고 방문·제외 사유를 집계한다. 방문 페이지별 영역과 interaction을 수집하며 시작 페이지의 `elements`만 시나리오 근거로 쓰는 제한도 해소한다.

### P1. Imported TC와 Page-first 경로 통합

기존 자연어 TC를 직접 click/assert 명세로 변환하지 않는다.

```text
Imported TC 선택
→ 목적·행동·기대 결과만 추출
→ 시작 URL 확인
→ Page-first discovery
→ 기능 후보와 TC 비교
→ QA 검토·revision 저장
→ 승인
→ Worker 실행
```

## 5. 공통 완료 기준

KG-WEB-021에서 다음을 모두 만족해야 한다.

- `#모바일`, `#전체`이 기능 후보로 생성됨
- TC 행동과 실제 role selector가 연결됨
- 클릭 전후 선택 상태와 게임 목록 변화 근거가 존재함
- 승인 계획에 CLICK과 후속 ASSERT가 포함됨
- Worker가 실제 필터 버튼을 클릭함
- 전후 스크린샷과 상태 근거가 저장됨
- 다른 TC를 선택하면 이전 versionId가 재사용되지 않음
- PASS가 표시 확인이 아니라 필터 기능 성공을 의미함
- 실제 AI 호출은 별도 승인 전까지 0회 유지
