"""TC-independent page discovery and scenario drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0008_page_first"
down_revision = "0007_page_discoveries"
branch_labels = depends_on = None


def upgrade():
    op.alter_column("page_discoveries", "test_case_version_id", nullable=True)
    op.create_table("page_scenarios",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("discovery_id", pg.UUID(as_uuid=True), sa.ForeignKey("page_discoveries.id"), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    # Fail rather than silently delete TC-independent discoveries.
    op.alter_column("page_discoveries", "test_case_version_id", nullable=False)
    op.drop_table("page_scenarios")
