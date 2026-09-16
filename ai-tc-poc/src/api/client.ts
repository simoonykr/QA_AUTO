import type { ApiErrorBody, AuthenticatedUser, CreateExecutionRequest, DiscoverySelection, DiscoveryStartResponse, EnvironmentSummary, Execution, ExecutionActionResponse, ExecutionDetails, ExecutionHistoryResponse, ExecutionPlan, ExecutionPolicy, ImportedTestCaseItem, LoginResponse, PageDiscovery, PageFirstDiscovery, PageFirstStartRequest, PageScenarioDraft, ScenarioApproveRequest, ScenarioCompareRequest, ScenarioComparison, ScenarioReviewRequest, StructuredTestCase, TestAccountSummary, TestCaseImportResponse, TestCaseSummary, TestCaseVersionApproval, TestCaseVersionStepPatch } from './types'
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
      signal: init?.signal ?? AbortSignal.timeout(30000),
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
const mockExecutionPlans = new Map<string,ExecutionPlan>()
const mockPlanKey = (versionId:string,environmentId:string) => `${versionId}:${environmentId}`
const mockDiscoveries = new Map<string,{polls:number;value:PageDiscovery}>()
const mockPageFirstDiscoveries = new Map<string,{polls:number;value:PageFirstDiscovery}>()
const mockPageScenarios = new Map<string,PageScenarioDraft>()

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
    return { fileName: file.name, format: extension.toUpperCase(), title: file.name.replace(/\.[^.]+$/, ''), rawText, warnings: [], detectedTestCaseCount:0, testCases:[] }
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
      automationStatus:'AUTOMATABLE', automationReason:'페이지 분석 후 자동 실행할 수 있습니다.',
    }
  },

  async structureImportedTestCase(testCase:ImportedTestCaseItem):Promise<StructuredTestCase> {
    if (!USE_MOCK_API) return request('/test-case-versions/imported/structure',{method:'POST',body:JSON.stringify({testCase})})
    return this.structureTestCase(testCase.title,testCase.rawText)
  },

  async listExecutions(status?:string,testCaseId?:string,limit=50,offset=0):Promise<ExecutionHistoryResponse> {
    const query=new URLSearchParams({limit:String(limit),offset:String(offset)});if(status)query.set('status',status);if(testCaseId)query.set('testCaseId',testCaseId)
    if (!USE_MOCK_API) return request(`/executions${query.size?`?${query}`:''}`)
    return {items:[],total:0}
  },

  async approveTestCaseVersion(versionId: string): Promise<TestCaseVersionApproval> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/approve`, { method: 'POST' })
    return { versionId, status: 'READY' }
  },

  async getExecutionPlan(versionId: string, environmentId: string): Promise<ExecutionPlan> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/execution-plan?environmentId=${encodeURIComponent(environmentId)}`)
    const key=mockPlanKey(versionId,environmentId)
    const existing=mockExecutionPlans.get(key)
    if (existing) return structuredClone(existing)
    const plan:ExecutionPlan={
      versionId, status: 'READY', revision: 1, planHash: 'mock-plan-hash',
      environment: { id: environmentId, name: 'Staging', baseUrl: 'https://staging.storefront.test' },
      steps: mockSteps.map((step,index)=>({stepNo:index+1,id:step.id,title:step.title,action:step.action,url:step.url,selector:step.selector,value:step.value?'***':null,operator:step.operator,expected:step.expected,timeoutMs:step.timeoutMs??10000})),
      warnings: [], executable: true, source: 'RULE_BASED', automationStatus:'AUTOMATABLE', automationReason:'페이지 분석 후 자동 실행할 수 있습니다.',
    }
    mockExecutionPlans.set(key,plan)
    return structuredClone(plan)
  },

  async updateTestCaseVersionStep(versionId: string, stepId: string, environmentId: string, patch: TestCaseVersionStepPatch): Promise<ExecutionPlan> {
    if (USE_MOCK_API) {
      const plan=await this.getExecutionPlan(versionId,environmentId)
      const updated={...plan,revision:plan.revision+1,planHash:`mock-plan-${Date.now()}`,steps:plan.steps.map(step=>step.id===stepId?{...step,...patch}:step),warnings:[],executable:true}
      mockExecutionPlans.set(mockPlanKey(versionId,environmentId),updated)
      return structuredClone(updated)
    }
    return request(`/test-case-versions/${versionId}/steps/${encodeURIComponent(stepId)}?environmentId=${encodeURIComponent(environmentId)}`, {
      method: 'PATCH', body: JSON.stringify(patch),
    })
  },

  async deleteTestCaseVersionStep(versionId: string, stepId: string, environmentId: string): Promise<ExecutionPlan> {
    if (USE_MOCK_API) {
      const plan=await this.getExecutionPlan(versionId,environmentId)
      const steps=plan.steps.filter(step=>step.id!==stepId).map((step,index)=>({...step,stepNo:index+1}))
      const updated:ExecutionPlan={...plan,revision:plan.revision+1,planHash:steps.length?`mock-plan-${Date.now()}`:null,steps,warnings:steps.length?[]:[{code:'EXECUTION_PLAN_INVALID',message:'실행 단계가 비어 있습니다.',missingFields:[]}],executable:steps.length>0}
      mockExecutionPlans.set(mockPlanKey(versionId,environmentId),updated)
      return structuredClone(updated)
    }
    return request(`/test-case-versions/${versionId}/steps/${encodeURIComponent(stepId)}?environmentId=${encodeURIComponent(environmentId)}`, { method:'DELETE' })
  },

  async startPageDiscovery(versionId:string,environmentId:string):Promise<DiscoveryStartResponse> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/discover`, {method:'POST',body:JSON.stringify({environmentId,maxPages:1,maxAiCalls:0})})
    const discoveryId=crypto.randomUUID()
    const plan=await this.getExecutionPlan(versionId,environmentId)
    const steps=plan.steps.filter(step=>['click','fill','assert'].includes(step.action)&&step.assertionType!=='url').map((step,index)=>({
      stepId:step.id,targetDescription:step.targetDescription??step.title,resolutionStatus:'RESOLVED' as const,selectedCandidateId:`candidate-${index+1}`,
      candidates:[{id:`candidate-${index+1}`,strategy:'ROLE_NAME' as const,selector:step.selector??`[data-testid="${step.id}"]`,matchCount:1,visible:true,enabled:true,confidence:.94}],
    }))
    mockDiscoveries.set(discoveryId,{polls:0,value:{discoveryId,status:'QUEUED',revision:plan.revision,pages:[],steps:[],warnings:[],executable:false,errorCode:null}})
    window.setTimeout(()=>{const item=mockDiscoveries.get(discoveryId);if(item)item.value={...item.value,status:'COMPLETED',pages:[{url:plan.environment.baseUrl,title:'Mock 대상 페이지',fingerprint:'mock-page-fingerprint',iframeCount:0,hasShadowDom:false}],steps,executable:true}},900)
    return {discoveryId,status:'QUEUED'}
  },

  async getPageDiscovery(versionId:string,discoveryId:string):Promise<PageDiscovery> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/discoveries/${discoveryId}`)
    const item=mockDiscoveries.get(discoveryId)
    if (!item) throw new ApiError({code:'DISCOVERY_NOT_FOUND',message:'페이지 분석을 찾을 수 없습니다.',requestId:'mock',retryable:false},404)
    item.polls+=1
    if (item.value.status==='QUEUED'&&item.polls>1) item.value={...item.value,status:'SCANNING'}
    return structuredClone(item.value)
  },

  async applyPageDiscovery(versionId:string,discoveryId:string,selections:DiscoverySelection[],environmentId:string):Promise<ExecutionPlan> {
    if (!USE_MOCK_API) return request(`/test-case-versions/${versionId}/discoveries/${discoveryId}/apply`, {method:'POST',body:JSON.stringify({selections})})
    const discovery=await this.getPageDiscovery(versionId,discoveryId)
    const plan=await this.getExecutionPlan(versionId,environmentId)
    const selected=new Map(selections.map(item=>[item.stepId,item.candidateId]))
    const steps=plan.steps.map(step=>{const result=discovery.steps.find(item=>item.stepId===step.id);const candidate=result?.candidates.find(item=>item.id===(selected.get(step.id)??result.selectedCandidateId));return candidate?{...step,selector:candidate.selector,resolutionStatus:'RESOLVED' as const}:step})
    const updated={...plan,revision:plan.revision+1,planHash:`mock-discovery-${Date.now()}`,steps,warnings:[],executable:true}
    mockExecutionPlans.set(mockPlanKey(versionId,environmentId),updated)
    return structuredClone(updated)
  },

  async startPageFirstDiscovery(input:PageFirstStartRequest):Promise<{discoveryId:string;status:'QUEUED'}> {
    if (!USE_MOCK_API) return request('/page-discoveries',{method:'POST',body:JSON.stringify({...input,maxPages:input.maxPages??1,maxAiCalls:0})})
    const discoveryId=crypto.randomUUID()
    mockPageFirstDiscoveries.set(discoveryId,{polls:0,value:{discoveryId,status:'QUEUED',errorCode:null,pages:[{url:input.startUrl,title:'',fingerprint:'',depth:0,elementCount:0}],elements:[],areas:[],interactions:[],stateChanges:[],warnings:[],scope:{includeInternalLinks:input.includeInternalLinks??false,maxDepth:input.maxDepth??0,maxPages:input.maxPages??1},aiUsage:{source:'RULE_BASED',callCount:0}}})
    return {discoveryId,status:'QUEUED'}
  },

  async getPageFirstDiscovery(discoveryId:string):Promise<PageFirstDiscovery> {
    if (!USE_MOCK_API) return request(`/page-discoveries/${discoveryId}`)
    const item=mockPageFirstDiscoveries.get(discoveryId)
    if (!item) throw new ApiError({code:'DISCOVERY_NOT_FOUND',message:'페이지 분석을 찾을 수 없습니다.',requestId:'mock',retryable:false},404)
    item.polls+=1
    if(item.polls===2)item.value={...item.value,status:'SCANNING'}
    if(item.polls>=3)item.value={...item.value,status:'COMPLETED',pages:[{url:item.value.pages[0]?.url??'https://staging.storefront.test',title:'Storefront',fingerprint:'mock-page-first-fingerprint',depth:0,elementCount:2}],elements:[
      {elementId:'element-1',selector:'[data-testid="game-filter-pc"]',name:'#PC 필터',matchCount:1,visible:true,enabled:true,tag:'button',role:'button',areaKind:'main',areaName:'전체게임 필터',interactable:true},
      {elementId:'element-2',selector:'[data-testid="game-list"]',name:'전체게임 목록',matchCount:1,visible:true,enabled:true,tag:'section',areaKind:'main',areaName:'전체게임',interactable:false},
    ],areas:[{id:'area-main',kind:'main',name:'전체게임',elementIds:['element-1','element-2']}],interactions:[{id:'interaction-1',areaId:'area-main',elementId:'element-1',kind:'button',name:'#PC 필터',selector:'[data-testid="game-filter-pc"]',enabled:true,risk:'READ_ONLY_CANDIDATE',source:'PAGE_DISCOVERY'}],stateChanges:[{id:'state-change-1',interactionId:'interaction-1',selector:'[data-testid="game-filter-pc"]',before:{url:item.value.pages[0]?.url??'https://staging.storefront.test',ariaPressed:'false',ariaSelected:null,checked:null},after:{url:item.value.pages[0]?.url??'https://staging.storefront.test',ariaPressed:'true',ariaSelected:null,checked:null},source:'PLAYWRIGHT_OBSERVED'}],scenarioCandidates:[{id:'function-candidate-1',areaId:'area-main',areaName:'전체게임',purpose:'#PC 필터를 선택하면 활성 상태가 변경된다.',preconditions:['전체게임 영역이 표시되어야 합니다.'],steps:[{action:'click',interactionId:'interaction-1',selector:'[data-testid="game-filter-pc"]'},{action:'assert',assertion:{type:'observed_state',changedFields:['ariaPressed'],expected:{ariaPressed:'true'}}}],evidence:{elementIds:['element-1'],interactionIds:['interaction-1'],stateChangeIds:['state-change-1']},automationStatus:'MANUAL_REVIEW_REQUIRED',confidence:.96,coverage:'MISSING_IN_TC',source:'RULE_BASED_OBSERVED'}],coverage:{COVERED:0,PARTIAL:0,MISSING_IN_TC:1,TC_ONLY:0,NOT_AUTOMATABLE:0},warnings:[{code:'LIMITED_READ_ONLY_DISCOVERY',message:'안전한 읽기 전용 범위만 분석했습니다. 외부 이동과 위험 동작은 제외됩니다.'}]}
    return structuredClone(item.value)
  },

  async generatePageScenario(discoveryId:string):Promise<PageScenarioDraft> {
    if (!USE_MOCK_API) return request(`/page-discoveries/${discoveryId}/scenarios`,{method:'POST',body:JSON.stringify({maxAiCalls:0})})
    const discovery=await this.getPageFirstDiscovery(discoveryId)
    const steps=discovery.elements.map((element,index)=>({id:`step-${index+1}`,action:'assert' as const,targetDescription:element.name,selector:element.selector,assertion:{type:'element' as const,operator:'visible' as const,expected:true as const},source:'PAGE_DISCOVERY' as const,evidence:{elementId:element.elementId,fingerprint:discovery.pages[0]?.fingerprint??'',url:discovery.pages[0]?.url??'',observed:'visible' as const}}))
    const comparisons:ScenarioComparison[]=steps.map((step,index)=>({id:`page-${index+1}`,result:'PAGE_ONLY',text:step.targetDescription,draft:step.targetDescription,decision:'PENDING',stepId:step.id,source:'PAGE_DISCOVERY',evidence:'페이지에서 유일하고 표시된 기본 검증 단계입니다.'}))
    const value:PageScenarioDraft={scenarioId:crypto.randomUUID(),discoveryId,revision:1,status:'REVIEW_REQUIRED',purpose:'탐색 페이지의 검증된 요소 표시 확인',pages:discovery.pages,steps,comparisons,scenarioCandidates:discovery.scenarioCandidates,coverage:discovery.coverage,automationStatus:'MANUAL_REVIEW_REQUIRED',warnings:[{code:'SCENARIO_REVIEW_REQUIRED',message:'모든 페이지 기본 단계를 검토해 주세요.'}],executable:false,aiUsage:{source:'RULE_BASED',callCount:0,inputTokens:0,outputTokens:0,costUsd:'0'},environmentId:'env-staging'}
    mockPageScenarios.set(value.scenarioId,value)
    return structuredClone(value)
  },

  async getPageScenario(scenarioId:string):Promise<PageScenarioDraft> {
    if (!USE_MOCK_API) return request(`/page-scenarios/${scenarioId}`)
    const value=mockPageScenarios.get(scenarioId)
    if(!value)throw new ApiError({code:'SCENARIO_NOT_FOUND',message:'시나리오를 찾을 수 없습니다.',requestId:'mock',retryable:false},404)
    return structuredClone(value)
  },

  async comparePageScenario(scenarioId:string,input:ScenarioCompareRequest):Promise<PageScenarioDraft> {
    if (!USE_MOCK_API) return request(`/page-scenarios/${scenarioId}/compare`,{method:'POST',body:JSON.stringify(input)})
    const current=await this.getPageScenario(scenarioId)
    if(current.revision!==input.expectedRevision)throw new ApiError({code:'SCENARIO_REVISION_CONFLICT',message:'다른 변경이 반영되었습니다. 최신 상태를 확인해 주세요.',requestId:'mock',retryable:false},409)
    const lines=input.rawText.split(/\r?\n/).map(value=>value.replace(/^[-*\d.)\s]+/,'').trim()).filter(Boolean).slice(0,200)
    const comparisons:ScenarioComparison[]=lines.map((text,index)=>{const step=current.steps.find(item=>text===`${item.targetDescription} 표시`||text===`${item.targetDescription} 표시 확인`);return {id:`tc-${index+1}`,result:step?'MATCHED':/육안|디자인|자연스럽|정상적|적절|품질/.test(text)?'NOT_AUTOMATABLE':'TC_ONLY',text,draft:text,decision:'PENDING',stepId:step?.id??null,source:'TEST_CASE',evidence:step?'페이지에서 유일하고 표시된 요소와 정확히 일치합니다.':'검증된 페이지 근거와 자동 연결되지 않았습니다.'}})
    current.steps.filter(step=>!comparisons.some(item=>item.stepId===step.id)).forEach((step,index)=>comparisons.push({id:`page-${index+1}`,result:'PAGE_ONLY',text:step.targetDescription,draft:step.targetDescription,decision:'PENDING',stepId:step.id,source:'PAGE_DISCOVERY',evidence:'페이지에서 검증됐지만 TC에는 없는 기본 표시 확인입니다.'}))
    const candidateCovered=lines.some(line=>/#PC|PC 필터/.test(line))
    const scenarioCandidates=current.scenarioCandidates?.map(candidate=>({...candidate,coverage:candidateCovered?'COVERED' as const:'MISSING_IN_TC' as const}))
    const coverage={COVERED:candidateCovered?(scenarioCandidates?.length??0):0,PARTIAL:0,MISSING_IN_TC:candidateCovered?0:(scenarioCandidates?.length??0),TC_ONLY:comparisons.filter(item=>item.result==='TC_ONLY').length,NOT_AUTOMATABLE:comparisons.filter(item=>item.result==='NOT_AUTOMATABLE').length}
    const updated={...current,revision:current.revision+1,comparisons,scenarioCandidates,coverage,extractedTestCase:{target:lines[0]??'',actions:lines.slice(1),expectedResults:lines.slice(-1),source:'RULE_BASED' as const,aiCallCount:0 as const},warnings:[{code:'SCENARIO_REVIEW_REQUIRED',message:'모든 비교 항목의 처리 방식을 선택해 주세요.'}]}
    mockPageScenarios.set(scenarioId,updated);return structuredClone(updated)
  },

  async reviewPageScenario(scenarioId:string,input:ScenarioReviewRequest):Promise<PageScenarioDraft> {
    if (!USE_MOCK_API) return request(`/page-scenarios/${scenarioId}/review`,{method:'PATCH',body:JSON.stringify(input)})
    const current=await this.getPageScenario(scenarioId)
    if(current.revision!==input.expectedRevision)throw new ApiError({code:'SCENARIO_REVISION_CONFLICT',message:'다른 변경이 반영되었습니다. 최신 상태를 확인해 주세요.',requestId:'mock',retryable:false},409)
    if(current.status==='READY')throw new ApiError({code:'SCENARIO_ALREADY_APPROVED',message:'승인된 시나리오는 변경할 수 없습니다.',requestId:'mock',retryable:false},409)
    const selected=new Map(input.selections.map(item=>[item.comparisonId,item]))
    for(const item of current.comparisons??[]){const selection=selected.get(item.id);if(selection&&['ADD','IGNORE'].includes(selection.decision)&&!['MATCHED','PAGE_ONLY'].includes(item.result))throw new ApiError({code:'COMPARISON_EVIDENCE_REQUIRED',message:'근거 없는 항목은 추가하거나 유지할 수 없습니다.',requestId:'mock',retryable:false},422)}
    const comparisons=current.comparisons?.map(item=>{const selection=selected.get(item.id);return selection?{...item,decision:selection.decision,draft:selection.draft??item.draft,source:selection.draft!==undefined?'MANUAL' as const:item.source}:item})??[]
    const pending=comparisons.some(item=>item.decision==='PENDING')
    const updated={...current,revision:current.revision+1,comparisons,warnings:pending?[{code:'SCENARIO_REVIEW_REQUIRED',message:'모든 비교 항목의 처리 방식을 선택해 주세요.'}]:[]}
    mockPageScenarios.set(scenarioId,updated);return structuredClone(updated)
  },

  async approvePageScenario(scenarioId:string,input:ScenarioApproveRequest):Promise<PageScenarioDraft> {
    if (!USE_MOCK_API) return request(`/page-scenarios/${scenarioId}/approve`,{method:'POST',body:JSON.stringify(input)})
    const current=await this.getPageScenario(scenarioId)
    if(current.revision!==input.expectedRevision)throw new ApiError({code:'SCENARIO_REVISION_CONFLICT',message:'다른 변경이 반영되었습니다. 최신 상태를 확인해 주세요.',requestId:'mock',retryable:false},409)
    if(current.status==='READY')return current
    if(!current.comparisons?.length||current.comparisons.some(item=>item.decision==='PENDING'))throw new ApiError({code:'SCENARIO_REVIEW_REQUIRED',message:'모든 비교 항목을 검토해 주세요.',requestId:'mock',retryable:false},422)
    if(!current.comparisons.some(item=>['ADD','IGNORE'].includes(item.decision)&&item.stepId))throw new ApiError({code:'SCENARIO_EMPTY',message:'실행할 검증 단계가 없습니다.',requestId:'mock',retryable:false},422)
    const updated={...current,status:'READY' as const,executable:true,automationStatus:'PARTIALLY_AUTOMATABLE' as const,versionId:crypto.randomUUID(),environmentId:current.environmentId??'env-staging',warnings:[{code:'PARTIAL_SCOPE',message:'수동·제외 항목은 자동 실행 범위에 포함되지 않습니다.'}]}
    mockPageScenarios.set(scenarioId,updated);return structuredClone(updated)
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
