"""correct the local demo target to the nginx container port"""
from alembic import op

revision = "0003_fix_demo_target_port"
down_revision = "0002_worker_demo_target"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        UPDATE environments
        SET base_url = 'http\://demo-target'
        WHERE id = '00000000-0000-0000-0000-000000000301'
          AND base_url = 'http\://demo-target\:8080'
    """)


def downgrade() -> None:
    op.execute(r"""
        UPDATE environments
        SET base_url = 'http\://demo-target\:8080'
        WHERE id = '00000000-0000-0000-0000-000000000301'
          AND base_url = 'http\://demo-target'
    """)
