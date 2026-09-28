import hashlib, json
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID, uuid4
from sqlalchemy import select
from app.core.errors import DomainError
from app.db.models import Execution, ExecutionSuite, ExecutionSuiteItem, StructureBatch, StructureBatchItem, TestCaseVersion
from app.modules.ai.service import StructureService
from app.modules.executions.repository import ExecutionRuleError, SqlExecutionRepository
from app.modules.test_cases.execution_plan import ExecutionPlanError
from app.modules.test_cases.repository import SqlTestCaseRepository, TestCaseVersionRuleError
from app.schemas.batches import BatchApprovalResponse, BatchApprovalResult, ExecutionSuiteItemResponse, ExecutionSuiteResponse, StructureBatchItemResponse, StructureBatchResponse
from app.schemas.executions import CreateExecutionRequest
from app.schemas.test_cases import StructureRequest

class BatchRuleError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

class BatchRepository:
    def __init__(self, session, settings, actor_id, request_id):
        self.session, self.settings = session, settings
        self.organization_id, self.project_id = UUID(settings.default_organization_id), UUID(settings.default_project_id)
        self.actor_id, self.request_id = actor_id, request_id

    async def create_structure_batch(self, body, key):
        digest = self._digest(body)
        existing = await self.session.scalar(select(StructureBatch).where(StructureBatch.organization_id == self.organization_id, StructureBatch.idempotency_key == key))
        if existing:
            if existing.request_digest != digest: raise BatchRuleError("IDEMPOTENCY_CONFLICT", "같은 Idempotency-Key에 다른 요청 내용이 사용되었습니다.")
            return await self.structure_batch(existing.id)
        batch = StructureBatch(organization_id=self.organization_id, project_id=self.project_id, import_batch_id=body.importBatchId, idempotency_key=key, request_digest=digest, status="PROCESSING")
        self.session.add(batch); await self.session.flush()
        for source in body.items:
            self.session.add(StructureBatchItem(organization_id=self.organization_id, batch_id=batch.id, item_id=source.itemId, external_id=source.testCase.externalId, title=source.testCase.title, raw_text=source.testCase.rawText, status="QUEUED"))
        await self.session.commit()
        for source in body.items:
            item = await self.session.scalar(select(StructureBatchItem).where(StructureBatchItem.batch_id == batch.id, StructureBatchItem.item_id == source.itemId))
            item.status = "STRUCTURING"; await self.session.commit()
            try:
                request = StructureRequest(title=source.testCase.title, rawText=source.testCase.rawText)
                result = await StructureService(self.session, self.settings).structure(request, uuid4())
                saved = await self._tc().save_structured(request, result, source.testCase)
                version = await self.session.get(TestCaseVersion, UUID(saved.versionId)); item = await self.session.get(StructureBatchItem, item.id)
                item.version_id, item.test_case_id = version.id, version.test_case_id
                item.revision, item.status, item.completed_at = int((version.structured_spec or {}).get("planRevision") or 1), "REVIEW_REQUIRED", datetime.now(UTC)
                await self.session.commit()
            except (TestCaseVersionRuleError, DomainError) as exc:
                await self.session.rollback(); item = await self.session.scalar(select(StructureBatchItem).where(StructureBatchItem.batch_id == batch.id, StructureBatchItem.item_id == source.itemId))
                item.status = "CONFLICT" if getattr(exc, "code", "").endswith("CONFLICT") else "FAILED"
                item.error_code, item.error_message, item.completed_at = getattr(exc, "code", "STRUCTURE_FAILED"), getattr(exc, "message", "구조화하지 못했습니다."), datetime.now(UTC); await self.session.commit()
        rows = await self._items(batch.id); statuses = {x.status for x in rows}; batch = await self.session.get(StructureBatch, batch.id)
        batch.status = "COMPLETED" if statuses <= {"REVIEW_REQUIRED", "READY"} else "FAILED" if statuses <= {"FAILED", "CONFLICT"} else "PARTIAL_SUCCESS"
        batch.completed_at = datetime.now(UTC); await self.session.commit(); return await self.structure_batch(batch.id)

    async def structure_batch(self, batch_id):
        batch = await self.session.scalar(select(StructureBatch).where(StructureBatch.id == batch_id, StructureBatch.organization_id == self.organization_id, StructureBatch.project_id == self.project_id))
        if not batch: raise BatchRuleError("STRUCTURE_BATCH_NOT_FOUND", "구조화 Batch를 찾을 수 없습니다.")
        rows = await self._items(batch.id)
        return StructureBatchResponse(batchId=batch.id, status=batch.status, items=[StructureBatchItemResponse(itemId=x.item_id, externalId=x.external_id, testCaseId=x.test_case_id, versionId=x.version_id, revision=x.revision, status=x.status, errorCode=x.error_code, errorMessage=x.error_message) for x in rows], counts=dict(Counter(x.status for x in rows)), createdAt=batch.created_at, completedAt=batch.completed_at)

    async def approve(self, batch_id, body):
        batch = await self.session.scalar(select(StructureBatch).where(StructureBatch.id == batch_id, StructureBatch.organization_id == self.organization_id))
        if not batch: raise BatchRuleError("STRUCTURE_BATCH_NOT_FOUND", "구조화 Batch를 찾을 수 없습니다.")
        output=[]
        for req in body.items:
            item=await self.session.scalar(select(StructureBatchItem).where(StructureBatchItem.batch_id==batch_id,StructureBatchItem.version_id==req.versionId))
            if not item: output.append(BatchApprovalResult(versionId=req.versionId,expectedRevision=req.expectedRevision,status="EXCLUDED",errorCode="VERSION_NOT_IN_BATCH",reason="이 Batch의 Version이 아닙니다.")); continue
            version=await self.session.get(TestCaseVersion,req.versionId); actual=int((version.structured_spec or {}).get("planRevision") or 1) if version else None
            if actual!=req.expectedRevision: output.append(BatchApprovalResult(versionId=req.versionId,expectedRevision=req.expectedRevision,status="CONFLICT",errorCode="TC_VERSION_CONFLICT",reason=f"현재 revision은 {actual}입니다.")); continue
            try:
                await self._tc().approve(req.versionId); item=await self.session.get(StructureBatchItem,item.id); item.status="READY"; await self.session.commit(); output.append(BatchApprovalResult(versionId=req.versionId,expectedRevision=req.expectedRevision,status="READY"))
            except (TestCaseVersionRuleError,ExecutionPlanError) as exc:
                await self.session.rollback(); output.append(BatchApprovalResult(versionId=req.versionId,expectedRevision=req.expectedRevision,status="EXCLUDED",errorCode=getattr(exc,"code","PLAN_NOT_EXECUTABLE"),reason=getattr(exc,"message","실행할 수 없습니다.")))
        return BatchApprovalResponse(batchId=batch_id,items=output)

    async def create_suite(self, body, key):
        digest=self._digest(body); existing=await self.session.scalar(select(ExecutionSuite).where(ExecutionSuite.organization_id==self.organization_id,ExecutionSuite.idempotency_key==key))
        if existing:
            if existing.request_digest!=digest: raise BatchRuleError("IDEMPOTENCY_CONFLICT","같은 Idempotency-Key에 다른 요청 내용이 사용되었습니다.")
            return await self.suite(existing.id)
        suite=ExecutionSuite(organization_id=self.organization_id,project_id=self.project_id,environment_id=body.environmentId,idempotency_key=key,request_digest=digest,status="QUEUED",retry_policy=body.retryPolicy); self.session.add(suite); await self.session.commit()
        for index,version_id in enumerate(body.testCaseVersionIds):
            status,execution_id,code,reason="EXCLUDED",None,None,None
            try:
                response=await self._exec().create(CreateExecutionRequest(testCaseVersionId=str(version_id),environmentId=str(body.environmentId),browser=body.browser,accountId=str(body.accountId) if body.accountId else None,viewport=body.viewport,locale=body.locale,limits=body.limits,requireRiskApproval=body.requireRiskApproval),f"suite:{suite.id}:{index}:{version_id}"); status,execution_id=response.status,UUID(response.id)
            except (ExecutionRuleError,ExecutionPlanError) as exc: code,reason=getattr(exc,"code","PLAN_NOT_EXECUTABLE"),getattr(exc,"message","실행할 수 없습니다.")
            self.session.add(ExecutionSuiteItem(organization_id=self.organization_id,suite_id=suite.id,test_case_version_id=version_id,execution_id=execution_id,status=status,error_code=code,error_message=reason)); await self.session.commit()
        return await self.suite(suite.id)

    async def suite(self,suite_id):
        suite=await self.session.scalar(select(ExecutionSuite).where(ExecutionSuite.id==suite_id,ExecutionSuite.organization_id==self.organization_id,ExecutionSuite.project_id==self.project_id))
        if not suite: raise BatchRuleError("EXECUTION_SUITE_NOT_FOUND","Execution Suite를 찾을 수 없습니다.")
        rows=(await self.session.scalars(select(ExecutionSuiteItem).where(ExecutionSuiteItem.suite_id==suite.id))).all(); items=[]
        for row in rows:
            status=row.status
            if row.execution_id:
                execution=await self.session.get(Execution,row.execution_id)
                if execution: status=execution.status.value
            items.append(ExecutionSuiteItemResponse(testCaseVersionId=row.test_case_version_id,executionId=row.execution_id,status=status,errorCode=row.error_code,reason=row.error_message))
        statuses=[x.status for x in items]; terminal={"PASS","FAIL","BLOCKED","NEEDS_REVIEW","CANCELLED","SYSTEM_ERROR","EXCLUDED"}
        aggregate="PASS" if statuses and all(x=="PASS" for x in statuses) else "FAIL" if statuses and all(x in terminal for x in statuses) and any(x in {"FAIL","SYSTEM_ERROR"} for x in statuses) else "BLOCKED" if statuses and all(x in terminal for x in statuses) else "RUNNING" if "RUNNING" in statuses else "QUEUED"
        return ExecutionSuiteResponse(executionSuiteId=suite.id,status=aggregate,items=items,counts=dict(Counter(statuses)),createdAt=suite.created_at)

    async def _items(self,batch_id): return (await self.session.scalars(select(StructureBatchItem).where(StructureBatchItem.batch_id==batch_id).order_by(StructureBatchItem.created_at,StructureBatchItem.id))).all()
    def _tc(self): return SqlTestCaseRepository(self.session,self.organization_id,self.project_id,self.actor_id,self.request_id)
    def _exec(self): return SqlExecutionRepository(self.session,self.organization_id,self.project_id,self.actor_id,self.request_id)
    @staticmethod
    def _digest(body): return hashlib.sha256(json.dumps(body.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
