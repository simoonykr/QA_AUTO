from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TestCase, TestCaseVersion
from app.schemas.test_cases import TestCaseSummary


class SqlTestCaseRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session = session
        self.organization_id = organization_id

    async def list(self) -> list[TestCaseSummary]:
        latest_version = (
            select(TestCaseVersion.status)
            .where(TestCaseVersion.test_case_id == TestCase.id)
            .order_by(desc(TestCaseVersion.version_no))
            .limit(1)
            .scalar_subquery()
        )
        rows = (await self.session.execute(
            select(TestCase, latest_version.label("status"))
            .where(TestCase.organization_id == self.organization_id)
            .order_by(desc(TestCase.created_at))
        )).all()
        return [
            TestCaseSummary(
                id=item.display_id,
                title=item.title,
                group=item.group_name,
                status=status or "DRAFT",
                passRate=0,
                lastExecutedAt="실행 기록 없음",
            )
            for item, status in rows
        ]
