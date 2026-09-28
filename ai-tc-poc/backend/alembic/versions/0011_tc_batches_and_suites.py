"""add independent TC structure batches and execution suites"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_tc_batches_and_suites"
down_revision = "0010_resource_domains"
branch_labels = depends_on = None


def upgrade():
    op.create_table("structure_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_table("structure_batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("structure_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.Text()), sa.Column("title", sa.Text(), nullable=False), sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_cases.id")),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_case_versions.id")),
        sa.Column("revision", sa.Integer()), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text()), sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("batch_id", "item_id"),
    )
    op.create_table("execution_suites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("environment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False), sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("retry_policy", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_table("execution_suite_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_suites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_case_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_case_versions.id"), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("executions.id")),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("error_code", sa.Text()), sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("suite_id", "test_case_version_id"),
    )


def downgrade():
    op.drop_table("execution_suite_items")
    op.drop_table("execution_suites")
    op.drop_table("structure_batch_items")
    op.drop_table("structure_batches")
