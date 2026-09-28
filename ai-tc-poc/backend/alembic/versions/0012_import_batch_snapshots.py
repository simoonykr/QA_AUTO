"""persist import batch item snapshots and latest versions"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_import_batch_snapshots"
down_revision = "0011_tc_batches_and_suites"
branch_labels = depends_on = None

def upgrade():
    op.create_table("import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False), sa.Column("file_format", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table("import_batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("external_id", sa.Text()),
        sa.Column("title", sa.Text(), nullable=False), sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_cases.id")),
        sa.Column("latest_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_case_versions.id")),
        sa.Column("latest_revision", sa.Integer()), sa.Column("status", sa.Text(), nullable=False, server_default="IMPORTED"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("batch_id", "position"),
    )

def downgrade():
    op.drop_table("import_batch_items")
    op.drop_table("import_batches")
