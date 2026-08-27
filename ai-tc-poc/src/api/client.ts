import type { ApiErrorBody, CreateExecutionRequest, Execution, StructuredTestCase, TestCaseSummary } from './types'
import { mockSteps, mockTestCases } from './mockData'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'

export class ApiError extends Error {
  constructor(public body: ApiErrorBody, public status: number) { super(body.message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) throw new ApiError(await response.json() as ApiErrorBody, response.status)
  return response.json() as Promise<T>
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export const api = {
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
}
