# 프론트엔드 ↔ 백엔드 연동 메모

## 2026-09-16 기능 자동화 전환 작업 순서

- 백엔드가 먼저 `scenarioCandidates`, 기능 단위 coverage, 안전한 일반 버튼 클릭 전후 근거, click/assert 실행 계획과 Worker 계약을 확정한다.
- 프론트는 독립 P0인 TC 목록 행별 version 선택·이전 `activeVersionId` 초기화를 병행하고, 백엔드 계약 반영 후 기능 후보 검토·TC 보강·실행 증적 UI를 연결한다.
- KakaoGames 실검증에서 29개 표시 assertion만 생성되고 `#모바일` 클릭은 실행되지 않았다. 상세 계약과 완료 조건은 [`KAKAOGAMES_FUNCTIONAL_AUTOMATION_WORKPLAN.md`](KAKAOGAMES_FUNCTIONAL_AUTOMATION_WORKPLAN.md) 기준이다.

## 2026-09-15 discovery 경고 프론트 표시 완료

- 완료 응답의 기존 `warnings[].code/message`를 분석 범위·제외 항목 카드에 모두 표시한다. `PAGE_SKIPPED`를 포함한 서버 경고가 더 이상 성공 상태 뒤에 숨지 않는다.
- 경고는 분석 실패나 실행 가능 판정으로 재해석하지 않으며 기존 endpoint·enum·승인 조건을 변경하지 않는다. Mock에는 `LIMITED_READ_ONLY_DISCOVERY` 예시를 추가했다.
- 기능 후보·coverage 계약이 추가되면 이 경고 영역을 제외·미지원 수와 연결할 예정이다. 추가 API 변경 요청은 없다.

## 2026-09-15 stateChanges interaction 참조 수정

- `stateChanges[].interactionId`는 이제 같은 discovery의 `interactions[].id`를 정확히 참조한다. 이전 구현처럼 `elements[].elementId`를 반환하지 않는다.
- 프론트 `3bdb8fb`의 `state.interactionId === interaction.id` 매핑과 일치하며 API 필드 추가·enum 변경은 없다.

## 2026-09-15 안전한 상태 변화 근거 프론트 연동 완료

- discovery 응답의 선택 필드 `stateChanges[]`를 영역별 interaction에 매핑하고, 실제로 달라진 URL·ARIA·checked 전후 값만 표시한다. 응답이 없는 기존 discovery도 기존 UI로 정상 동작한다.
- 상태 변화 수와 `PLAYWRIGHT_OBSERVED` 출처를 표시하되, 기능 시나리오·TC coverage·Worker 실행 단계로 변환하지 않는다. 현재 승인 조건과 실행 근거는 변경하지 않았다.
- Mock에는 `aria-pressed=false → true` 관찰 예시를 추가했다. 추가 API 변경 요청은 없으며 다음 연동 대기는 기능 후보와 coverage enum 계약이다.

## 2026-09-14 안전한 토글 상태 변화 관찰 계약

- discovery GET에 선택 필드 `stateChanges[]`가 추가된다. 각 항목은 `interactionId`, 검증 selector, `before/after`의 URL·ariaPressed·ariaSelected·checked, `source=PLAYWRIGHT_OBSERVED`를 포함한다.
- checkbox/radio/tab과 명시적 ARIA 토글만 최대 10개 관찰한다. 폼 내부·위험 문구·일반 버튼·링크·입력은 실행하지 않는다. 변화가 실제 확인되지 않은 후보는 응답에 넣지 않는다.
- 기존 `areas/interactions/elements`와 승인 조건은 바뀌지 않는다. 프론트는 후속 기능 후보 계약 전까지 stateChanges를 자동화 완료나 TC coverage로 표현하지 않는다.

## 2026-09-14 화면 영역·상호작용 근거 프론트 연동 완료

- discovery 완료 화면에 `areas`와 `interactions`를 영역별로 표시한다. interaction의 kind/name/selector/enabled를 보여주되 `READ_ONLY_CANDIDATE`는 실행 가능한 클릭 시나리오가 아니라 관찰 근거로 안내한다.
- `PageFirstElement`의 신규 선택 필드는 기존 표시 assertion과 selector 근거를 보조하며 승인 조건은 변경하지 않았다.
- 실제 API 요청의 `maxPages:1` 강제 덮어쓰기를 제거했다. `includeInternalLinks/maxDepth/maxPages` 사용자 선택을 그대로 보내고 기본값만 1로 보정한다.
- Mock discovery에도 area/interaction 예시와 scope를 추가했다. 추가 endpoint·enum 변경 요청은 없다.

## 2026-09-14 화면 영역·상호작용 근거 계약

- `GET /api/v1/page-discoveries/{id}`에 선택 필드 `areas`, `interactions`가 추가됐다. `areas`는 `id/kind/name/elementIds`, `interactions`는 `id/areaId/elementId/kind/name/selector/enabled/risk/source`를 반환한다.
- `elements`에도 선택 필드 `tag`, `role`, `areaKind`, `areaName`, `interactable`가 추가됐다. 기존 필드와 fingerprint/Worker 검증은 호환된다.
- `risk=READ_ONLY_CANDIDATE`는 자동 실행 가능 판정이 아니다. 프론트는 클릭 시나리오나 coverage 결과로 과장하지 말고, 후속 상태 변화 검증 계약 전까지 관찰 근거로만 표시해야 한다.
- AI 호출은 0회이며 클릭·입력·iframe 검증·기능 추론은 아직 수행하지 않는다. 다음 연동 요청은 백엔드의 상태 변화와 `COVERED|PARTIAL|MISSING_IN_TC|TC_ONLY|NOT_AUTOMATABLE` 계약 이후다.

## 2026-09-14 bounded crawl 프론트 연동 완료

- `includeInternalLinks`, `maxDepth`, `maxPages` 입력과 응답 `scope`, `pages[].depth`, `pages[].elementCount` 표시를 연결했다. 요청 기본값과 서버 제약은 bounded crawl 1차 계약을 따른다.
- 내부 링크 포함 여부를 바꾸면 이전 discovery·scenario·revision 상태를 초기화한다. 분석 중에는 기존 busy 방어로 범위 변경과 중복 요청을 막는다.
- 연결 페이지의 후보 합계를 별도로 표시하되 `elements` 및 실행 근거가 시작 페이지에 한정된다는 경고를 유지한다. 추가 API/타입 변경 요청은 없다.
- 영역·상호작용·상태 변화·기능 coverage 계약이 추가되면 동일 화면의 커버리지 요약과 TC 누락 제안에 연결한다.

## 2026-09-14 bounded crawl 1차 계약

- 기존 `POST /page-discoveries` 요청에 선택 필드 `includeInternalLinks?: boolean`(기본 false), `maxDepth?: number`(0~2, 기본 0), `maxPages?: number`(1~5, 기본 1)를 추가했다. 기존 `{maxPages:1,maxAiCalls:0}` 요청은 그대로 동작한다.
- 내부 링크 포함 시 `includeInternalLinks=true`, `maxDepth>=1`을 함께 보내야 한다. 내부 링크를 끈 상태에서 깊이 또는 페이지 수를 늘리는 모순된 요청은 `DISCOVERY_SCOPE_INVALID`/422다.
- GET 응답에 선택적 `scope:{includeInternalLinks,maxDepth,maxPages}`, 각 `pages[]`에 선택적 `depth`, `elementCount`가 추가된다. 기존 필드는 변경하지 않았다.
- 방문 후보는 현재 navigation allowlist의 정확한 도메인, HTTP(S), query/fragment/인증정보 없음 조건을 모두 만족해야 한다. logout/delete/checkout/payment 등 위험 경로는 방문하지 않으며, 최대 깊이·페이지 수를 초과하지 않고 같은 정규화 URL은 한 번만 방문한다.
- 이번 1차는 탐색 범위와 페이지별 후보 수집 기반만 제공한다. `elements`, 시나리오 생성, 승인·Worker fingerprint는 시작 페이지 기준을 유지한다. 프론트는 후속 계약 전까지 연결된 페이지 전체가 자동화됐다고 표시하면 안 된다.
- 백엔드 전체·실제 Chromium 107 passed, TypeScript·프로덕션 빌드 통과, AI 호출 0회.

## 2026-09-14 기능 커버리지·누락 TC 보강 요청

- 프론트는 현 계약의 `PAGE_ONLY`를 `TC 누락 제안`으로 표시하고, 검증된 근거를 `ADD`로 즉시 review revision에 저장하는 커버리지 UX를 반영했다. endpoint와 enum 변경은 없다.
- 다음 백엔드 응답은 요소 수가 아니라 `areas`, `interactions`, `scenarioCandidates`, `coverage`를 반환해야 한다. coverage는 `COVERED|PARTIAL|MISSING_IN_TC|TC_ONLY|NOT_AUTOMATABLE`, 각 제안은 안정 ID, 기능 영역, 목적, 사전 상태, action/assertion 단계, 근거 element ID, confidence, automationStatus를 포함한다.
- 분석 요청은 현재 페이지/내부 링크 여부, maxPages, maxDepth를 명시하며 navigation/resource allowlist와 위험 행동 정책을 계속 적용한다. 클릭 전후 DOM·URL·활성 상태·목록 변화는 Playwright가 검증하고 전체 HTML·입력값·쿠키는 저장하지 않는다.
- 제안 채택은 중복 없는 새 draft revision으로 저장하고 selector/fingerprint를 재검증한다. 승인된 READY 버전은 변경하지 않으며 새 versionId만 실행에 사용한다. 실제 AI 활성화 전에는 규칙 기반/0회와 기능 제한을 응답에 명시한다.
- 이 계약이 추가되기 전 프론트는 PAGE_ONLY 표시 assertion만 다루며, 이를 전체 기능 테스트 커버리지로 표시하지 않는다.

## 2026-09-14 P0 후속 배포 확인

- `3d16ff8`까지 Temporary Staging 재배포 완료. `0010_resource_domains`가 적용됐고 Staging의 `resourceDomains=["cdn.jsdelivr.net"]` 응답 계약을 유지한다.
- 동일 `https://kakaogames.com/` discovery가 `COMPLETED`, 요소 29개를 반환하여 이전 `elements=[]` 재현은 해소됐다. title은 공란으로 남아 프론트가 `제목 없음` fallback을 사용한다.
- 프론트의 요소 0개 초안 생성 차단과 실행 선택 0개 승인 차단은 서버의 기존 `SCENARIO_EMPTY` 방어를 보완한다. API enum/endpoint 추가 변경은 없다.
- 회귀: 백엔드 104 passed/1 skipped, TypeScript·프로덕션 빌드·외부 Chromium UI 통과, AI 호출 0회.

## 2026-09-14 Temporary Staging 발견 사항

- 현재 배포에서 `https://kakaogames.com/` 페이지 우선 discovery가 `COMPLETED`이면서 `title` 없음, `elements=[]`를 반환했다. 이전 main 검증의 후보 29개와 다르므로 백엔드는 배포 이미지, `0010_resource_domains`, resource allowlist 및 렌더 안정화 적용을 우선 확인한다.
- `COMPLETED + elements=0`을 프론트가 정상 완료로 처리해 빈 기본 시나리오 생성까지 허용한다. 백엔드는 분석 불충분 warning/code를 반환하고, 프론트는 요소 0개일 때 생성·승인을 차단한다.
- TC 입력 5개 행은 전부 TC_ONLY였다. 모든 행 제외 후 revision 7, pending 0에서 승인 버튼이 활성화됐으나 서버는 SCENARIO_EMPTY 사용자 메시지 `실행할 검증 단계가 없습니다.`로 거절했다. 프론트 승인 활성 조건에 `scenario.steps.length > 0`과 실행 선택 존재 여부를 포함한다.
- 상세 재현과 완료 조건은 [`PAGE_FIRST_STAGING_TEST_2026-09-14.md`](PAGE_FIRST_STAGING_TEST_2026-09-14.md), 합의 UX는 [`PAGE_FIRST_USER_SCENARIO.md`](PAGE_FIRST_USER_SCENARIO.md)를 따른다.

## 2026-09-11 렌더링 리소스·시나리오 후보 확대

- 환경 응답에 선택 필드 `resourceDomains`를 추가했다. `allowedDomains`는 최상위 문서 navigation에만 사용하고, 정적 하위 리소스는 두 목록의 정확한 도메인 및 하위 도메인에서만 GET/HEAD로 허용한다. Staging은 migration `0010_resource_domains`로 `cdn.jsdelivr.net`을 명시한다.
- Worker와 페이지 우선 discovery는 load 완료, visible body, 750ms 안정화 후 요소 수집·성공 증적을 생성한다. 성공 증적은 viewport PNG이며 실행 모니터 주소창은 Artifact key 대신 실제 navigation URL을 표시한다.
- 페이지 분석 후보는 유일한 `data-testid`와 유일한 role+accessible name을 가진 제목·버튼·링크·입력 계열이다. 최대 50개, 표시·활성 상태를 저장하며 전체 HTML·입력값은 수집하지 않는다.
- 실제 KakaoGames 검증에서 본문 1,518자, 후보 29개를 확인했다. 광고·외부 API 등 명시하지 않은 호스트는 계속 차단됐다. 백엔드 104 passed/1 skipped, 실제 Chromium 1 passed, TypeScript 통과, AI 0회.

## 2026-09-11 재검증 3차: 중복 이동·WAIT·Staging 허용 도메인

- 구조화는 동일 URL의 `navigate`가 WAIT/assert 등 다른 단계 사이에 떨어져 있어도 최초 한 번만 유지한다. 비교는 trailing slash 제거와 소문자 정규화 기준이다. 기존 저장 버전은 자동 수정하지 않으므로 새 구조화 요청이 필요하다.
- `wait/domcontentloaded`는 selector가 없는 정상 단계다. 프론트 검토 및 실행 계획에는 `문서 로딩 완료 대기`로 표시하며 `필수 값 확인 필요`로 안내하지 않는다.
- migration `0009_allow_kakaogames_staging`은 기본 Staging 환경의 allowedDomains에 정확히 `kakaogames.com`만 추가한다. 하위 도메인을 포괄 허용하지 않으며 사용자정보·query·fragment URL 차단과 GET/HEAD 요청 제한은 유지한다.
- a4498d6의 지속 오류 카드와 좁은 화면 overflow 보완을 실제 public 이미지에 포함한다. API 및 공유 TypeScript 타입 변경은 없다.
- 검증: 백엔드 103 passed/경고 3건, TypeScript 통과, AI 호출 0회.
- 외부 HTTPS 배포 UI에서 `https://kakaogames.com/` discovery COMPLETED, 중복 제거·WAIT 문구·지속 오류·1280px 클릭을 확인했다. 기존 KG-WEB-001 저장 버전에는 소급 적용되지 않는다.

## 2026-09-11 재검증 2차: 진행 표시·원문 분류

- 프론트 최소 수정 배포: 분석 POST 수락 즉시 QUEUED 표시, API 30초 timeout, 공통 알림 수동 닫기(자동 소멸 제거), 시작 URL 자동 채움 제거. 두 화면 실제 Chromium 테스트 통과.
- 구조화는 importer의 `단계 N:` 래퍼 및 독립 번호 제거 후 분류한다. 연속 동일 URL 이동 중복 제거. selector 미해결 시 automationStatus=MANUAL_REVIEW_REQUIRED로 안내한다. 이전 저장 데이터는 자동 재작성하지 않는다.
- action=wait, operator=domcontentloaded 지원 추가. 기존 action 타입에 wait가 이미 포함돼 타입 확장 없음. selector는 불필요하며 문서 파싱 완료 대기만 의미한다. 다른 wait operator는 승인/실행 차단한다. 페이지 데이터 로딩 완료 검증은 별도 assertion이 필요하다.
- 검증: 백엔드 102 passed, TypeScript/이미지 빌드 통과, AI 0회. 사용자 XLSX 원본 대신 동일 래퍼 형태 합성 원문 회귀 테스트 및 배포 UI 검증을 사용했다.

## 2026-09-11 분석 오류·대상 URL 계약

- 기존 TC discovery 시작은 원문에 단일 HTTP(S) URL이 필요하다. 없으면 TARGET_URL_REQUIRED/422, 여러 개면 TARGET_URL_AMBIGUOUS/422, 환경 allowlist 위반 또는 인증정보/query/fragment 포함이면 TARGET_URL_NOT_ALLOWED/422. 페이지 우선에서는 기존 startUrl을 사용한다.
- navigate URL 미지정은 더 이상 환경 기본 demo-target으로 대체하지 않는다. 실행 계획에서 TARGET_URL_REQUIRED로 차단된다. 과거 저장 버전은 자동 수정하지 않으며 원문을 고쳐 새 버전으로 분석한다.
- 비동기 분석 FAILED의 errorCode 및 warnings[].code/message: DISCOVERY_TIMEOUT(접속/검증 시간 초과), DISCOVERY_CONNECTION_FAILED(DNS·네트워크·인증서 등 연결 오류), DISCOVERY_BROWSER_ERROR(기타 브라우저 오류), DISCOVERY_INTERNAL_ERROR(내부 처리 오류), TARGET_URL_NOT_ALLOWED(도메인 위반). 원본 예외·비밀 URL은 응답하지 않는다. 프론트는 재분석 버튼과 해당 안내를 표시한다.
- 기존 discovery에서 미확정/없는 검증 요소는 NEEDS_REVIEW 및 DISCOVERY_ELEMENTS_UNRESOLVED warning, executable=false다. FAILED와 구분하여 검토/분석 필요로 표시한다. 응답 필드·타입 변경은 없으며 code는 기존 string 필드다.
- Worker 실제 반복 실패 원인(hashlib 누락) 수정. 기존 discovery COMPLETED, 페이지 우선 실행 PASS, 실패 증적 PNG 정상. 전체 100 passed/TypeScript 통과/AI 0회.
- 프론트 담당: 업로드 TC를 페이지 우선 시나리오로 연결, 대상 URL·환경 표시, automationStatus와 실제 executable 구분, 좁은 화면 배치 보완. 백엔드 규칙 분류는 명시적인 기대 결과에 한정되며 자유 문장의 완전한 의미 이해를 보장하지 않는다.

## 2026-09-09 로컬 통합 배포 확인

- Docker 엔진 복구 및 `.env.public`/`compose.public-demo.yml` 빌드·migration·배포 성공. 테스트 페이지: `http://localhost:8080` (배포 PC 전용). 기존 데모 로그인 사용, 자격증명은 채팅/Git에 공개하지 않는다.
- 실제 페이지 우선 분석·선택 저장·승인(동일 revision 멱등성)·Worker 3단계 PASS. 의도적 실패 및 MinIO PNG 저장/다운로드 확인. API/공유 타입 변경 없음.
- frontend 이미지 빌드 성공, 백엔드 전체 89 passed, 실제 AI 0회. 환경 선택은 demo-target 포함 테스트 환경, 시작 URL은 `http://demo-target`, TC 없이 검토 생성 가능. 실제 운영 계정/개인정보 사용 금지.
- 재배포 시 AI_ENABLED=false/AI_MAX_CALLS_PER_RUN=0 프로세스 override 유지. Secure 쿠키 설정을 낮추지 않았으며 로컬 smoke만 loopback 요청에 쿠키를 명시한다.
- 외부 HTTPS 터널은 보안 검토 차단으로 미제공. 사용자 외부 공개 승인 후 별도 연결·HTTPS 쿠키 검증 필요. localhost 결과를 외부 Staging 검증 완료로 간주하지 않는다.

## 2026-09-09 실제 브라우저 검증

- API/타입 계약 변경 없음. 실제 Chromium에서 합성 페이지의 요소 수집 → 검토 선택 → Worker 표시 assertion → DOM 변경 차단 회귀를 추가·통과했다. 외부 페이지 및 AI 호출 없음.
- `RUN_BROWSER_TESTS=1`로 `tests/test_page_first_browser.py` 활성화 가능(Playwright Chromium 설치 필요). 정식 전체 89 passed/경고 4건, TypeScript 통과.
- 이는 브라우저 컴포넌트 통합 검증이다. Docker 엔진 연결 불가로 PostgreSQL·Redis·MinIO·배포 E2E 완료를 뜻하지 않는다. 프론트는 기존 계약을 유지하며 Staging 실검증은 엔진 복구 후 진행한다.

## 2026-09-08 21:17 계약 회귀 확인

- 프론트 4a14a45 연동 보완 반영 확인. 추가 API/타입 변경 없음.
- 실제 앱 HTTP 경로의 비교·검토·GET 직렬화, revision 충돌 409와 requestId, 미인증 401 방어를 테스트에 고정했다. DB는 대역 사용, 실제 AI 0회.
- 백엔드 정식 전체 88 passed/경고 4건 및 TypeScript 통과. PostgreSQL·브라우저·Staging 통합 검증은 여전히 별도다.

## 2026-09-08 20:47 연동 보완

- b381700 프론트 연동 확인 후 새 시나리오 생성 응답에 검증 단계별 PAGE_ONLY/PENDING comparisons를 추가했다. 기존 타입 변경은 없다. 자연어 TC가 없어도 이 행을 검토·저장하고 승인한다. 빈 페이지 또는 미검토 항목은 여전히 승인되지 않는다.
- 선택적인 TC 비교를 수행하면 초기 행을 대체하고 모든 선택을 PENDING으로 초기화한다. 기존 저장 초안의 빈 comparisons는 자동 변경하지 않으므로 새 초안을 생성한다.
- Mock도 초기 행 및 서버 승인 안전장치와 맞출 필요가 있다. 승인 environmentId는 실행 환경에 유지해야 한다. 프론트 검토·승인 비동기 응답은 입력 변경 시 폐기한다.
- 백엔드 전체 86 passed/경고 4건, TypeScript 통과, 실제 AI 0회. Staging 배포 검증은 별도다.

## 페이지 우선 2차 계약 (2026-09-08, a35df71 이후 백엔드)

이 절이 아래 1차의 승인·실행 미지원 설명을 대체한다. 기존 Mock UI는 유지하며 프론트 담당자가 연결한다. 모든 경로는 `/api/v1` 기준이며 기존 인증·요청 에러 처리는 동일하다.

| 순서 | API | 요청 | 응답 |
| --- | --- | --- | --- |
| 선택적 단순 추출 | POST `/test-cases/extract` | `{rawText}` | `{target, actions: string[], expectedResults: string[], source: "RULE_BASED", aiCallCount: 0}` |
| 비교 및 저장 | POST `/page-scenarios/{id}/compare` | `{expectedRevision, rawText}` | 전체 PageScenarioDraft, revision +1 |
| 선택 저장 | PATCH `/page-scenarios/{id}/review` | `{expectedRevision, selections: [{comparisonId, decision, draft?}]}` | 전체 PageScenarioDraft, revision +1 |
| 승인 | POST `/page-scenarios/{id}/approve` | `{expectedRevision}` | 전체 PageScenarioDraft, READY, executable=true, versionId, environmentId |
| 최신 상태 | GET `/page-scenarios/{id}` | 없음 | 동일 전체 응답 |

- 추가 응답: `comparisons: [{id,result,text,draft,decision,stepId,source,evidence}]`, `extractedTestCase`, `versionId`, `environmentId`. source는 TEST_CASE/PAGE_DISCOVERY이며 문구 변경 시 MANUAL. 원문 text와 수정 draft는 별도 보존한다.
- result는 MATCHED/TC_ONLY/PAGE_ONLY/CONFLICT/NOT_AUTOMATABLE. decision은 PENDING/ADD/MANUAL/EXCLUDE/IGNORE. ADD 및 IGNORE는 검증된 MATCHED/PAGE_ONLY 단계만 실행에 포함한다. IGNORE는 해당 페이지 단계를 유지한다는 뜻이며 충돌을 무시하고 강제 실행하는 기능이 아니다. MANUAL/EXCLUDE는 실행에서 제외한다.
- 매칭은 RULE_BASED 제한 구현이다. 유일한 요소 이름과 정확히 일치하는 `이름 표시`, `이름 표시 확인`, `이름 is visible`만 MATCHED다. 클릭·입력 기대 결과는 표시 assertion으로 대체하지 않는다. 미확인 항목을 추가하려면 향후 별도 근거 검증이 필요하다.
- rawText는 선택한 단일 TC의 줄 단위 내용(최대 50,000자)이다. 대상/전제조건, 행동, 기대 결과를 보존하며 Result/BTS ID/Comment/Source 등 보고 필드는 제외한다. XLSX 바이너리 또는 여러 TC 표 전체를 전송하지 않는다. 파이프 표는 TC_TABLE_REQUIRES_IMPORT/422. 빈 내용은 TC_EMPTY/422, 추출·비교 항목 최대 200개다.
- 비교를 다시 실행하면 이전 선택·문구 편집을 초기화한다. 검토 PATCH는 선택한 행만 수정한다. 요청 expectedRevision에는 마지막 서버 revision을 사용하고 성공 응답 전체로 상태를 교체한다. 로컬 revision을 서버에 맞추기 위해 임의 증가시키거나 409 후 자동 재시도하지 않는다.
- 오래된 revision: SCENARIO_REVISION_CONFLICT/409 → 최신 GET 후 사용자 재검토. 승인 후 수정: SCENARIO_ALREADY_APPROVED/409 → 새 시나리오 생성. 모든 행 선택 전 SCENARIO_REVIEW_REQUIRED/422, 실행 가능한 선택이 없으면 SCENARIO_EMPTY/422. 미검증 ADD/IGNORE는 COMPARISON_EVIDENCE_REQUIRED/422. 문구 변경은 assertion 의미나 근거를 바꾸지 않는다.
- 승인 시 완료된 최근 30분 이내 discovery와 요소의 유일성·표시·selector·fingerprint를 검증한다. 오래되면 DISCOVERY_STALE/409로 새 분석을 요구한다. 승인은 revision을 증가시키지 않고 동일 revision 재요청은 동일 versionId를 반환한다. 승인 후 시나리오는 변경 불가이며 별도의 READY TC 버전으로 고정된다.
- 승인 응답 이후 `GET /test-case-versions/{versionId}/execution-plan?environmentId=...`와 기존 `POST /executions`를 사용한다. 실행 요청 형식/Idempotency-Key는 기존 계약 그대로이며 maxAiCalls=0을 유지한다. 승인 API 자체는 Worker 실행을 시작하지 않는다. scenarioId를 testCaseVersionId로 보내지 않는다.
- Worker가 다른 environment/revision 또는 접속 직후 변경된 fingerprint를 발견하면 차단한다. 페이지 우선 실행만 discovery와 같은 GET/HEAD·허용 URL·서비스워커 제한을 적용한다. 동적 페이지·viewport/locale 차이도 재분석이 필요한 변경으로 판정될 수 있다.
- READY도 `automationStatus=PARTIALLY_AUTOMATABLE`, PARTIAL_SCOPE 경고를 유지한다. 수동·제외 항목까지 통과한 것으로 표시하면 안 된다. 전체 업무 자동화나 실제 AI 의미 비교 완료를 뜻하지 않는다.
- 공유 타입: TCExtraction, ScenarioComparison, ScenarioCompareRequest, ScenarioReviewRequest, ScenarioApproveRequest 및 PageScenarioDraft 응답 확장. 기존 API/Mock 호환 유지. 신규 migration은 없으며 1차 `0008_page_first` 적용이 필요하다.
- 검증: 백엔드 정식 전체 84 passed/경고 4건/AI 호출 0회, `npm run typecheck` 통과. Docker 엔진 미실행으로 PostgreSQL 동시성·실브라우저·Temporary Staging 통합 검증은 별도 필요하다.

## 페이지 우선 1차 계약 (2026-09-08, 제한된 초안 생성)

- `POST /api/v1/page-discoveries`: `{ environmentId, startUrl, maxPages: 1, maxAiCalls: 0 }` → HTTP 202 `{ discoveryId, status: "QUEUED" }`. TC 버전 없이 생성한다.
- `GET /api/v1/page-discoveries/{discoveryId}`: `QUEUED → SCANNING → COMPLETED|FAILED`, pages·elements·warnings·errorCode·aiUsage 반환. 1~2초 polling으로 조회한다.
- `POST /api/v1/page-discoveries/{discoveryId}/scenarios`: `{ maxAiCalls: 0 }` → HTTP 201 시나리오 초안. 완료되지 않은 discovery는 `DISCOVERY_NOT_READY`/409.
- `GET /api/v1/page-scenarios/{scenarioId}`: 저장한 동일 초안 조회. 모든 리소스는 조직·프로젝트 범위로 제한한다.
- 현재는 1페이지의 유일한 data-testid 및 role+accessible name 요소를 수집한다. 실제로 표시된 요소에 대한 visible assertion, PAGE_DISCOVERY 출처와 elementId·URL·fingerprint 근거를 저장한다. 클릭·입력, iframe 내부 검증과 업무 결과 추론은 수행하지 않는다.
- URL은 환경 navigation allowlist 내 HTTP(S), 인증정보·query·fragment 없는 주소만 허용한다. 정적 리소스는 별도 `resourceDomains`와 navigation allowlist의 정확한 도메인·하위 도메인에서 GET/HEAD만 허용하며 서비스워커를 차단한다.
- 모든 초안은 revision=1, REVIEW_REQUIRED, executable=false, aiUsage=RULE_BASED/0이다. 생성 버튼을 AI 생성으로 표기하지 않는다. 아직 승인·실행 API에 scenarioId를 보내면 안 된다.
- 반복 생성은 별도 scenarioId를 만든다. 편집 revision API, testCaseVersionId 연결, AI 생성, TC 비교·보강, 승인·Worker 실행 연결은 후속 구현이다. maxAiCalls=1과 미지원 필드는 422로 거절한다.
- 프론트 타입: PageFirstStartRequest, PageFirstDiscovery, PageScenarioDraft. 기존 API/Mock은 유지한다. 새 Mock UI 연결은 이 계약으로 후속 작업한다.
- DB migration `0008_page_first` 적용 필요. Docker 엔진 미실행으로 실제 배포·Playwright/DB 통합 검증은 미완료.

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

### 페이지 기능 후보·TC 커버리지 계약 (2026-09-16)

- 페이지 탐색 상세와 시나리오 draft는 선택 필드 `scenarioCandidates`와 `coverage`를 반환한다. 기존 필드는 변경하지 않아 기존 프론트와 호환된다.
- 후보는 Playwright가 `PLAYWRIGHT_OBSERVED`로 확인한 상태 변화와 서버가 수집한 `areaId`, `interactionId`, `elementId`만 사용한다. AI가 selector나 URL을 새로 만들지 않는다.
- `scenarioCandidates[]`는 `id`, `areaId`, `areaName`, `purpose`, `preconditions`, `steps`, `evidence`, `automationStatus`, `confidence`, `coverage`, `source`를 포함한다.
- 현재 단계 계약은 검증된 selector를 쓰는 `click`과 클릭 뒤 관찰된 `url`, `ariaPressed`, `ariaSelected`, `checked` 변화에 대한 `observed_state` assertion이다.
- `evidence`는 후보를 만든 `elementIds`, `interactionIds`, `stateChangeIds`를 제공한다. 같은 영역·selector의 중복 후보는 하나로 병합한다.
- `POST /api/v1/page-scenarios/{scenarioId}/compare-tc` 호출 시 추출된 TC의 action·expected result와 후보를 비교해 `COVERED`, `PARTIAL`, `MISSING_IN_TC`를 계산한다. 전체 enum은 향후 비교를 위해 `TC_ONLY`, `NOT_AUTOMATABLE`도 포함한다.
- 일반 버튼·영역 fingerprint 및 Worker 계약이 아래와 같이 완료됐다. 시작 상태 복구가 확인되지 않은 후보는 계속 `MANUAL_REVIEW_REQUIRED`이며 자동 실행할 수 없다.

### 일반 버튼 관찰·기능 후보 실행 계약 (2026-09-16)

- discovery의 `stateChanges[]`는 선택 필드 `pageFingerprint`, `changedAreas`, `restored`를 추가로 반환한다. `changedAreas[]`는 영역의 `kind`, `name`, 클릭 전후 `itemCount`, 클릭 전후 SHA-256 fingerprint만 포함하며 전체 HTML·입력값·쿠키는 포함하지 않는다.
- 폼 밖이며 selector 단일 일치, 표시·활성 상태인 `button|checkbox|radio|tab`만 최대 10개 관찰한다. 저장·전송·다운로드·결제·삭제·로그아웃 등 위험 문구는 제외한다.
- 클릭 뒤 시작 URL과 fingerprint 복구가 확인된 후보만 `automationStatus=AUTOMATABLE`이다. 복구 실패 후보는 `MANUAL_REVIEW_REQUIRED`이며 다음 후보 관찰과 자동 실행을 중단한다.
- `POST /api/v1/page-scenarios/{scenarioId}/candidates/{candidateId}/apply`, 요청 `{ expectedRevision }`: 복구·근거 검증된 후보를 현재 draft의 `selectedCandidateIds`에 저장하고 revision을 증가시킨다. 중복 적용은 ID 기준으로 병합한다.
- 수동 후보 적용은 HTTP 422 `SCENARIO_CANDIDATE_NOT_AUTOMATABLE`, 없는 후보는 404 `SCENARIO_CANDIDATE_NOT_FOUND`, revision 불일치는 기존 409 `SCENARIO_REVISION_CONFLICT`이다.
- 승인 시 서버는 discovery의 interaction ID, state-change ID, selector, `restored=true`를 다시 대조하고 `navigate → 기존 표시 assertion → click → observed_state assertion` 계획을 만든다.
- Worker의 `observed_state` assertion은 URL, `ariaPressed`, `ariaSelected`, checked, 페이지 fingerprint 및 변경 영역의 item count/fingerprint를 재수집해 비교한다. 불일치는 `EXPECTED_STATE_NOT_CHANGED` 또는 `LIST_CHANGE_NOT_OBSERVED`로 실패한다.
- Worker는 기능 click 직전 `INTERACTION_BEFORE_SCREENSHOT`, 직후 `INTERACTION_AFTER_SCREENSHOT` PNG를 저장한다. 최종 성공·실패 증적 계약도 그대로 유지한다.
- 프론트 다음 연결: `AUTOMATABLE` 카드의 `추가 후 테스트`에서 후보 apply API 호출 → 반환 revision/coverage/selectedCandidateIds 반영 → 기존 승인 API 호출 → 반환 versionId로 실행 설정 이동. `MANUAL_REVIEW_REQUIRED`는 apply 버튼을 비활성화한다.

### observed-state 실행 계획 응답 수정 (2026-09-17)

- `ExecutionPlanStep.expected`는 기존 문자열뿐 아니라 `observed_state`의 객체 기대값도 반환한다. `assertionType`은 기존 `url|text|element`에 `observed_state`가 추가됐다.
- 프론트 실행 계획 화면은 객체 기대값을 안전하게 JSON 문자열로 표시하고 “관찰 상태 검증”으로 안내한다. 자동 생성된 observed-state를 기존 문자열 단계 편집기로 암묵 변환하지 않는다.
- 재현 Version `cc384675-876b-403f-bb06-bbd56b3d0cc4`는 `READY`, plan revision `35`, `navigate → element assert → click → observed_state assert`로 정상 저장돼 있었으며 500 원인은 공개 응답 DTO 직렬화 제한이었다.
- 자연어 TC의 기능 후보 accessible name과 클릭/선택/목록 갱신 문구가 일치하면 비교 결과를 `MATCHED`로 반환하고 `candidateId`와 Playwright 관찰 근거를 제공한다. 기능 coverage의 `COVERED`와 TC 비교 `CONFLICT`가 동시에 나타나던 모순을 제거했다.
- 페이지 탐색 제한 경고는 “일반 버튼 미수행” 대신 “고유하고 안전한 일반 버튼·토글만 제한 관찰”로 최신 정책과 일치시켰다.
- 최대 3페이지 요청이 KakaoGames에서 1페이지만 방문하는 현상은 이번 500 수정과 독립적이며, JS 이동 후보·방문 제외 사유 집계가 필요한 P1 다중 페이지 탐색 범위로 유지한다.

### 일반 버튼 기능 후보 실행 프론트 연결 완료 (2026-09-16)

- 후보 apply API를 연결하고 응답의 최신 revision, coverage, selectedCandidateIds, warnings를 화면 상태에 반영한다.
- `AUTOMATABLE` 후보만 추가할 수 있고 `MANUAL_REVIEW_REQUIRED`, 이미 선택된 후보, 요청 처리 중 중복 클릭은 비활성화한다. 409 revision 충돌은 기존 최신 시나리오 재조회 흐름으로 복구한다.
- 관찰 근거에 변경 영역의 항목 수와 시작 상태 복구 여부를 표시한다. 적용 완료 후보는 카드와 버튼 상태로 구분되며 기존 승인 API가 반환한 versionId를 실행 설정으로 전달한다.
- Mock도 영역 fingerprint 변화·복구 성공·후보 적용·승인 후 `AUTOMATABLE`을 재현한다. 번들 Node 기준 TypeScript와 프로덕션 빌드가 통과했다.

### 페이지 기능 후보·TC 커버리지 프론트 연결 (2026-09-16)

- discovery와 scenario 응답의 `scenarioCandidates`, `coverage`를 동일한 기능 후보 카드와 5종 커버리지 요약으로 표시한다. TC 비교 뒤 서버가 갱신한 상태도 즉시 반영한다.
- 후보별 영역·목적·click/assert 단계·근거 개수·신뢰도를 표시하며 `MANUAL_REVIEW_REQUIRED`는 실행 가능이나 승인 완료로 표현하지 않는다.
- Mock은 관찰된 토글 후보와 `MISSING_IN_TC` 집계를 제공하고, TC에 `#PC` 필터가 포함되면 `COVERED`로 전환해 회귀를 확인할 수 있다.
- 프론트 타입 검사와 프로덕션 빌드는 통과했다. 다음 연동은 백엔드의 일반 버튼 영역 fingerprint 및 Worker 재현 계약 완료 후 진행한다.

- 구조화 단계는 `targetDescription`, `selectorHint`, `resolutionStatus`를 반환한다. 원문 근거가 없는 selector는 저장하지 않으며 초기 상태는 `UNRESOLVED`이다.
- `POST /api/v1/test-case-versions/{versionId}/discover`: `{ environmentId, maxPages: 1..3, maxAiCalls: 0..1 }`, HTTP 202 `{ discoveryId, status: "QUEUED" }`
- `GET /api/v1/test-case-versions/{versionId}/discoveries/{discoveryId}`: `QUEUED → PROVISIONING → SCANNING → MAPPING → VALIDATING → COMPLETED|NEEDS_REVIEW|FAILED` 상태와 페이지 fingerprint, 단계별 후보를 반환한다.
- 후보는 `DATA_TESTID`, `ROLE_NAME`, `LABEL`, `PLACEHOLDER`, `ID_NAME`, `LINK_URL`, `VISIBLE_TEXT`, `CSS` 전략과 `matchCount`, `visible`, `enabled`, `confidence`를 포함한다.
- 단계 상태는 `UNRESOLVED`, `RESOLVING`, `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `STALE`이다. 모든 실행 대상 단계가 `RESOLVED`가 아니면 `executable=false`이며 승인을 차단한다.
- `POST /api/v1/test-case-versions/{versionId}/discoveries/{discoveryId}/apply`: `{ selections: [{ stepId, candidateId }] }`; 선택된 실제 검증 selector를 저장하고 revision·planHash를 재계산한 `ExecutionPlanResponse`를 반환한다.
- 페이지 수집 데이터는 상호작용 요소의 접근성 이름·label·placeholder·안정 ID 등으로 제한하며 input 값, 쿠키, 비밀번호, 토큰, 개인정보와 전체 HTML은 저장하거나 AI에 전달하지 않는다.
- 현재 통합 검증 기본값은 `maxAiCalls=0`이며 규칙 기반 후보를 Playwright로 검증한다. AI 기반 의미 매핑을 활성화할 때도 TC당 최대 1회와 일일 예산 원장을 그대로 적용한다.
- OpenAI 의미 매핑 Gateway/서비스는 구현되어 있다. 입력은 단계의 `action`, `targetDescription`, `selectorHint`와 정제된 페이지 요소 메타데이터뿐이며, 모델은 서버가 부여한 `elementId`만 반환할 수 있다. 서버는 미등록 step/element ID를 폐기한다.
- 동일 의미 매핑 입력은 모델·prompt version을 포함한 hash로 캐시하며 캐시 응답은 `CACHE/0회`, 실제 응답만 `AI/1회`로 기록한다. 테스트는 Fake Gateway만 사용해 네트워크 호출을 0회로 유지한다.
- Worker의 자동 AI 의미 매핑 호출은 아직 연결하지 않았다. 별도 통합 승인 전에는 페이지 분석 요청을 계속 `maxAiCalls=0`으로 보내고 규칙 기반 Playwright 검증을 사용한다.

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
- 같은 프로젝트에서 동일한 `externalId`를 다시 구조화하면 기존 TestCase를 재사용하고 다음 `versionNo`의 새 `REVIEW_REQUIRED` TestCaseVersion을 만든다. 최초 생성 경쟁 또는 버전 충돌이 해소되지 않으면 표준 `TC_IMPORT_CONFLICT`/`TC_VERSION_CONFLICT`를 HTTP 409로 반환한다.
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
- Worker는 실패 단계의 `FAILURE_SCREENSHOT`뿐 아니라 성공 실행의 마지막 단계에 `SUCCESS_SCREENSHOT` 1건을 저장한다.
- 실행 모니터는 상세 응답의 최신 Artifact를 실제 테스트 페이지 최종 화면으로 표시한다. 과거 실행처럼 Artifact가 없으면 재실행 안내를 표시한다.
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
- 각 단계 결과를 `step_runs`에 저장하고 실패 화면 및 성공 실행의 최종 화면을 MinIO `tracepilot-artifacts` 버킷에 보관
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
