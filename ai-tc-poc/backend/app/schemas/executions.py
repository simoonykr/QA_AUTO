from datetime import datetime
from typing import Literal
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
