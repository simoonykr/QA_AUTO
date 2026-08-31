"""seed executable structured steps for the local worker demo"""
from alembic import op

revision = "0004_seed_worker_steps"
down_revision = "0003_fix_demo_target_port"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statement = r"""
        UPDATE test_case_versions
        SET structured_spec = '{
          "schemaVersion": 1,
          "steps": [
            {"id":"step-1","title":"페이지 진입","action":"navigate","timeoutMs":10000},
            {"id":"step-2","title":"테스트 이메일 입력","action":"fill","selector":"[data-testid=email]","value":"qa-runner@example.test","timeoutMs":10000},
            {"id":"step-3","title":"로그인 선택","action":"click","selector":"[data-testid=login]","timeoutMs":10000},
            {"id":"step-4","title":"환영 문구 확인","action":"assert","selector":"[data-testid=welcome]","operator":"contains","expected":"환영합니다","timeoutMs":10000}
          ]
        }'::jsonb
        WHERE id = '00000000-0000-0000-0000-000000000501'
          AND structured_spec IS NULL
    """
    # SQLAlchemy treats JSON's ``:10000`` fragments as bind parameters unless
    # literal colons are escaped before passing textual SQL to Alembic.
    op.execute(statement.replace(":", r"\:"))


def downgrade() -> None:
    op.execute("UPDATE test_case_versions SET structured_spec = NULL WHERE id = '00000000-0000-0000-0000-000000000501'")
