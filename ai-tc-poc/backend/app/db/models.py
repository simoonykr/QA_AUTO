import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ExecutionStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CANCELLED = "CANCELLED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class TestCaseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class AiUsageStatus(str, enum.Enum):
    RESERVED = "RESERVED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "project_key"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Environment(Base):
    __tablename__ = "environments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    viewport: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TestAccount(Base):
    __tablename__ = "test_accounts"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="AVAILABLE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestCaseVersion(Base):
    __tablename__ = "test_case_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_cases.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[TestCaseStatus] = mapped_column(Enum(TestCaseStatus, name="test_case_status", create_type=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_case_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_case_versions.id"), nullable=False)
    environment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(Enum(ExecutionStatus, name="execution_status"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_execution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("executions.id"))


class StepRun(Base):
    __tablename__ = "step_runs"
    __table_args__ = (UniqueConstraint("execution_id", "step_no", "attempt"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    assertion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    error_code: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("step_runs.id", ondelete="SET NULL"))
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus, name="outbox_status"), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiUsageLedger(Base):
    __tablename__ = "ai_usage_ledger"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AiUsageStatus] = mapped_column(Enum(AiUsageStatus, name="ai_usage_status"), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    upstream_request_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiStructureCache(Base):
    __tablename__ = "ai_structure_cache"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    structured_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "request_hash", "model"),)
