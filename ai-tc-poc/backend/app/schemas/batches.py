from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.executions import ExecutionLimits
from app.schemas.test_cases import ImportedTestCaseItem


class StructureBatchInput(BaseModel):
    itemId: UUID
    testCase: ImportedTestCaseItem


class CreateStructureBatchRequest(BaseModel):
    importBatchId: UUID | None = None
    items: list[StructureBatchInput] = Field(min_length=1, max_length=100)
    maxConcurrency: int = Field(default=3, ge=1, le=10)
    maxAiCallsPerCase: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [item.itemId for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("itemId는 Batch 안에서 중복될 수 없습니다.")
        external_ids = [item.testCase.externalId for item in self.items if item.testCase.externalId]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("동일 externalId는 하나의 Batch에서 중복 처리할 수 없습니다.")
        return self


StructureBatchItemStatus = Literal["QUEUED", "STRUCTURING", "REVIEW_REQUIRED", "READY", "FAILED", "CONFLICT", "CANCELLED"]


class StructureBatchItemResponse(BaseModel):
    itemId: UUID
    externalId: str | None = None
    testCaseId: UUID | None = None
    versionId: UUID | None = None
    revision: int | None = None
    status: StructureBatchItemStatus
    errorCode: str | None = None
    errorMessage: str | None = None


class StructureBatchResponse(BaseModel):
    batchId: UUID
    status: Literal["QUEUED", "PROCESSING", "COMPLETED", "PARTIAL_SUCCESS", "FAILED"]
    items: list[StructureBatchItemResponse]
    counts: dict[str, int]
    createdAt: datetime
    completedAt: datetime | None = None


class BatchApprovalItem(BaseModel):
    versionId: UUID
    expectedRevision: int = Field(ge=1)


class BatchApprovalRequest(BaseModel):
    items: list[BatchApprovalItem] = Field(min_length=1, max_length=100)


class BatchApprovalResult(BaseModel):
    versionId: UUID
    expectedRevision: int
    status: Literal["READY", "EXCLUDED", "CONFLICT", "FAILED"]
    errorCode: str | None = None
    reason: str | None = None


class BatchApprovalResponse(BaseModel):
    batchId: UUID
    items: list[BatchApprovalResult]


class CreateExecutionSuiteRequest(BaseModel):
    testCaseVersionIds: list[UUID] = Field(min_length=1, max_length=100)
    environmentId: UUID
    retryPolicy: Literal["MANUAL"] = "MANUAL"
    browser: Literal["Chromium", "Firefox", "WebKit"] = "Chromium"
    accountId: UUID | None = None
    viewport: str = "1440x900"
    locale: str = "ko-KR"
    limits: ExecutionLimits = Field(default_factory=lambda: ExecutionLimits(timeoutMinutes=10, maxAiCalls=0, retryCount=0))
    requireRiskApproval: bool = True

    @model_validator(mode="after")
    def unique_versions(self):
        if len(self.testCaseVersionIds) != len(set(self.testCaseVersionIds)):
            raise ValueError("testCaseVersionIds는 중복될 수 없습니다.")
        return self


class ExecutionSuiteItemResponse(BaseModel):
    testCaseVersionId: UUID
    executionId: UUID | None = None
    status: str
    errorCode: str | None = None
    reason: str | None = None


class ExecutionSuiteResponse(BaseModel):
    executionSuiteId: UUID
    status: str
    items: list[ExecutionSuiteItemResponse]
    counts: dict[str, int]
    createdAt: datetime
