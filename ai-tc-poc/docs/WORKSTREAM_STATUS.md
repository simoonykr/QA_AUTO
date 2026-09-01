# 프론트엔드·백엔드 공용 작업 현황

마지막 갱신: 2026-09-01

이 문서는 두 담당 에이전트의 공용 전달판이다. 각 담당자는 작업 시작 전에 읽고, 작업 완료 커밋에서 자기 영역을 직접 갱신한다.

## 현재 공동 목표

Firebase UI 데모를 실제 FastAPI·PostgreSQL·Redis·MinIO·Playwright Worker와 연결된 로그인 가능 통합 데모로 전환한다. 실제 AI API 호출은 통합 구조가 안정될 때까지 사용하지 않는다.

## 환경 운영 합의

- `Local`: 현재 개발 PC의 Docker 통합 환경이다. `http://localhost:8080`은 해당 PC에서만 사용한다.
- `Temporary Staging`: 회사·관계자 검수를 위한 임시 HTTPS 터널이다. 현재 PC의 `localhost:8080`으로 연결하며 PC, Docker Desktop, 터널 프로세스가 모두 실행 중이어야 한다.
- `Staging`: 향후 별도 서버와 고정 HTTPS 주소로 운영한다. 가입·승인, 자동화, API 통합을 라이브 반영 전에 검증한다.
- `Production`: 실제 사용자용 정식 도메인과 별도 DB·비밀정보를 사용하는 라이브 환경이다.

현재 다음 단계는 Temporary Staging 주소를 열어 회사에서 통합 데모를 확인하는 것이다. 회사 외부 접속 공인 IP 후보는 `59.13.192.250`, `59.12.234.2`이며, 고정 Staging에서는 이 주소를 접근 허용 정책에 사용할 수 있다. 임시 터널 단계는 데모 로그인으로 보호하고, IP 제한은 고정 터널·도메인 구성 시 적용한다.

환경별 DB, 세션 서명 키, 계정, API 키는 공유하지 않는다. 실제 AI API는 모든 환경에서 계속 비활성화하고 `maxAiCalls=0`을 유지한다.

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

백엔드에 요청:

- 외부 FastAPI HTTPS 주소와 `/api/**` 연결 방식
- 운영 쿠키·CORS·SSE 인증 확인
- 가입·승인 API 계약

다음 작업:

- 실제 API 주소가 준비되면 Mock 비활성화 통합 테스트
- 가입 신청·승인 대기·거절 화면을 백엔드 계약에 맞춰 연결
- 파일 업로드 UI 연결

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

프론트엔드에 요청:

- 모든 실제 API 요청에서 `credentials: 'include'` 유지
- 설정 API 실패 시 실행 차단
- `AUTH_REQUIRED`와 승인 상태별 화면 유지
- SSE 실패 시 2초 polling fallback 유지
- 실제 AI 연동 전 `maxAiCalls=0` 유지
- 배포 빌드는 동일 출처 `/api/v1`을 사용하고 임시·고정 Staging 주소를 소스 코드에 하드코딩하지 않음
- Local·Staging·Production 표시가 필요한 경우 비밀정보가 아닌 빌드 환경명만 사용

다음 작업:

- Cloudflare 임시 HTTPS 터널로 Temporary Staging 구성 및 회사 네트워크 접속 확인
- 확인 후 고정 Staging 서버·도메인·회사 IP 접근 제한 결정
- PostgreSQL·Redis·MinIO·Worker 외부 통합 배포
- Firebase와 실제 API 연결 후 인증·SSE·증적 통합 검증
- 가입·승인·사용자 역할 API
- 프론트 파일 가져오기 UI와 `/test-cases/import` 실제 연결
- 추출된 원문을 구조화·실행 생성 흐름으로 연결

## 최근 검증

- 백엔드: `26 passed`
- Docker 통합: PostgreSQL·Redis·MinIO·API·Outbox·Playwright Worker·Frontend 정상 실행
- 실제 Worker smoke execution: `PASS`, AI 호출 `0`
- 프론트엔드: 타입 검사 및 Firebase 데모 빌드 통과
- Firebase UI: `https://tracepilot-demo.web.app`
- Firebase 공개 회귀: 대시보드·주요 메뉴·Mock PASS 실행 확인

## 차단 사항

- 실제 백엔드 공개에는 서버 제공 방식과 비용 정책 결정이 필요하다.
- 실제 AI API 연결은 의도적으로 보류한다.
