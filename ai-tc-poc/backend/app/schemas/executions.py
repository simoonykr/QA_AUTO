from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


ExecutionStatusValue = Literal[
    "QUEUED", "PROVISIONING", "RUNNING", "WAITING_APPROVAL", "CANCEL_REQUESTED",
    "PASS", "FAIL", "BLOCKED", "NEEDS_REVIEW", "CANCELLED", "SYSTEM_ERROR",
]


class ExecutionLimits(BaseModel):
    timeoutMinutes: int = Field(ge=1, le=30)
    maxAiCalls: int = Field(ge=0, le=50)
    retryCount: int = Field(ge=0, le=2)


class CreateExecutionRequest(BaseModel):
    testCaseVersionId: str
    environmentId: str
    browser: Literal["Chromium", "Firefox", "WebKit"]
    accountId: str
    viewport: str
    locale: str
    limits: ExecutionLimits
    requireRiskApproval: bool = True


class ExecutionResponse(BaseModel):
    id: str
    status: ExecutionStatusValue
    testCaseVersionId: str
    queuedAt: datetime
    startedAt: datetime | None = None
    endedAt: datetime | None = None
    parentExecutionId: str | None = None


class ExecutionActionResponse(BaseModel):
    execution: ExecutionResponse
    accepted: bool = True


class StepRunResponse(BaseModel):
    id: str
    stepNo: int
    planStepId: str | None = None
    status: str
    action: dict[str, Any] | None = None
    assertion: dict[str, Any] | None = None
    errorCode: str | None = None
    startedAt: datetime | None = None
    endedAt: datetime | None = None


class ArtifactResponse(BaseModel):
    id: str
    stepRunId: str | None = None
    type: str
    objectKey: str
    sha256: str
    sizeBytes: int
    createdAt: datetime


class ExecutionPlanComparison(BaseModel):
    testCaseVersionId: str
    planHash: str
    planRevision: int
    environmentId: str
    baseUrl: str
    plannedStepCount: int
    actualStepCount: int
    stepCountMatches: bool


class ExecutionDetailsResponse(BaseModel):
    execution: ExecutionResponse
    result: dict[str, Any] | None = None
    errorCode: str | None = None
    steps: list[StepRunResponse]
    artifacts: list[ArtifactResponse]
    plan: ExecutionPlanComparison | None = None


class ExecutionListItem(BaseModel):
    id: str
    testCaseId: str
    testCaseTitle: str
    testCaseVersionId: str
    status: ExecutionStatusValue
    errorCode: str | None = None
    plannedStepCount: int = 0
    actualStepCount: int = 0
    queuedAt: datetime
    startedAt: datetime | None = None
    endedAt: datetime | None = None
    durationMs: int | None = None
    artifactCount: int = 0
    parentExecutionId: str | None = None


class ExecutionListResponse(BaseModel):
    items: list[ExecutionListItem]
    total: int = Field(ge=0)
