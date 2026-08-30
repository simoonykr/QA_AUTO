# Firebase Hosting 배포

Firebase 프로젝트: `tracepilot-demo`

## 화면 시연용 배포

이 방식은 프론트 UI와 Mock 데이터만 제공한다. Firebase Hosting은 정적 파일만 배포하므로 서버의 HttpOnly 데모 인증을 대신할 수 없다. 실제 비밀번호 보호가 필요하면 아래의 백엔드 연결 단계가 완료된 뒤 공개한다.

```bash
pnpm install
pnpm build:firebase-demo
npx firebase-tools deploy --only hosting --project tracepilot-demo
```

배포 주소:

- `https://tracepilot-demo.web.app`
- `https://tracepilot-demo.firebaseapp.com`

## 실제 백엔드 연결

실제 배포에서는 빌드 시 아래 값을 사용한다.

```env
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=/api/v1
```

Firebase Hosting의 `/api/**` 요청을 Google Cloud의 HTTPS 백엔드로 전달하거나, 동일 사이트 reverse proxy 구조를 사용해야 한다. 데모 계정 비밀번호를 `VITE_*` 변수나 프론트 코드에 넣지 않는다. `VITE_*` 값은 최종 JavaScript에 포함되어 방문자가 볼 수 있다.

## 최초 로그인

Firebase CLI가 로그인되지 않은 PC에서는 다음 명령을 한 번 실행한다.

```bash
npx firebase-tools login
```

브라우저에서 프로젝트 소유 Google 계정으로 승인을 완료한 후 deploy 명령을 실행한다.
