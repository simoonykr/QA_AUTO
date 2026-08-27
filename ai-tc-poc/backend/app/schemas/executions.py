from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


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
    status: Literal["QUEUED", "RUNNING", "WAITING_APPROVAL", "PASS", "FAIL", "BLOCKED", "CANCELLED"]
    testCaseVersionId: str
    queuedAt: datetime
