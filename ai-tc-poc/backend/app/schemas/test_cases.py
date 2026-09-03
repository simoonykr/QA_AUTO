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
    detectedTestCaseCount: int = Field(default=0, ge=0)
    testCases: list["ImportedTestCaseItem"] = Field(default_factory=list)


class ImportedTestCaseItem(BaseModel):
    externalId: str | None = None
    title: str
    depth1: str | None = None
    depth2: str | None = None
    depth3: str | None = None
    precondition: str | None = None
    steps: list[str] = Field(default_factory=list)
    expected: str | None = None
    sourceUrl: str | None = None
    rawText: str
    auditFields: dict[str, str] = Field(default_factory=dict)


class SelectedImportStructureRequest(BaseModel):
    testCase: ImportedTestCaseItem


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
    assertionType: Literal["url", "text", "element"] | None = None
    timeoutMs: int | None = Field(default=None, ge=100, le=60_000)
    targetDescription: str | None = None
    selectorHint: dict[str, str] = Field(default_factory=dict)
    resolutionStatus: Literal["UNRESOLVED", "RESOLVING", "RESOLVED", "AMBIGUOUS", "NOT_FOUND", "STALE"] | None = None
    actionIntent: str | None = None


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
    automationStatus: Literal["AUTOMATABLE", "PARTIALLY_AUTOMATABLE", "MANUAL_REVIEW_REQUIRED", "UNSUPPORTED"] = "MANUAL_REVIEW_REQUIRED"
    automationReason: str = "실행 가능성을 검토해야 합니다."


class TestCaseVersionApproval(BaseModel):
    versionId: str
    status: Literal["READY"]


class TestCaseVersionStepPatch(BaseModel):
    selector: str | None = None
    url: str | None = None
    operator: str | None = None
    expected: str | None = None
    value: str | None = None
    secretRef: str | None = None
    assertionType: Literal["url", "text", "element"] | None = None


class ExecutionPlanEnvironment(BaseModel):
    id: str
    name: str
    baseUrl: str


class ExecutionPlanStep(BaseModel):
    stepNo: int
    id: str
    title: str
    action: str
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    secretRef: str | None = None
    operator: str | None = None
    expected: str | None = None
    assertionType: Literal["url", "text", "element"] | None = None
    timeoutMs: int
    targetDescription: str | None = None
    selectorHint: dict[str, str] = Field(default_factory=dict)
    resolutionStatus: Literal["UNRESOLVED", "RESOLVING", "RESOLVED", "AMBIGUOUS", "NOT_FOUND", "STALE"] | None = None


class ExecutionPlanWarning(BaseModel):
    code: str
    message: str
    stepNo: int | None = None
    stepId: str | None = None
    missingFields: list[str] = Field(default_factory=list)


class ExecutionPlanResponse(BaseModel):
    versionId: str
    status: TestCaseStatus
    revision: int
    planHash: str | None = None
    environment: ExecutionPlanEnvironment
    steps: list[ExecutionPlanStep]
    warnings: list[ExecutionPlanWarning] = Field(default_factory=list)
    executable: bool
    source: Literal["AI", "CACHE", "RULE_BASED"]
    automationStatus: Literal["AUTOMATABLE", "PARTIALLY_AUTOMATABLE", "MANUAL_REVIEW_REQUIRED", "UNSUPPORTED"] = "MANUAL_REVIEW_REQUIRED"
    automationReason: str = "실행 가능성을 검토해야 합니다."


DiscoveryStatus = Literal["QUEUED", "PROVISIONING", "SCANNING", "MAPPING", "VALIDATING", "COMPLETED", "NEEDS_REVIEW", "FAILED", "CANCELLED"]


class DiscoveryStartRequest(BaseModel):
    environmentId: UUID
    maxPages: int = Field(default=1, ge=1, le=3)
    maxAiCalls: int = Field(default=0, ge=0, le=1)


class DiscoveryStartResponse(BaseModel):
    discoveryId: UUID
    status: Literal["QUEUED"]


class SelectorCandidate(BaseModel):
    id: str
    strategy: Literal["DATA_TESTID", "ROLE_NAME", "LABEL", "PLACEHOLDER", "ID_NAME", "LINK_URL", "VISIBLE_TEXT", "CSS"]
    selector: str
    matchCount: int = Field(ge=0)
    visible: bool
    enabled: bool
    confidence: float = Field(ge=0, le=1)


class DiscoveryStepResult(BaseModel):
    stepId: str
    targetDescription: str
    resolutionStatus: Literal["UNRESOLVED", "RESOLVING", "RESOLVED", "AMBIGUOUS", "NOT_FOUND", "STALE"]
    selectedCandidateId: str | None = None
    candidates: list[SelectorCandidate] = Field(default_factory=list)


class DiscoveryPage(BaseModel):
    url: str
    title: str
    fingerprint: str
    iframeCount: int = Field(default=0, ge=0)
    hasShadowDom: bool = False


class DiscoveryResponse(BaseModel):
    discoveryId: UUID
    status: DiscoveryStatus
    revision: int
    pages: list[DiscoveryPage] = Field(default_factory=list)
    steps: list[DiscoveryStepResult] = Field(default_factory=list)
    warnings: list[ExecutionPlanWarning] = Field(default_factory=list)
    executable: bool = False
    errorCode: str | None = None


class DiscoverySelection(BaseModel):
    stepId: str
    candidateId: str


class DiscoveryApplyRequest(BaseModel):
    selections: list[DiscoverySelection] = Field(default_factory=list)
