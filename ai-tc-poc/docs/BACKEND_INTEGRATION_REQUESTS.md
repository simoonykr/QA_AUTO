# 백엔드 통합 요청사항

프론트엔드는 로그인·로그아웃, 세션 복구, `AUTH_REQUIRED`, 승인 상태 화면, 실행 설정 리소스 및 실행 결과 연동까지 완료되었다. Firebase UI 데모를 실제 백엔드 통합 데모로 전환하기 위해 아래 항목의 확인과 전달을 요청한다.

## 배포 및 네트워크

1. 외부에서 접근 가능한 FastAPI HTTPS 주소를 확정한다.
2. Firebase Hosting의 `/api/**` reverse proxy 사용 여부 또는 교차 도메인 API 연결 방식을 확정한다.
3. 다음 Firebase Origin을 운영 CORS 허용 목록에 반영한다.
   - `https://tracepilot-demo.web.app`
   - `https://tracepilot-demo.firebaseapp.com`
4. 실제 배포 환경의 health endpoint와 점검 방법을 공유한다.

## 인증 및 쿠키

1. 운영 세션 쿠키에 `HttpOnly=true`, `Secure=true`를 적용한다.
2. 프론트와 API가 서로 다른 사이트라면 `SameSite=None` 적용 여부를 검증한다.
3. 실제 통합 테스트에 사용할 데모 계정은 GitHub가 아닌 별도의 안전한 채널로 전달한다.
4. 로그인 실패, 세션 만료, 권한 부족에 사용하는 HTTP 상태와 오류 코드를 확정한다.
5. SSE 연결에서도 세션 쿠키 인증과 만료 처리가 동일하게 동작하는지 확인한다.

## 실행 및 증적

1. `GET /api/v1/executions/{executionId}/events`가 Firebase 배포 환경에서 쿠키 인증과 함께 동작하는지 확인한다.
2. `GET /api/v1/executions/{executionId}/artifacts/{artifactId}`가 조직·프로젝트·실행 범위를 검사한 뒤 PNG 증적만 반환하는지 확인한다.
3. Worker 오류 코드와 사용자에게 표시 가능한 메시지의 대응표를 공유한다.
4. PostgreSQL, Redis, MinIO 및 Playwright Worker가 포함된 외부 통합 환경의 준비 상태를 공유한다.

## 후속 API 계약

1. 가입 신청, 관리자 승인·거절, 사용자 및 역할 관리 API의 일정과 초안 계약을 공유한다.
2. ~~XLSX/DOCX 테스트 케이스 업로드·파싱 API의 일정, 파일 크기 제한, 허용 확장자와 오류 코드를 공유한다.~~ 완료: `FRONTEND_BACKEND_SYNC.md`의 파일 가져오기 계약 참고.

## AI 연동 원칙

- 현재 개발·CI·Firebase UI 데모에서는 실제 AI API를 호출하지 않는다.
- 프론트의 기본 실행 설정은 `maxAiCalls: 0`을 유지한다.
- 전체 실행 구조가 안정된 뒤 별도 AI 통합 환경에서 호출 한도, 토큰 예산, 캐시 및 재시도 정책을 적용한다.
- AI API 키와 모델 관련 비밀정보는 서버 환경변수 또는 Secret Manager에만 저장하고 프론트 코드와 `VITE_*` 환경변수에는 넣지 않는다.

