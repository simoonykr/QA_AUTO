# 공개 데모 배포 가이드

## 목표

한 대의 Docker 서버에서 프론트, API, Worker, PostgreSQL, Redis, MinIO를 함께 실행한다. 외부에는 `frontend`의 HTTP 포트 하나만 공개한다. 프론트와 API가 같은 주소를 사용하므로 HttpOnly 로그인 쿠키와 SSE가 별도 CORS 설정 없이 동작한다.

```text
인터넷 → HTTPS 프록시 → frontend:80 → /api/* → api:8000
                                  ├─ PostgreSQL (내부 전용)
                                  ├─ Redis (내부 전용)
                                  ├─ MinIO (내부 전용)
                                  └─ Playwright Worker
```

## 서버 준비

- Linux 서버
- Docker Engine과 Docker Compose
- 최소 권장 메모리 4GB (Playwright Chromium 포함)
- HTTPS를 제공할 도메인 또는 클라우드 HTTPS 프록시

DB, Redis, MinIO 포트는 방화벽이나 공유기에서 열지 않는다. 외부에는 HTTPS `443`만 공개하는 구성을 권장한다.

## 환경변수

```bash
cp .env.public.example .env.public
```

`.env.public`에 강한 임의 값을 입력한다. `POSTGRES_PASSWORD`는 DB URL에 안전하게 들어가도록 영문·숫자 조합을 사용한다. 이 파일은 `*.env` 규칙으로 Git에서 제외된다.

HTTPS 배포에서는 반드시 다음 값을 유지한다.

```env
DEMO_AUTH_ENABLED=true
DEMO_COOKIE_SECURE=true
DEMO_COOKIE_SAMESITE=lax
```

권장 구성은 프론트와 API를 같은 사이트에서 제공하고 `/api/**`를 FastAPI로 전달하는 방식이다. 이때 `SameSite=lax`를 유지하고 `DEMO_COOKIE_DOMAIN`은 비워 둔다.

Firebase 프론트와 별도 API 도메인을 직접 연결해야 하는 경우에만 다음을 함께 검토한다.

```env
CORS_ORIGINS=["https://tracepilot-demo.web.app","https://tracepilot-demo.firebaseapp.com"]
DEMO_COOKIE_SECURE=true
DEMO_COOKIE_SAMESITE=none
```

교차 사이트 쿠키 구성은 브라우저 정책의 영향을 받으므로 동일 사이트 `/api` 프록시가 우선이다. 운영 환경에서 `DEMO_COOKIE_SECURE=false`이거나 `SameSite=None`인데 Secure가 아니면 API 서버가 시작되지 않는다.

## 실행

```bash
docker compose --env-file .env.public -f compose.public-demo.yml up -d --build
docker compose --env-file .env.public -f compose.public-demo.yml ps
```

서버 내부 확인 주소는 기본적으로 `http://127.0.0.1:8080`이다. 실제 인터넷 공개는 이 포트 앞에 HTTPS reverse proxy 또는 클라우드 load balancer를 둔다.

## 업데이트

```bash
git pull --ff-only origin main
docker compose --env-file .env.public -f compose.public-demo.yml up -d --build
```

DB migration은 `migrate` 서비스가 배포 때 자동 적용한다. PostgreSQL, Redis, MinIO 데이터는 Docker named volume에 유지된다.

## 확인 항목

- `/health`가 HTTP 200인지 확인
- 로그인하지 않고 `/api/v1/test-cases` 호출 시 HTTP 401인지 확인
- 데모 로그인 후 TC 목록과 실행 화면이 표시되는지 확인
- 실행 생성 후 Worker가 PASS/FAIL로 종료되는지 확인
- 실패 실행의 증적 PNG가 조회되는지 확인
- DB, Redis, MinIO 포트가 인터넷에서 접근되지 않는지 확인

## 정식 가입·승인 방식으로 확장

현재 reverse proxy와 동일 출처 쿠키 구조는 그대로 유지한다. 이후 백엔드에서 가입 요청과 승인 상태를 DB에 저장하고, 프론트에서 가입·승인 대기·관리자 승인 화면을 추가한다.
