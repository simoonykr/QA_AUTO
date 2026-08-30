# TracePilot 에이전트 협업 규칙

이 저장소에서 프론트엔드와 백엔드 작업을 수행하는 모든 에이전트는 사용자를 전달자로 사용하지 않고 GitHub `main`과 `ai-tc-poc/docs/WORKSTREAM_STATUS.md`를 공용 전달 채널로 사용한다.

## 작업 시작

1. 작업 전 `git fetch origin`으로 원격 상태를 확인한다.
2. 로컬 변경이 없으면 최신 `origin/main`을 기준으로 시작한다. 로컬 커밋이 있으면 강제 push 없이 rebase한다.
3. 다음 문서를 먼저 확인한다.
   - `ai-tc-poc/docs/WORKSTREAM_STATUS.md`
   - `ai-tc-poc/docs/FRONTEND_BACKEND_SYNC.md`
   - `ai-tc-poc/docs/BACKEND_INTEGRATION_REQUESTS.md`
4. 상대 담당자가 남긴 `요청` 중 현재 작업을 막는 항목을 우선 처리한다.

## 담당 범위

- 프론트엔드: `ai-tc-poc/src/**`, 프론트 빌드 설정, UI 문서
- 백엔드: `ai-tc-poc/backend/**`, DB migration, Worker, API, 배포 구성
- 공통 계약: `src/api/types.ts`와 `backend/app/schemas/**`
- 공통 문서: `ai-tc-poc/docs/**`

상대 담당 범위의 구현을 임의로 크게 변경하지 않는다. API 필드, enum 또는 endpoint를 변경할 때는 양쪽 타입을 같은 커밋 또는 연속 커밋으로 맞추고 상태 문서에 호환성 영향을 기록한다.

## 작업 완료

1. 담당 테스트와 빌드를 실행한다.
2. 같은 커밋에 `WORKSTREAM_STATUS.md`의 자기 담당 영역을 갱신한다.
3. 완료 항목, 새 요청, 검증 결과, 커밋 예정 내용을 기록한다.
4. `origin/main`을 다시 확인하고 필요하면 rebase한다.
5. force push 없이 `main`에 push한다. push가 거절되면 최신 원격을 가져와 rebase하고 테스트 후 재시도한다.

## 공통 안전 원칙

- 실제 AI API는 별도의 최종 통합 승인 전까지 호출하지 않는다.
- 실행 요청의 `maxAiCalls` 기본값은 `0`을 유지한다.
- 비밀번호, API 키, 세션 서명 키를 Git, 프론트 코드, `VITE_*` 변수에 저장하지 않는다.
- Firebase Mock 배포는 UI 시연용이며 실제 데이터 입력 용도로 취급하지 않는다.
- 사용자의 선택이나 유료 클라우드 결제가 필요한 작업만 사용자에게 요청한다.
- 구현·계약·테스트로 해결할 수 있는 전달 업무는 에이전트가 상태 문서와 커밋으로 직접 처리한다.

## 충돌 처리

- 상대방의 새 커밋을 삭제하거나 되돌리지 않는다.
- 충돌이 담당 범위 밖이면 상대 변경을 유지하고 자신의 변경을 최소화한다.
- 계약 해석이 두 가지 이상이고 결과가 크게 달라질 때만 사용자에게 결정을 요청한다.
