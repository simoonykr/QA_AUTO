from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


TestCaseStatus = Literal["DRAFT", "REVIEW_REQUIRED", "READY", "ARCHIVED"]


class TestCaseSummary(BaseModel):
    id: str
    title: str
    group: str
    status: TestCaseStatus
    passRate: int = Field(ge=0, le=100)
    lastExecutedAt: str


class StructureRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    rawText: str = Field(min_length=10, max_length=50_000)


class ImportedTestCase(BaseModel):
    fileName: str
    format: Literal["txt", "csv", "xlsx", "docx"]
    title: str
    rawText: str
    warnings: list[str] = Field(default_factory=list)


class StructuredStep(BaseModel):
    id: str
    title: str
    note: str
    action: Literal["navigate", "click", "fill", "select", "press", "scroll", "wait", "upload", "assert"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    operator: str | None = None
    expected: str | None = None
    timeoutMs: int | None = Field(default=None, ge=100, le=60_000)


class AssertionSpec(BaseModel):
    type: Literal["url", "element", "text", "attribute", "count", "network", "visual_change"]
    operator: str
    expected: str
    timeoutMs: int = Field(ge=100, le=60_000)


class AiUsageSummary(BaseModel):
    source: Literal["AI", "CACHE", "RULE_BASED"]
    callCount: int = Field(ge=0, le=1)
    inputTokens: int = Field(ge=0)
    outputTokens: int = Field(ge=0)
    costUsd: str
    dailySpentUsd: str
    dailyBudgetUsd: str


class StructuredTestCase(BaseModel):
    versionId: str
    status: Literal["REVIEW_REQUIRED", "READY"] = "REVIEW_REQUIRED"
    title: str
    preconditions: list[str]
    steps: list[StructuredStep]
    assertions: list[AssertionSpec]
    assumptions: list[str]
    confidence: float = Field(ge=0, le=1)
    aiUsage: AiUsageSummary


class TestCaseVersionApproval(BaseModel):
    versionId: str
    status: Literal["READY"]
