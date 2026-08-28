"""point the local PoC environment at the worker demo target"""
from alembic import op

revision = "0002_worker_demo_target"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        UPDATE environments
        SET base_url = 'http\://demo-target',
            allowed_domains = '["demo-target"]'::jsonb
        WHERE id = '00000000-0000-0000-0000-000000000301'
    """)


def downgrade() -> None:
    op.execute(r"""
        UPDATE environments
        SET base_url = 'https\://example.test',
            allowed_domains = '["example.test"]'::jsonb
        WHERE id = '00000000-0000-0000-0000-000000000301'
    """)
