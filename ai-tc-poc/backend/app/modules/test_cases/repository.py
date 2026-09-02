from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, Project, TestCase, TestCaseVersion
from app.schemas.test_cases import StructureRequest, StructuredTestCase, TestCaseSummary, TestCaseVersionApproval


class TestCaseVersionRuleError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


class SqlTestCaseRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID, project_id: UUID | None = None, actor_id: UUID | None = None, request_id: UUID | None = None):
        self.session = session
        self.organization_id = organization_id
        self.project_id = project_id
        self.actor_id = actor_id
        self.request_id = request_id

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

    async def save_structured(self, body: StructureRequest, result: StructuredTestCase) -> StructuredTestCase:
        if not self.project_id:
            raise TestCaseVersionRuleError("PROJECT_NOT_FOUND", "프로젝트 정보를 찾을 수 없습니다.")
        project = await self.session.scalar(select(Project).where(
            Project.id == self.project_id,
            Project.organization_id == self.organization_id,
        ))
        if not project:
            raise TestCaseVersionRuleError("PROJECT_NOT_FOUND", "프로젝트 정보를 찾을 수 없습니다.")
        now = datetime.now(UTC)
        test_case_id = uuid4()
        version_id = UUID(result.versionId)
        test_case = TestCase(
            id=test_case_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            display_id=f"TC-{str(test_case_id)[:8].upper()}",
            title=body.title,
            group_name="Imported",
            created_at=now,
        )
        structured_spec = result.model_dump(
            mode="json",
            exclude={"versionId", "status", "title", "aiUsage"},
            exclude_none=True,
        )
        structured_spec["schemaVersion"] = 1
        version = TestCaseVersion(
            id=version_id,
            organization_id=self.organization_id,
            test_case_id=test_case_id,
            version_no=1,
            raw_text=body.rawText,
            structured_spec=structured_spec,
            status="REVIEW_REQUIRED",
            created_at=now,
        )
        self.session.add(test_case)
        self.session.add(version)
        self.session.add(self._audit("test_case_version.structured", version_id, {"status": "REVIEW_REQUIRED"}))
        await self.session.commit()
        return result.model_copy(update={"status": "REVIEW_REQUIRED"})

    async def approve(self, version_id: UUID) -> TestCaseVersionApproval:
        version = await self.session.scalar(
            select(TestCaseVersion)
            .join(TestCase, TestCase.id == TestCaseVersion.test_case_id)
            .where(
                TestCaseVersion.id == version_id,
                TestCaseVersion.organization_id == self.organization_id,
                TestCase.organization_id == self.organization_id,
                TestCase.project_id == self.project_id,
            )
            .with_for_update()
        )
        if not version:
            raise TestCaseVersionRuleError("TC_VERSION_NOT_FOUND", "테스트 케이스 버전을 찾을 수 없습니다.")
        if version.status == "READY":
            return TestCaseVersionApproval(versionId=str(version.id), status="READY")
        if version.status != "REVIEW_REQUIRED" or not version.structured_spec:
            raise TestCaseVersionRuleError("TC_VERSION_NOT_REVIEWABLE", "검토 대기 중인 구조화 버전만 승인할 수 있습니다.")
        version.status = "READY"
        self.session.add(self._audit("test_case_version.approved", version.id, {"status": "READY"}))
        await self.session.commit()
        return TestCaseVersionApproval(versionId=str(version.id), status="READY")

    def _audit(self, action: str, resource_id: UUID, metadata: dict) -> AuditEvent:
        return AuditEvent(
            organization_id=self.organization_id,
            actor_id=self.actor_id,
            action=action,
            resource_type="test_case_version",
            resource_id=str(resource_id),
            request_id=self.request_id or uuid4(),
            metadata_json=metadata,
        )
