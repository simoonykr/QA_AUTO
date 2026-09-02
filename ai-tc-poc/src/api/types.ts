export type TestCaseStatus = 'DRAFT' | 'REVIEW_REQUIRED' | 'READY' | 'ARCHIVED'
export type ExecutionStatus = 'QUEUED' | 'PROVISIONING' | 'RUNNING' | 'WAITING_APPROVAL' | 'CANCEL_REQUESTED' | 'PASS' | 'FAIL' | 'BLOCKED' | 'NEEDS_REVIEW' | 'CANCELLED' | 'SYSTEM_ERROR'
export type ActionType = 'navigate' | 'click' | 'fill' | 'select' | 'press' | 'scroll' | 'wait' | 'upload'
export type AssertionType = 'url' | 'element' | 'text' | 'attribute' | 'count' | 'network' | 'visual_change'
export type UserRole = 'OWNER' | 'QA' | 'VIEWER'
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface AuthenticatedUser {
  id: string
  displayName: string
  role: UserRole
  approvalStatus: ApprovalStatus
}

export interface LoginResponse { user: AuthenticatedUser; expiresIn: number }

export interface EnvironmentSummary {
  id: string
  name: string
  baseUrl: string
  allowedDomains: string[]
  defaultViewport: string
}

export interface TestAccountSummary { id: string; name: string; status: string }

export interface ExecutionPolicy {
  allowedActions: Array<'navigate' | 'click' | 'fill' | 'assert'>
  supportedBrowsers: Array<'Chromium'>
  maxTimeoutMinutes: number
  maxAiCalls: number
  maxRetries: number
  requireRiskApproval: boolean
}

export interface TestCaseSummary {
  id: string
  title: string
  group: string
  status: TestCaseStatus
  passRate: number
  lastExecutedAt: string
}

export interface StructuredStep {
  id: string
  title: string
  note: string
  action: ActionType | 'assert'
  confidence?: number
  url?: string | null
  selector?: string | null
  value?: string | null
  operator?: string | null
  expected?: string | null
  timeoutMs?: number | null
}

export interface StructuredTestCase {
  versionId: string
  status: 'REVIEW_REQUIRED' | 'READY'
  title: string
  preconditions: string[]
  steps: StructuredStep[]
  assertions: Array<{ type: AssertionType; operator: string; expected: string; timeoutMs: number }>
  assumptions: string[]
  confidence: number
  aiUsage: {
    source: 'AI' | 'CACHE' | 'RULE_BASED'
    callCount: 0 | 1
    inputTokens: number
    outputTokens: number
    costUsd: string
    dailySpentUsd: string
    dailyBudgetUsd: string
  }
}

export interface TestCaseVersionApproval { versionId: string; status: 'READY' }

export interface ExecutionPlanStep {
  stepNo: number
  id: string
  title: string
  action: string
  url?: string | null
  selector?: string | null
  value?: string | null
  secretRef?: string | null
  operator?: string | null
  expected?: string | null
  timeoutMs: number
}

export interface ExecutionPlan {
  versionId: string
  status: TestCaseStatus
  revision: number
  planHash?: string | null
  environment: { id: string; name: string; baseUrl: string }
  steps: ExecutionPlanStep[]
  warnings: Array<{ code: string; message: string; stepNo?: number | null }>
  executable: boolean
  source: 'AI' | 'CACHE' | 'RULE_BASED'
}

export interface TestCaseImportResponse {
  fileName: string
  format: string
  title: string
  rawText: string
  warnings: string[]
}

export interface CreateExecutionRequest {
  testCaseVersionId: string
  environmentId: string
  browser: 'Chromium' | 'Firefox' | 'WebKit'
  accountId: string
  viewport: string
  locale: string
  limits: { timeoutMinutes: number; maxAiCalls: number; retryCount: number }
  requireRiskApproval: boolean
}

export interface Execution {
  id: string
  status: ExecutionStatus
  testCaseVersionId: string
  queuedAt: string
  startedAt?: string | null
  endedAt?: string | null
  parentExecutionId?: string | null
}

export interface ExecutionActionResponse { execution: Execution; accepted: boolean }

export interface ExecutionStepRun {
  id: string
  stepNo: number
  planStepId?: string | null
  status: string
  action?: Record<string, unknown> | null
  assertion?: Record<string, unknown> | null
  errorCode?: string | null
  startedAt?: string | null
  endedAt?: string | null
}

export interface ExecutionArtifact {
  id: string
  stepRunId?: string | null
  type: string
  objectKey: string
  sha256: string
  sizeBytes: number
  createdAt: string
}

export interface ExecutionDetails {
  execution: Execution
  result?: Record<string, unknown> | null
  errorCode?: string | null
  steps: ExecutionStepRun[]
  artifacts: ExecutionArtifact[]
  plan?: {
    testCaseVersionId: string
    planHash: string
    planRevision: number
    environmentId: string
    baseUrl: string
    plannedStepCount: number
    actualStepCount: number
    stepCountMatches: boolean
  } | null
}

export interface ApiErrorBody {
  code: string
  message: string
  requestId: string
  retryable: boolean
  details?: Record<string, unknown>
}
