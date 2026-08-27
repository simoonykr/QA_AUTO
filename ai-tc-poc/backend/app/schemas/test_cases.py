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


class StructuredStep(BaseModel):
    id: str
    title: str
    note: str
    action: Literal["navigate", "click", "fill", "select", "press", "scroll", "wait", "upload", "assert"]
    confidence: float | None = Field(default=None, ge=0, le=1)


class AssertionSpec(BaseModel):
    type: Literal["url", "element", "text", "attribute", "count", "network", "visual_change"]
    operator: str
    expected: str
    timeoutMs: int = Field(ge=100, le=60_000)


class StructuredTestCase(BaseModel):
    versionId: str
    title: str
    preconditions: list[str]
    steps: list[StructuredStep]
    assertions: list[AssertionSpec]
    assumptions: list[str]
    confidence: float = Field(ge=0, le=1)
