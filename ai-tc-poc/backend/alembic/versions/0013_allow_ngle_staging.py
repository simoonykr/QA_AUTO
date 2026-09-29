"""allow ngle public site in the temporary staging environment"""

from alembic import op


revision = "0013_allow_ngle_staging"
down_revision = "0012_import_batch_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE environments
        SET allowed_domains = allowed_domains || '["ngle.co.kr", "www.ngle.co.kr"]'::jsonb,
            resource_domains = resource_domains || '["ngle.co.kr", "www.ngle.co.kr"]'::jsonb
        WHERE id = '00000000-0000-0000-0000-000000000301'
          AND NOT (allowed_domains ? 'ngle.co.kr')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE environments
        SET allowed_domains = (allowed_domains - 'ngle.co.kr') - 'www.ngle.co.kr',
            resource_domains = (resource_domains - 'ngle.co.kr') - 'www.ngle.co.kr'
        WHERE id = '00000000-0000-0000-0000-000000000301'
    """)
