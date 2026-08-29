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
}

export interface StructuredTestCase {
  versionId: string
  title: string
  preconditions: string[]
  steps: StructuredStep[]
  assertions: Array<{ type: AssertionType; operator: string; expected: string; timeoutMs: number }>
  assumptions: string[]
  confidence: number
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
}

export interface ApiErrorBody {
  code: string
  message: string
  requestId: string
  retryable: boolean
  details?: Record<string, unknown>
}
