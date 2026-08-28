"""initial TracePilot schema"""
from pathlib import Path
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    sql_path = Path(__file__).resolve().parents[2] / "db" / "001_initial.sql"
    sql = sql_path.read_text(encoding="utf-8").replace(":", r"\:")
    op.execute(sql)

def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS audit_events, outbox_events, artifacts, step_runs, executions,
          test_accounts, test_case_versions, test_cases, environments, projects, memberships,
          users, organizations CASCADE;
        DROP TYPE IF EXISTS outbox_status, execution_status, test_case_status;
    """)
