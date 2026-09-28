from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from app.db.models import ImportBatch, ImportBatchItem, TestCaseVersion
from app.schemas.test_cases import ImportBatchDetail, ImportBatchItemState, ImportedTestCase

class ImportBatchError(Exception):
    def __init__(self, code: str, message: str): self.code, self.message = code, message

class ImportBatchRepository:
    def __init__(self, session, organization_id: UUID, project_id: UUID):
        self.session, self.organization_id, self.project_id = session, organization_id, project_id

    async def create(self, imported: ImportedTestCase) -> None:
        batch = ImportBatch(id=imported.importBatchId, organization_id=self.organization_id, project_id=self.project_id,
            file_name=imported.fileName, file_format=imported.format, title=imported.title,
            warnings=imported.warnings, detected_count=imported.detectedTestCaseCount)
        self.session.add(batch)
        for position, source in enumerate(imported.testCases):
            self.session.add(ImportBatchItem(id=source.itemId, organization_id=self.organization_id, batch_id=batch.id,
                position=position, external_id=source.externalId, title=source.title, raw_text=source.rawText,
                payload=source.model_dump(mode="json", exclude_none=False), status="IMPORTED"))
        await self.session.commit()

    async def link_version(self, item_id: UUID | None, version_id: UUID, status: str) -> None:
        if not item_id: return
        item = await self.session.scalar(select(ImportBatchItem).where(
            ImportBatchItem.id == item_id, ImportBatchItem.organization_id == self.organization_id,
        ))
        if not item: return
        version = await self.session.get(TestCaseVersion, version_id)
        if not version: return
        item.test_case_id, item.latest_version_id = version.test_case_id, version.id
        item.latest_revision = int((version.structured_spec or {}).get("planRevision") or 1)
        item.status, item.updated_at = status, datetime.now(UTC)
        await self.session.commit()

    async def set_status(self, item_id: UUID | None, status: str) -> None:
        if not item_id: return
        item = await self.session.scalar(select(ImportBatchItem).where(
            ImportBatchItem.id == item_id, ImportBatchItem.organization_id == self.organization_id,
        ))
        if item:
            item.status, item.updated_at = status, datetime.now(UTC)
            await self.session.commit()

    async def get(self, batch_id: UUID) -> ImportBatchDetail:
        batch = await self.session.scalar(select(ImportBatch).where(
            ImportBatch.id == batch_id, ImportBatch.organization_id == self.organization_id,
            ImportBatch.project_id == self.project_id,
        ))
        if not batch: raise ImportBatchError("IMPORT_BATCH_NOT_FOUND", "가져오기 Batch를 찾을 수 없습니다.")
        rows = (await self.session.scalars(select(ImportBatchItem).where(
            ImportBatchItem.batch_id == batch.id, ImportBatchItem.organization_id == self.organization_id,
        ).order_by(ImportBatchItem.position))).all()
        states=[]
        for row in rows:
            status=row.status
            if row.latest_version_id:
                version=await self.session.get(TestCaseVersion,row.latest_version_id)
                if version:
                    status=version.status.value if hasattr(version.status,"value") else str(version.status)
                    row.latest_revision=int((version.structured_spec or {}).get("planRevision") or row.latest_revision or 1)
            states.append(ImportBatchItemState(itemId=row.id,testCase=row.payload,testCaseId=row.test_case_id,
                latestVersionId=row.latest_version_id,revision=row.latest_revision,status=status))
        return ImportBatchDetail(importBatchId=batch.id,fileName=batch.file_name,format=batch.file_format,title=batch.title,
            warnings=batch.warnings,detectedTestCaseCount=batch.detected_count,items=states,createdAt=batch.created_at.isoformat())
