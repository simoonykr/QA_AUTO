"""add page discoveries"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_page_discoveries"
down_revision = "0006_ai_usage_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_discoveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("test_case_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_case_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("environment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="QUEUED"),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error_code", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_page_discoveries_organization_id", "page_discoveries", ["organization_id"])
    op.create_index("ix_page_discoveries_test_case_version_id", "page_discoveries", ["test_case_version_id"])


def downgrade() -> None:
    op.drop_index("ix_page_discoveries_test_case_version_id", table_name="page_discoveries")
    op.drop_index("ix_page_discoveries_organization_id", table_name="page_discoveries")
    op.drop_table("page_discoveries")
