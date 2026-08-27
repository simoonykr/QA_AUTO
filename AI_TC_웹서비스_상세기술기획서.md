# AI 기반 TC 자동 수행 웹서비스 상세 기술기획서

- 문서 상태: 개발 착수안 v1.0
- 기준일: 2026-08-27
- 대상: 제품, Frontend, Backend, Infra, QA
- 결론: **Conditional Go** — PoC 실행 계약 확정 후 착수

## 0. 문서 목적과 기준

비정형 자연어 TC(Test Case)를 구조화하고, 격리된 브라우저에서 UI를 탐색·조작·검증한 뒤 재현 가능한 증적과 결과를 제공하는 다중 사용자 웹서비스의 구현 기준을 정의한다. 초기 제품은 웹 자동화만 대상으로 하며, 복잡한 마이크로서비스와 Kubernetes는 실사용 부하가 확인된 이후로 미룬다.

### 0.1 확정 원칙

1. 초기 구조는 모듈러 모놀리스 API + PostgreSQL + Redis Queue + 격리 Playwright Worker + S3 호환 Object Storage다.
2. AI는 TC 구조화, selector 후보 재순위화, 제한적 예외 복구에만 사용한다.
3. 로그인, 권한, 정책, 상태 전이, assertion, timeout은 규칙 기반 코드가 최종 권한을 가진다.
4. 실행은 테스트 전용 계정과 허용 도메인에서만 가능하다.
5. 모든 실행 단계는 입력, 판단, 행동, 전후 상태, assertion, 비용을 감사 가능하게 남긴다.

### 0.2 기본 가정과 확인 필요

| 구분 | 기본 가정 | 확인 필요 |
|---|---|---|
| 대상 | 사내 또는 테스트 전용 웹서비스 1개 | 첫 PoC URL과 소유 조직 |
| 브라우저 | Chromium 최신 안정판, 1440×900, ko-KR | Firefox/WebKit 필요 여부 |
| 인증 | 이메일/비밀번호 기반 앱 인증, 대상 사이트 계정은 secret 저장 | SSO, MFA, CAPTCHA 처리 |
| 규모 | 조직 1~5개, 사용자 50명, 동시 실행 10개 | 1년 내 최대 사용자·동시 실행 |
| TC | 대표 TC 20~30개, 명시적 기대 결과 보유 | 실제 원문과 정답 판정자 |
| 보존 | 메타데이터 1년, screenshot/trace 90일 | 법무·보안 보존 요구 |
| AI | 외부 멀티모달 API 사용 가능 | 허용 공급자, 리전, 월 예산 |

## 1. 전체 시스템 구성

```text
[Browser / Frontend]
  HTTPS REST + SSE
         |
         v
[Modular Monolith Backend API] ---------------- [Auth / Secret Provider]
  Project/TC/Execution/Policy/Report/Admin       OIDC, Vault/KMS or encrypted DB
         |             |              |
         | SQL         | enqueue      | presigned URL
         v             v              v
   [PostgreSQL]     [Redis Queue]   [Object Storage]
                         |
                  lease/heartbeat
                         v
              [Isolated Playwright Worker]
                 | observe/action/assert
                 v
              [Target Web Service]
                         |
                         v
             [AI/Execution Orchestrator]
       structured output, policy gate, cost budget

All components -> structured logs/metrics/traces -> [Observability]
```

### 1.1 컴포넌트 책임

| 컴포넌트 | 책임 | 금지/비책임 |
|---|---|---|
| Frontend | TC 편집, 실행 설정, 실시간 상태, 증적 검토, 승인/중단 | secret 평문 보관, 상태 임의 변경 |
| Backend API | 인증·RBAC, 도메인 모델, 상태 전이, 정책, API, 감사 로그 | 장시간 브라우저 실행 |
| AI/Execution Orchestrator | 목표 단계 선택, 관찰 축약, AI 호출, action 제안, 비용·step 제한 | 정책 우회, 직접 브라우저 제어 |
| Playwright Worker | 세션 생성, 관찰, 허용 action 실행, deterministic assertion, 증적 생성 | 사용자 권한 판단, 임의 외부 URL 접근 |
| Redis Queue | 대기열, lease, heartbeat, cancel flag, 짧은 상태 캐시 | 영구 진실 원장 |
| PostgreSQL | 사용자·TC·실행·단계·정책·감사 데이터의 source of truth | 대용량 영상/trace 저장 |
| Object Storage | screenshot, trace, video(선택), 업로드 원본, 결과 export | 공개 버킷 운영 |
| 인증/비밀정보 | OIDC/session, secret 암호화, 실행 시 일회성 주입 | prompt/로그로 secret 노출 |
| 관측성 | 메트릭, trace, 오류, 비용, 경보 | TC 민감정보 무제한 수집 |

통신은 외부 HTTPS, 내부 TLS를 기본으로 한다. Backend가 execution row를 먼저 commit한 뒤 queue에 `execution_id`만 전달한다. Worker는 DB에서 권한이 축소된 실행 snapshot을 조회하며, Object Storage는 짧은 만료의 presigned URL만 사용한다.

## 2. 프론트엔드 IA와 화면 명세

```text
로그인
└─ 조직 선택
   ├─ 대시보드
   ├─ 프로젝트
   │  ├─ 환경
   │  ├─ 테스트 계정/데이터
   │  ├─ TC 목록
   │  │  ├─ 작성/가져오기
   │  │  └─ 구조화 검토
   │  └─ 실행 목록
   │     ├─ 실행 설정
   │     ├─ 실시간 모니터
   │     └─ 결과 상세
   └─ 관리자
      ├─ 사용자/역할
      ├─ 실행 한도/정책
      ├─ AI 모델/비용
      └─ 감사 로그
```

| 화면 | 상세 기능 | 주요 권한/상태 |
|---|---|---|
| 로그인 | OIDC 또는 이메일 로그인, 조직 선택, 세션 만료 안내 | 모든 사용자 |
| 대시보드 | 실행 수, pass rate, 최근 실패, queue/worker 상태, AI 비용, 프로젝트 필터 | Viewer+ |
| 프로젝트/환경 | 프로젝트 CRUD, base URL, allowed domains, locale, viewport, timeout, 정책 연결 | Project Admin |
| TC 목록 | 검색, 태그, 상태, 최신 버전, 최근 결과, 다중 선택 실행 | Editor+ |
| 작성/가져오기 | 원문 입력, CSV/XLSX/DOCX/TXT 업로드, 파싱 미리보기, 중복 검사 | Editor+ |
| 구조화 검토 | 전제조건·steps·data·assertions 표시, 원문 대비 diff, 오류/모호성, 승인·수정 | Editor/Reviewer |
| 실행 설정 | TC 버전, 환경, 계정 lease, browser/viewport, 변수, step/time/cost budget | Runner+ |
| 실시간 모니터 | SSE 타임라인, 현재 screenshot, action/근거, 비용, 승인·중단·재개 | Runner; 위험행동은 Approver |
| 결과 상세 | Pass/Fail/Blocked/Needs Review, step 전후 증적, trace 다운로드, 실패 분류, 재실행 | Viewer+ |
| 계정/데이터 | secret 별칭, 사용 가능 여부, lease, fixture/reset 작업, 사용 이력 | Project Admin; 평문 재표시 금지 |
| 관리자 | 사용자·role, quota, retention, model allowlist, worker, audit 검색 | Org Admin |

공통 UX 기준: mutation 전 권한 확인, destructive action 이중 확인, 모든 비동기 작업은 상태·재시도 가능 여부 표시, 비밀값은 입력 후 다시 표시하지 않는다.

## 3. 사용자 흐름과 상태 전이

### 3.1 대표 흐름

1. Editor가 TC 원문을 등록하거나 파일을 가져온다.
2. 시스템이 `DRAFT` 버전을 만들고 비동기로 구조화한다.
3. Reviewer가 구조화 결과와 모호성 경고를 수정·승인해 `READY`로 만든다.
4. Runner가 환경, 계정, 변수, budget을 선택하고 실행을 요청한다.
5. Backend가 정책·quota를 검사하고 `QUEUED` execution을 생성한다.
6. Worker가 lease를 획득하면 `PROVISIONING` → `RUNNING`으로 전이한다.
7. 각 step은 observe → decide → policy check → act → verify 순으로 실행한다.
8. 위험 action은 `WAITING_APPROVAL`에서 승인 또는 거절을 기다린다.
9. 사용자는 `CANCEL_REQUESTED`를 요청할 수 있고 Worker가 safe point에서 `CANCELLED`로 확정한다.
10. 자동 재시도는 transient 오류만 새 attempt로 수행한다.
11. 결과가 애매하면 `NEEDS_REVIEW`; Reviewer가 근거를 보고 최종 결과를 확정한다.

### 3.2 상태 모델

```text
TC Version: DRAFT -> STRUCTURING -> REVIEW_REQUIRED -> READY -> ARCHIVED
                         \-> STRUCTURE_FAILED -> STRUCTURING

Execution: QUEUED -> PROVISIONING -> RUNNING -> PASS|FAIL|BLOCKED|NEEDS_REVIEW
              |           |           |  \-> WAITING_APPROVAL -> RUNNING|BLOCKED
              |           |           \-> CANCEL_REQUESTED -> CANCELLED
              \-----------+---------------> SYSTEM_ERROR -> QUEUED(new attempt)
```

터미널 상태는 덮어쓰지 않는다. 재실행은 기존 row 변경이 아니라 새 execution과 `parent_execution_id` 연결로 생성한다.

## 4. 백엔드 모듈 경계

| 모듈 | 책임 | 처리 방식 |
|---|---|---|
| Identity/Tenant | 로그인, session, org membership, RBAC | 동기 |
| Project/Environment | 프로젝트, 실행 환경, allowed domain, 정책 | 동기 |
| TestCase | TC·버전·태그·import·review | CRUD 동기, import/구조화 비동기 |
| Execution | 실행 생성, 상태 머신, cancel/retry/approval | 명령 동기, 실행 비동기 |
| Orchestrator | step 계획, AI 호출, budget, 복구 | Worker 내부 비동기 |
| Policy | action/domain/file/quota 검증 | 실행 직전 동기 |
| Account/Data | secret reference, lease, fixture/reset | 예약 동기, reset 비동기 |
| Artifact/Report | metadata, presigned URL, 결과 집계 | 업로드 비동기, 조회 동기 |
| Admin/Audit | 사용자, quota, retention, 감사 이벤트 | 동기 + batch 정리 |
| Notification | 완료·실패 알림 | outbox 기반 비동기 |

DB transaction과 외부 enqueue 사이 유실을 막기 위해 transactional outbox를 사용한다. API는 queue 완료를 기다리지 않고 `202 Accepted`와 resource ID를 반환한다.

## 5. REST API 초안

공통: `/api/v1`, JSON, cursor pagination, `Idempotency-Key` 지원. 오류 형식은 `{code,message,request_id,details,retryable}`이다.

| Method / Endpoint | 핵심 요청 → 응답 | 권한 | 주요 오류 |
|---|---|---|---|
| POST `/auth/session` | credential/OIDC code → user, orgs | Public | AUTH_INVALID, MFA_REQUIRED |
| GET `/projects` | filter,cursor → projects | Viewer | FORBIDDEN |
| POST `/projects` | name,key → project | Org Admin | CONFLICT |
| POST `/projects/{id}/environments` | base_url,domains,viewport,policy_id → environment | Project Admin | DOMAIN_NOT_ALLOWED |
| GET `/test-cases` | project,status,tag,cursor → items | Viewer | — |
| POST `/test-cases` | project_id,title,raw_text,tags → testcase/version | Editor | VALIDATION_ERROR |
| POST `/test-cases/imports` | upload_id,mapping → import_job | Editor | FILE_TYPE_DENIED, FILE_TOO_LARGE |
| POST `/test-case-versions/{id}/structure` | model_profile,budget → job | Editor | TC_NOT_DRAFT, QUOTA_EXCEEDED |
| PATCH `/test-case-versions/{id}` | expected_version,structured_spec → version | Editor | VERSION_CONFLICT |
| POST `/test-case-versions/{id}/approve` | comment → READY | Reviewer | REVIEW_BLOCKED |
| POST `/executions` | tc_version_ids,environment_id,account_id,variables,budgets → executions | Runner | TC_NOT_READY, ACCOUNT_BUSY, POLICY_DENIED |
| GET `/executions/{id}` | execution,steps,summary | Viewer | NOT_FOUND |
| GET `/executions/{id}/events` | SSE cursor → event stream | Viewer | STREAM_EXPIRED |
| POST `/executions/{id}/cancel` | reason → CANCEL_REQUESTED | Runner | TERMINAL_STATE |
| POST `/executions/{id}/retry` | from_step?,reason → new execution | Runner | NOT_RETRYABLE |
| POST `/executions/{id}/approvals/{aid}` | decision,comment → approval | Approver | APPROVAL_EXPIRED |
| POST `/executions/{id}/finalize` | final_status,reason → confirmed result | Reviewer | NOT_REVIEWABLE |
| POST `/accounts` | name,secret_payload,scope → secret reference | Project Admin | SECRET_PROVIDER_ERROR |
| POST `/accounts/{id}/reset` | fixture_id → reset job | Runner | ACCOUNT_BUSY |
| GET `/artifacts/{id}/download` | — → short-lived URL | Viewer | ARTIFACT_EXPIRED |
| GET `/admin/audit-events` | actor,action,time,cursor → events | Org Admin | FORBIDDEN |

모든 path resource는 `organization_id` scope를 서버에서 재확인하며, 클라이언트가 보낸 tenant ID를 신뢰하지 않는다.

## 6. 데이터베이스 설계

모든 주요 테이블은 `id uuid`, `organization_id uuid`, `created_at`, `updated_at`을 갖는다. 삭제는 기본 soft delete이며 감사·보존 만료 작업만 hard delete한다.

| 테이블 | PK/FK 및 핵심 컬럼 | 주요 인덱스 |
|---|---|---|
| organizations | id, name, status | unique(name) |
| users | id, email, display_name, status | unique(lower(email)) |
| memberships | org_id FK, user_id FK, role | unique(org_id,user_id) |
| projects | id, org_id FK, key, name, status | unique(org_id,key) |
| environments | id, project_id FK, base_url, allowed_domains jsonb, viewport jsonb, policy_id FK | (project_id,status) |
| test_cases | id, project_id FK, title, current_version_id FK, tags | GIN(tags), (project_id,updated_at) |
| test_case_versions | id, test_case_id FK, version_no, raw_text, structured_spec jsonb, schema_version, status, reviewer_id | unique(test_case_id,version_no), (status,updated_at) |
| executions | id, project_id FK, tc_version_id FK, environment_id FK, account_id FK, parent_execution_id FK, status, attempt, budgets jsonb, result, error_code, started_at, ended_at | (project_id,created_at desc), partial(status non-terminal) |
| step_runs | id, execution_id FK, step_no, goal, status, action jsonb, assertion jsonb, error_code, confidence, duration_ms, token_cost | unique(execution_id,step_no,attempt), (execution_id,step_no) |
| execution_events | id bigint, execution_id FK, sequence, type, payload jsonb, occurred_at | unique(execution_id,sequence), BRIN(occurred_at) |
| artifacts | id, execution_id FK, step_run_id FK nullable, type, object_key, sha256, size, expires_at | (execution_id,type), (expires_at) |
| accounts | id, project_id FK, name, secret_ref, status, last_reset_at | unique(project_id,name) |
| account_leases | id, account_id FK, execution_id FK, status, leased_until, heartbeat_at | partial unique(account_id) where active |
| approvals | id, execution_id FK, step_run_id FK, action_digest, status, expires_at, decided_by | (execution_id,status) |
| policies | id, project_id FK nullable, version, rules jsonb, status | unique(project_id,version) |
| model_profiles | id, org_id FK, provider, model, prompt_version, limits jsonb, status | (org_id,status) |
| outbox_events | id, aggregate_type/id, type, payload, published_at | partial(published_at is null) |
| audit_events | id bigint, org_id, actor_id, action, resource_type/id, before/after_digest, ip, occurred_at | (org_id,occurred_at desc), (resource_type,resource_id) |

### 6.1 Enum

- Role: `VIEWER, EDITOR, REVIEWER, RUNNER, APPROVER, PROJECT_ADMIN, ORG_ADMIN`
- TC status: `DRAFT, STRUCTURING, REVIEW_REQUIRED, READY, STRUCTURE_FAILED, ARCHIVED`
- Execution status: `QUEUED, PROVISIONING, RUNNING, WAITING_APPROVAL, CANCEL_REQUESTED, PASS, FAIL, BLOCKED, NEEDS_REVIEW, CANCELLED, SYSTEM_ERROR`
- Step status: `PENDING, OBSERVING, DECIDING, POLICY_CHECK, ACTING, VERIFYING, PASS, FAIL, BLOCKED, SKIPPED`

### 6.2 보존/삭제

- 실행·step·audit 메타데이터: 기본 365일.
- screenshot/trace/upload: 기본 90일, 프로젝트별 단축 가능.
- secret: 계정 삭제 즉시 revoke 후 7일 내 암호문 제거.
- 사용자 삭제: 개인정보 익명화, 감사 이벤트 actor는 비식별 ID 유지.
- retention worker는 legal hold를 확인하고 batch 삭제하며 삭제 이벤트를 감사 로그에 남긴다.

## 7. Queue와 Worker

### 7.1 Job lifecycle

`PENDING -> LEASED -> RUNNING -> SUCCEEDED | FAILED_RETRYABLE | FAILED_FINAL | CANCELLED | DEAD_LETTER`

1. Backend가 execution과 outbox를 동일 transaction으로 저장한다.
2. publisher가 Redis queue에 `job_id, execution_id, attempt`를 enqueue한다.
3. Worker는 atomic lease를 얻고 10초마다 heartbeat한다.
4. lease 기본 60초, heartbeat 3회 누락 시 reaper가 회수한다.
5. 전체 timeout 15분, step timeout 60초, approval timeout 10분을 기본값으로 둔다.
6. cancel flag는 action 사이 safe point에서 확인하고 browser context를 종료한다.

### 7.2 재시도와 복구

- 자동 재시도: browser crash, worker loss, 일시적 storage/AI 429·5xx만 최대 2회, exponential backoff+jitter.
- 재시도 금지: assertion failure, policy denied, 잘못된 TC, 인증 실패, 파괴적 action 거절.
- 멱등성: `(execution_id, attempt)` unique, action마다 `action_digest` 저장. 외부 side effect 가능 action은 자동 재실행하지 않는다.
- Worker 장애 시 lease 만료 후 새 Worker가 새 attempt를 시작한다. 기존 browser session은 복구하지 않고 fixture/reset 후 처음부터 수행한다.
- 동시성: org/project/account quota와 Worker slot을 모두 만족해야 lease. 동일 account active lease는 1개다.
- Redis 소실 시 PostgreSQL의 non-terminal execution과 outbox를 기준으로 queue를 재구성한다.

## 8. AI와 실행 오케스트레이션

### 8.1 AI 역할

| 단계 | AI 입력 | AI 출력 | 규칙 기반 보호 |
|---|---|---|---|
| TC 구조화 | 원문, 허용 action/assertion schema | preconditions, steps, expected results, ambiguity | JSON Schema 검증, Reviewer 승인 |
| selector 재순위화 | 축약 DOM/a11y 후보, 목표, screenshot crop | 후보 ID 순위와 근거 | 후보 외 selector 생성 금지 |
| 예외 복구 | 최근 action, 화면 변화, 오류, 제한된 후보 | retry/wait/dismiss/blocked 제안 | 최대 복구 2회, policy 재검사 |

DOM/a11y로 후보를 먼저 생성하고 AI에는 내부 `candidate_id`만 제공한다. 전체 screenshot은 후보 생성 실패 시에만 전송한다. AI가 반환한 좌표·URL·JavaScript를 그대로 실행하지 않는다.

### 8.2 Prompt/model/version

- prompt template은 Git과 `model_profiles.prompt_version`으로 버전 관리한다.
- 각 실행에 provider, model, prompt version, schema version, temperature, 입력/출력 token, latency, cost를 snapshot한다.
- 운영 변경은 staging golden TC 평가 통과 후 활성화한다.
- structured output은 strict JSON Schema로 검증하며 1회 repair 후 실패하면 `AI_OUTPUT_INVALID`다.

### 8.3 비용 제한

- 기본: execution당 20 AI calls, 40k input token, 8k output token, 미화 $0.50 상당 상한.
- 조직 일/월 quota, 사용자별 동시 실행 quota를 둔다.
- 80% 도달 시 이벤트 경고, 100%에서 `BUDGET_EXCEEDED`로 Blocked 처리한다.
- 동일한 목표+DOM digest의 결과는 짧게 cache하되 tenant/model/prompt version을 cache key에 포함한다.

## 9. Action/Assertion Schema와 오류 코드

### 9.1 Action JSON Schema 초안

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["action_id", "type", "target", "timeout_ms"],
  "properties": {
    "action_id": {"type": "string", "format": "uuid"},
    "type": {"enum": ["click", "fill", "select", "press", "scroll", "wait", "navigate", "upload"]},
    "target": {
      "type": "object",
      "required": ["candidate_id"],
      "properties": {"candidate_id": {"type": "string"}, "expected_role": {"type": "string"}, "expected_name": {"type": "string"}},
      "additionalProperties": false
    },
    "value_ref": {"type": ["string", "null"], "description": "변수 또는 secret 별칭; 평문 secret 금지"},
    "timeout_ms": {"type": "integer", "minimum": 100, "maximum": 60000},
    "risk": {"enum": ["LOW", "MEDIUM", "HIGH"]},
    "reason": {"type": "string", "maxLength": 500}
  },
  "additionalProperties": false
}
```

`navigate`는 target 대신 allowlist 검증된 상대 경로만 허용하고, `upload`는 사전 검사된 artifact ID만 받도록 실제 구현에서 `oneOf` subtype으로 분리한다.

### 9.2 Assertion JSON Schema 초안

```json
{
  "type": "object",
  "required": ["type", "operator", "expected", "timeout_ms"],
  "properties": {
    "type": {"enum": ["url", "element", "text", "attribute", "count", "network", "visual_change"]},
    "candidate_id": {"type": ["string", "null"]},
    "operator": {"enum": ["equals", "contains", "matches", "exists", "not_exists", "gte", "lte", "changed"]},
    "expected": {},
    "timeout_ms": {"type": "integer", "minimum": 100, "maximum": 60000},
    "case_sensitive": {"type": "boolean", "default": false}
  },
  "additionalProperties": false
}
```

### 9.3 오류 코드

- 입력/TC: `VALIDATION_ERROR, TC_NOT_READY, TC_AMBIGUOUS, AI_OUTPUT_INVALID`
- 탐색/행동: `ELEMENT_NOT_FOUND, ELEMENT_AMBIGUOUS, ACTION_TIMEOUT, ACTION_NO_EFFECT, NAVIGATION_BLOCKED`
- 검증: `ASSERTION_FAILED, ASSERTION_UNSUPPORTED`
- 정책/보안: `POLICY_DENIED, APPROVAL_REQUIRED, APPROVAL_REJECTED, DOMAIN_NOT_ALLOWED, FILE_DENIED, SECRET_UNAVAILABLE`
- 자원/운영: `ACCOUNT_BUSY, WORKER_LOST, BROWSER_CRASH, QUEUE_TIMEOUT, STORAGE_ERROR, RATE_LIMITED`
- 한도: `STEP_LIMIT_EXCEEDED, TIME_LIMIT_EXCEEDED, BUDGET_EXCEEDED, RETRY_EXHAUSTED`

## 10. 보안 설계

1. RBAC: API endpoint와 resource scope를 모두 검사한다. Reviewer와 Approver는 프로젝트별 지정 가능하다.
2. Tenant 격리: 모든 row에 org scope, repository 기본 조건 강제, Object Storage key와 encryption context도 org별 분리한다. 운영 단계에서는 PostgreSQL RLS를 방어층으로 추가한다.
3. Secret: Vault/KMS가 권장된다. MVP에서 encrypted DB를 쓰면 envelope encryption, key rotation, 평문 미저장, 실행 시 메모리 주입, 종료 즉시 폐기를 적용한다.
4. 마스킹: 알려진 secret과 입력 field를 로그·prompt·screenshot에서 마스킹한다. screenshot은 민감 selector 영역을 blur한 사본만 장기 보관한다.
5. SSRF: environment의 scheme은 HTTPS, DNS/IP resolve 후 private/link-local/metadata IP 차단, redirect마다 재검사, egress proxy allowlist 적용.
6. 도메인: base domain과 명시된 subdomain만 허용. 새 origin 이동·popup은 차단하고 이벤트로 남긴다.
7. 파일: 허용 확장자와 실제 MIME 일치 검사, 크기 제한, zip bomb·path traversal 차단, 악성코드 검사 후 격리 저장. 자동 다운로드는 기본 차단한다.
8. 파괴적 행동: 결제·삭제·권한·계정 변경 키워드와 화면 정책을 조합해 차단 또는 승인 요구. 승인에는 action digest와 만료시간을 묶어 TOCTOU를 막는다.
9. Prompt injection: 페이지 텍스트는 관찰 데이터로 표시하고 system instruction과 분리한다. 페이지가 제안한 URL·명령·script는 실행하지 않는다.
10. 감사: 로그인, 권한·정책·secret·TC 승인·실행·승인·다운로드·삭제를 append-only audit로 남긴다.

## 11. 서버와 배포

### 11.1 환경

| 환경 | 구성 | 목적 |
|---|---|---|
| Local | Docker Compose: web, api, worker, postgres, redis, minio, mail mock | 단일 명령 개발·통합 테스트 |
| Staging | 운영과 같은 이미지, 별도 DB/bucket/secret, synthetic 계정 | golden TC, 부하·보안 검증 |
| Production | managed PostgreSQL/Redis/Object Storage 권장, API 2 replicas, worker pool | 가용성·백업·확장 |

MVP는 Docker Compose 또는 소규모 컨테이너 서비스로 시작한다. Kubernetes 전환 조건은 Worker 30개 이상, 여러 worker pool, 자동 확장·노드 격리가 운영 병목이 될 때다.

### 11.2 CI/CD

- PR: lint, type check, unit, migration check, API contract, Playwright synthetic TC, secret scan, dependency/image scan.
- main: immutable image build, SBOM·서명, staging 자동 배포, golden TC 통과 후 운영 승인 배포.
- DB migration은 backward compatible expand/contract 방식을 사용하고 자동 rollback 대신 복구 runbook을 둔다.
- 일일 PostgreSQL backup + PITR 7일, Object Storage versioning, 분기별 restore drill.

### 11.3 모니터링

- 메트릭: API p95/error, queue age/depth, active worker, lease loss, execution outcome, step latency, AI calls/cost, storage failure.
- 로그: request_id, execution_id, step_id를 공통 correlation key로 사용하고 secret/raw page text는 기본 제외.
- 경보: queue age 5분 초과, worker heartbeat 급감, system error 5% 초과, AI quota 80%, DB/storage 오류.

## 12. 비기능 요구사항

| 항목 | MVP 목표/가정 |
|---|---|
| 동시 실행 | 10개, org별 기본 3개; 설정 가능 |
| API 성능 | 일반 조회/명령 p95 500ms 이하(SSE·upload 제외) |
| Queue | 정상 부하에서 95%가 60초 내 시작 |
| 실행 시간 | 기본 15분, 최대 30분; step 60초 |
| 가용성 | 월 99.5%, 계획 점검 제외 |
| RPO/RTO | 24시간/4시간; 운영 확장 시 1시간/1시간 검토 |
| 보존 | 메타 365일, artifact 90일, audit 365일 |
| 브라우저 | Chromium latest-1 우선; Firefox/WebKit 제외 |
| 접근성 | 서비스 UI WCAG 2.1 AA 핵심 항목, 키보드 조작 |
| 비용 | 실행별·조직별 AI 상한, 비용 추적 95% 이상 |
| 추적성 | 모든 execution/step에 correlation ID와 immutable event sequence |

## 13. 일정, 백로그, 인력

### 13.1 3~4주 PoC

| 주차 | 산출물 | 완료 기준 |
|---|---|---|
| 1주 | PoC 계약, TC schema, Playwright harness, 대상/계정/reset | 대표 TC 20~30개와 기대 결과 승인 |
| 2주 | TC 구조화, DOM/a11y 후보, action/assertion executor | 기본 click/fill/wait/assert 흐름 동작 |
| 3주 | selector 재순위화, screenshot fallback, trace/report | 단일 사용자 end-to-end 실행과 재현 로그 |
| 4주 | golden run, 실패 분류, 비용·성공률 분석, Go 판단 | 사전 합의 KPI 보고서와 제한사항 확정 |

PoC 인력: Backend/Automation 1~2명, Frontend 0.5명, QA 1명, Product 0.5명. Infra/Security는 각 0.2명 지원.

### 13.2 8~12주 MVP(2주 스프린트)

| Sprint | 핵심 백로그 |
|---|---|
| S0(1주) | 실행 계약·ADR, repo/CI, local compose, schema/API baseline |
| S1 | 인증/RBAC, 프로젝트·환경, TC CRUD/import, 구조화 review UI |
| S2 | execution state machine, outbox/queue/lease, 격리 worker, account lease |
| S3 | orchestrator, policy gate, approval/cancel/retry, SSE monitor |
| S4 | 결과 상세, artifacts, 감사, secret masking, retention |
| S5 | quota/cost, golden regression, 부하·보안·복구 테스트, staging pilot |

권장 인력: Frontend 1, Backend 2(그중 1명 automation 중심), Infra 0.5, QA automation 1, Product/Design 0.5, Security 자문 0.2. 3명 이하라면 import 형식, 관리자 대시보드, 영상, PDF export를 뒤로 미룬다.

## 14. 제외 범위, 리스크, 미결정

### 14.1 PoC/MVP 제외

- 모바일/Appium, 게임 전투·좌표 중심 자동화
- CAPTCHA 자동 우회, 임의 MFA 처리
- 결제·실데이터 삭제·권한 변경 자동 수행
- 브라우저 3종 완전 호환, 모바일 웹
- 범용 JavaScript 실행, 임의 shell/network tool
- 고급 visual regression, self-healing selector 영구 학습
- Kubernetes, 다지역 active-active, 물리 tenant 분리
- Jira/TestRail 양방향 동기화, SSO, PDF/영상 export(후순위)

### 14.2 주요 기술 리스크

| 리스크 | 영향 | 완화/중단 기준 |
|---|---|---|
| 비정형 TC 모호성 | 잘못된 계획·판정 | Reviewer 승인; 구조화 정확도 목표 미달 시 입력 템플릿 강화 |
| 동적 UI/iframe/shadow DOM | selector 실패 | 후보 전략·trace; 핵심 TC 성공률 80% 미달 시 범위 축소 |
| AI 비용/지연 | UX·운영비 악화 | DOM 우선, cache, budget; 실행당 상한 초과 시 모델/흐름 변경 |
| 테스트 데이터 오염 | 비결정적 결과 | account lease+reset; reset 불가 대상은 PoC 제외 |
| 개인정보/secret 노출 | 보안 사고 | 전용 계정·마스킹·보존 단축; 요구 충족 전 운영 배포 금지 |
| Worker 불안정 | 중복 side effect | 격리·lease·idempotency; 파괴 action 자동 재시도 금지 |

### 14.3 착수 전 미결정 항목

1. PoC 사이트, 대표 TC와 소유자, 기대 결과의 최종 승인자.
2. 대상 시스템 인증 방식과 fixture/reset API 유무.
3. 허용 AI 공급자·리전·데이터 보존 옵션·월 예산.
4. 동시 실행 목표, 실행당 최대 시간, artifact 보존기간.
5. 위험 action 분류와 승인자, 업무시간 밖 승인 timeout.
6. secret provider 선택과 운영 인프라 제공 방식.
7. TC import 우선 형식과 기존 필드 mapping.

## 15. 담당별 작업 분해와 수용 기준

### 15.1 Frontend

- 로그인부터 프로젝트/TC/실행/결과까지 route와 권한 guard가 구현된다.
- 구조화 검토 화면에서 원문과 구조화 결과를 비교·수정·승인할 수 있다.
- 실행 모니터가 SSE 재연결과 event cursor를 지원하고 중복 이벤트를 표시하지 않는다.
- 승인·중단·재시도는 현재 상태에서 가능할 때만 노출되며 서버 충돌을 처리한다.
- secret은 저장 후 평문으로 다시 표시하거나 브라우저 storage에 저장하지 않는다.
- 주요 화면은 loading/empty/error/forbidden 상태와 키보드 조작을 제공한다.

### 15.2 Backend

- OpenAPI 문서와 오류 envelope가 구현되고 contract test를 통과한다.
- 모든 resource 접근에서 org/project scope와 RBAC가 서버에서 검증된다.
- execution 상태 전이는 허용된 edge만 원자적으로 처리하며 terminal 상태를 덮어쓰지 않는다.
- execution 생성과 enqueue가 outbox로 유실 없이 연결된다.
- retry는 새 execution/attempt를 생성하고 원본 결과와 감사를 보존한다.
- audit 대상 mutation은 actor, resource, request_id, 결과를 남긴다.

### 15.3 Worker/AI

- 각 실행은 별도 browser context/container에서 수행되고 종료 후 storage·cookie가 폐기된다.
- lease/heartbeat/cancel/timeout/retry/idempotency 통합 테스트가 있다.
- action은 schema 검증과 policy gate를 통과해야만 Playwright에 전달된다.
- deterministic assertion이 AI 판정보다 우선하며 모든 step에 전후 증적이 연결된다.
- model/prompt/schema version과 token/cost가 실행에 기록된다.
- golden TC에서 구조화·요소 선택·완주율과 실패 분류를 재현 가능하게 측정한다.

### 15.4 Infra/Security

- Local Compose로 신규 개발자가 문서대로 전체 stack을 실행할 수 있다.
- staging/production의 DB, bucket, Redis, key, 계정이 분리된다.
- egress allowlist, private IP/metadata 차단, secret rotation, image/dependency scan이 검증된다.
- DB restore와 Redis 소실 후 queue 재구성 runbook을 실제로 시험한다.
- dashboard와 필수 경보가 배포 전에 활성화된다.

### 15.5 QA/Product

- 대표 TC 20~30개는 난이도, precondition, 입력 데이터, deterministic 기대 결과, reset 절차를 가진다.
- Pass/Fail/Blocked/Needs Review와 오류 코드별 기대 동작이 테스트 케이스화된다.
- happy path 외에 worker loss, AI 429/invalid JSON, account busy, approval timeout, cancel race, storage failure를 검증한다.
- PoC 종료 시 완주율, 올바른 판정률, selector 정확도, 재현 가능한 실패율, 시간, AI 비용을 보고한다.
- MVP 착수 Go 기준과 범위 축소 기준을 시작 전에 서면 승인한다.

## 16. 착수 게이트

다음 다섯 항목이 모두 충족되면 PoC 개발을 시작한다.

1. 웹 단일 대상과 allowed domain이 확정됐다.
2. 대표 TC 20~30개와 deterministic 기대 결과가 승인됐다.
3. 테스트 계정, fixture/reset, 데이터 책임자가 준비됐다.
4. 금지·승인 필요 action과 승인자가 확정됐다.
5. AI 공급자, 데이터 정책, 비용 상한이 보안·제품 책임자의 승인을 받았다.

PoC 종료 후 MVP Go는 선정 TC 완주율 80% 이상, 올바른 최종 판정률 90% 이상, 실패 원인 분류 가능률 95% 이상, 중대한 보안 위반 0건, 실행당 비용이 합의 상한 이내일 때 승인한다. 수치는 대상 TC가 확정된 뒤 최종 조정한다.
