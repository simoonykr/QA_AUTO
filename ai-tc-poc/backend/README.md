# TracePilot Backend

The backend is a modular FastAPI monolith. PostgreSQL is the source of truth, Redis is reserved for the execution queue and leases, and MinIO provides local S3-compatible artifact storage.

Current slice implements health, PostgreSQL-backed test-case listing and execution creation, deterministic TC structuring, common error envelopes, request IDs, CORS, and the initial PostgreSQL schema. Execution creation and its `execution.queued` outbox event are committed atomically. The `outbox-publisher` Compose service publishes pending events to the `tracepilot:executions` Redis Stream.

Run the local stack from `ai-tc-poc` with `docker compose up --build`. The one-shot `migrate` service runs `alembic upgrade head` before the API and outbox publisher start. Existing PostgreSQL volumes created before Alembic adoption must be recreated once for local development.

Execution creation now verifies that the test-case version is `READY`, and that the environment and available account belong to the configured organization/project. A canonical SHA-256 request digest detects reuse of an idempotency key with a different body. Execution, outbox, and audit records are committed in the same database transaction.

Frontend execution integration endpoints:

- `POST /api/v1/executions` — create an execution (`Idempotency-Key` required)
- `GET /api/v1/executions/{executionId}` — read the current execution state
- `POST /api/v1/executions/{executionId}/cancel` — request cancellation
- `POST /api/v1/executions/{executionId}/retry` — create a child execution (`Idempotency-Key` required)

The PoC will use SSE for live execution events. Until the worker/event projection is implemented, the frontend can poll the GET endpoint every two seconds and stop on `PASS`, `FAIL`, `BLOCKED`, `NEEDS_REVIEW`, `CANCELLED`, or `SYSTEM_ERROR`.

Local CORS allows `http://127.0.0.1:5173`. The frontend should use `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1`; a Vite proxy is not required for the local PoC.
