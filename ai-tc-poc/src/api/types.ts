export type TestCaseStatus = 'DRAFT' | 'REVIEW_REQUIRED' | 'READY' | 'ARCHIVED'
export type ExecutionStatus = 'QUEUED' | 'RUNNING' | 'WAITING_APPROVAL' | 'PASS' | 'FAIL' | 'BLOCKED' | 'CANCELLED'
export type ActionType = 'navigate' | 'click' | 'fill' | 'select' | 'press' | 'scroll' | 'wait' | 'upload'
export type AssertionType = 'url' | 'element' | 'text' | 'attribute' | 'count' | 'network' | 'visual_change'

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
}

export interface ApiErrorBody {
  code: string
  message: string
  requestId: string
  retryable: boolean
  details?: Record<string, unknown>
}
