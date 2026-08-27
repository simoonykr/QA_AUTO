# Frontend API contract

`client.ts` is the only transport boundary used by UI code. Local development uses the in-memory mock by default. When the backend is ready, set `VITE_USE_MOCK_API=false` and configure `VITE_API_BASE_URL`.

Errors follow `{ code, message, requestId, retryable, details }`. Mutating endpoints use `Idempotency-Key`; execution state is server-authoritative. Secrets are represented only by account or variable references and must never be returned to the frontend.
