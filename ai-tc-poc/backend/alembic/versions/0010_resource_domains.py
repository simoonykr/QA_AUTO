"""separate navigation and static resource domain allowlists"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_resource_domains"
down_revision = "0009_allow_kakaogames_staging"
branch_labels = depends_on = None


def upgrade():
    op.add_column("environments", sa.Column(
        "resource_domains", postgresql.JSONB(astext_type=sa.Text()),
        nullable=False, server_default=sa.text("'[]'::jsonb"),
    ))
    op.execute("""
        UPDATE environments
        SET resource_domains = '["cdn.jsdelivr.net"]'::jsonb
        WHERE id = '00000000-0000-0000-0000-000000000301' AND name = 'Staging'
    """)


def downgrade():
    op.drop_column("environments", "resource_domains")
