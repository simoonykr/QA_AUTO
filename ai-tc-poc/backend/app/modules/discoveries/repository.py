from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, Environment, OutboxEvent, OutboxStatus, PageDiscovery, Project, TestCase, TestCaseVersion
from app.modules.test_cases.repository import SqlTestCaseRepository, TestCaseVersionRuleError
from app.schemas.test_cases import DiscoveryApplyRequest, DiscoveryResponse, DiscoveryStartRequest, DiscoveryStartResponse, ExecutionPlanResponse


class DiscoveryRuleError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message


class DiscoveryRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID, project_id: UUID, actor_id: UUID, request_id: UUID):
        self.session, self.organization_id, self.project_id = session, organization_id, project_id
        self.actor_id, self.request_id = actor_id, request_id

    async def start(self, version_id: UUID, body: DiscoveryStartRequest, ai_ready: bool) -> DiscoveryStartResponse:
        version = await self._version(version_id)
        if not version:
            raise DiscoveryRuleError("TC_VERSION_NOT_FOUND", "테스트 케이스 버전을 찾을 수 없습니다.")
        if version.status != "REVIEW_REQUIRED":
            raise DiscoveryRuleError("TC_VERSION_NOT_REVIEWABLE", "검토 대기 버전만 페이지 분석할 수 있습니다.")
        environment = await self.session.scalar(select(Environment).where(
            Environment.id == body.environmentId, Environment.organization_id == self.organization_id,
            Environment.project_id == self.project_id,
        ))
        if not environment:
            raise DiscoveryRuleError("ENVIRONMENT_NOT_FOUND", "실행 환경을 찾을 수 없습니다.")
        if body.maxAiCalls and not ai_ready:
            raise DiscoveryRuleError("AI_DISABLED", "AI가 비활성화되어 규칙 기반 페이지 분석만 사용할 수 있습니다.")
        discovery_id = uuid4()
        discovery = PageDiscovery(
            id=discovery_id,
            organization_id=self.organization_id, project_id=self.project_id,
            test_case_version_id=version_id, environment_id=body.environmentId,
            status="QUEUED", settings={"maxPages": body.maxPages, "maxAiCalls": body.maxAiCalls},
        )
        self.session.add(discovery)
        self.session.add(OutboxEvent(
            organization_id=self.organization_id, aggregate_type="page_discovery", aggregate_id=discovery_id,
            event_type="page_discovery.requested", payload={"discoveryId": str(discovery_id)}, status=OutboxStatus.PENDING,
            attempts=0, available_at=datetime.now(UTC),
        ))
        self.session.add(self._audit("page_discovery.requested", discovery_id, {"versionId": str(version_id), "maxAiCalls": body.maxAiCalls}))
        await self.session.commit()
        return DiscoveryStartResponse(discoveryId=discovery_id, status="QUEUED")

    async def get(self, version_id: UUID, discovery_id: UUID) -> DiscoveryResponse:
        item = await self._discovery(version_id, discovery_id)
        if not item:
            raise DiscoveryRuleError("DISCOVERY_NOT_FOUND", "페이지 분석을 찾을 수 없습니다.")
        result = item.result or {}
        return DiscoveryResponse(
            discoveryId=item.id, status=item.status, revision=int(result.get("revision") or 1),
            pages=result.get("pages") or [], steps=result.get("steps") or [], warnings=result.get("warnings") or [],
            executable=bool(result.get("executable")), errorCode=item.error_code,
        )

    async def apply(self, version_id: UUID, discovery_id: UUID, body: DiscoveryApplyRequest) -> ExecutionPlanResponse:
        item = await self._discovery(version_id, discovery_id, lock=True)
        if not item:
            raise DiscoveryRuleError("DISCOVERY_NOT_FOUND", "페이지 분석을 찾을 수 없습니다.")
        if item.status not in {"COMPLETED", "NEEDS_REVIEW"}:
            raise DiscoveryRuleError("DISCOVERY_NOT_APPLICABLE", "완료되거나 검토 대기 중인 분석만 적용할 수 있습니다.")
        version = await self._version(version_id, lock=True)
        if not version or version.status != "REVIEW_REQUIRED":
            raise DiscoveryRuleError("TC_VERSION_NOT_REVIEWABLE", "승인 전 버전에만 분석 결과를 적용할 수 있습니다.")
        result = item.result or {}
        selections = {selection.stepId: selection.candidateId for selection in body.selections}
        mapped = {step["stepId"]: step for step in result.get("steps") or []}
        spec = dict(version.structured_spec or {})
        steps = [dict(step) for step in spec.get("steps") or []]
        for step in steps:
            mapping = mapped.get(str(step.get("id")))
            if not mapping:
                continue
            candidate_id = selections.get(mapping["stepId"]) or mapping.get("selectedCandidateId")
            candidate = next((value for value in mapping.get("candidates") or [] if value.get("id") == candidate_id), None)
            if not candidate or candidate.get("matchCount") != 1 or not candidate.get("visible") or not candidate.get("enabled"):
                step["resolutionStatus"] = mapping.get("resolutionStatus") or "NOT_FOUND"
                continue
            step["selector"] = candidate["selector"]
            step["resolutionStatus"] = "RESOLVED"
        unresolved = [step for step in steps if step.get("action") in {"click", "fill", "assert"} and step.get("resolutionStatus") != "RESOLVED"]
        if unresolved:
            raise DiscoveryRuleError("DISCOVERY_SELECTION_REQUIRED", "해결되지 않은 단계의 후보를 선택하거나 다시 분석해 주세요.")
        spec["steps"] = steps
        spec["planRevision"] = int(spec.get("planRevision") or 1) + 1
        spec["pageDiscovery"] = {
            "discoveryId": str(item.id), "pages": result.get("pages") or [], "fingerprint": result.get("fingerprint"),
            "discoveredAt": item.ended_at.isoformat() if item.ended_at else None,
            "model": result.get("model"), "promptVersion": result.get("promptVersion"), "aiUsage": result.get("aiUsage"),
        }
        version.structured_spec = spec
        self.session.add(self._audit("page_discovery.applied", item.id, {"versionId": str(version.id), "planRevision": spec["planRevision"]}))
        await self.session.commit()
        plan_repository = SqlTestCaseRepository(self.session, self.organization_id, self.project_id, self.actor_id, self.request_id)
        return await plan_repository.execution_plan(version.id, item.environment_id)

    async def _version(self, version_id: UUID, lock: bool = False):
        statement = select(TestCaseVersion).join(TestCase, TestCase.id == TestCaseVersion.test_case_id).where(
            TestCaseVersion.id == version_id, TestCaseVersion.organization_id == self.organization_id,
            TestCase.organization_id == self.organization_id, TestCase.project_id == self.project_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def _discovery(self, version_id: UUID, discovery_id: UUID, lock: bool = False):
        statement = select(PageDiscovery).where(
            PageDiscovery.id == discovery_id, PageDiscovery.test_case_version_id == version_id,
            PageDiscovery.organization_id == self.organization_id, PageDiscovery.project_id == self.project_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    def _audit(self, action: str, resource_id: UUID, metadata: dict) -> AuditEvent:
        return AuditEvent(
            organization_id=self.organization_id, actor_id=self.actor_id, action=action,
            resource_type="page_discovery", resource_id=str(resource_id), request_id=self.request_id or uuid4(), metadata_json=metadata,
        )
