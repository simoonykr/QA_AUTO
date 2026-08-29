from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Environment, TestAccount
from app.schemas.resources import EnvironmentSummary, TestAccountSummary


class SqlResourceRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID, project_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.project_id = project_id

    async def environments(self) -> list[EnvironmentSummary]:
        rows = (await self.session.scalars(
            select(Environment)
            .where(
                Environment.organization_id == self.organization_id,
                Environment.project_id == self.project_id,
            )
            .order_by(Environment.name)
        )).all()
        return [EnvironmentSummary(
            id=str(item.id),
            name=item.name,
            baseUrl=item.base_url,
            allowedDomains=item.allowed_domains,
            defaultViewport=f"{item.viewport.get('width', 1440)}x{item.viewport.get('height', 900)}",
        ) for item in rows]

    async def test_accounts(self) -> list[TestAccountSummary]:
        rows = (await self.session.scalars(
            select(TestAccount)
            .where(
                TestAccount.organization_id == self.organization_id,
                TestAccount.project_id == self.project_id,
            )
            .order_by(TestAccount.name)
        )).all()
        return [TestAccountSummary(id=str(item.id), name=item.name, status=item.status) for item in rows]
