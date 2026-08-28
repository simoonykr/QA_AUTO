# AI TC PoC 로컬 실행 가이드

이 프로젝트는 사용자 화면(React/Vite)과 백엔드 API(FastAPI), PostgreSQL, Redis, MinIO로 구성됩니다.

## 다른 개발자 PC에서 실행하기

### 준비물

- Git
- Docker Desktop (WSL 2 방식)
- Node.js 22 이상
- pnpm

### 1. 소스 받기

```bash
git clone https://github.com/simoonykr/QA_AUTO.git
cd QA_AUTO/ai-tc-poc
```

이미 소스가 있다면 `git pull`로 최신 `main`을 받습니다.

### 2. 프론트 환경설정

`.env.example`을 `.env`로 복사합니다.

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_USE_MOCK_API=false
```

### 3. 백엔드 실행

Docker Desktop을 먼저 실행한 후 `ai-tc-poc` 폴더에서 실행합니다.

```bash
docker compose up -d --build
```

정상 실행 확인:

```bash
docker compose ps
```

### 4. 프론트 실행

```bash
pnpm install
pnpm dev
```

### 접속 주소

- 프론트: http://127.0.0.1:5173
- 백엔드 API: http://127.0.0.1:8000
- API 문서: http://127.0.0.1:8000/docs
- MinIO 관리 화면: http://127.0.0.1:9001

`127.0.0.1` 주소는 실행한 PC에서만 접근할 수 있습니다. 인증 기능을 완성하기 전에는 API와 DB를 인터넷에 직접 공개하지 않습니다.

## 종료 및 재실행

백엔드 종료:

```bash
docker compose down
```

데이터는 Docker volume에 유지됩니다. 다음 실행은 `docker compose up -d`로 충분합니다.

프론트는 실행 중인 터미널에서 `Ctrl+C`로 종료합니다.

## 프론트 개발 참고

- API 타입: `src/api/types.ts`
- API 호출 코드: `src/api/client.ts`
- 백엔드 스키마: `backend/app/schemas/`
- 프론트·백엔드 연동 메모: `docs/FRONTEND_BACKEND_SYNC.md`
- 백엔드 상세 내용: `backend/README.md`

프론트가 Mock API를 사용해야 할 때만 `.env`의 `VITE_USE_MOCK_API`를 `true`로 변경합니다.
