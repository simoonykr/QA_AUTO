import type { ApiErrorBody, AuthenticatedUser, CreateExecutionRequest, EnvironmentSummary, Execution, ExecutionActionResponse, ExecutionDetails, ExecutionPlan, ExecutionPolicy, LoginResponse, StructuredTestCase, TestAccountSummary, TestCaseImportResponse, TestCaseSummary, TestCaseVersionApproval, TestCaseVersionStepPatch } from './types'
import { mockSteps, mockTestCases } from './mockData'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
export const apiConfig = { baseUrl: API_BASE_URL, mock: USE_MOCK_API }
export type HealthStatus = { status: string; environment: string }

export class ApiError extends Error {
  constructor(public body: ApiErrorBody, public status: number) { super(body.message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const url = /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`
    const response = await fetch(url, {
      ...init,
      credentials: 'include',
      headers: init?.body instanceof FormData ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (!response.ok) {
      const fallback: ApiErrorBody = { code: 'HTTP_ERROR', message: `요청에 실패했습니다. (${response.status})`, requestId: response.headers.get('x-request-id') ?? 'unknown', retryable: response.status >= 500 }
      const body = await response.json().catch(() => fallback) as Partial<ApiErrorBody>
      if (response.status === 401 && body.code === 'AUTH_REQUIRED') window.dispatchEvent(new Event('tracepilot:auth-required'))
      throw new ApiError({ ...fallback, ...body }, response.status)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError({ code: 'NETWORK_ERROR', message: 'API 서버에 연결할 수 없습니다.', requestId: 'client', retryable: true }, 0)
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export const api = {
  subscribeExecution(id: string, onDetails: (details: ExecutionDetails) => void, onError: () => void): () => void {
    if (USE_MOCK_API) return () => undefined
    const source = new EventSource(`${API_BASE_URL}/executions/${id}/events`, { withCredentials: true })
    const receive = (event: MessageEvent<string>) => {
      try { onDetails(JSON.parse(event.data) as ExecutionDetails) } catch { onError() }
    }
    source.addEventListener('execution.updated', receive as EventListener)
    source.addEventListener('execution.completed', receive as EventListener)
    source.onerror = onError
    return () => source.close()
  },

  artifactUrl(executionId: string, artifactId: string): string {
    return `${API_BASE_URL}/executions/${executionId}/artifacts/${artifactId}`
  },

  async login(username: string, password: string): Promise<LoginResponse> {
    if (USE_MOCK_API) return { user: { id: 'demo:qa', displayName: username || 'qa', role: 'OWNER', approvalStatus: 'APPROVED' }, expiresIn: 28800 }
    return request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  },

  async me(): Promise<AuthenticatedUser> {
    if (USE_MOCK_API) return { id: 'demo:qa', displayName: '김민준', role: 'OWNER', approvalStatus: 'APPROVED' }
    return request('/auth/me')
  },

  async logout(): Promise<void> {
    if (!USE_MOCK_API) await request('/auth/logout', { method: 'POST' })
  },

  async checkHealth(): Promise<HealthStatus> {
    if (USE_MOCK_API) return { status: 'ok', environment: 'mock' }
    const apiOrigin = /^https?:\/\//.test(API_BASE_URL)
      ? new URL(API_BASE_URL).origin
      : window.location.origin
    const healthUrl = `${apiOrigin}/health`
    return request(healthUrl)
  },

  async listTestCases(): Promise<TestCaseSummary[]> {
    if (!USE_MOCK_API) return request('/test-cases')
    await wait(180)
    return structuredClone(mockTestCases)
  },

  async importTestCase(file: File): Promise<TestCaseImportResponse> {
    if (!USE_MOCK_API) {
      const body = new FormData()
      body.append('file', file)
      return request('/test-cases/import', { method: 'POST', body })
    }
    const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!['txt','csv'].includes(extension)) throw new ApiError({ code: 'MOCK_BINARY_IMPORT_UNAVAILABLE', message: 'XLSX/DOCX 가져오기는 실제 백엔드가 연결된 통합 스테이징에서 사용할 수 있습니다.', requestId: 'mock', retryable: false }, 400)
    const rawText = await file.text()
    if (!rawText.trim()) throw new ApiError({ code: 'EMPTY_TEST_CASE_FILE', message: '파일에서 테스트 케이스 내용을 찾지 못했습니다.', requestId: 'mock', retryable: false }, 422)
    return { fileName: file.name, format: extension.toUpperCase(), title: file.name.replace(/\.[^.]+$/, ''), rawText, warnings: [] }
  },

  async listEnvironments(): Promise<EnvironmentSummary[]> {
    if (!USE_MOCK_API) return request('/environments')
    return [{ id: 'env-staging', name: 'Staging', baseUrl: 'https://staging.storefront.test', allowedDomains: ['staging.storefront.test'], defaultViewport: '1440x900' }]
  },

  async listTestAccounts(): Promise<TestAccountSummary[]> {
    if (!USE_MOCK_API) return request('/test-accounts')
    return [{ id: 'qa-runner-01', name: 'QA Runner 01', status: 'AVAILABLE' }]
  },

  async getExecutionPolicy(): Promise<ExecutionPolicy> {
    if (!USE_MOCK_API) return request('/execution-policies/current')
    return { allowedActions: ['navigate','click','fill','assert'], supportedBrowsers: ['Chromium'], maxTimeoutMinutes: 30, maxAiCalls: 0, maxRetries: 2, requireRiskApproval: true }
  },

  async structureTestCase(title: string, rawText: string): Promise<StructuredTestCase> {
    if (!USE_MOCK_API) return request('/test-case-versions/current/structure', { method: 'POST', body: JSON.stringify({ title, rawText }) })
    await wait(950)
    return {
      versionId: crypto.randomUUID(), status: 'REVIEW_REQUIRED', title,
      preconditions: ['Staging 환경과 미사용 이메일 계정이 준비되어 있다.'],
      steps: structuredClone(mockSteps),
      assertions: [
        { type: 'text', operator: 'contains', expected: '환영', timeoutMs: 10000 },
        { type: 'url', operator: 'matches', expected: '/dashboard', timeoutMs: 10000 },
      ],
      assumptions: rawText.includes('안전한 비밀번호') ? ['test_password 변수를 사용합니다.'] : [],
      confidence: 0.94,
      aiUsage: { source: 'RULE_BASED', callCount: 0, inputTokens: 0, outputTokens: 0, costUsd: '0', dailySpentUsd: '0', dailyBudgetUsd: '0' },
    }
  },

  async approveTestCaseVersion(versionId: string): Promise<TestCaseVersionApproval> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/approve`, { method: 'POST' })
    return { versionId, status: 'READY' }
  },

  async getExecutionPlan(versionId: string, environmentId: string): Promise<ExecutionPlan> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/execution-plan?environmentId=${encodeURIComponent(environmentId)}`)
    const structured = await this.structureTestCase('Mock execution plan', '페이지에 접속하고 결과를 확인한다.')
    return {
      versionId, status: 'READY', revision: 1, planHash: 'mock-plan-hash',
      environment: { id: environmentId, name: 'Staging', baseUrl: 'https://staging.storefront.test' },
      steps: structured.steps.map((step,index)=>({stepNo:index+1,id:step.id,title:step.title,action:step.action as 'navigate'|'fill'|'click'|'assert',url:step.url,selector:step.selector,value:step.value?'***':null,operator:step.operator,expected:step.expected,timeoutMs:step.timeoutMs??10000})),
      warnings: [], executable: true, source: structured.aiUsage.source,
    }
  },

  async updateTestCaseVersionStep(versionId: string, stepId: string, environmentId: string, patch: TestCaseVersionStepPatch): Promise<ExecutionPlan> {
    return request(`/test-case-versions/${versionId}/steps/${encodeURIComponent(stepId)}?environmentId=${encodeURIComponent(environmentId)}`, {
      method: 'PATCH', body: JSON.stringify(patch),
    })
  },

  async createExecution(input: CreateExecutionRequest): Promise<Execution> {
    if (!USE_MOCK_API) return request('/executions', { method: 'POST', body: JSON.stringify(input), headers: { 'Idempotency-Key': crypto.randomUUID() } })
    await wait(300)
    return { id: `EX-${Date.now()}`, status: 'QUEUED', testCaseVersionId: input.testCaseVersionId, queuedAt: new Date().toISOString() }
  },

  async getExecution(id: string): Promise<Execution> {
    if (!USE_MOCK_API) return request(`/executions/${id}`)
    return { id, status: 'RUNNING', testCaseVersionId: crypto.randomUUID(), queuedAt: new Date().toISOString(), startedAt: new Date().toISOString() }
  },

  async getExecutionDetails(id: string): Promise<ExecutionDetails> {
    if (!USE_MOCK_API) return request(`/executions/${id}/details`)
    const execution = await this.getExecution(id)
    return {
      execution: { ...execution, status: 'PASS', endedAt: new Date().toISOString() },
      result: { status: 'PASS', stepCount: 4, errorCode: null },
      errorCode: null,
      steps: [
        { id: 'step-1', stepNo: 1, status: 'PASS', action: { type: 'navigate', url: 'https://staging.storefront.test' } },
        { id: 'step-2', stepNo: 2, status: 'PASS', action: { type: 'fill', selector: '#email', value: '***' } },
        { id: 'step-3', stepNo: 3, status: 'PASS', action: { type: 'click', selector: '[data-testid=login]' } },
        { id: 'step-4', stepNo: 4, status: 'PASS', action: { type: 'assert', selector: '[data-testid=welcome]' }, assertion: { type: 'text', operator: 'contains', expected: '환영합니다' } },
      ],
      artifacts: [],
    }
  },

  async cancelExecution(id: string): Promise<ExecutionActionResponse> {
    if (!USE_MOCK_API) return request(`/executions/${id}/cancel`, { method: 'POST' })
    return { accepted: true, execution: { id, status: 'CANCEL_REQUESTED', testCaseVersionId: crypto.randomUUID(), queuedAt: new Date().toISOString() } }
  },

  async retryExecution(id: string): Promise<ExecutionActionResponse> {
    if (!USE_MOCK_API) return request(`/executions/${id}/retry`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
    return { accepted: true, execution: { id: `EX-${Date.now()}`, status: 'QUEUED', testCaseVersionId: crypto.randomUUID(), queuedAt: new Date().toISOString(), parentExecutionId: id } }
  },
}
