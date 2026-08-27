# TracePilot Backend

The backend is a modular FastAPI monolith. PostgreSQL is the source of truth, Redis is reserved for the execution queue and leases, and MinIO provides local S3-compatible artifact storage.

Current slice implements health, test-case listing, deterministic TC structuring, execution creation, common error envelopes, request IDs, CORS, and the initial PostgreSQL schema. The next slice replaces seed/in-memory repositories with SQLAlchemy repositories and publishes execution jobs through the transactional outbox.
