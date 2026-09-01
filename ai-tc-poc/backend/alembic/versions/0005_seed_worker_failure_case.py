"""seed a reproducible assertion failure case for the local worker demo"""

from alembic import op


revision = "0005_seed_worker_failure"
down_revision = "0004_seed_worker_steps"
branch_labels = None
depends_on = None


FAILURE_VERSION_ID = "00000000-0000-0000-0000-000000000502"
TEST_CASE_ID = "00000000-0000-0000-0000-000000000401"
ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    statement = rf"""
        INSERT INTO test_case_versions (
          id, organization_id, test_case_id, version_no, raw_text, structured_spec, status
        ) VALUES (
          '{FAILURE_VERSION_ID}',
          '{ORGANIZATION_ID}',
          '{TEST_CASE_ID}',
          2,
          '자동화 실패 증적 검증용 assertion mismatch TC',
          '{{
            "schemaVersion": 1,
            "steps": [
              {{"id":"step-1","title":"페이지 진입","action":"navigate","timeoutMs":10000}},
              {{"id":"step-2","title":"테스트 이메일 입력","action":"fill","selector":"[data-testid=email]","value":"qa-runner@example.test","timeoutMs":10000}},
              {{"id":"step-3","title":"로그인 선택","action":"click","selector":"[data-testid=login]","timeoutMs":10000}},
              {{"id":"step-4","title":"잘못된 환영 문구 확인","action":"assert","selector":"[data-testid=welcome]","operator":"contains","expected":"의도적으로 존재하지 않는 문구","timeoutMs":1000}}
            ]
          }}'::jsonb,
          'READY'
        )
        ON CONFLICT (id) DO UPDATE SET
          raw_text = EXCLUDED.raw_text,
          structured_spec = EXCLUDED.structured_spec,
          status = EXCLUDED.status
    """
    op.execute(statement.replace(":", r"\:"))


def downgrade() -> None:
    op.execute(f"DELETE FROM test_case_versions WHERE id = '{FAILURE_VERSION_ID}'")
