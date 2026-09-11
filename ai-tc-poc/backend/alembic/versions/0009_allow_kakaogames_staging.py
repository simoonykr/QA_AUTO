"""allow the requested KakaoGames target in the demo Staging environment"""
from alembic import op

revision = "0009_allow_kakaogames_staging"
down_revision = "0008_page_first"
branch_labels = depends_on = None


def upgrade():
    op.execute("""
        UPDATE environments
        SET allowed_domains = CASE
            WHEN allowed_domains ? 'kakaogames.com' THEN allowed_domains
            ELSE allowed_domains || '[\"kakaogames.com\"]'::jsonb
        END
        WHERE id = '00000000-0000-0000-0000-000000000301' AND name = 'Staging'
    """)


def downgrade():
    op.execute("""
        UPDATE environments
        SET allowed_domains = allowed_domains - 'kakaogames.com'
        WHERE id = '00000000-0000-0000-0000-000000000301' AND name = 'Staging'
    """)
