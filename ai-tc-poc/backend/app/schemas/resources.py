from typing import Literal

from pydantic import BaseModel, Field


class EnvironmentSummary(BaseModel):
    id: str
    name: str
    baseUrl: str
    allowedDomains: list[str]
    defaultViewport: str


class TestAccountSummary(BaseModel):
    id: str
    name: str
    status: str


class ExecutionPolicyResponse(BaseModel):
    allowedActions: list[Literal["navigate", "click", "fill", "assert"]]
    supportedBrowsers: list[Literal["Chromium"]]
    maxTimeoutMinutes: int = Field(ge=1)
    maxAiCalls: int = Field(ge=0)
    maxRetries: int = Field(ge=0)
    requireRiskApproval: bool
