# 프론트엔드·백엔드 공용 작업 현황

마지막 갱신: 2026-09-03

이 문서는 두 담당 에이전트의 공용 전달판이다. 각 담당자는 작업 시작 전에 읽고, 작업 완료 커밋에서 자기 영역을 직접 갱신한다.

## 현재 공동 목표

Firebase UI 데모를 실제 FastAPI·PostgreSQL·Redis·MinIO·Playwright Worker와 연결된 로그인 가능 통합 데모로 전환한다. 실제 AI API 호출은 통합 구조가 안정될 때까지 사용하지 않는다.

자연어 TC를 실행 가능한 계획으로 만들기 위한 다음 설계는 [`AI_PAGE_DISCOVERY_REQUIREMENTS.md`](AI_PAGE_DISCOVERY_REQUIREMENTS.md)를 기준으로 한다. QA에게 selector 작성을 요구하지 않고 AI 구조화와 Playwright 페이지 탐색·후보 검증을 분리한다.

## 환경 운영 합의

- `Local`: 현재 개발 PC의 Docker 통합 환경이다. `http://localhost:8080`은 해당 PC에서만 사용한다.
- `UI Staging (Mock)`: 현재 Firebase에 배포된 `https://tracepilot-demo.web.app`이다. 프론트 화면 검수용이며 Mock API를 사용하므로 실제 FastAPI·DB·Redis·MinIO·Playwright 실행과 연결된 통합 스테이징은 아니다.
- `Temporary Staging`: 회사·관계자 검수를 위한 임시 HTTPS 터널이다. 현재 PC의 `localhost:8080`으로 연결하며 PC, Docker Desktop, 터널 프로세스가 모두 실행 중이어야 한다.
- `Staging`: 향후 별도 서버와 고정 HTTPS 주소로 운영한다. 가입·승인, 자동화, API 통합을 라이브 반영 전에 검증한다.
- `Production`: 실제 사용자용 정식 도메인과 별도 DB·비밀정보를 사용하는 라이브 환경이다.

현재 UI Staging은 이미 운영 중이다. 백엔드의 다음 단계는 Temporary Staging 주소를 열어 Firebase Mock 화면과 별도로 실제 API·Worker가 연결된 통합 데모를 회사에서 확인하는 것이다. 회사 외부 접속 공인 IP 후보는 `59.13.192.250`, `59.12.234.2`이며, 고정 Staging에서는 이 주소를 접근 허용 정책에 사용할 수 있다. 임시 터널 단계는 데모 로그인으로 보호하고, IP 제한은 고정 터널·도메인 구성 시 적용한다.

환경별 DB, 세션 서명 키, 계정, API 키는 공유하지 않는다. 실제 AI는 로컬 TC 구조화 검증에만 예산·캐시·1회 제한을 적용해 활성화했으며 Playwright 실행은 `maxAiCalls=0`을 유지한다.

## 프론트엔드 현황

완료:

- 로그인·로그아웃·세션 복구 및 승인 상태 UX
- 실행 환경·테스트 계정·실행 정책 API 연결
- 서버 정책에 따른 실행 선택 제한
- 실행 SSE, polling fallback 및 증적 표시
- AI 호출 기본값 `0`
- Firebase Mock 데모 빌드
- Firebase 최신 main 재배포 및 공개 화면 회귀 테스트
- AI 토큰 없이 규칙 기반 TC 구조화·검토·실행 흐름 명시
- 실행 정책의 `maxAiCalls`에 따라 AI 호출 선택지를 `0회` 또는 `0회/1회`로 제한하고, 기본 실행 요청과 Mock 정책을 `0`으로 유지
- Firebase Mock 실행 완료 시 `navigate/fill/click/assert` 4단계 상세가 결과 화면에 표시되도록 공개 데모 회귀 보완
- 테스트 케이스 TXT/CSV/XLSX/DOCX 가져오기 UI를 실제 `/test-cases/import` multipart API에 연결하고 10MB·확장자 검증, 로딩·경고·오류 표시 반영
- 구조화 API의 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED`를 전용 분할 검토 상태로 표시하고 감지 TC 수·원문 길이 안내 및 승인·실행 차단
- 새 TC 시작·파일 교체·승인 후 원문 편집 시 이전 승인 `versionId`를 즉시 무효화해 과거 구조화 결과 실행 방지
- 실행 설정과 생성 사이에 예상 시나리오·UUID·구조화 출처·필수 파라미터 검증 화면을 추가하고, 실행 모니터의 고정 로그인 데모 화면 제거
- 실제 동일 출처 배포에서 상태 확인이 `/api/v1/health`로 잘못 조합되던 문제를 수정하고 `/health` 직접 호출로 통일
- 구조화 검토 화면에서 실행 환경별 계획을 조회하고 warning의 `stepNo`·`stepId`·`missingFields`로 오류 단계를 강조
- 승인 전 selector·URL·operator·expected·value·secretRef·assertionType 부분 편집을 PATCH API에 연결하고 반환된 revision·plan hash·warnings·executable을 즉시 반영
- 서버 실행 계획의 `executable=true`일 때만 검토 승인 버튼을 활성화하고, 마스킹된 value는 사용자가 직접 변경하지 않는 한 PATCH body에서 제외
- 구조화 검토 단계와 편집 패널에 삭제 버튼·확인 절차·중복 요청 방지를 추가하고 DELETE 응답의 재번호된 단계, revision, plan hash, warnings, executable을 즉시 반영
- 단계 삭제의 `TC_STEP_NOT_FOUND`는 계획 새로고침으로 복구하고 `TC_VERSION_NOT_REVIEWABLE`은 승인 완료 버전 수정 불가로 구분 안내하며, Mock도 버전·환경별 연속 삭제와 전체 삭제 차단 상태를 재현
- 구조화 검토 화면에 페이지 분석 시작, 상태 polling, 탐색 페이지 fingerprint, 단계별 selector 후보·검증 결과·신뢰도, 복수 후보 선택과 결과 적용 UI를 연결
- 페이지 분석 요청은 현재 `maxPages=1`, `maxAiCalls=0`으로 고정하고 적용 응답의 steps·revision·planHash·warnings·executable을 승인 기준에 즉시 반영하며 Mock에도 동일 흐름을 구현

백엔드에 요청:

- 외부 FastAPI HTTPS 주소와 `/api/**` 연결 방식
- 운영 쿠키·CORS·SSE 인증 확인
- 가입·승인 API 계약

다음 작업:

- 가입 신청·승인 대기·거절 화면을 백엔드 계약에 맞춰 연결
- 다중 TC 자동 분리 API가 확정되면 선택·분리·일괄 저장 UX 연결

## 백엔드 현황

완료:

- 테스트 케이스·구조화·실행 생성·조회·중단·재시도 API
- 실행 환경·테스트 계정·실행 정책 API
- SSE 실행 이벤트와 PNG 증적 API
- PostgreSQL·Redis outbox·MinIO·Playwright Worker 로컬 구성
- 공용 데모 세션 인증
- 운영 Cookie Secure·SameSite·Domain 설정 및 안전성 검증
- health endpoint와 표준 오류 envelope
- TXT·CSV·XLSX·DOCX 테스트 케이스 업로드·텍스트 추출 API
- Windows Docker Desktop 로컬 통합 환경 실행
- 로그인 → 실행 생성 → Redis → Playwright Worker → `PASS` 전체 흐름 검증 (`maxAiCalls=0`)
- OpenAI 서버 환경변수와 실행당·일일 예산 설정 추가; 키가 없으면 정책을 `maxAiCalls=0`으로 강제하는 fail-closed 보호 적용
- OpenAI 키는 로컬 비밀파일에 입력 완료했으나 실제 Gateway·비용 원장·예산 차단은 아직 미구현이므로 API 호출은 시작하지 않음
- 최신 main 로컬 Compose에서 실제 Chromium 성공·실패 TC 통합 검증 완료
- 실패 assertion용 재현 가능한 migration `0005_seed_worker_failure` 추가
- `.env.public`의 DB·MinIO·데모 인증·세션 비밀값을 실행 중 컨테이너에서 노출 없이 복구
- 필수 비밀값 누락 시 Compose 실행 전 중단하는 PowerShell 시작 검증 추가
- TC 구조화 전용 OpenAI Gateway와 요청당 최대 1회 제한 구현
- 토큰·비용 원장, UTC 일일 `$1` 예산 선차단, 조직·모델·동일 입력 캐시 구현
- 구조화 응답 `aiUsage` 및 표준 AI 오류 계약 문서화
- API 컨테이너 재생성 후에도 Nginx가 Docker DNS를 갱신하도록 reverse proxy `502` 복구 보완
- AI 비활성 구조화가 원문과 무관한 고정 로그인 예제를 반환하던 문제 수정
- 구조화 요청의 9,613자 원문 무손실 전달 및 다중 TC 102건 감지 회귀 테스트 추가
- 다중 TC를 단일 성공 결과로 축약하지 않고 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED` 검토 오류로 반환
- 구조화 요청마다 실제 TestCase와 고유 UUID TestCaseVersion을 생성하고 `raw_text`, `structured_spec`, `REVIEW_REQUIRED` 상태 저장
- `POST /api/v1/test-case-versions/{versionId}/approve` 추가 및 승인 후 `READY` 전환
- 실행 생성 시 실제 UUID 버전의 조직·프로젝트·READY 상태 검증, `tcv-new-v1` alias 제거
- Worker가 execution의 동일 조직·프로젝트 버전과 저장된 `structured_spec.steps`만 조회·실행하도록 강화
- 프론트 검토 승인 버튼을 실제 승인 API에 연결하고 반환 `versionId`를 실행 설정·생성 요청까지 전달
- 실행 계획 조회 API, action별 필수 파라미터·URL allowlist·지원 action 서버 검증 추가
- 승인과 실행 생성을 잘못된 계획에서 차단하고 입력값을 계획 응답에서 마스킹
- 실행 생성 시 plan hash/revision/환경/단계 수 snapshot 저장, Worker 시작 전 DB 계획과 재검증
- 실행 상세에 계획 UUID·hash·revision·환경·계획/실제 단계 수와 단계별 `planStepId` 추가
- 프론트 실행 예정 시나리오를 서버 `executable`, `warnings` 단일 기준으로 전환
- XLSX 구조화 요청 전 결과 집계·보고서 메타데이터 영역을 제외하고 실제 TC 헤더부터 전송하며 제외 행 수를 UI에 표시 (`Expected Result` 유지)
- 최신 `main` `3ec9900`을 기존 Cloudflare Quick Tunnel에 공개용 Compose로 재배포하고, 파일 업로드부터 실제 Worker 성공·실패까지 재현 가능한 HTTPS 검증 스크립트 추가
- 실행 계획 오류에 `stepNo`·`stepId`·`missingFields`를 추가하고 URL assertion은 selector 없이, text/element assertion은 selector 필수로 분리 검증
- 승인 전 `PATCH /test-case-versions/{versionId}/steps/{stepId}`로 selector·URL·operator·expected·value/secretRef를 수정하고 revision/hash를 재계산하는 API 추가
- 원문에 없는 AI selector를 제거하고 `assumptions`에 검토 사유를 남기는 selector grounding 보호 추가
- XLSX TC 헤더 이전 결과 집계·보고서 메타데이터를 제외하고 Expected Result를 보존하며 제외 행 수·감지 TC 수 warning 반환
- 승인 전 `DELETE /test-case-versions/{versionId}/steps/{stepId}`로 불필요한 구조화 단계를 삭제하고 단계 번호·revision·plan hash를 재계산하는 API 추가
- XLSX 구조화 입력에서 TC 헤더, 숫자만 있는 행, 반복 `Not Test/Source` 보고 행을 제외하고 실제 필터 결과를 기준으로 TC 수를 계산
- XLSX 정상 행의 TC ID 또는 Step·Expected Result를 우선 판별해 Result=`Not Test`, Comment=`Source:`가 있어도 보존하도록 보완
- 자연어 구조화 단계에 `targetDescription`·`selectorHint`·selector 해결 상태를 추가하고 원문 근거 없는 selector를 `UNRESOLVED`로 유지
- 페이지 분석 작업·상태·결과를 저장하는 `page_discoveries` migration과 조직·프로젝트 범위 API 추가
- 승인 전 `discover → 상태 조회 → 후보 선택/apply` API를 추가하고 적용 시 revision·plan hash·fingerprint·감사 로그 갱신
- Playwright Worker가 허용 환경 URL을 읽기 전용으로 탐색하고 정제된 접근성·상호작용 요소만 수집하여 selector 후보의 개수·표시·활성 상태를 실제 검증
- `UNRESOLVED`·`AMBIGUOUS`·`NOT_FOUND`·`STALE` 단계가 남으면 실행 계획과 승인을 차단하도록 서버 검증 강화

프론트엔드에 요청:

- 모든 실제 API 요청에서 `credentials: 'include'` 유지
- 설정 API 실패 시 실행 차단
- `AUTH_REQUIRED`와 승인 상태별 화면 유지
- SSE 실패 시 2초 polling fallback 유지
- 실제 AI 연동 전 `maxAiCalls=0` 유지
- 배포 빌드는 동일 출처 `/api/v1`을 사용하고 임시·고정 Staging 주소를 소스 코드에 하드코딩하지 않음
- Local·Staging·Production 표시가 필요한 경우 비밀정보가 아닌 빌드 환경명만 사용
- AI 정책이 `1`일 때 선택지를 `0회`, `1회`로 제한하고 키·달러 예산 환경변수는 프론트에서 참조하지 않음
- 단계 편집 화면에서 DELETE API를 연결하고 확인창·중복 클릭 방지·반환 계획 즉시 반영·마지막 단계 삭제 시 승인 차단 처리

다음 작업:

- Cloudflare 임시 HTTPS 터널로 Temporary Staging 구성 및 회사 네트워크 접속 확인
- 프론트에서 구조화 결과의 `aiUsage.source`, 호출 수, 토큰·비용 표시 여부 결정
- 확인 후 고정 Staging 서버·도메인·회사 IP 접근 제한 결정
- PostgreSQL·Redis·MinIO·Worker 외부 통합 배포
- Firebase와 실제 API 연결 후 인증·SSE·증적 통합 검증
- 가입·승인·사용자 역할 API
- 다중 TC 파일의 서버 자동 분리 API/UX 설계(현재는 명확한 검토 상태 반환)
- 프론트에서 검증 Execution/Artifact를 사용해 단계 상세·실패 PNG 화면 교차 확인
- 프론트 페이지 분석 진행 상태·후보 선택·적용 UI 연결 (`AI_PAGE_DISCOVERY_REQUIREMENTS.md` 기준)
- 규칙 기반 Playwright 후보 검증 통합 확인 후 OpenAI 의미 매핑을 TC당 최대 1회·일일 예산 내에서 활성화

## 최근 검증

- 페이지 분석 API·구조화/실행 차단·민감정보 마스킹 회귀 포함 백엔드 단위 테스트 `55 passed` (Docker 일회성 테스트 컨테이너, AI 호출 0)

- 백엔드: `48 passed` (`3 warnings`), 프론트 배포 Dockerfile 프로덕션 빌드 통과
- 백엔드 단계 삭제·XLSX 오탐 회귀: `51 passed` (`3 warnings`)
- 실제 `KakaoGames_AI_Automation.xlsx` 검증: 메타데이터 9행 제외, `KG-WEB-001`~`KG-WEB-021` 고유 TC 21건 보존, `XLSX_TEST_CASES_DETECTED:21`
- 구조화 회귀: 정확히 9,613자 원문 보존, 102건 다중 TC 감지, AI 호출 전 `MULTIPLE_TEST_CASES_REVIEW_REQUIRED` 차단 확인
- AI 사용량 계약: 실제 Gateway 결과 `AI/1`, 캐시 `CACHE/0`, AI 비활성 원문 기반 결과 `RULE_BASED/0`
- 영속 버전 통합: Version `787dc8b2-cecf-4ae4-b438-9786a7a65e2f`, 승인 전 `TC_NOT_READY`(409), 승인 `READY`
- 실제 Worker 통합 Execution `f322af6c-c3f5-4b93-99ee-8fd0f5d6a24b`: 저장된 navigate/fill/click/assert 4단계 전체 `PASS`, AI 호출 `0`
- 계획 검증 Version `5ea8101f-8ca9-4e19-ab83-d7fa5b3adc38`, Execution `bbf2ac81-84e7-42ef-9529-bee62826ca48`: 계획 hash 64자·revision 1·마스킹 확인, 4개 `planStepId`와 실제 단계 모두 일치, 최종 `PASS`, AI 호출 `0`
- Temporary Staging 최신 재배포: 기존 Quick Tunnel URL 유지, `/health` 200, 미인증 API 401, 데모 로그인 200, 공개 호스트 포트는 frontend `8080`만 노출
- 파일 기반 성공 Version `ec034696-6bd6-46c7-b7fb-cad261de0892`, Execution `930d4547-5bb4-4472-b250-dd7e039e3718`: `executable=true`, revision 1, plan hash `fa3f083e83d203ec695bd00545363ab32d5bb6de1f8ba315acc4e22fcf3daeab`, 계획/실제 각 4단계, `stepCountMatches=true`, `step-1..4` 모두 `planStepId` 및 action·selector·expected 일치, 최종 `PASS`
- 의도적 실패 Version `647eae19-34df-4722-a40d-dd87ead60db2`, Execution `5d35f1e2-09b2-49d5-96ec-bb976ef7ea2b`: 4번 assert 실패, `ASSERTION_FAILED`, PNG Artifact `bdbbd9da-f54d-490c-8704-b69c96eb1af2` 다운로드 및 PNG signature 확인
- 필수값 누락 Version `f7361da1-8887-4b8f-9fb8-1c0b6f2b88d2`: 계획 `executable=false`, `STEP_PARAMETER_MISSING`, 승인 HTTP 422로 실행 차단
- 단계 수정 API 실환경 검증 Version `bb4afc1a-7f9d-4cc2-9ee3-626a47a0f8d8`: 누락 warning에 step 2/`step-2`/`value,secretRef`, PATCH 후 revision `1→2→3` 및 hash 변경, selector 없는 URL assertion `executable=true`, 승인 200
- assert selector 누락 실환경 검증 Version `a1be9190-3a62-4e73-aa62-b67a9cb047e7`: `assumptions` 검토 안내, 계획·승인 오류 모두 step 4/`step-4`/`missingFields=[selector]`, 승인 422 확인
- 위 성공·실패 실행은 모두 `maxAiCalls=0`, 구조화 `RULE_BASED/0회/$0`; API·Outbox·Worker 로그에서 비밀값, OpenAI 네트워크, 고정 Seed UUID, `tcv-new-v1`/fallback 표식 미검출
- 검증 중 최초 fixture의 `#email/#submit/#welcome` selector가 실제 대상 DOM과 달라 실패한 문제를 발견했고, 파일 fixture를 대상의 `data-testid` 계약에 맞춰 수정하여 재검증 완료. `demo-target`은 선택된 테스트 환경으로만 사용됐으며 고정 Seed·로그인 샘플 fallback은 사용하지 않음
- 필수 파라미터 누락 계획은 승인 시 `STEP_PARAMETER_MISSING`으로 차단 확인
- Docker 통합: PostgreSQL·Redis·MinIO·API·Outbox·Playwright Worker·Frontend 정상 실행
- 실제 Worker smoke execution: `PASS`, AI 호출 `0`
- 성공 Execution `201c45fc-c846-4cce-b847-1a9fd01c3202`: navigate/fill/click/assert 전체 `PASS`
- 실패 Execution `0a5c5cf4-2179-464e-8504-7df5cb78084c`: 최종 `FAIL`, `ASSERTION_FAILED`, 4단계 `STEP_FAILED`
- 실패 Artifact `8c980f7a-d1e9-4b83-a569-40ba6f6e4ad6`: MinIO PNG 및 API 다운로드 확인
- API·Outbox·Worker 로그 비밀값 미검출, AI 호출 `0회`, 관찰 비용 `$0`
- OpenAI 최초 구조화: 실제 호출 `1회`, 입력 `275`, 출력 `173` 토큰, 비용 `$0.00014505`
- 동일 구조화 재요청: `CACHE`, OpenAI 호출 `0회`, 추가 비용 `$0`
- AI 독립 Playwright Execution `fbc2e998-9600-41ff-8364-bd4a8ac4d3a4`: 4단계 전체 `PASS`, 원장·비용 변화 없음
- 프론트엔드: 타입 검사 및 Firebase 데모 빌드 통과
- 프론트 AI 정책 UI: 서버 정책 `0/1`에 따른 선택 제한 및 요청값 상한 적용 검증
- 프론트 구조화 단계 편집: TypeScript 검사, 실제 API 프로덕션 빌드, Firebase Mock 빌드 통과
- 프론트 구조화 단계 삭제: TypeScript 검사, 실제 API 프로덕션 빌드, Firebase Mock 빌드 통과
- 프론트 페이지 분석·selector resolution: TypeScript 검사, 실제 API 프로덕션 빌드, Firebase Mock 빌드 통과
- 최신 `main` `4b516d9` Temporary Staging 재배포: 프론트 Docker 프로덕션 빌드 통과, `/health` 200, 미인증 API 401, 기존 Quick Tunnel 유지, 외부 공개 포트는 frontend `8080`만 사용
- HTTPS 성공 검증 Version `f0869071-9fdb-4f25-be56-3580f65c67bd`, Execution `8e61b8d7-d612-406d-9aca-545c8b5e12a0`: plan hash `613541ba457b545e9003f2654247a87c07df58283295642129289c98d0387694`, 계획/실제 4단계 및 `planStepId` 일치, 최종 `PASS`
- HTTPS 실패 검증 Execution `8fb52bc6-207b-44ba-b63b-c4441387e9ea`: 최종 `FAIL`, `ASSERTION_FAILED`, 실패 PNG Artifact `8ca2274f-7dff-459e-9ceb-c6e249361139` 및 PNG signature 확인
- HTTPS 단계 편집 검증 Version `32ab90d3-1c61-4cc4-9c9a-0f029661944e`: PATCH 전 `executable=false`, `missingFields=[value,secretRef]`; 저장 후 revision `1→2`, plan hash 재계산, `executable=true`, 승인 200
- 위 HTTPS 재검증은 API `AI_ENABLED=false`, 실행 `maxAiCalls=0`, 구조화 `RULE_BASED/0회/$0` 상태로 수행
- HTTPS 단계 삭제 검증 Version `476ca1df-2b55-4123-bf7e-acb33cde1e75`: 4단계 중 1개 삭제 후 revision `1→2`, plan hash 변경, 남은 `stepNo=1,2,3`; 전체 삭제 후 revision 5, `steps=[]`, `executable=false`, `EXECUTION_PLAN_INVALID` 확인
- Firebase UI: `https://tracepilot-demo.web.app`
- Firebase 공개 회귀: 대시보드·주요 메뉴·Mock PASS 실행 확인
- OpenAI 설정 변경: 정적 diff 검사 통과. Docker Desktop 엔진 미실행으로 백엔드 테스트는 다음 작업에서 재검증 필요

## 차단 사항

- 실제 백엔드 공개에는 서버 제공 방식과 비용 정책 결정이 필요하다.
- 외부 공개 전 Gateway 서버의 고정 배포 방식과 Secret Manager 적용이 필요하다.

상세 통합 검증 기록은 `docs/LOCAL_PLAYWRIGHT_VALIDATION.md`를 기준으로 한다.
