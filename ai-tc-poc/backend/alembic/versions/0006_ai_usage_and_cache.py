"""add AI usage ledger and structure cache"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_ai_usage_cache"
down_revision = "0005_seed_worker_failure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM("RESERVED", "COMPLETED", "FAILED", name="ai_usage_status", create_type=False)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_cost_usd", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("upstream_request_id", sa.Text()),
        sa.Column("error_code", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ai_usage_ledger_organization_id", "ai_usage_ledger", ["organization_id"])
    op.create_index("ix_ai_usage_ledger_request_hash", "ai_usage_ledger", ["request_hash"])
    op.create_table(
        "ai_structure_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("structured_result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "request_hash", "model", name="uq_ai_structure_cache_request"),
    )


def downgrade() -> None:
    op.drop_table("ai_structure_cache")
    op.drop_index("ix_ai_usage_ledger_request_hash", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_organization_id", table_name="ai_usage_ledger")
    op.drop_table("ai_usage_ledger")
    postgresql.ENUM(name="ai_usage_status").drop(op.get_bind(), checkfirst=True)
