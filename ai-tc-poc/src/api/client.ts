import type { ApiErrorBody, CreateExecutionRequest, Execution, ExecutionActionResponse, StructuredTestCase, TestCaseSummary } from './types'
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
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (!response.ok) {
      const fallback: ApiErrorBody = { code: 'HTTP_ERROR', message: `요청에 실패했습니다. (${response.status})`, requestId: response.headers.get('x-request-id') ?? 'unknown', retryable: response.status >= 500 }
      const body = await response.json().catch(() => fallback) as Partial<ApiErrorBody>
      throw new ApiError({ ...fallback, ...body }, response.status)
    }
    return response.json() as Promise<T>
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError({ code: 'NETWORK_ERROR', message: 'API 서버에 연결할 수 없습니다.', requestId: 'client', retryable: true }, 0)
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export const api = {
  async checkHealth(): Promise<HealthStatus> {
    if (USE_MOCK_API) return { status: 'ok', environment: 'mock' }
    const healthUrl = /^https?:\/\//.test(API_BASE_URL)
      ? `${new URL(API_BASE_URL).origin}/health`
      : '/health'
    return request(healthUrl)
  },

  async listTestCases(): Promise<TestCaseSummary[]> {
    if (!USE_MOCK_API) return request('/test-cases')
    await wait(180)
    return structuredClone(mockTestCases)
  },

  async structureTestCase(title: string, rawText: string): Promise<StructuredTestCase> {
    if (!USE_MOCK_API) return request('/test-case-versions/current/structure', { method: 'POST', body: JSON.stringify({ title, rawText }) })
    await wait(950)
    return {
      versionId: 'tcv-new-v1', title,
      preconditions: ['Staging 환경과 미사용 이메일 계정이 준비되어 있다.'],
      steps: structuredClone(mockSteps),
      assertions: [
        { type: 'text', operator: 'contains', expected: '환영', timeoutMs: 10000 },
        { type: 'url', operator: 'matches', expected: '/dashboard', timeoutMs: 10000 },
      ],
      assumptions: rawText.includes('안전한 비밀번호') ? ['test_password 변수를 사용합니다.'] : [],
      confidence: 0.94,
    }
  },

  async createExecution(input: CreateExecutionRequest): Promise<Execution> {
    if (!USE_MOCK_API) return request('/executions', { method: 'POST', body: JSON.stringify(input), headers: { 'Idempotency-Key': crypto.randomUUID() } })
    await wait(300)
    return { id: `EX-${Date.now()}`, status: 'QUEUED', testCaseVersionId: input.testCaseVersionId, queuedAt: new Date().toISOString() }
  },

  async getExecution(id: string): Promise<Execution> {
    if (!USE_MOCK_API) return request(`/executions/${id}`)
    return { id, status: 'RUNNING', testCaseVersionId: 'tcv-new-v1', queuedAt: new Date().toISOString(), startedAt: new Date().toISOString() }
  },

  async cancelExecution(id: string): Promise<ExecutionActionResponse> {
    if (!USE_MOCK_API) return request(`/executions/${id}/cancel`, { method: 'POST' })
    return { accepted: true, execution: { id, status: 'CANCEL_REQUESTED', testCaseVersionId: 'tcv-new-v1', queuedAt: new Date().toISOString() } }
  },

  async retryExecution(id: string): Promise<ExecutionActionResponse> {
    if (!USE_MOCK_API) return request(`/executions/${id}/retry`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
    return { accepted: true, execution: { id: `EX-${Date.now()}`, status: 'QUEUED', testCaseVersionId: 'tcv-new-v1', queuedAt: new Date().toISOString(), parentExecutionId: id } }
  },
}
