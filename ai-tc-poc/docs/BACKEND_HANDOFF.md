# TracePilot 백엔드 작업 인수인계서

- 대상 작업자: 집 PC에서 서버·백엔드·DB·Queue를 담당하는 개발자
- 기준 브랜치: `main`
- 작업 브랜치: `backend`
- 프론트 담당 브랜치: `frontend`
- 저장소: `https://github.com/simoonykr/QA_AUTO`
- 프로젝트 경로: `ai-tc-poc`

## 1. 이번 작업의 목표

현재 프론트엔드는 mock API를 이용해 아래 사용자 흐름을 시연한다.

1. TC 목록 조회
2. 자연어 TC 작성
3. AI 구조화
4. 구조화 결과 검토·승인
5. 실행 환경·계정·제한 설정
6. 테스트 실행 생성
7. 실시간 실행 모니터
8. 결과 및 단계별 증적 확인

백엔드 작업의 목표는 이 흐름에서 사용하는 임시 데이터를 PostgreSQL 기반 실제 API로 교체하고, 실행 요청을 Redis Queue에 안전하게 발행할 수 있는 상태까지 완성하는 것이다. 이번 단계에서는 Playwright로 실제 웹 페이지를 조작하는 Worker 전체를 완성하지 않는다. 다만 다음 단계에서 Worker를 연결할 수 있도록 job payload, lease, 상태 전이, outbox를 확정한다.

## 2. 저장소와 브랜치 운영

### 2.1 최초 시작

```powershell
git clone https://github.com/simoonykr/QA_AUTO.git
cd QA_AUTO
git switch main
git pull --ff-only origin main
git switch -c backend
```

이미 clone한 저장소라면 다음 명령으로 시작한다.

```powershell
git switch main
git pull --ff-only origin main
git switch backend
git rebase main
```

### 2.2 담당 파일

집 PC 작업자가 주로 수정할 경로:

- `ai-tc-poc/backend/**`
- `ai-tc-poc/docker-compose.yml`
- 백엔드 실행에 필요한 루트 문서 또는 스크립트
- API 계약 변경이 필요한 경우 `ai-tc-poc/src/api/types.ts`

프론트 담당자가 주로 수정할 경로:

- `ai-tc-poc/src/App.tsx`
- `ai-tc-poc/src/styles.css`
- 프론트 컴포넌트·hook·페이지

`src/api/types.ts`와 `src/api/client.ts`는 공유 경계다. 변경 전 커밋 또는 PR에 API 변경 이유를 기록한다. 프론트 UI 파일은 백엔드 브랜치에서 수정하지 않는다.

### 2.3 권장 커밋 단위

1. `Add SQLAlchemy domain models and repositories`
2. `Persist test case APIs in PostgreSQL`
3. `Persist execution creation with outbox`
4. `Publish execution jobs to Redis queue`
5. `Add backend integration tests and local setup docs`

작업 중간에도 위 단위로 push해 프론트 담당자가 변경 내역을 확인할 수 있게 한다.

## 3. 현재 구현 상태

### 3.1 이미 구현된 백엔드

- FastAPI 애플리케이션: `backend/app/main.py`
- 설정: `backend/app/core/config.py`
- Async SQLAlchemy session factory: `backend/app/core/database.py`
- 공통 도메인 오류 응답: `backend/app/core/errors.py`
- TC API: `backend/app/modules/test_cases/router.py`
- 실행 생성 API: `backend/app/modules/executions/router.py`
- Pydantic 요청·응답 스키마: `backend/app/schemas/**`
- PostgreSQL 초기 SQL: `backend/db/001_initial.sql`
- Docker Compose: PostgreSQL, Redis, MinIO, API
- API 테스트: `backend/tests/test_api.py`

### 3.2 현재 임시 구현

- TC 목록은 Python 배열을 반환한다.
- TC 구조화는 고정된 deterministic 응답을 반환한다.
- 실행 생성 결과와 idempotency key는 프로세스 메모리에 저장한다.
- 실행 row, outbox event, audit event를 DB에 저장하지 않는다.
- Redis queue publisher와 worker consumer가 없다.
- 인증·RBAC·tenant context는 아직 기본 ID만 설정되어 있다.
- DB migration은 단일 초기 SQL이며 Alembic이 없다.

## 4. 개발 환경 준비

### 4.1 필수 프로그램

- Git
- Python 3.12 권장
- Docker Desktop 또는 Docker Engine + Compose
- 선택: PostgreSQL client, Redis CLI

### 4.2 Python 환경

```powershell
cd ai-tc-poc/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 4.3 인프라 실행

프로젝트 루트 `ai-tc-poc`에서 실행한다.

```powershell
docker compose up -d postgres redis minio
docker compose ps
```

PostgreSQL 초기 SQL은 새 volume 생성 시 자동 실행된다. 기존 volume에 스키마 변경을 반영하려면 Alembic migration을 사용한다. 단순히 SQL 파일을 수정해도 기존 DB에는 자동 반영되지 않는다.

### 4.4 API 실행

```powershell
cd backend
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

확인 주소:

- Health: `http://127.0.0.1:8000/health`
- OpenAPI UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

### 4.5 테스트

```powershell
python -m pytest -q
```

현재 기준 5개 테스트가 통과해야 한다. DB repository가 추가되면 test database fixture를 포함한 통합 테스트로 확장한다.

## 5. 우선 구현 범위

### P0-1. SQLAlchemy 모델과 Alembic 구성

#### 작업 내용

1. `backend/app/models` 또는 각 도메인 모듈 내부에 SQLAlchemy 2.x declarative model을 만든다.
2. `001_initial.sql`의 핵심 테이블을 ORM 모델과 일치시킨다.
3. Alembic을 추가하고 현재 스키마를 첫 migration으로 만든다.
4. 모든 tenant 데이터 모델에 `organization_id`를 포함한다.
5. UUID는 Python과 PostgreSQL 모두 UUID 타입을 사용한다.
6. 모든 시간은 timezone-aware UTC로 저장한다.

#### 이번 단계 필수 모델

- Organization
- User
- Membership
- Project
- Environment
- TestCase
- TestCaseVersion
- TestAccount
- Execution
- StepRun
- Artifact
- OutboxEvent
- AuditEvent

#### 구현 규칙

- API에서 전달받은 `organization_id`를 신뢰하지 않는다.
- tenant context가 정식 인증으로 교체되기 전에는 설정의 `DEFAULT_ORGANIZATION_ID`를 dependency에서 주입한다.
- JSONB는 구조화 TC, 실행 설정, action, assertion, outbox payload에만 사용한다.
- 검색·관계·상태 전이에 필요한 값은 별도 컬럼으로 둔다.
- execution 터미널 상태를 다시 RUNNING으로 변경하지 못하게 서비스 계층에서 검사한다.

#### 수용 기준

- `alembic upgrade head`가 빈 DB에 성공한다.
- `alembic downgrade base` 후 재업그레이드가 가능하다.
- SQLAlchemy metadata와 migration 스키마가 일치한다.
- 필수 unique·partial index가 생성된다.

### P0-2. Repository와 Unit of Work

#### 작업 내용

Router에서 직접 SQL을 호출하지 않고 다음 계층을 둔다.

```text
router -> application service -> repository -> AsyncSession -> PostgreSQL
```

권장 인터페이스:

- `TestCaseRepository.list_summaries(project_id, cursor, limit)`
- `TestCaseRepository.get_version(version_id)`
- `TestCaseRepository.save_structured_result(version_id, result)`
- `ExecutionRepository.get_by_idempotency_key(org_id, key)`
- `ExecutionRepository.create(request, actor, key)`
- `OutboxRepository.add(event_type, aggregate_id, payload)`
- `AuditRepository.add(action, resource, actor, request_id, metadata)`

하나의 명령에서 execution, outbox, audit을 저장할 때 동일 DB transaction과 session을 사용한다.

#### 수용 기준

- service test에서 repository를 대체할 수 있다.
- rollback 시 execution과 outbox가 함께 저장되지 않는다.
- tenant ID가 다른 row는 조회할 수 없다.

### P0-3. TC 목록 API를 DB로 전환

#### 대상 API

```http
GET /api/v1/test-cases
```

#### 요청 query

- `projectId`: 필수
- `status`: 선택
- `query`: 제목·display ID 검색
- `cursor`: 선택
- `limit`: 기본 20, 최대 100

#### 응답 계약

현재 프론트 타입을 유지한다.

```json
[
  {
    "id": "TC-142",
    "title": "신규 사용자 이메일 회원가입",
    "group": "Authentication",
    "status": "READY",
    "passRate": 96,
    "lastExecutedAt": "2026-08-27T07:42:18Z"
  }
]
```

장기적으로는 `{items,nextCursor}` envelope가 권장되지만 현재 프론트가 배열을 기대한다. envelope로 변경할 경우 같은 PR에서 `src/api/types.ts`, `src/api/client.ts`도 수정하고 프론트 담당자에게 알린다.

#### Seed 데이터

로컬 개발용으로 다음을 idempotent하게 생성하는 seed script를 추가한다.

- Organization: TracePilot Local
- User: qa.lead@local.test
- Project: Storefront QA
- Environment: Staging
- Test account 2개
- TC 4개와 READY/REVIEW_REQUIRED 버전

실제 비밀번호를 seed나 Git에 넣지 않는다. `secret_ref`는 `local://qa-runner-01` 같은 별칭만 사용한다.

#### 수용 기준

- seed 후 API가 4개 TC를 반환한다.
- 다른 organization의 TC가 섞이지 않는다.
- 검색·상태 filter가 동작한다.
- 없는 project 접근은 404 또는 403 정책에 따라 일관되게 응답한다.

### P0-4. TC 구조화 저장

#### 대상 API

현재 임시 endpoint:

```http
POST /api/v1/test-case-versions/current/structure
```

권장 최종 endpoint:

```http
POST /api/v1/test-case-versions/{version_id}/structure
```

현재 프론트의 `current`는 임시다. 실제 version ID 기반 endpoint를 추가하고 프론트 계약을 함께 변경한다.

#### 처리 절차

1. version이 현재 organization에 속하는지 확인한다.
2. 상태가 DRAFT 또는 STRUCTURE_FAILED인지 확인한다.
3. 상태를 STRUCTURING으로 변경한다.
4. PoC에서는 deterministic structurer를 호출한다.
5. JSON Schema/Pydantic으로 결과를 검증한다.
6. structured_spec, schema_version, confidence를 저장한다.
7. assumption이 있으면 REVIEW_REQUIRED, 없고 정책상 자동 승인 가능한 경우에도 초기 MVP에서는 REVIEW_REQUIRED로 둔다.
8. audit event를 기록한다.

AI 공급자 연결은 별도 후속 작업이다. 먼저 `Structurer` protocol을 정의하고 `DeterministicStructurer`를 구현한다. 나중에 `LlmStructurer`로 교체할 수 있어야 한다.

#### 오류 코드

- `TC_VERSION_NOT_FOUND`
- `TC_NOT_DRAFT`
- `AI_OUTPUT_INVALID`
- `STRUCTURE_FAILED`
- `BUDGET_EXCEEDED`

#### 수용 기준

- 구조화 요청 후 DB status와 structured_spec이 갱신된다.
- 같은 version에 동시에 요청하면 하나만 처리된다.
- 실패 시 STRUCTURE_FAILED와 오류 코드가 저장된다.
- raw text와 structured result가 감사 가능하다.

### P0-5. 실행 생성과 transactional outbox

#### 대상 API

```http
POST /api/v1/executions
Idempotency-Key: <uuid>
```

#### 검증 순서

1. Idempotency-Key 존재 여부
2. 같은 organization에서 같은 key로 생성된 execution 조회
3. TC version 상태가 READY인지 확인
4. Environment·Account가 동일 project·organization인지 확인
5. browser, viewport, locale, timeout, AI call, retry 한도 검사
6. account active lease 여부 검사
7. execution `QUEUED` 생성
8. outbox `execution.requested` 생성
9. audit `execution.created` 생성
10. transaction commit

중복 key 요청은 동일 execution을 반환한다. key가 같지만 body digest가 다르면 `IDEMPOTENCY_CONFLICT`를 반환하는 것이 권장된다.

#### Outbox payload

```json
{
  "schemaVersion": 1,
  "jobId": "uuid",
  "executionId": "uuid",
  "organizationId": "uuid",
  "attempt": 1,
  "requestedAt": "2026-08-27T07:42:18Z"
}
```

secret, 원문 계정 정보, 전체 TC 내용을 queue payload에 넣지 않는다. Worker가 execution ID로 권한이 축소된 snapshot을 조회하게 한다.

#### 수용 기준

- execution과 outbox가 동일 transaction에 저장된다.
- outbox 저장 실패 시 execution도 rollback된다.
- 같은 idempotency key를 2회 호출해도 row가 1개다.
- body가 다른 중복 key는 충돌 오류가 난다.
- READY가 아닌 TC는 실행할 수 없다.

### P0-6. Redis Queue publisher

#### 책임

Outbox publisher는 PostgreSQL의 PENDING event를 읽어 Redis에 발행하고 성공한 event만 PUBLISHED 처리한다.

#### 권장 루프

1. `SELECT ... FOR UPDATE SKIP LOCKED`로 PENDING event batch 조회
2. Redis stream 또는 list에 job 발행
3. 발행 성공 후 published_at과 PUBLISHED 갱신
4. 실패 시 attempts 증가, available_at을 backoff
5. 최대 재시도 후 FAILED 및 경보

PoC에서는 Redis Streams를 권장한다.

- Stream: `tracepilot:execution-jobs`
- Consumer group: `playwright-workers`
- Event key: `job_id`

Publisher 중복 발행 가능성을 전제로 Worker가 `jobId` 또는 `(executionId,attempt)` 멱등성을 검사해야 한다.

#### 실행 방식

API 프로세스의 background task보다 별도 publisher process가 안전하다.

```powershell
python -m app.workers.outbox_publisher
```

Docker Compose에도 `publisher` service를 추가한다.

#### 수용 기준

- outbox event가 Redis Stream에 발행된다.
- publisher 재시작 후 PENDING event를 계속 처리한다.
- Redis 중단 중에는 event가 DB에 남아 있고 복구 후 발행된다.
- 같은 event가 중복 발행되어도 consumer 기준 중복 실행되지 않는다.

## 6. 상태 전이 규칙

Execution 상태는 다음 전이만 허용한다.

```text
QUEUED -> PROVISIONING -> RUNNING
RUNNING -> WAITING_APPROVAL -> RUNNING
RUNNING -> PASS | FAIL | BLOCKED | NEEDS_REVIEW | SYSTEM_ERROR
QUEUED | PROVISIONING | RUNNING | WAITING_APPROVAL -> CANCEL_REQUESTED
CANCEL_REQUESTED -> CANCELLED
```

터미널 상태:

- PASS
- FAIL
- BLOCKED
- NEEDS_REVIEW
- CANCELLED
- SYSTEM_ERROR

터미널 상태는 변경하지 않는다. 재실행은 기존 execution을 QUEUED로 되돌리지 않고 새 execution을 만들며 `parent_execution_id`로 연결한다.

상태 전이 함수 예시:

```python
await execution_service.transition(
    execution_id=execution_id,
    expected_status="QUEUED",
    next_status="PROVISIONING",
)
```

DB update에는 현재 상태 조건을 포함해 race를 막는다.

```sql
UPDATE executions
SET status = 'PROVISIONING', started_at = now()
WHERE id = :id AND organization_id = :org_id AND status = 'QUEUED';
```

affected row가 0이면 `EXECUTION_STATE_CONFLICT`를 반환한다.

## 7. 공통 API 규칙

### 7.1 오류 응답

모든 오류는 아래 형식을 유지한다.

```json
{
  "code": "TC_NOT_READY",
  "message": "승인되지 않은 TC는 실행할 수 없습니다.",
  "requestId": "uuid",
  "retryable": false,
  "details": {}
}
```

FastAPI validation error와 예상하지 못한 500 오류도 같은 envelope로 변환한다. 500 응답에는 stack trace나 secret을 포함하지 않는다.

### 7.2 요청 ID

- 요청의 `X-Request-ID`가 유효한 UUID면 유지한다.
- 없거나 잘못됐으면 서버가 UUID를 생성한다.
- response header, 로그, audit event, outbox payload metadata에 같은 ID를 사용한다.

### 7.3 날짜·이름

- API JSON 날짜: ISO 8601 UTC, 예: `2026-08-27T07:42:18Z`
- DB 컬럼: snake_case
- JSON: 현재 프론트 계약에 맞춘 camelCase
- 내부 Python: snake_case를 사용하고 Pydantic alias generator로 변환하는 방식을 권장한다.

### 7.4 인증 임시 정책

정식 인증 전에는 개발 전용 dependency를 둔다.

```python
class RequestContext:
    organization_id: UUID
    user_id: UUID
    roles: set[str]
```

환경변수 기본 ID를 사용하되 `APP_ENV=production`에서는 임시 인증으로 서버가 시작되지 않게 한다. 클라이언트가 보낸 organization/user ID 헤더만으로 권한을 부여하면 안 된다.

## 8. DB 상세 주의사항

### 8.1 인덱스

최소 유지 대상:

- `users(lower(email))` unique
- `projects(organization_id, project_key)` unique
- `test_cases(project_id, display_id)` unique
- `test_case_versions(test_case_id, version_no)` unique
- `test_case_versions(organization_id, status, created_at desc)`
- `executions(organization_id, idempotency_key)` unique
- active execution partial index
- pending outbox partial index
- artifact expiry index
- audit organization/time index

### 8.2 Idempotency

메모리 dict는 제거한다. execution table에 다음을 추가하는 것이 권장된다.

- `idempotency_key`
- `request_digest`

요청 body는 canonical JSON으로 직렬화한 뒤 SHA-256 digest를 저장한다. 같은 key와 같은 digest는 기존 응답, 같은 key와 다른 digest는 409를 반환한다.

### 8.3 Account lease

현재 initial SQL에는 account lease 전용 테이블이 빠져 있다. 다음 migration에 추가한다.

필드:

- id
- organization_id
- account_id
- execution_id
- status: ACTIVE, RELEASED, EXPIRED
- leased_until
- heartbeat_at
- created_at

`account_id WHERE status='ACTIVE'` partial unique index를 적용한다.

이번 작업에서 Worker가 아직 없더라도 실행 생성 시 계정 충돌을 검증할 수 있도록 repository와 schema를 준비한다.

## 9. Queue·Worker 경계

이번 작업의 Worker 범위는 job 계약과 최소 consumer skeleton까지다.

### Job lifecycle

```text
PENDING -> LEASED -> RUNNING -> SUCCEEDED
                            -> FAILED_RETRYABLE
                            -> FAILED_FINAL
                            -> CANCELLED
```

### 필수 원칙

- Redis는 영구 원장이 아니다. DB execution 상태가 source of truth다.
- Worker는 `executionId`만으로 실행 snapshot을 API/DB에서 조회한다.
- secret은 Worker가 필요한 시점에 secret provider에서 가져온다.
- queue message ack는 DB 상태 저장 이후 수행한다.
- Worker crash 시 lease 만료 후 새 attempt로 복구한다.
- 파괴 가능 action은 자동 retry하지 않는다.

실제 Playwright 브라우저 조작은 다음 개발 단계로 남긴다.

## 10. 테스트 계획

### Unit test

- 상태 전이 허용/거부
- idempotency digest
- TC 구조화 상태 규칙
- execution budget validation
- outbox backoff 계산

### Repository integration test

- organization scope 강제
- execution+outbox atomicity
- unique idempotency
- account active lease 충돌
- `FOR UPDATE SKIP LOCKED` 동시 publisher

### API contract test

- 프론트 TypeScript 타입과 응답 key 일치
- 오류 envelope 일치
- ISO 날짜 형식
- 필수 Idempotency-Key
- validation error code

### 장애 테스트

- Redis가 중단돼도 실행 요청은 DB/outbox에 보존
- Redis 복구 후 publisher가 event 발행
- PostgreSQL transaction 실패 시 부분 row 없음
- publisher 중복 실행에도 동일 event 처리 안전

## 11. 프론트 연결 방법

백엔드 API가 동작하면 프론트 루트에 `.env.local`을 만든다. 이 파일은 Git에 올리지 않는다.

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_USE_MOCK_API=false
```

프론트 실행:

```powershell
cd ai-tc-poc
pnpm install
pnpm dev
```

연결 확인 순서:

1. TC 목록 화면이 DB seed 데이터를 표시한다.
2. 새 TC 구조화 요청이 실제 API에 도달한다.
3. 구조화 결과가 프론트 검토 화면에 표시된다.
4. 실행 설정 완료 후 `POST /executions`가 202를 반환한다.
5. DB에 execution, outbox, audit row가 함께 생성된다.

실시간 SSE와 실제 실행 결과는 아직 mock으로 유지해도 된다.

## 12. 보안 체크리스트

- `.env`, secret, 토큰, 실제 QA 계정이 Git에 포함되지 않는다.
- CORS는 `127.0.0.1:5173`과 명시된 환경만 허용한다.
- API 로그에 raw password, cookie, authorization header를 기록하지 않는다.
- queue payload와 audit metadata에 secret을 넣지 않는다.
- DB 오류 원문을 API 응답으로 반환하지 않는다.
- production에서 기본 organization/user ID를 사용하지 못하게 한다.
- allowed domain 검증은 API와 향후 Worker 양쪽에서 수행할 수 있게 환경 모델에 보존한다.

## 13. 완료 조건

다음 조건을 모두 만족하면 이번 백엔드 작업이 완료된 것으로 본다.

1. Docker Compose로 PostgreSQL, Redis, MinIO가 정상 실행된다.
2. Alembic migration과 seed가 빈 DB에서 성공한다.
3. TC 목록이 PostgreSQL에서 조회된다.
4. TC 구조화 결과와 상태가 PostgreSQL에 저장된다.
5. 실행 생성 시 execution, outbox, audit이 하나의 transaction으로 저장된다.
6. Idempotency-Key 중복 요청이 같은 execution을 반환한다.
7. Outbox publisher가 Redis Stream에 job을 발행한다.
8. Redis 장애 후 복구해도 event가 유실되지 않는다.
9. tenant scope와 상태 전이 테스트가 존재한다.
10. 전체 backend test가 통과한다.
11. OpenAPI JSON과 프론트 타입의 주요 필드가 일치한다.
12. `.env`와 secret이 커밋되지 않는다.

## 14. 작업 종료 및 전달

```powershell
git status
python -m pytest -q
git add ai-tc-poc/backend ai-tc-poc/docker-compose.yml ai-tc-poc/src/api
git commit -m "Persist executions and publish queue jobs"
git push -u origin backend
```

GitHub에서 `backend -> main` PR을 생성한다. PR 설명에 다음을 포함한다.

- 구현한 API와 migration
- 로컬 실행 방법
- 테스트 결과
- 프론트 계약 변경 사항
- 남은 작업
- 알려진 위험 또는 데이터 초기화 필요 여부

프론트 담당자가 `frontend` 브랜치에서 작업 중이라면 `main`에 바로 push하지 않는다. PR 단위로 검토·통합해 충돌을 최소화한다.

## 15. 이번 단계 제외 범위

- 실제 멀티모달 LLM 공급자 호출
- 실제 Playwright 브라우저 실행
- screenshot/trace의 MinIO 업로드
- SSE 실시간 실행 이벤트
- 정식 OIDC/SSO 인증
- 조직 관리자 UI와 완전한 RBAC
- Kubernetes 배포
- 모바일/Appium Worker

위 항목은 DB·Queue 기반이 안정화된 다음 단계에서 구현한다.
