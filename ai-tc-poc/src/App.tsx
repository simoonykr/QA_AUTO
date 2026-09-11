import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, Bot, Check, CheckCircle2,
  ChevronDown, CircleDot, Clock3, FileText, Gauge, LayoutDashboard,
  ListChecks, MoreHorizontal, Play, Plus, Search, Settings,
  ShieldCheck, Sparkles, Square, TerminalSquare, TestTube2, Users, XCircle,
  Upload, WandSparkles, Save, Database, KeyRound, MonitorCheck,
  Download, ExternalLink, RefreshCw, Eye, ChevronRight, Trash2,
} from 'lucide-react'
import { api, apiConfig, ApiError } from './api/client'
import type { AuthenticatedUser, CreateExecutionRequest, DiscoverySelection, EnvironmentSummary, Execution, ExecutionDetails, ExecutionHistoryItem, ExecutionPlan, ExecutionPlanStep, ExecutionPolicy, ExecutionStepRun, ImportedTestCaseItem, PageDiscovery, PageFirstDiscovery, PageScenarioDraft, ScenarioComparison, ScenarioComparisonResult, ScenarioDecision, StructuredTestCase, TestAccountSummary, TestCaseSummary, TestCaseVersionStepPatch } from './api/types'

type View = 'dashboard' | 'cases' | 'history' | 'page-first' | 'author' | 'configure' | 'plan' | 'run' | 'result' | 'environments' | 'accounts' | 'policies'
type RunState = 'idle' | 'running' | 'paused' | 'done' | 'failed'
type AuthorStage = 'draft' | 'structuring' | 'split-review' | 'review' | 'ready'
type ApiConnection = 'mock' | 'checking' | 'online' | 'offline'
type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'
const ACTIVE_EXECUTION_KEY = 'tracepilot.activeExecutionId'

const workerSteps = [
  { title: '실행 대기열 등록', note: 'Redis Stream에서 Worker 할당을 기다립니다.', type: 'QUEUE' },
  { title: '격리 브라우저 준비', note: 'Chromium 컨텍스트와 viewport를 생성합니다.', type: 'PROVISION' },
  { title: '대상 페이지 접속', note: '허용 도메인을 검사하고 DOM 로드를 확인합니다.', type: 'NAVIGATE' },
]
function executionPresentation(status: Execution['status']): { runState: RunState; activeStep: number } {
  if (status === 'PASS') return { runState: 'done', activeStep: 3 }
  if (['FAIL','BLOCKED','NEEDS_REVIEW','CANCELLED','SYSTEM_ERROR'].includes(status)) return { runState: 'failed', activeStep: 3 }
  if (status === 'WAITING_APPROVAL') return { runState: 'paused', activeStep: 2 }
  if (status === 'RUNNING' || status === 'CANCEL_REQUESTED') return { runState: 'running', activeStep: 2 }
  return { runState: 'running', activeStep: status === 'PROVISIONING' ? 1 : 0 }
}

function App() {
  const [view, setView] = useState<View>('dashboard')
  const [runState, setRunState] = useState<RunState>('idle')
  const [activeStep, setActiveStep] = useState(0)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [authorStage, setAuthorStage] = useState<AuthorStage>('draft')
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null)
  const [activeEnvironmentId, setActiveEnvironmentId] = useState<string | null>(null)
  const [activeStructured, setActiveStructured] = useState<StructuredTestCase | null>(null)
  const [pendingExecution, setPendingExecution] = useState<CreateExecutionRequest | null>(null)
  const [testCases, setTestCases] = useState<TestCaseSummary[]>([])
  const [loadingCases, setLoadingCases] = useState(true)
  const [startingRun, setStartingRun] = useState(false)
  const [execution, setExecution] = useState<Execution | null>(null)
  const [executionDetails, setExecutionDetails] = useState<ExecutionDetails | null>(null)
  const [apiConnection, setApiConnection] = useState<ApiConnection>(apiConfig.mock ? 'mock' : 'checking')
  const [backendEnvironment, setBackendEnvironment] = useState(apiConfig.mock ? 'mock' : '')
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking')
  const [currentUser, setCurrentUser] = useState<AuthenticatedUser | null>(null)
  const [authNotice, setAuthNotice] = useState('')

  useEffect(() => {
    api.me().then(user => { setCurrentUser(user); setAuthStatus('authenticated') }).catch(() => setAuthStatus('unauthenticated'))
    const requireLogin = () => { setAuthNotice('세션이 만료되었습니다. 다시 로그인해 주세요.'); setCurrentUser(null); setAuthStatus('unauthenticated') }
    window.addEventListener('tracepilot:auth-required', requireLogin)
    return () => window.removeEventListener('tracepilot:auth-required', requireLogin)
  }, [])

  useEffect(() => {
    if (authStatus !== 'authenticated' || currentUser?.approvalStatus !== 'APPROVED') return
    setLoadingCases(true)
    api.listTestCases().then(setTestCases).catch((error) => setNotice(error instanceof ApiError ? error.body.message : '테스트 케이스를 불러오지 못했습니다.')).finally(() => setLoadingCases(false))
  }, [authStatus, currentUser?.approvalStatus])

  const checkBackend = async () => {
    if (apiConfig.mock || authStatus !== 'authenticated') return
    setApiConnection('checking')
    try {
      const health = await api.checkHealth()
      setBackendEnvironment(health.environment)
      setApiConnection(health.status === 'ok' ? 'online' : 'offline')
    } catch {
      setBackendEnvironment('')
      setApiConnection('offline')
    }
  }

  useEffect(() => { void checkBackend() }, [authStatus])

  useEffect(() => {
    if (apiConfig.mock || authStatus !== 'authenticated') return
    const executionId = window.sessionStorage.getItem(ACTIVE_EXECUTION_KEY)
    if (!executionId) return
    api.getExecution(executionId).then(restored => {
      const presentation = executionPresentation(restored.status)
      setExecution(restored)
      setRunState(presentation.runState)
      setActiveStep(presentation.activeStep)
      setView('run')
      void api.getExecutionDetails(restored.id).then(setExecutionDetails).catch(() => undefined)
    }).catch(() => window.sessionStorage.removeItem(ACTIVE_EXECUTION_KEY))
  }, [authStatus])

  useEffect(() => {
    if (apiConfig.mock || !execution || !['QUEUED','PROVISIONING','RUNNING','WAITING_APPROVAL','CANCEL_REQUESTED'].includes(execution.status)) return
    let pollingTimer:number|undefined
    let terminalReceived=false
    const applyDetails=(details:ExecutionDetails)=>{
      setExecutionDetails(details)
      setExecution(details.execution)
      const presentation = executionPresentation(details.execution.status)
      setRunState(presentation.runState)
      setActiveStep(presentation.activeStep)
      terminalReceived=['PASS','FAIL','BLOCKED','NEEDS_REVIEW','CANCELLED','SYSTEM_ERROR'].includes(details.execution.status)
    }
    const poll=()=>api.getExecutionDetails(execution.id).then(applyDetails).catch(error=>toast(error instanceof ApiError?error.body.message:'실행 상태를 확인하지 못했습니다.'))
    const startPolling=()=>{if(pollingTimer||terminalReceived)return;void poll();pollingTimer=window.setInterval(poll,2000)}
    const unsubscribe=api.subscribeExecution(execution.id,applyDetails,startPolling)
    return () => { unsubscribe(); if(pollingTimer)window.clearInterval(pollingTimer) }
  }, [execution?.id, execution?.status])

  const filtered = useMemo(() => testCases.filter((t) => `${t.id} ${t.title} ${t.group}`.toLowerCase().includes(query.toLowerCase())), [query, testCases])

  const createRun = async (input: CreateExecutionRequest) => {
    if (startingRun) return
    setStartingRun(true)
    try {
      const created = await api.createExecution(input)
      if (!apiConfig.mock) window.sessionStorage.setItem(ACTIVE_EXECUTION_KEY, created.id)
      setExecution(created)
      setExecutionDetails(null)
      setRunState('running'); setActiveStep(1); setView('run')
      if (apiConfig.mock) {
        window.setTimeout(() => setActiveStep(2), 900)
        window.setTimeout(() => setActiveStep(3), 1800)
        window.setTimeout(() => { void api.getExecutionDetails(created.id).then(details=>{setExecution(details.execution);setExecutionDetails(details);setActiveStep(details.steps.length);setRunState('done')}) }, 2800)
      }
    } catch (error) {
      toast(error instanceof ApiError ? error.body.message : '실행을 시작하지 못했습니다.')
    } finally { setStartingRun(false) }
  }
  const startRun = () => {
    if (!activeVersionId) {
      setAuthorStage('draft'); setView('author'); toast('테스트 케이스를 구조화하고 승인한 뒤 실행해 주세요.')
      return
    }
    setView('configure')
  }
  const cancelRun = async () => {
    if (execution && !apiConfig.mock) {
      try { setExecution((await api.cancelExecution(execution.id)).execution); toast('실행 중단을 요청했습니다.') }
      catch (error) { return toast(error instanceof ApiError ? error.body.message : '실행을 중단하지 못했습니다.') }
    }
    setRunState('idle'); setActiveStep(0)
  }
  const retryRun = async () => {
    if (execution && !apiConfig.mock) {
      try { const retried=(await api.retryExecution(execution.id)).execution; window.sessionStorage.setItem(ACTIVE_EXECUTION_KEY, retried.id); setExecution(retried); setExecutionDetails(null); setRunState('running'); setActiveStep(0); setView('run'); return }
      catch (error) { return toast(error instanceof ApiError ? error.body.message : '실행을 재시도하지 못했습니다.') }
    }
    startRun()
  }
  const openHistoryExecution = async (item:ExecutionHistoryItem) => {
    try {
      const details=await api.getExecutionDetails(item.id)
      setExecution(details.execution);setExecutionDetails(details);setView('result')
    } catch (error) { toast(error instanceof ApiError ? error.body.message : '실행 상세를 불러오지 못했습니다.') }
  }

  const toast = (message: string) => { setNotice(message) }

  const login = async (username: string, password: string) => {
    const response = await api.login(username, password)
    setAuthNotice('')
    setCurrentUser(response.user)
    setAuthStatus('authenticated')
  }

  const logout = async () => {
    try { await api.logout() } finally {
      window.sessionStorage.removeItem(ACTIVE_EXECUTION_KEY)
      setExecution(null); setExecutionDetails(null); setAuthNotice(''); setCurrentUser(null); setAuthStatus('unauthenticated')
    }
  }

  if (authStatus === 'checking') return <AuthLoading/>
  if (authStatus === 'unauthenticated') return <LoginPage notice={authNotice} onLogin={login}/>
  if (!currentUser) return <LoginPage notice={authNotice} onLogin={login}/>
  if (currentUser.approvalStatus !== 'APPROVED') return <ApprovalGate user={currentUser} onLogout={logout}/>

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView('dashboard')} aria-label="대시보드로 이동">
          <span className="brand-mark"><Sparkles size={19}/></span>
          <span><strong>TracePilot</strong><small>AI Test Operations</small></span>
        </button>
        <nav>
          <p className="nav-label">Workspace</p>
          <Nav active={view === 'dashboard'} icon={<LayoutDashboard/>} label="대시보드" onClick={() => setView('dashboard')}/>
          <Nav active={view === 'cases'} icon={<ListChecks/>} label="테스트 케이스" badge="24" onClick={() => setView('cases')}/>
          <Nav active={view === 'run'} icon={<Activity/>} label="실행 모니터" badge="3" onClick={() => setView('run')}/>
          <Nav active={view === 'history'} icon={<Clock3/>} label="실행 이력" onClick={() => setView('history')}/>
          <Nav active={view === 'page-first'} icon={<WandSparkles/>} label="AI 시나리오" onClick={() => setView('page-first')}/>
          <p className="nav-label spaced">Manage</p>
          <Nav active={view === 'environments'} icon={<TerminalSquare/>} label="실행 환경" onClick={() => setView('environments')}/>
          <Nav active={view === 'accounts'} icon={<Users/>} label="계정 및 데이터" onClick={() => setView('accounts')}/>
          <Nav active={view === 'policies'} icon={<ShieldCheck/>} label="정책 및 승인" onClick={() => setView('policies')}/>
        </nav>
        <div className="project-card">
          <div className="project-dot">S</div><div><b>Storefront QA</b><small>Staging · Chromium</small></div><ChevronDown size={16}/>
        </div>
        <button className="user-card" onClick={logout} title="로그아웃"><span className="avatar">{currentUser.displayName.slice(0,1)}</span><span><b>{currentUser.displayName}</b><small>{currentUser.role}</small></span><Settings size={17}/></button>
      </aside>

      <main>
        <header className="topbar">
          <div className="connection-area">
            <span className="environment"><CircleDot size={13}/> Staging</span>
            <span className={`sync ${apiConnection}`}><span/> {apiConnection === 'mock' ? 'Mock API 사용 중' : apiConnection === 'checking' ? 'Backend 확인 중' : apiConnection === 'online' ? `Backend 연결됨${backendEnvironment ? ` · ${backendEnvironment}` : ''}` : 'Backend 연결 끊김'}</span>
            {apiConnection === 'offline' && <button className="sync-retry" onClick={checkBackend}><RefreshCw size={12}/> 재연결</button>}
          </div>
          <div className="top-actions"><button className="icon-button" aria-label="알림"><AlertTriangle size={18}/><i/></button><button className="primary" onClick={startRun} disabled={startingRun}>{startingRun?<Activity className="spin" size={16}/>:<Play size={16} fill="currentColor"/>} {startingRun?'실행 생성 중':'새 실행'}</button></div>
        </header>

        {view === 'dashboard' && <Dashboard onRun={startRun} onCases={() => setView('cases')}/>} 
        {view === 'cases' && <Cases query={query} setQuery={setQuery} rows={filtered} loading={loadingCases} onRun={startRun} onCreate={() => {setActiveVersionId(null); setActiveEnvironmentId(null); setActiveStructured(null); setAuthorStage('draft'); setView('author')}}/>}
        {view === 'history' && <ExecutionHistoryPage onOpen={openHistoryExecution}/>}
        {view === 'page-first' && <PageFirstScenario onToast={toast} onApproved={(approved)=>{if(!approved.versionId)return;setActiveVersionId(approved.versionId);setActiveEnvironmentId(approved.environmentId??null);setActiveStructured(toStructuredTestCase(approved));setView('configure')}}/>}
        {view === 'author' && <Author stage={authorStage} setStage={setAuthorStage} onBack={() => setView('cases')} onRun={() => setView('configure')} onVersion={versionId=>{setActiveVersionId(versionId);setActiveEnvironmentId(null)}} onStructured={setActiveStructured} onToast={toast}/>}
        {view === 'configure' && activeVersionId && <RunConfigure versionId={activeVersionId} lockedEnvironmentId={activeEnvironmentId} onBack={() => setView(activeEnvironmentId?'page-first':'author')} onStart={request=>{setPendingExecution(request);setView('plan')}} starting={startingRun}/>}
        {view === 'plan' && activeStructured && pendingExecution && <ExecutionPlanPreview structured={activeStructured} request={pendingExecution} onBack={()=>setView('configure')} onConfirm={()=>void createRun(pendingExecution)} starting={startingRun}/>}
        {view === 'run' && <RunMonitor state={runState} execution={execution} details={executionDetails} activeStep={activeStep} start={startRun} stop={cancelRun} onResult={() => setView('result')}/>}
        {view === 'result' && <ResultDetail execution={execution} details={executionDetails} onBack={() => setView('dashboard')} onRetry={retryRun}/>}
        {view === 'environments' && <ManagementPage kind="environment" onToast={toast}/>}
        {view === 'accounts' && <ManagementPage kind="account" onToast={toast}/>}
        {view === 'policies' && <ManagementPage kind="policy" onToast={toast}/>}
      </main>
      {notice && <div className="toast" role="status" style={{zIndex:10000,maxWidth:'calc(100vw - 32px)'}}>{notice}<button onClick={()=>setNotice('')} aria-label="알림 닫기">닫기</button></div>}
    </div>
  )
}

function AuthLoading() {
  return <main className="auth-shell"><section className="auth-card auth-loading"><span className="brand-mark"><Sparkles size={19}/></span><Activity className="spin"/><p>로그인 상태를 확인하고 있습니다.</p></section></main>
}

function LoginPage({notice,onLogin}:{notice:string;onLogin:(username:string,password:string)=>Promise<void>}) {
  const [mode,setMode]=useState<'login'|'signup'>('login')
  const [username,setUsername]=useState('')
  const [password,setPassword]=useState('')
  const [submitting,setSubmitting]=useState(false)
  const [error,setError]=useState('')
  const submit=async(e:React.FormEvent)=>{e.preventDefault();if(submitting)return;setSubmitting(true);setError('');try{await onLogin(username,password)}catch(err){setError(err instanceof ApiError?err.body.message:'로그인 요청에 실패했습니다.')}finally{setSubmitting(false)}}
  if(mode==='signup')return <main className="auth-shell"><section className="auth-card approval-card"><span className="approval-icon"><Users/></span><p className="eyebrow">ACCESS REQUEST</p><h1>가입 신청 기능을 준비하고 있습니다.</h1><p className="auth-copy">향후 가입 신청 후 관리자 승인을 받은 사용자만 로그인할 수 있습니다. 현재 데모는 관리자에게 공용 계정을 요청해 주세요.</p><button className="secondary wide" onClick={()=>setMode('login')}>로그인으로 돌아가기</button></section></main>
  return <main className="auth-shell"><section className="auth-card"><div className="auth-brand"><span className="brand-mark"><Sparkles size={19}/></span><div><strong>TracePilot</strong><small>AI Test Operations</small></div></div><p className="eyebrow">SECURE DEMO ACCESS</p><h1>테스트 워크스페이스 로그인</h1><p className="auth-copy">관리자에게 전달받은 데모 계정으로 로그인해 주세요. 세션은 안전한 HttpOnly 쿠키로 유지됩니다.</p>{notice&&<div className="auth-notice"><Clock3 size={15}/>{notice}</div>}<form onSubmit={submit}><label>아이디<input autoFocus autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>비밀번호<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<div className="auth-error"><AlertTriangle size={15}/>{error}</div>}<button className="primary wide" disabled={submitting}>{submitting?<Activity className="spin" size={16}/>:<KeyRound size={16}/>} {submitting?'로그인 중':'로그인'}</button></form><button className="auth-link" onClick={()=>setMode('signup')}>계정이 없으신가요? 가입 신청 안내</button><small className="auth-help"><ShieldCheck size={13}/> 계정 정보는 브라우저 저장소에 저장하지 않습니다.</small></section></main>
}

function ApprovalGate({user,onLogout}:{user:AuthenticatedUser;onLogout:()=>void}) {
  const rejected=user.approvalStatus==='REJECTED'
  return <main className="auth-shell"><section className="auth-card approval-card"><span className={`approval-icon ${rejected?'rejected':''}`}>{rejected?<XCircle/>:<Clock3/>}</span><p className="eyebrow">ACCOUNT APPROVAL</p><h1>{rejected?'접근 승인이 거절되었습니다.':'관리자 승인을 기다리고 있습니다.'}</h1><p className="auth-copy">{user.displayName} 계정은 현재 <b>{user.approvalStatus}</b> 상태입니다. 승인 상태가 변경된 후 다시 로그인해 주세요.</p><button className="secondary wide" onClick={onLogout}>로그아웃</button></section></main>
}

function Nav({active, icon, label, badge, onClick}: {active?: boolean; icon: React.ReactNode; label: string; badge?: string; onClick: () => void}) {
  return <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}><span>{icon}</span>{label}{badge && <em>{badge}</em>}</button>
}

function Dashboard({onRun, onCases}: {onRun: () => void; onCases: () => void}) {
  const [history,setHistory]=useState<ExecutionHistoryItem[]>([])
  const [historyTotal,setHistoryTotal]=useState(0)
  useEffect(()=>{api.listExecutions().then(result=>{setHistory(result.items);setHistoryTotal(result.total)}).catch(()=>{setHistory([]);setHistoryTotal(0)})},[])
  const completed=history.filter(item=>['PASS','FAIL','BLOCKED','NEEDS_REVIEW','CANCELLED','SYSTEM_ERROR'].includes(item.status))
  const passRate=completed.length?Math.round(completed.filter(item=>item.status==='PASS').length*1000/completed.length)/10:0
  const durations=history.map(item=>item.durationMs).filter((value):value is number=>typeof value==='number')
  const averageDuration=durations.length?Math.round(durations.reduce((sum,value)=>sum+value,0)/durations.length/1000):0
  return <section className="page dashboard">
    <div className="page-heading"><div><p className="eyebrow">THURSDAY, AUGUST 27</p><h1>좋은 오후예요, 민준님.</h1><p>오늘도 안정적인 릴리스를 위한 테스트를 시작해 볼까요?</p></div><button className="secondary"><Clock3 size={16}/> 최근 7일 <ChevronDown size={15}/></button></div>
    <div className="metrics">
      <Metric icon={<TestTube2/>} label="전체 실행" value={String(historyTotal)} delta="실제 API 집계" tone="blue"/>
      <Metric icon={<CheckCircle2/>} label="통과율" value={`${passRate}%`} delta={`${completed.length}건 완료 기준`} tone="green"/>
      <Metric icon={<Clock3/>} label="평균 실행 시간" value={`${averageDuration}s`} delta="시작·종료 기록 기준" tone="violet"/>
      <Metric icon={<Gauge/>} label="AI API" value="OFF" delta="토큰 사용 없음" tone="amber"/>
    </div>
    <div className="dashboard-grid">
      <article className="panel runs-panel">
        <div className="panel-head"><div><h2>최근 실행</h2><p>프로젝트의 최신 자동화 결과입니다.</p></div><button className="text-button" onClick={onCases}>전체 보기 <ArrowRight size={15}/></button></div>
        {history.slice(0,4).map(item=>{const tone=item.status==='PASS'?'pass':item.status==='RUNNING'?'running':'fail';return <div className="run-row" key={item.id}><StatusIcon type={tone}/><div><b>{item.testCaseTitle}</b><small>{item.testCaseId} · {new Date(item.queuedAt).toLocaleString()}</small></div><span className={`pill ${tone}`}>{item.status}</span><time>{item.durationMs==null?'-':`${Math.round(item.durationMs/1000)}s`}</time><MoreHorizontal/></div>})}
        {history.length===0&&<div className="empty-table">아직 저장된 실행 이력이 없습니다.</div>}
      </article>
      <article className="panel quick-run">
        <div className="orb"><Bot size={27}/></div><p className="eyebrow">QUICK RUN</p><h2>검증할 흐름을<br/>바로 실행하세요.</h2><p>현재는 AI API 없이 승인된 구조와 Playwright Worker로 테스트 흐름을 검증합니다.</p><button className="primary wide" onClick={onRun}><Play size={16} fill="currentColor"/> 테스트 실행</button>
        <div className="limits"><span><b>0</b> AI 호출</span><span><b>15m</b> 실행 제한</span></div>
      </article>
    </div>
    <div className="dashboard-grid lower">
      <article className="panel chart-panel"><div className="panel-head"><div><h2>품질 추이</h2><p>최근 7일 실행 결과</p></div><div className="legend"><span className="green-dot"/> Pass <span className="red-dot"/> Fail</div></div><div className="chart"><div style={{height:'48%'}}/><div style={{height:'62%'}}/><div style={{height:'55%'}}/><div style={{height:'80%'}}/><div style={{height:'68%'}}/><div style={{height:'88%'}}/><div className="today" style={{height:'94%'}}/></div><div className="days"><span>금</span><span>토</span><span>일</span><span>월</span><span>화</span><span>수</span><span>오늘</span></div></article>
      <article className="panel insight"><div className="insight-title"><Sparkles size={18}/><b>품질 인사이트</b><span>NEW</span></div><h3>검색 필터 TC의 실패가 증가했어요.</h3><p>최근 실행 결과에서 가격 슬라이더 탐색 성공률이 18% 감소했습니다. selector 후보를 재검토해 보세요.</p><button className="text-button">상세 분석 보기 <ArrowRight size={15}/></button></article>
    </div>
  </section>
}

function Metric({icon,label,value,delta,tone}: {icon: React.ReactNode; label:string; value:string; delta:string; tone:string}) { return <article className="metric"><div className={`metric-icon ${tone}`}>{icon}</div><div><p>{label}</p><strong>{value}</strong><small className={tone}>{delta}</small></div></article> }
function StatusIcon({type}: {type:'pass'|'running'|'fail'}) { return <span className={`status-icon ${type}`}>{type==='pass'?<Check/>:type==='fail'?<XCircle/>:<Activity/>}</span> }

const HISTORY_PAGE_SIZE=20
function ExecutionHistoryPage({onOpen}:{onOpen:(item:ExecutionHistoryItem)=>Promise<void>}) {
  const [status,setStatus]=useState('ALL')
  const [testCaseId,setTestCaseId]=useState('')
  const [appliedTestCaseId,setAppliedTestCaseId]=useState('')
  const [offset,setOffset]=useState(0)
  const [result,setResult]=useState<{items:ExecutionHistoryItem[];total:number}>({items:[],total:0})
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const load=()=>{setLoading(true);setError('');api.listExecutions(status==='ALL'?undefined:status,appliedTestCaseId||undefined,HISTORY_PAGE_SIZE,offset).then(setResult).catch(err=>{setResult({items:[],total:0});setError(err instanceof ApiError?err.body.message:'실행 이력을 불러오지 못했습니다.')}).finally(()=>setLoading(false))}
  useEffect(load,[status,appliedTestCaseId,offset])
  const applySearch=(event:React.FormEvent)=>{event.preventDefault();setOffset(0);setAppliedTestCaseId(testCaseId.trim())}
  const page=Math.floor(offset/HISTORY_PAGE_SIZE)+1
  const pages=Math.max(1,Math.ceil(result.total/HISTORY_PAGE_SIZE))
  return <section className="page">
    <div className="page-heading compact"><div><p className="eyebrow">EXECUTION HISTORY</p><h1>실행 이력</h1><p>저장된 실행 결과를 상태와 테스트 케이스별로 조회합니다.</p></div><button className="secondary" onClick={load} disabled={loading}><RefreshCw className={loading?'spin':''} size={14}/> 새로고침</button></div>
    <form className="toolbar" onSubmit={applySearch}><div className="search"><Search size={17}/><input value={testCaseId} onChange={event=>setTestCaseId(event.target.value)} placeholder="테스트 케이스 ID 검색"/></div><Select value={status} setValue={value=>{setStatus(value);setOffset(0)}} options={['ALL','QUEUED','PROVISIONING','RUNNING','PASS','FAIL','BLOCKED','NEEDS_REVIEW','CANCELLED','SYSTEM_ERROR']}/><button className="secondary" type="submit">조회</button></form>
    <article className="panel table-panel history-table"><table><thead><tr><th>테스트 케이스</th><th>상태</th><th>단계</th><th>실행 시각</th><th>소요 시간</th><th>증적</th><th/></tr></thead><tbody>{result.items.map(item=>{const tone=item.status==='PASS'?'pass':['QUEUED','PROVISIONING','RUNNING'].includes(item.status)?'running':'fail';return <tr key={item.id}><td><span className={`status-icon ${tone}`}><Activity/></span><span><b>{item.testCaseTitle}</b><small>{item.testCaseId} · {item.id}</small></span></td><td><span className={`pill ${tone}`}>{item.status}</span>{item.errorCode&&<small>{item.errorCode}</small>}</td><td>{item.actualStepCount} / {item.plannedStepCount}</td><td>{new Date(item.queuedAt).toLocaleString('ko-KR')}</td><td>{item.durationMs==null?'-':`${Math.round(item.durationMs/1000)}s`}</td><td>{item.artifactCount}개</td><td><button className="row-play" onClick={()=>void onOpen(item)} aria-label={`${item.testCaseTitle} 실행 상세`}><Eye size={14}/></button></td></tr>})}</tbody></table>
      {loading&&<div className="empty-table"><Activity className="spin" size={16}/> 실행 이력을 불러오는 중입니다.</div>}{!loading&&error&&<div className="empty-table error-text">{error}</div>}{!loading&&!error&&result.items.length===0&&<div className="empty-table">조건에 맞는 실행 이력이 없습니다.</div>}
      <div className="history-pagination"><span>전체 {result.total}건 · {page}/{pages} 페이지</span><div><button className="secondary" disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-HISTORY_PAGE_SIZE))}>이전</button><button className="secondary" disabled={offset+HISTORY_PAGE_SIZE>=result.total||loading} onClick={()=>setOffset(offset+HISTORY_PAGE_SIZE)}>다음</button></div></div>
    </article>
  </section>
}

function PageFirstScenario({onToast,onApproved}:{onToast:(message:string)=>void;onApproved:(scenario:PageScenarioDraft)=>void}) {
  const [environments,setEnvironments]=useState<EnvironmentSummary[]>([])
  const [environmentId,setEnvironmentId]=useState('')
  const [startUrl,setStartUrl]=useState('')
  const [tcContext,setTcContext]=useState('')
  const [discoveryId,setDiscoveryId]=useState('')
  const [discovery,setDiscovery]=useState<PageFirstDiscovery|null>(null)
  const [scenario,setScenario]=useState<PageScenarioDraft|null>(null)
  const [starting,setStarting]=useState(false)
  const [generating,setGenerating]=useState(false)
  const [comparisons,setComparisons]=useState<ScenarioComparison[]>([])
  const [editingComparisonId,setEditingComparisonId]=useState('')
  const [mockRevision,setMockRevision]=useState(1)
  const [reviewing,setReviewing]=useState(false)
  const [approving,setApproving]=useState(false)
  const [analysisError,setAnalysisError]=useState<{code:string;message:string}|null>(null)
  const requestGeneration=useRef(0)
  useEffect(()=>{api.listEnvironments().then(items=>{setEnvironments(items);setEnvironmentId(items[0]?.id??'')}).catch(error=>onToast(error instanceof ApiError?error.body.message:'실행 환경을 불러오지 못했습니다.'))},[])
  useEffect(()=>{
    if(!discoveryId)return
    let active=true,timer:number|undefined
    const poll=async()=>{try{const result=await api.getPageFirstDiscovery(discoveryId);if(!active)return;setDiscovery(result);if(result.status==='FAILED')setAnalysisError(discoveryFailure(result.errorCode,result.warnings));if(!['COMPLETED','FAILED'].includes(result.status))timer=window.setTimeout(()=>void poll(),1500)}catch(error){if(active){setAnalysisError(errorFeedback(error,'페이지 분석 상태를 확인하지 못했습니다.'));setDiscoveryId('');setDiscovery(null)}}}
    void poll();return()=>{active=false;if(timer)window.clearTimeout(timer)}
  },[discoveryId])
  const start=async()=>{
    if(!environmentId||!startUrl.trim()||starting)return onToast('실행 환경과 시작 URL을 확인해 주세요.')
    const generation=++requestGeneration.current
    setStarting(true);setAnalysisError(null);setDiscoveryId('');setDiscovery(null);setScenario(null);setComparisons([]);setEditingComparisonId('');setMockRevision(1)
    onToast('페이지 분석 요청 중입니다.')
    try{const result=await api.startPageFirstDiscovery({environmentId,startUrl:startUrl.trim(),maxPages:1,maxAiCalls:0});if(generation!==requestGeneration.current)return;setDiscovery({discoveryId:result.discoveryId,status:'QUEUED',pages:[],elements:[],warnings:[],errorCode:null,aiUsage:{source:'RULE_BASED',callCount:0}});setDiscoveryId(result.discoveryId);onToast('읽기 전용 페이지 분석을 시작했습니다.')}
    catch(error){if(generation===requestGeneration.current)setAnalysisError(errorFeedback(error,'페이지 분석을 시작하지 못했습니다.'))}
    finally{if(generation===requestGeneration.current)setStarting(false)}
  }
  const generate=async()=>{
    if(!discoveryId||discovery?.status!=='COMPLETED'||generating)return
    const generation=requestGeneration.current;setGenerating(true)
    try{let result=await api.generatePageScenario(discoveryId);if(generation!==requestGeneration.current)return;if(tcContext.trim())result=await api.comparePageScenario(result.scenarioId,{expectedRevision:result.revision,rawText:tcContext.trim()});if(generation!==requestGeneration.current)return;setScenario(result);setMockRevision(result.revision);setComparisons(result.comparisons??[]);onToast(tcContext.trim()?'TC 비교 결과를 생성했습니다.':'페이지 근거 시나리오 초안을 생성했습니다.')}
    catch(error){if(generation===requestGeneration.current)onToast(error instanceof ApiError?error.body.message:'시나리오를 생성하지 못했습니다.')}
    finally{if(generation===requestGeneration.current)setGenerating(false)}
  }
  const updateComparison=(id:string,patch:Partial<ScenarioComparison>)=>setComparisons(items=>items.map(item=>item.id===id?{...item,...patch}:item))
  const decide=async(id:string,decision:ScenarioDecision)=>{if(!scenario||reviewing)return;const item=comparisons.find(row=>row.id===id);if(!item)return;const generation=requestGeneration.current;setReviewing(true);try{const updated=await api.reviewPageScenario(scenario.scenarioId,{expectedRevision:scenario.revision,selections:[{comparisonId:id,decision,draft:item.draft!==item.text?item.draft:undefined}]});if(generation!==requestGeneration.current)return;setScenario(updated);setMockRevision(updated.revision);setComparisons(updated.comparisons??[]);setEditingComparisonId('');onToast('검토 선택을 서버 revision에 저장했습니다.')}catch(error){if(generation===requestGeneration.current)await handleScenarioError(error,scenario.scenarioId)}finally{if(generation===requestGeneration.current)setReviewing(false)}}
  const handleScenarioError=async(error:unknown,scenarioId:string)=>{if(error instanceof ApiError&&error.body.code==='SCENARIO_REVISION_CONFLICT'){try{const latest=await api.getPageScenario(scenarioId);setScenario(latest);setMockRevision(latest.revision);setComparisons(latest.comparisons??[]);setEditingComparisonId('');return onToast('다른 변경이 반영되어 최신 상태를 불러왔습니다. 다시 검토해 주세요.')}catch{return onToast('최신 시나리오를 불러오지 못했습니다.')}}onToast(error instanceof ApiError?error.body.message:'시나리오 요청을 처리하지 못했습니다.')}
  const approve=async()=>{if(!scenario||pendingCount||approving)return;const generation=requestGeneration.current;setApproving(true);try{const updated=await api.approvePageScenario(scenario.scenarioId,{expectedRevision:scenario.revision});if(generation!==requestGeneration.current)return;setScenario(updated);if(!updated.versionId)throw new Error('versionId missing');onToast('시나리오를 승인했습니다. 실행 설정으로 이동합니다.');onApproved(updated)}catch(error){if(generation===requestGeneration.current)await handleScenarioError(error,scenario.scenarioId)}finally{if(generation===requestGeneration.current)setApproving(false)}}
  const invalidate=()=>{requestGeneration.current+=1;setAnalysisError(null);setDiscoveryId('');setDiscovery(null);setScenario(null);setComparisons([]);setEditingComparisonId('');setMockRevision(1)}
  const pendingCount=comparisons.filter(item=>item.decision==='PENDING').length
  const busy=starting||generating||reviewing||approving||Boolean(discovery&&!['COMPLETED','FAILED'].includes(discovery.status))
  const selectedEnvironment=environments.find(item=>item.id===environmentId)
  return <section className="page page-first-page"><div className="page-heading compact"><div><p className="eyebrow">PAGE-FIRST SCENARIO</p><h1>AI 시나리오 초안</h1><p>실제 페이지에서 검증된 요소로 기본 시나리오를 만들고 자연어 TC를 보강 자료로 비교합니다.</p></div><span className="phase-badge">PHASE 2 · AI 0회</span></div>
    <div className="page-first-grid"><article className="panel page-first-input"><div className="section-head"><div><h2>1. 분석 대상</h2><p>현재 범위는 한 페이지의 data-testid 표시 검증입니다.</p></div><MonitorCheck/></div><label className="field-label">실행 환경</label><div className="select-wrap"><select value={environmentId} onChange={e=>{const id=e.target.value;invalidate();setEnvironmentId(id);setStartUrl('')}} disabled={busy}>{environments.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><ChevronDown/></div><div className="target-context"><b>{selectedEnvironment?.name??'환경 미선택'}</b><span>허용 기준: {selectedEnvironment?.baseUrl??'-'}</span></div><label className="field-label">시작 URL</label><input className="field-input" value={startUrl} onChange={e=>{invalidate();setStartUrl(e.target.value)}} disabled={busy} placeholder="분석할 https:// 주소를 직접 입력하세요."/><label className="field-label">선택적 자연어 TC</label><textarea className="tc-editor page-first-tc" value={tcContext} onChange={e=>{invalidate();setTcContext(e.target.value)}} disabled={busy} placeholder="선택한 단일 TC의 대상, 행동, 기대 결과를 줄 단위로 입력하세요. 비교 결과는 서버 revision에 저장됩니다."/><div className="privacy-note"><ShieldCheck/><span>GET/HEAD만 허용하며 입력값·쿠키·비밀번호·전체 HTML은 수집하지 않습니다.</span></div>{analysisError&&<div className="config-error persistent-error"><AlertTriangle/><div><b>{analysisError.code}</b><span>{analysisError.message}</span></div></div>}<button type="button" className="ai-button" onClick={()=>void start()} disabled={busy||!environmentId||!startUrl.trim()}>{starting?<Activity className="spin"/>:<Search/>}{starting?'분석 요청 중':'페이지 분석 시작'}</button></article>
      <article className="panel page-first-progress"><div className="section-head"><div><h2>2. 분석 진행</h2><p>페이지 접속부터 시나리오 초안 생성까지 확인합니다.</p></div><span className={`live ${discovery?.status==='COMPLETED'?'done':discovery?'running':''}`}>{discovery?.status??'대기'}</span></div><div className="page-first-stages">{['페이지 접속','요소 수집','후보 검증','시나리오 초안'].map((label,index)=>{const complete=(discovery?.status==='COMPLETED'&&index<3)||Boolean(scenario);const active=!scenario&&((discovery?.status==='SCANNING'&&index<=1)||(discovery?.status==='COMPLETED'&&index===2));return <div className={complete?'complete':active?'active':''} key={label}><span>{complete?<Check/>:index+1}</span><b>{label}</b></div>})}</div>{discovery?.pages.map(page=><div className="page-summary" key={page.fingerprint}><ExternalLink/><div><b>{page.title||'제목 없음'}</b><small>{page.url}<br/>fingerprint {page.fingerprint.slice(0,16)}</small></div></div>)}{discovery?.status==='COMPLETED'&&<><div className="element-count"><Database/><span>검증 요소 <b>{discovery.elements.length}개</b></span></div><button type="button" className="primary wide" onClick={()=>void generate()} disabled={generating}>{generating?<Activity className="spin"/>:<WandSparkles/>}{generating?'초안 생성 중':'기본 시나리오 생성'}</button></>}</article></div>
    {scenario&&<article className="panel scenario-review"><div className="panel-head"><div><h2>3. 시나리오 비교·편집</h2><p>{scenario.purpose} · 서버 revision {mockRevision}</p></div><div className="review-state"><span className={`pill ${pendingCount?'review':'pass'}`}>{pendingCount?`미결정 ${pendingCount}건`:'검토 완료'}</span><button className="primary" onClick={()=>void approve()} disabled={Boolean(pendingCount)||busy||scenario.status==='READY'}>{approving?<Activity className="spin"/>:<ShieldCheck/>}{scenario.status==='READY'?'승인 완료':approving?'승인 중':'승인 후 실행 설정'}</button></div></div><div className="scenario-columns"><div><h3>페이지 근거 단계</h3>{scenario.steps.map((step,index)=><div className="scenario-step" key={step.id}><span>{index+1}</span><div><b>{step.targetDescription}</b><code>{step.selector}</code><small><em>PAGE DISCOVERY</em> · {step.assertion.operator} · {step.evidence.observed}</small></div></div>)}</div><div><h3>TC 비교 및 보강</h3>{comparisons.length?comparisons.map(item=><div className={`comparison-card ${item.result.toLowerCase()} ${item.decision!=='PENDING'?'decided':''}`} key={item.id}><div className="comparison-title"><b>{item.result.replace('_',' ')} · {comparisonLabel(item.result)}</b>{item.decision!=='PENDING'&&<span>{decisionLabel(item.decision)}</span>}</div>{editingComparisonId===item.id?<textarea value={item.draft} onChange={event=>updateComparison(item.id,{draft:event.target.value})}/>:<p>{item.draft}</p>}<small>{item.source.replace('_',' ')} · {item.evidence}</small><div className="comparison-actions">{editingComparisonId===item.id?<><button className="secondary" onClick={()=>void decide(item.id,item.result==='MATCHED'||item.result==='PAGE_ONLY'?'ADD':'MANUAL')} disabled={reviewing||!item.draft.trim()}><Save/>수정 저장</button><button className="secondary" onClick={()=>{updateComparison(item.id,{draft:item.text});setEditingComparisonId('')}} disabled={reviewing}>취소</button></>:<><button className="secondary" onClick={()=>void decide(item.id,'ADD')} disabled={reviewing||!['MATCHED','PAGE_ONLY'].includes(item.result)}>시나리오에 추가</button><button className="secondary" onClick={()=>void decide(item.id,'MANUAL')} disabled={reviewing}>수동 검증</button><button className="secondary" onClick={()=>setEditingComparisonId(item.id)} disabled={reviewing}>문구 수정</button><button className="secondary" onClick={()=>void decide(item.id,'EXCLUDE')} disabled={reviewing}>제외</button></>}</div></div>):<div className="empty-table">TC 없이 페이지 기본 시나리오만 검토합니다.</div>}<div className="mock-contract-note"><ShieldCheck/><span>검토 선택은 서버 revision에 저장됩니다. 수동·제외 항목은 실행 결과의 통과 범위에 포함되지 않습니다.</span></div>{scenario.warnings.map(item=><div className="config-error" key={item.code}><AlertTriangle/><div><b>{item.code}</b><span>{item.message}</span></div></div>)}</div></div></article>}
  </section>
}

function comparisonLabel(result:ScenarioComparisonResult) { return ({MATCHED:'일치',TC_ONLY:'TC에만 있음',PAGE_ONLY:'페이지에만 있음',CONFLICT:'불일치',NOT_AUTOMATABLE:'자동화 불가'} as const)[result] }
function decisionLabel(decision:ScenarioDecision) { return ({PENDING:'미결정',ADD:'추가됨',MANUAL:'수동 검증',EXCLUDE:'제외됨',IGNORE:'유지'} as const)[decision] }

function errorFeedback(error:unknown,fallback:string) {
  return error instanceof ApiError?{code:error.body.code,message:error.body.message}:{code:'DISCOVERY_REQUEST_FAILED',message:fallback}
}

function discoveryFailure(code:string|null|undefined,warnings:Array<{code:string;message:string}>) {
  const known:Record<string,string>={
    DISCOVERY_TIMEOUT:'페이지 접속 또는 요소 검증 시간이 초과됐습니다. 대상 상태를 확인하고 다시 분석해 주세요.',
    DISCOVERY_CONNECTION_FAILED:'대상 페이지 연결에 실패했습니다. URL, DNS, 인증서와 네트워크 상태를 확인해 주세요.',
    DISCOVERY_BROWSER_ERROR:'브라우저 접속 또는 요소 수집에 실패했습니다. 대상 URL과 연결 상태를 확인해 주세요.',
    DISCOVERY_INTERNAL_ERROR:'페이지 분석 중 내부 오류가 발생했습니다. 잠시 후 다시 분석해 주세요.',
    TARGET_URL_NOT_ALLOWED:'선택한 환경에서 허용되지 않은 URL입니다. 환경과 대상 URL을 확인해 주세요.',
  }
  const errorCode=code??'DISCOVERY_FAILED'
  return {code:errorCode,message:warnings.find(item=>item.code===errorCode)?.message??known[errorCode]??'페이지 분석에 실패했습니다. 입력을 유지한 채 다시 시도할 수 있습니다.'}
}

function toStructuredTestCase(scenario:PageScenarioDraft):StructuredTestCase {
  return {versionId:scenario.versionId??'',status:'READY',title:scenario.purpose,preconditions:scenario.pages.map(page=>`${page.url} 페이지 접근`),steps:scenario.steps.map(step=>({id:step.id,title:step.targetDescription,note:`${step.source} · ${step.evidence.observed}`,action:'assert',confidence:1,selector:step.selector,operator:step.assertion.operator,expected:String(step.assertion.expected),assertionType:step.assertion.type,targetDescription:step.targetDescription,resolutionStatus:'RESOLVED'})),assertions:scenario.steps.map(step=>({type:'element',operator:step.assertion.operator,expected:String(step.assertion.expected),timeoutMs:5000})),assumptions:scenario.warnings.map(item=>item.message),confidence:1,aiUsage:{source:'RULE_BASED',callCount:0,inputTokens:0,outputTokens:0,costUsd:'0',dailySpentUsd:'0',dailyBudgetUsd:'0'},automationStatus:scenario.automationStatus,automationReason:'검증된 페이지 표시 assertion과 QA 검토 선택만 실행합니다.'}
}

function prepareStructureRawText(rawText:string):{rawText:string;excludedLineCount:number;excludedResultColumns:number} {
  const lines=rawText.split(/\r?\n/)
  const markerIndex=lines.findIndex(line=>/do not put test cases above this line/i.test(line))
  let preparedLines=lines
  let excludedLineCount=0
  if(markerIndex>=0) {
    preparedLines=lines.slice(markerIndex+1)
    excludedLineCount=markerIndex+1
  } else {
    const tableIndex=lines.findIndex(line=>{const value=line.toLowerCase();return line.includes('|')&&/\bid\b/.test(value)&&value.includes('step')&&(value.includes('expected result')||value.includes('기대 결과'))})
    const hasSummary=lines.slice(0,Math.max(tableIndex,0)).some(line=>/result\s*\|\s*count\s*\|\s*rate|^(pass|fail|n\/?a|block|not test|total)\s*\|/i.test(line.trim()))
    if(tableIndex>0&&hasSummary){preparedLines=lines.slice(tableIndex);excludedLineCount=tableIndex}
  }
  const headerIndex=preparedLines.findIndex(line=>line.toLowerCase().includes('expected result')||line.includes('기대 결과'))
  if(headerIndex>=0&&preparedLines[headerIndex].includes('|')) {
    const headers=preparedLines[headerIndex].split('|').map(cell=>cell.trim())
    const expectedIndex=headers.findIndex(header=>/expected result|기대 결과/i.test(header))
    if(expectedIndex>=0&&headers.length>expectedIndex+1) {
      const excludedResultColumns=headers.length-expectedIndex-1
      const functionalLines=preparedLines.map((line,index)=>index>=headerIndex&&line.includes('|')?line.split('|').slice(0,expectedIndex+1).join(' | ').trim():line)
      return {rawText:functionalLines.join('\n').trim(),excludedLineCount,excludedResultColumns}
    }
  }
  return {rawText:preparedLines.join('\n').trim(),excludedLineCount,excludedResultColumns:0}
}

function ManagementPage({kind,onToast}:{kind:'environment'|'account'|'policy';onToast:(s:string)=>void}) {
  const data = {
    environment: { eyebrow:'EXECUTION TARGETS', title:'실행 환경', desc:'테스트 대상 URL과 브라우저 접근 범위를 관리합니다.', button:'환경 추가', icon:<TerminalSquare/>, rows:[['Staging','https://staging.storefront.test','정상'],['Development','https://dev.storefront.test','정상']] },
    account: { eyebrow:'TEST DATA', title:'계정 및 데이터', desc:'실행에 사용할 계정 별칭과 데이터 세트를 안전하게 관리합니다.', button:'계정 추가', icon:<Users/>, rows:[['qa-runner-01','signup-default-v2','사용 가능'],['qa-runner-02','checkout-default-v1','사용 가능']] },
    policy: { eyebrow:'SAFETY GUARDRAILS', title:'정책 및 승인', desc:'외부 이동과 파괴적 행동에 대한 실행 승인 규칙을 설정합니다.', button:'정책 추가', icon:<ShieldCheck/>, rows:[['외부 도메인 이동','항상 차단','활성'],['결제·삭제 행동','실행 전 승인','활성'],['파일 다운로드','허용 목록만','활성']] },
  }[kind]
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">{data.eyebrow}</p><h1>{data.title}</h1><p>{data.desc}</p></div><button className="primary" onClick={()=>onToast(`${data.button} 기능은 API 연결 후 저장됩니다.`)}><Plus size={16}/>{data.button}</button></div>
    <div className="manage-summary"><article className="panel"><span>{data.icon}</span><div><small>등록 항목</small><b>{data.rows.length}</b></div></article><article className="panel"><span><CheckCircle2/></span><div><small>정상 상태</small><b>{data.rows.length}</b></div></article><article className="panel"><span><Clock3/></span><div><small>최근 변경</small><b>오늘 18:32</b></div></article></div>
    <article className="panel manage-list"><div className="panel-head"><div><h2>{data.title} 목록</h2><p>변경 사항은 감사 로그에 기록됩니다.</p></div><button className="secondary" onClick={()=>onToast('목록을 새로고침했습니다.')}><RefreshCw size={14}/> 새로고침</button></div>{data.rows.map((row)=><div className="manage-row" key={row[0]}><span className="manage-icon">{data.icon}</span><div><b>{row[0]}</b><small>{row[1]}</small></div><span className="pill pass">{row[2]}</span><button className="icon-button" aria-label={`${row[0]} 설정`} onClick={()=>onToast(`${row[0]} 상세 설정을 선택했습니다.`)}><Settings size={16}/></button></div>)}</article>
  </section>
}

function Cases({query,setQuery,rows,loading,onRun,onCreate}: {query:string; setQuery:(s:string)=>void; rows:TestCaseSummary[]; loading:boolean; onRun:()=>void; onCreate:()=>void}) {
  const [status,setStatus] = useState('ALL')
  const [group,setGroup] = useState('ALL')
  const visibleRows = rows.filter(row => (status === 'ALL' || row.status === status) && (group === 'ALL' || row.group === group))
  const groups = [...new Set(rows.map(row => row.group))]
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">TEST LIBRARY</p><h1>테스트 케이스</h1><p>자연어 TC를 구조화하고 실행 준비 상태를 관리합니다.</p></div><button className="primary" onClick={onCreate}><Plus size={16}/> 새 테스트 케이스</button></div>
    <div className="toolbar"><div className="search"><Search size={17}/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="ID, 이름 또는 그룹 검색"/></div><Select value={status} setValue={setStatus} options={['ALL','READY','REVIEW_REQUIRED']}/><Select value={group} setValue={setGroup} options={['ALL',...groups]}/><button className="secondary" onClick={onCreate}><Upload size={15}/> 파일로 새 TC</button></div>
    <article className="panel table-panel"><table><thead><tr><th>테스트 케이스</th><th>그룹</th><th>준비 상태</th><th>최근 성공률</th><th>마지막 실행</th><th/></tr></thead><tbody>{visibleRows.map((row)=><tr key={row.id}><td><span className="file-icon"><FileText/></span><span><b>{row.title}</b><small>{row.id}</small></span></td><td>{row.group}</td><td><span className={`pill ${row.status==='READY'?'pass':'review'}`}>{row.status.replace('_',' ')}</span></td><td><div className="rate"><span><i style={{width:`${row.passRate}%`}}/></span>{row.passRate}%</div></td><td>{row.lastExecutedAt}</td><td><button className="row-play" onClick={onRun} aria-label={`${row.title} 실행`}><Play size={14}/></button></td></tr>)}</tbody></table>{loading&&<div className="empty-table"><Activity className="spin" size={16}/> 테스트 케이스를 불러오는 중입니다.</div>}{!loading&&visibleRows.length===0&&<div className="empty-table">조건에 맞는 테스트 케이스가 없습니다.</div>}</article>
  </section>
}

function Author({stage,setStage,onBack,onRun,onVersion,onStructured,onToast}: {stage:AuthorStage; setStage:(s:AuthorStage)=>void; onBack:()=>void; onRun:()=>void; onVersion:(id:string|null)=>void; onStructured:(value:StructuredTestCase|null)=>void; onToast:(s:string)=>void}) {
  const [title,setTitle] = useState('신규 사용자 이메일 회원가입')
  const [raw,setRaw] = useState('Staging 환경에 접속한다.\n회원가입 버튼을 누르고 사용하지 않은 이메일과 안전한 비밀번호를 입력한다.\n약관에 동의한 뒤 가입을 완료한다.\n가입 완료 후 환영 메시지와 대시보드가 표시되는지 확인한다.')
  const [importedFile,setImportedFile] = useState('')
  const [importing,setImporting] = useState(false)
  const [importWarnings,setImportWarnings] = useState<string[]>([])
  const [importedTestCases,setImportedTestCases] = useState<ImportedTestCaseItem[]>([])
  const [selectedImportedId,setSelectedImportedId] = useState('')
  const [excludedMetadataLines,setExcludedMetadataLines] = useState(0)
  const [excludedResultColumns,setExcludedResultColumns] = useState(0)
  const [splitReview,setSplitReview] = useState<{detectedTestCaseCount:number;rawTextLength:number}|null>(null)
  const [structured,setStructured] = useState<StructuredTestCase | null>(null)
  const [reviewEnvironments,setReviewEnvironments] = useState<EnvironmentSummary[]>([])
  const [reviewEnvironmentId,setReviewEnvironmentId] = useState('')
  const [reviewPlan,setReviewPlan] = useState<ExecutionPlan | null>(null)
  const [planLoading,setPlanLoading] = useState(false)
  const [planError,setPlanError] = useState('')
  const [editingStep,setEditingStep] = useState<ExecutionPlanStep | null>(null)
  const [stepDraft,setStepDraft] = useState({selector:'',url:'',operator:'',expected:'',value:'',secretRef:'',assertionType:''})
  const [dirtyFields,setDirtyFields] = useState<Array<keyof TestCaseVersionStepPatch>>([])
  const [savingStep,setSavingStep] = useState(false)
  const [deletingStepId,setDeletingStepId] = useState<string | null>(null)
  const [discoveryId,setDiscoveryId] = useState<string | null>(null)
  const [discovery,setDiscovery] = useState<PageDiscovery | null>(null)
  const [candidateSelections,setCandidateSelections] = useState<Record<string,string>>({})
  const [discoveryStarting,setDiscoveryStarting] = useState(false)
  const [discoveryApplying,setDiscoveryApplying] = useState(false)
  const [discoveryError,setDiscoveryError] = useState<{code:string;message:string}|null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(()=>{
    if (stage!=='review') return
    api.listEnvironments().then(items=>{
      setReviewEnvironments(items)
      setReviewEnvironmentId(current=>current||items[0]?.id||'')
    }).catch(error=>setPlanError(error instanceof ApiError?error.body.message:'실행 환경을 불러오지 못했습니다.'))
  },[stage])
  useEffect(()=>{
    if (stage!=='review'||!structured?.versionId||!reviewEnvironmentId) return
    setPlanLoading(true); setPlanError('')
    api.getExecutionPlan(structured.versionId,reviewEnvironmentId).then(setReviewPlan).catch(error=>{
      setReviewPlan(null); setPlanError(error instanceof ApiError?error.body.message:'실행 계획을 불러오지 못했습니다.')
    }).finally(()=>setPlanLoading(false))
  },[stage,structured?.versionId,reviewEnvironmentId])
  useEffect(()=>{
    if (stage!=='review'||!structured?.versionId||!discoveryId) return
    let active=true
    let timer:number|undefined
    const terminal=['COMPLETED','NEEDS_REVIEW','FAILED','CANCELLED']
    const poll=async()=>{
      try {
        const result=await api.getPageDiscovery(structured.versionId,discoveryId)
        if (!active) return
        setDiscovery(result)
        if (result.status==='FAILED') setDiscoveryError(discoveryFailure(result.errorCode,result.warnings))
        setCandidateSelections(current=>{const next={...current};result.steps.forEach(step=>{if(!next[step.stepId]&&step.selectedCandidateId)next[step.stepId]=step.selectedCandidateId});return next})
        if (!terminal.includes(result.status)) timer=window.setTimeout(()=>void poll(),1500)
      } catch (error) { if(active)setDiscoveryError(errorFeedback(error,'페이지 분석 상태를 확인하지 못했습니다.')) }
    }
    void poll()
    return()=>{active=false;if(timer)window.clearTimeout(timer)}
  },[stage,structured?.versionId,discoveryId])
  const importFile = async (file?: File) => {
    if (!file) return
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!['csv','xlsx','docx','txt'].includes(extension ?? '')) return onToast('지원하지 않는 파일 형식입니다.')
    if (file.size > 10 * 1024 * 1024) return onToast('파일 크기는 최대 10MB까지 지원합니다.')
    setImportedFile(file.name)
    setImportWarnings([])
    setExcludedMetadataLines(0)
    setExcludedResultColumns(0)
    setSplitReview(null)
    onVersion(null); onStructured(null)
    setImporting(true)
    try {
      const imported = await api.importTestCase(file)
      setTitle(imported.title)
      setRaw(imported.rawText)
      setImportWarnings(imported.warnings)
      setImportedTestCases(imported.testCases)
      const first=imported.testCases[0]
      setSelectedImportedId(first?.externalId??'')
      if(first){setTitle(first.title);setRaw(first.rawText)}
      setStage('draft')
      onToast(`${imported.fileName} 분석을 완료했습니다.`)
    } catch (error) {
      setImportedFile('')
      if (fileInput.current) fileInput.current.value=''
      onToast(error instanceof ApiError ? error.body.message : '파일을 가져오지 못했습니다.')
    } finally { setImporting(false) }
  }
  const structure = async () => {
    if (!title.trim() || raw.trim().length < 10) return onToast('테스트 이름과 10자 이상의 원문을 입력해 주세요.')
    const prepared=prepareStructureRawText(raw)
    setExcludedMetadataLines(prepared.excludedLineCount)
    setExcludedResultColumns(prepared.excludedResultColumns)
    setStage('structuring')
    try { const selected=importedTestCases.find(item=>item.externalId===selectedImportedId); const result=selected?await api.structureImportedTestCase({...selected,title:title.trim(),rawText:prepared.rawText}):await api.structureTestCase(title.trim(),prepared.rawText); setStructured(result); setReviewPlan(null); setEditingStep(null); onStructured(result); onVersion(null); setSplitReview(null); setStage('review') }
    catch (error) {
      if (error instanceof ApiError && error.body.code==='MULTIPLE_TEST_CASES_REVIEW_REQUIRED') {
        const count=Number(error.body.details?.detectedTestCaseCount)
        const length=Number(error.body.details?.rawTextLength)
        setStructured(null); onStructured(null)
        setSplitReview({detectedTestCaseCount:Number.isFinite(count)?count:0,rawTextLength:Number.isFinite(length)?length:raw.trim().length})
        setStage('split-review')
        onToast('여러 테스트 케이스가 감지되어 TC별 분리가 필요합니다.')
        return
      }
      setStage('draft'); onToast(error instanceof ApiError ? error.body.message : 'TC 구조화에 실패했습니다. 다시 시도해 주세요.')
    }
  }
  const approve = async () => {
    if (!structured||reviewPlan?.executable!==true) return onToast('실행 계획의 누락 항목을 먼저 수정해 주세요.')
    try {
      const approved=await api.approveTestCaseVersion(structured.versionId)
      const ready={...structured,status:approved.status}; setStructured(ready); onStructured(ready); onVersion(approved.versionId); setStage('ready')
      onToast('검토 승인이 완료되었습니다.')
    } catch (error) { onToast(error instanceof ApiError ? error.body.message : '검토 승인에 실패했습니다.') }
  }
  const openStepEditor = (step:ExecutionPlanStep) => {
    setEditingStep(step)
    setStepDraft({selector:step.selector??'',url:step.url??'',operator:step.operator??'',expected:step.expected??'',value:step.value==='***'?'':step.value??'',secretRef:step.secretRef??'',assertionType:step.assertionType??''})
    setDirtyFields([])
  }
  const changeStepField = (field:keyof TestCaseVersionStepPatch,value:string) => {
    setStepDraft(current=>({...current,[field]:value}))
    setDirtyFields(current=>current.includes(field)?current:[...current,field])
  }
  const saveStep = async () => {
    if (!structured||!editingStep||!reviewEnvironmentId||dirtyFields.length===0) return
    const dirty=new Set(dirtyFields)
    const patch:TestCaseVersionStepPatch={
      ...(dirty.has('selector')?{selector:stepDraft.selector.trim()||null}:{}), ...(dirty.has('url')?{url:stepDraft.url.trim()||null}:{}),
      ...(dirty.has('operator')?{operator:stepDraft.operator.trim()||null}:{}), ...(dirty.has('expected')?{expected:stepDraft.expected.trim()||null}:{}),
      ...(dirty.has('value')?{value:stepDraft.value||null}:{}), ...(dirty.has('secretRef')?{secretRef:stepDraft.secretRef.trim()||null}:{}),
      ...(dirty.has('assertionType')?{assertionType:(stepDraft.assertionType||null) as TestCaseVersionStepPatch['assertionType']}:{}),
    }
    setSavingStep(true)
    try {
      const updated=await api.updateTestCaseVersionStep(structured.versionId,editingStep.id,reviewEnvironmentId,patch)
      setReviewPlan(updated)
      const planStep=updated.steps.find(item=>item.id===editingStep.id)
      const next:StructuredTestCase=planStep?{...structured,steps:structured.steps.map(item=>item.id===planStep.id?{...item,url:planStep.url,selector:planStep.selector,value:planStep.value,secretRef:planStep.secretRef,operator:planStep.operator,expected:planStep.expected,assertionType:planStep.assertionType,timeoutMs:planStep.timeoutMs}:item)}:structured
      setStructured(next); onStructured(next); setEditingStep(null); setDirtyFields([])
      onToast(`단계를 저장했습니다. revision ${updated.revision}`)
    } catch (error) { onToast(error instanceof ApiError?error.body.message:'단계를 저장하지 못했습니다.') }
    finally { setSavingStep(false) }
  }
  const deleteStep = async (step:ExecutionPlanStep) => {
    if (!structured||!reviewEnvironmentId||deletingStepId||!window.confirm('이 실행 단계를 삭제하시겠습니까?')) return
    setDeletingStepId(step.id)
    try {
      const updated=await api.deleteTestCaseVersionStep(structured.versionId,step.id,reviewEnvironmentId)
      setReviewPlan(updated)
      const remainingIds=new Set(updated.steps.map(item=>item.id))
      const next={...structured,steps:structured.steps.filter(item=>remainingIds.has(item.id))}
      setStructured(next); onStructured(next)
      if (editingStep?.id===step.id) { setEditingStep(null); setDirtyFields([]) }
      onToast(`단계를 삭제했습니다. revision ${updated.revision}`)
    } catch (error) {
      if (error instanceof ApiError&&error.body.code==='TC_STEP_NOT_FOUND') {
        onToast('이미 삭제됐거나 현재 버전에 없는 단계입니다. 실행 계획을 새로고침합니다.')
        try { setReviewPlan(await api.getExecutionPlan(structured.versionId,reviewEnvironmentId)) } catch { setPlanError('실행 계획을 새로고침하지 못했습니다.') }
      } else if (error instanceof ApiError&&error.body.code==='TC_VERSION_NOT_REVIEWABLE') onToast('승인 완료된 버전은 실행 단계를 수정하거나 삭제할 수 없습니다.')
      else onToast(error instanceof ApiError?error.body.message:'단계를 삭제하지 못했습니다.')
    } finally { setDeletingStepId(null) }
  }
  const startDiscovery = async () => {
    if (!structured||!reviewEnvironmentId||discoveryStarting) return onToast('실행 환경과 구조화 결과를 확인해 주세요.')
    setDiscoveryStarting(true); setDiscoveryError(null); setDiscovery(null); setDiscoveryId(null); setCandidateSelections({})
    onToast('페이지 분석 요청 중입니다.')
    try { const result=await api.startPageDiscovery(structured.versionId,reviewEnvironmentId);setDiscovery({discoveryId:result.discoveryId,status:'QUEUED',revision:1,pages:[],steps:[],warnings:[],executable:false});setDiscoveryId(result.discoveryId);onToast('페이지 분석을 시작했습니다. AI 호출 없이 실제 화면 요소를 검증합니다.') }
    catch(error){setDiscoveryError(errorFeedback(error,'페이지 분석을 시작하지 못했습니다.'))}
    finally{setDiscoveryStarting(false)}
  }
  const applyDiscovery = async () => {
    if (!structured||!discovery||!reviewEnvironmentId||discoveryApplying) return
    const selections:DiscoverySelection[]=discovery.steps.map(step=>({stepId:step.stepId,candidateId:candidateSelections[step.stepId]??step.selectedCandidateId??''})).filter(item=>item.candidateId)
    setDiscoveryApplying(true)
    try {
      const updated=await api.applyPageDiscovery(structured.versionId,discovery.discoveryId,selections,reviewEnvironmentId)
      setReviewPlan(updated)
      const byId=new Map(updated.steps.map(step=>[step.id,step]))
      const next:StructuredTestCase={...structured,steps:structured.steps.map(step=>{const planStep=byId.get(step.id);return planStep?{...step,selector:planStep.selector,resolutionStatus:planStep.resolutionStatus}:step})}
      setStructured(next);onStructured(next);setDiscoveryId(null);setDiscovery(null)
      onToast(`페이지 분석 결과를 적용했습니다. revision ${updated.revision}`)
    } catch(error){onToast(error instanceof ApiError?error.body.message:'페이지 분석 결과를 적용하지 못했습니다.')}
    finally{setDiscoveryApplying(false)}
  }
  const selectImported = (item:ImportedTestCaseItem) => {setSelectedImportedId(item.externalId??'');setTitle(item.title);setRaw(item.rawText);setStructured(null);setDiscoveryError(null);onStructured(null);onVersion(null);setStage('draft')}
  const editTitle = (value:string) => { setTitle(value); setStructured(null); onStructured(null); setSplitReview(null); setExcludedMetadataLines(0); setExcludedResultColumns(0); onVersion(null); setStage('draft') }
  const editRaw = (value:string) => { setRaw(value); setStructured(null); onStructured(null); setSplitReview(null); setExcludedMetadataLines(0); setExcludedResultColumns(0); onVersion(null); setStage('draft') }
  const displayedAutomationStatus=stage==='review'&&reviewPlan?.executable!==true?'MANUAL_REVIEW_REQUIRED':structured?.automationStatus
  const displayedAutomationReason=stage==='review'&&reviewPlan?.executable!==true?'실행 계획에 미해결 항목이 있어 페이지 분석 또는 직접 검토가 필요합니다.':structured?.automationReason
  return <section className="page author-page">
    <div className="author-top"><button className="back-button" onClick={onBack}>← 테스트 케이스</button><div className="author-actions"><button className="secondary" onClick={()=>onToast('초안을 저장했습니다.')}><Save size={15}/> 초안 저장</button>{stage==='review'&&<button className="primary" onClick={()=>void approve()} disabled={reviewPlan?.executable!==true||planLoading||savingStep} title={reviewPlan?.executable?'검토 승인':'누락된 단계 필드를 먼저 수정해 주세요.'}><Check size={15}/> 검토 승인</button>}{stage==='ready'&&<button className="primary" onClick={onRun}><Play size={15}/> 실행 설정</button>}</div></div>
    <div className="author-heading"><div><span className={`stage-badge ${stage}`}>{stage==='draft'?'DRAFT':stage==='structuring'?'STRUCTURING':stage==='split-review'?'SPLIT REVIEW REQUIRED':stage==='review'?'REVIEW REQUIRED':'READY'}</span><h1>{title}</h1><p>TC-NEW · Storefront QA · Version 1</p></div><div className="progress-steps"><span className="complete"><Check/>원문 작성</span><i/><span className={stage!=='draft'?'complete':''}><WandSparkles/>규칙 기반 구조화</span><i/><span className={stage==='ready'?'complete':''}><ShieldCheck/>검토 승인</span></div></div>
    <div className="author-grid">
      <article className="panel editor-panel"><div className="section-head"><div><h2>자연어 테스트 케이스</h2><p>사람이 이해하기 쉬운 방식으로 수행 조건과 기대 결과를 작성하세요.</p></div><button className="secondary" onClick={()=>fileInput.current?.click()} disabled={importing}>{importing?<Activity className="spin" size={15}/>:<Upload size={15}/>} {importing?'업로드·분석 중':'파일 가져오기'}</button><input ref={fileInput} className="file-input" type="file" accept=".csv,.xlsx,.docx,.txt" onChange={e=>void importFile(e.target.files?.[0])}/></div>{importedFile&&<div className="imported-file"><FileText size={14}/><span>{importedFile}</span><button onClick={()=>{setImportedFile('');setImportWarnings([]);setImportedTestCases([]);setSelectedImportedId('');setExcludedMetadataLines(0);setExcludedResultColumns(0);onVersion(null);setStage('draft');if(fileInput.current)fileInput.current.value=''}} aria-label="가져온 파일 제거" disabled={importing}><XCircle size={14}/></button></div>}{importedTestCases.length>0&&<div className="imported-tc-list"><b>감지된 TC {importedTestCases.length}개 · 분석할 TC 선택</b><div>{importedTestCases.map(item=><button key={item.externalId??item.title} className={selectedImportedId===(item.externalId??'')?'selected':''} onClick={()=>selectImported(item)}><span>{item.externalId??'ID 없음'}</span><small>{item.title}</small></button>)}</div></div>}{importWarnings.length>0&&<div className="ambiguity"><AlertTriangle/><div><b>가져오기 경고 {importWarnings.length}개</b>{importWarnings.map(item=><p key={item}>{item}</p>)}</div></div>}{(excludedMetadataLines>0||excludedResultColumns>0)&&<div className="metadata-filter"><ShieldCheck/><div><b>결과 집계 {excludedMetadataLines}개 행 · 결과 기록 {excludedResultColumns}개 열 제외</b><p>실제 TC의 ID, 계층, 전제조건, Step, Expected Result만 구조화에 사용했습니다.</p></div></div>}<label className="field-label">테스트 이름</label><input className="field-input" value={title} onChange={e=>editTitle(e.target.value)} disabled={importing}/><label className="field-label">원문 TC</label><textarea className="tc-editor" value={raw} onChange={e=>editRaw(e.target.value)} disabled={importing}/><div className="editor-meta"><span>{raw.length}자</span><span>CSV · XLSX · DOCX · TXT · 최대 10MB</span></div><button className="ai-button" onClick={structure} disabled={stage==='structuring'||importing}>{stage==='structuring'?<><Activity className="spin"/> TC를 구조화하고 있습니다...</>:<><WandSparkles/> 선택한 TC 구조화 <ArrowRight/></>}</button></article>
      <article className={`panel review-panel ${(stage==='draft'||stage==='split-review')?'empty-review':''}`}>
        {stage==='draft'&&<div className="review-empty"><div><Bot/></div><h2>구조화 결과가 여기에 표시됩니다.</h2><p>현재는 AI 토큰 없이 전제조건, 실행 단계와 기대 결과를 안전한 규칙으로 분리합니다.</p><ul><li><Check/> 허용된 action으로 변환</li><li><Check/> 규칙 기반 assertion 생성</li><li><Check/> 위험 행동 자동 감지</li></ul></div>}
        {stage==='split-review'&&splitReview&&<div className="review-empty split-review"><div><ListChecks/></div><h2>TC별 분리가 필요합니다.</h2><p>하나의 파일에서 여러 테스트 케이스가 감지되어 단일 실행 단계로 구조화하지 않았습니다.</p><div className="split-review-stats"><span><b>{splitReview.detectedTestCaseCount.toLocaleString()}개</b> 감지된 TC</span><span><b>{splitReview.rawTextLength.toLocaleString()}자</b> 원문 길이</span></div><div className="ambiguity"><AlertTriangle/><div><b>검토가 필요한 상태입니다.</b><p>현재 원문을 TC별로 분리한 뒤 각각 구조화해야 합니다. 이 결과는 승인하거나 실행할 수 없습니다.</p></div></div></div>}
        {stage==='structuring'&&<div className="review-empty"><div className="pulse"><WandSparkles/></div><h2>TC 구조를 분석하는 중입니다.</h2><p>단계와 검증 조건을 안전한 실행 명령으로 변환하고 있습니다.</p><div className="skeleton-lines"><i/><i/><i/><i/></div></div>}
        {(stage==='review'||stage==='ready')&&structured&&<><div className="section-head"><div><h2>구조화 검토</h2><p>서버가 검증한 실행 계획을 승인 전에 확인하고 수정하세요.</p></div><span className="confidence">신뢰도 <b>{Math.round(structured.confidence*100)}%</b></span></div>
          <div className={`automation-assessment ${displayedAutomationStatus?.toLowerCase()}`}><ShieldCheck/><div><b>{displayedAutomationStatus?.replace(/_/g,' ')}</b><p>{displayedAutomationReason}</p></div></div>
          {stage==='review'&&<div className="review-plan-status"><label>검증 환경<select value={reviewEnvironmentId} onChange={event=>{setReviewEnvironmentId(event.target.value);setDiscoveryId(null);setDiscovery(null);setCandidateSelections({})}} disabled={planLoading||savingStep||discoveryStarting||Boolean(discoveryId)}>{reviewEnvironments.map(environment=><option key={environment.id} value={environment.id}>{environment.name}</option>)}</select></label><div><span>revision <b>{reviewPlan?.revision??'-'}</b></span><span>plan hash <b>{reviewPlan?.planHash?.slice(0,12)??'-'}</b></span><span className={reviewPlan?.executable?'plan-ok':'plan-blocked'}>{planLoading?'검증 중':reviewPlan?.executable?'실행 가능':'수정 필요'}</span><button className="secondary discovery-start" onClick={()=>void startDiscovery()} disabled={!reviewEnvironmentId||discoveryStarting||Boolean(discoveryId)}>{discoveryStarting?<Activity className="spin"/>:<Search/>} 페이지 분석 시작</button></div></div>}
          {stage==='review'&&discovery&&<div className="discovery-panel"><div className="discovery-head"><div><b>페이지 분석 · {discovery.status}</b><small>규칙 기반 후보 + Playwright 실제 검증 · AI 0회</small></div><span className={`resolution ${discovery.executable?'resolved':'needs-review'}`}>{discovery.executable?'후보 확인 완료':'검토 필요'}</span></div>{discovery.pages.map(page=><div className="discovery-page" key={page.fingerprint}><ExternalLink/><div><b>{page.title||'제목 없음'}</b><small>{page.url} · fingerprint {page.fingerprint.slice(0,12)} · iframe {page.iframeCount}{page.hasShadowDom?' · Shadow DOM':''}</small></div></div>)}{discovery.steps.map(step=><div className="discovery-step" key={step.stepId}><div className="discovery-step-title"><div><b>{step.targetDescription}</b><small>{step.stepId}</small></div><span className={`resolution ${step.resolutionStatus.toLowerCase()}`}>{step.resolutionStatus}</span></div>{step.candidates.length>0?<div className="candidate-list">{step.candidates.map(candidate=><label className={`${candidateSelections[step.stepId]===candidate.id?'selected':''} ${candidate.matchCount===1&&candidate.visible&&candidate.enabled?'valid':'invalid'}`} key={candidate.id}><input type="radio" name={`candidate-${step.stepId}`} value={candidate.id} checked={(candidateSelections[step.stepId]??step.selectedCandidateId)===candidate.id} onChange={()=>setCandidateSelections(current=>({...current,[step.stepId]:candidate.id}))} disabled={candidate.matchCount!==1||!candidate.visible||!candidate.enabled}/><span><b>{candidate.strategy} · {Math.round(candidate.confidence*100)}%</b><code>{candidate.selector}</code><small>일치 {candidate.matchCount} · {candidate.visible?'표시됨':'숨김'} · {candidate.enabled?'사용 가능':'비활성'}</small></span></label>)}</div>:<p className="discovery-empty">유효한 selector 후보를 찾지 못했습니다. 단계 편집 또는 재분석이 필요합니다.</p>}</div>)}{['COMPLETED','NEEDS_REVIEW','FAILED','CANCELLED'].includes(discovery.status)&&<div className="discovery-actions"><button className="secondary" onClick={()=>{setDiscoveryId(null);setDiscovery(null);setDiscoveryError(null);setCandidateSelections({})}}>닫기</button>{['COMPLETED','NEEDS_REVIEW'].includes(discovery.status)&&<button className="primary" onClick={()=>void applyDiscovery()} disabled={discoveryApplying||discovery.steps.some(step=>!(candidateSelections[step.stepId]??step.selectedCandidateId))}>{discoveryApplying?<Activity className="spin"/>:<Check/>} 분석 결과 적용</button>}</div>}</div>}
          {stage==='review'&&discoveryError&&<div className="config-error persistent-error"><AlertTriangle/><div><b>{discoveryError.code}</b><span>{discoveryError.message}</span></div><button type="button" className="secondary" onClick={()=>void startDiscovery()} disabled={discoveryStarting}>다시 분석</button></div>}
          {planError&&<div className="config-error"><AlertTriangle size={16}/><div><b>실행 계획 확인 실패</b><span>{planError}</span></div></div>}
          <div className="review-block"><label>전제조건 · {structured.preconditions.length}</label>{structured.preconditions.map(item=><div className="condition" key={item}><CheckCircle2/> {item}</div>)}</div>
          <div className="review-block"><label>실행 단계 · {(reviewPlan?.steps??structured.steps).length}</label>{(reviewPlan?.steps??structured.steps.map((step,index)=>({...step,stepNo:index+1,timeoutMs:step.timeoutMs??10000}))).map((step,i)=>{const warning=reviewPlan?.warnings.find(item=>item.stepId===step.id||item.stepNo===step.stepNo);const detail=step.action==='wait'?'문서 로딩 완료 대기':step.url||step.selector||('note' in step?step.note:'필수 값 확인 필요');return <div className={`structured-step ${warning?'invalid':''}`} key={step.id}><span>{step.stepNo??i+1}</span><div><b>{step.title}</b><small><em>{step.action.toUpperCase()}</em> {detail}</small>{warning&&<p className="step-warning">{warning.message}{warning.missingFields.length>0&&` · 누락: ${warning.missingFields.join(', ')}`}</p>}</div>{stage==='review'?<div className="step-row-actions"><button onClick={()=>openStepEditor(step as ExecutionPlanStep)} aria-label={`${step.title} 단계 편집`} title="단계 편집" disabled={Boolean(deletingStepId)}><Settings/></button><button className="delete-step" onClick={()=>void deleteStep(step as ExecutionPlanStep)} aria-label={`${step.title} 단계 삭제`} title="단계 삭제" disabled={Boolean(deletingStepId)}>{deletingStepId===step.id?<Activity className="spin"/>:<Trash2/>}</button></div>:<button aria-label={`${step.title} 추가 메뉴`}><MoreHorizontal/></button>}</div>})}</div>
          {stage==='review'&&editingStep&&<div className="step-editor"><div className="step-editor-head"><div><b>{editingStep.stepNo}단계 편집</b><small>{editingStep.title} · 변경된 필드만 서버에 저장합니다.</small></div><button onClick={()=>setEditingStep(null)} aria-label="단계 편집 닫기"><XCircle/></button></div><div className="step-editor-grid"><label>selector<input value={stepDraft.selector} onChange={e=>changeStepField('selector',e.target.value)} placeholder="예: #login-button"/></label><label>URL<input value={stepDraft.url} onChange={e=>changeStepField('url',e.target.value)} placeholder="예: /login 또는 https://..."/></label><label>operator<input value={stepDraft.operator} onChange={e=>changeStepField('operator',e.target.value)} placeholder="contains, equals, matches"/></label><label>expected<input value={stepDraft.expected} onChange={e=>changeStepField('expected',e.target.value)}/></label><label>value<input type="password" value={stepDraft.value} onChange={e=>changeStepField('value',e.target.value)} placeholder={editingStep.value==='***'?'기존 값 설정됨 · 변경 시에만 입력':'입력 값'}/></label><label>secretRef<input value={stepDraft.secretRef} onChange={e=>changeStepField('secretRef',e.target.value)} placeholder="예: TEST_PASSWORD"/></label><label>assertionType<select value={stepDraft.assertionType} onChange={e=>changeStepField('assertionType',e.target.value)}><option value="">선택 안 함</option><option value="url">url</option><option value="text">text</option><option value="element">element</option></select></label></div><div className="step-editor-actions"><button className="danger" onClick={()=>void deleteStep(editingStep)} disabled={Boolean(deletingStepId)||savingStep}>{deletingStepId===editingStep.id?<Activity className="spin"/>:<Trash2/>} 단계 삭제</button><span/><button className="secondary" onClick={()=>setEditingStep(null)} disabled={savingStep||Boolean(deletingStepId)}>취소</button><button className="primary" onClick={()=>void saveStep()} disabled={savingStep||Boolean(deletingStepId)||dirtyFields.length===0}>{savingStep?<Activity className="spin"/>:<Save/>} 저장 후 재검증</button></div></div>}
          <div className="review-block"><label>기대 결과 · {structured.assertions.length}</label>{structured.assertions.map((assertion,i)=><div className="assertion" key={`${assertion.type}-${i}`}><ShieldCheck/><div><b>{assertion.expected}</b><small>{assertion.type.toUpperCase()} · {assertion.operator.toUpperCase()} · timeout {assertion.timeoutMs/1000}s</small></div></div>)}</div>{stage==='review'&&structured.assumptions.length>0&&<div className="ambiguity"><AlertTriangle/><div><b>확인이 필요한 가정 {structured.assumptions.length}개</b>{structured.assumptions.map(item=><p key={item}>{item}</p>)}</div></div>}{stage==='ready'&&<div className="ready-box"><CheckCircle2/><div><b>실행 준비가 완료되었습니다.</b><p>승인된 {structured.versionId}은 수정할 수 없으며 변경 시 새 버전이 생성됩니다.</p></div></div>}</>}
      </article>
    </div>
  </section>
}

function ExecutionPlanPreview({structured,request,onBack,onConfirm,starting}:{structured:StructuredTestCase;request:CreateExecutionRequest;onBack:()=>void;onConfirm:()=>void;starting:boolean}) {
  const [plan,setPlan]=useState<ExecutionPlan|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{setPlan(null);setError('');api.getExecutionPlan(structured.versionId,request.environmentId).then(setPlan).catch(err=>setError(err instanceof ApiError?err.body.message:'실행 계획을 불러오지 못했습니다.'))},[structured.versionId,request.environmentId])
  const executable=plan?.executable===true&&plan.status==='READY'
  const steps=plan?.steps??[]
  return <section className="page plan-page"><div className="author-top"><button className="back-button" onClick={onBack}>← 실행 설정</button><span className={`stage-badge ${executable?'ready':'split-review'}`}>{executable?'EXECUTABLE':plan?'PLAN REVIEW REQUIRED':'PLAN LOADING'}</span></div><div className="page-heading compact"><div><p className="eyebrow">EXECUTION PLAN</p><h1>실행 예정 시나리오</h1><p>백엔드가 검증하고 Worker가 그대로 수행할 계획입니다.</p></div></div><div className="plan-summary"><article className="panel"><small>TC 버전</small><b>{structured.versionId}</b></article><article className="panel"><small>구조화 출처</small><b>{plan?.source??structured.aiUsage.source}</b></article><article className="panel"><small>실행 환경</small><b>{plan?.environment.name??request.environmentId}</b></article><article className="panel"><small>계획 revision</small><b>{plan?`${plan.revision} · ${plan.planHash?.slice(0,12)??'-'}`:'확인 중'}</b></article></div>{(error||plan&&!executable)&&<div className="config-error"><AlertTriangle size={16}/><div><b>실행할 수 없는 계획입니다.</b><span>{error||plan?.warnings.map(item=>`${item.stepNo?`${item.stepNo}단계 `:''}${item.message}`).join(' · ')}</span></div></div>}<div className="plan-grid"><article className="panel plan-steps"><div className="panel-head"><div><h2>예상 수행 단계</h2><p>{steps.length}개 단계 · 서버 검증 기준</p></div><span className={`pill ${executable?'pass':'fail'}`}>{executable?'READY':'BLOCKED'}</span></div>{steps.map(step=><div className="plan-step" key={step.id}><span>{step.stepNo}</span><div><b>{step.title}</b><small>{step.action.toUpperCase()} · {step.action==='wait'?'문서 로딩 완료 대기':step.url||step.selector||'필수 값 확인 필요'}</small>{step.action==='fill'&&<p>입력값: {step.value||step.secretRef||'-'}</p>}{step.action==='assert'&&<p>{step.operator} · {step.expected}</p>}</div></div>)}</article><aside className="panel plan-confirm"><ShieldCheck/><h2>최종 실행 확인</h2><p>서버의 plan hash와 단계가 실제 Worker 실행 기준입니다. 입력값은 마스킹됩니다.</p><dl><div><dt>단계</dt><dd>{steps.length}개</dd></div><div><dt>AI 호출 한도</dt><dd>{request.limits.maxAiCalls}회</dd></div><div><dt>재시도</dt><dd>{request.limits.retryCount}회</dd></div></dl><button className="primary wide" onClick={onConfirm} disabled={!executable||starting}>{starting?<Activity className="spin"/>:<Play/>} {starting?'실행 생성 중':'이 시나리오로 실행'}</button>{!executable&&<small>백엔드 실행 계획 검증을 통과해야 실행할 수 있습니다.</small>}</aside></div></section>
}

function RunConfigure({versionId,lockedEnvironmentId,onBack,onStart,starting}: {versionId:string; lockedEnvironmentId:string|null; onBack:()=>void; onStart:(input:CreateExecutionRequest)=>void; starting:boolean}) {
  const [environment,setEnvironment]=useState(lockedEnvironmentId??'env-staging')
  const [browser,setBrowser]=useState<CreateExecutionRequest['browser']>('Chromium')
  const [account,setAccount]=useState('qa-runner-01')
  const [viewport,setViewport]=useState('1440x900')
  const [locale,setLocale]=useState('ko-KR')
  const [duration,setDuration]=useState('15')
  const [maxAiCalls,setMaxAiCalls]=useState('0')
  const [retryCount,setRetryCount]=useState('2')
  const [approval,setApproval]=useState(true)
  const [environments,setEnvironments]=useState<EnvironmentSummary[]>([])
  const [accounts,setAccounts]=useState<TestAccountSummary[]>([])
  const [policy,setPolicy]=useState<ExecutionPolicy|null>(null)
  const [loadingResources,setLoadingResources]=useState(true)
  const [resourceError,setResourceError]=useState('')
  useEffect(()=>{Promise.all([api.listEnvironments(),api.listTestAccounts(),api.getExecutionPolicy()]).then(([nextEnvironments,nextAccounts,nextPolicy])=>{
    setEnvironments(nextEnvironments);setAccounts(nextAccounts);setPolicy(nextPolicy)
    const initialEnvironment=nextEnvironments.find(item=>item.id===lockedEnvironmentId)??nextEnvironments[0]
    if(initialEnvironment){setEnvironment(initialEnvironment.id);setViewport(initialEnvironment.defaultViewport)}
    if(nextAccounts[0])setAccount(nextAccounts[0].id)
    if(nextPolicy.supportedBrowsers[0])setBrowser(nextPolicy.supportedBrowsers[0])
    setApproval(nextPolicy.requireRiskApproval)
  }).catch(error=>setResourceError(error instanceof ApiError?error.body.message:'실행 설정을 불러오지 못했습니다.')).finally(()=>setLoadingResources(false))},[])
  const selectedEnvironment=environments.find(item=>item.id===environment)
  const selectedAccount=accounts.find(item=>item.id===account)
  const durationOptions=['10','15','30'].filter(value=>Number(value)<=(policy?.maxTimeoutMinutes??30))
  const allowedMaxAiCalls=Math.min(Math.max(policy?.maxAiCalls??0,0),1)
  const aiCallOptions=Array.from({length:allowedMaxAiCalls+1},(_,index)=>({value:String(index),label:`${index}회`}))
  const retryOptions=['0','1','2'].filter(value=>Number(value)<=(policy?.maxRetries??2))
  const submit = () => onStart({ testCaseVersionId:versionId, environmentId:environment, browser, accountId:account, viewport, locale, limits:{timeoutMinutes:Number(duration),maxAiCalls:Math.min(Number(maxAiCalls),allowedMaxAiCalls),retryCount:Number(retryCount)}, requireRiskApproval:approval })
  return <section className="page config-page">
    <div className="author-top"><button className="back-button" onClick={onBack}>← 구조화 검토</button><span className="config-id">TC-NEW · Version 1 · READY</span></div>
    <div className="page-heading compact"><div><p className="eyebrow">EXECUTION SETUP</p><h1>실행 설정</h1><p>격리된 브라우저에서 사용할 환경, 계정과 안전 한도를 확인하세요.</p></div></div>
    {resourceError&&<div className="config-error"><AlertTriangle size={15}/>{resourceError}</div>}
    <div className="config-grid"><div className="config-main">
      <ConfigCard icon={<MonitorCheck/>} title="실행 환경" caption="테스트 대상과 브라우저 조건">
        <div className="form-grid"><Field label="환경"><Select value={environment} disabled={Boolean(lockedEnvironmentId)} setValue={value=>{setEnvironment(value);const target=environments.find(item=>item.id===value);if(target)setViewport(target.defaultViewport)}} options={environments.map(item=>({value:item.id,label:item.name}))}/></Field><Field label="브라우저"><Select value={browser} setValue={value=>setBrowser(value as CreateExecutionRequest['browser'])} options={policy?.supportedBrowsers??['Chromium']}/></Field><Field label="화면 크기"><Select value={viewport} setValue={setViewport} options={[...new Set([selectedEnvironment?.defaultViewport??'1440x900','1920x1080','1280x720'])]}/></Field><Field label="언어"><Select value={locale} setValue={setLocale} options={['ko-KR','en-US']}/></Field></div><div className="safe-domain"><ShieldCheck/><div><b>{lockedEnvironmentId?'페이지 분석 환경 · 변경 불가':'허용 도메인'}</b><span>{selectedEnvironment?.allowedDomains.join(', ')||'환경을 불러오는 중입니다.'}</span></div></div>
      </ConfigCard>
      <ConfigCard icon={<KeyRound/>} title="테스트 계정과 데이터" caption="비밀값은 실행 시에만 Worker 메모리에 주입됩니다." tone="violet">
        <div className="form-grid"><Field label="테스트 계정"><Select value={account} setValue={setAccount} options={accounts.map(item=>({value:item.id,label:item.name}))}/></Field><Field label="데이터 세트"><Select value="signup-default-v2" options={['signup-default-v2']}/></Field></div><div className="account-status"><span/><div><b>{selectedAccount?.name??'계정 로딩 중'}</b><small>{selectedAccount?.status??'-'}</small></div><button>계정 상세 <ExternalLink/></button></div>
      </ConfigCard>
      <ConfigCard icon={<Gauge/>} title="실행 한도" caption="무한 반복과 예상치 못한 비용을 방지합니다." tone="amber">
        <div className="form-grid triple"><Field label="최대 실행 시간"><Select value={duration} setValue={setDuration} options={durationOptions}/></Field><Field label="최대 AI 호출"><Select value={maxAiCalls} setValue={setMaxAiCalls} options={aiCallOptions}/></Field><Field label="오류 재시도"><Select value={retryCount} setValue={setRetryCount} options={retryOptions}/></Field></div><div className="toggle-row"><div><b>위험 행동 시 사람 승인</b><span>서버 정책에 따라 위험 행동에서 실행을 일시정지합니다.</span></div><button className={`toggle ${approval?'on':''}`} onClick={()=>setApproval(!approval)} aria-pressed={approval}><i/></button></div>
      </ConfigCard>
    </div><aside className="panel launch-summary"><p className="eyebrow">EXECUTION SUMMARY</p><h2>승인된 TC 실행</h2><span className="summary-ready"><CheckCircle2/> {loadingResources?'설정 확인 중':'실행 준비 완료'}</span><dl><div><dt>환경</dt><dd>{selectedEnvironment?.name??environment}</dd></div><div><dt>브라우저</dt><dd>{browser}</dd></div><div><dt>계정</dt><dd>{selectedAccount?.name??account}</dd></div><div><dt>화면</dt><dd>{viewport}</dd></div><div><dt>AI 호출</dt><dd>{maxAiCalls}회</dd></div><div><dt>시간 제한</dt><dd>{duration}분</dd></div></dl><div className="cost-estimate"><Sparkles/><div><span>AI API 상태</span><b>{Number(maxAiCalls)===0?'비활성 · 토큰 사용 없음':`최대 ${maxAiCalls}회`}</b></div></div><button className="primary wide launch" onClick={submit} disabled={starting||loadingResources||Boolean(resourceError)||!environment||!account}><Eye/> 실행 예정 시나리오 확인</button><p className="launch-note"><ShieldCheck/> 시나리오 확인 후에만 Worker 실행이 생성됩니다.</p></aside></div>
  </section>
}

function ConfigCard({icon,title,caption,tone='',children}:{icon:React.ReactNode;title:string;caption:string;tone?:string;children:React.ReactNode}){return <article className="panel config-card"><div className="config-card-title"><span className={tone}>{icon}</span><div><h2>{title}</h2><p>{caption}</p></div></div>{children}</article>}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="config-field"><span>{label}</span>{children}</label>}
type SelectOption=string|{value:string;label:string}
function Select({value,options,setValue,disabled=false}:{value:string;options:SelectOption[];setValue?:(v:string)=>void;disabled?:boolean}){return <div className="select-wrap"><select value={value} onChange={e=>setValue?.(e.target.value)} disabled={disabled}>{options.map(option=>{const item=typeof option==='string'?{value:option,label:option}:option;return <option value={item.value} key={item.value}>{item.label}</option>})}</select><ChevronDown/></div>}

function stepAction(step: ExecutionStepRun) {
  return typeof step.action?.type === 'string' ? step.action.type.toUpperCase() : 'ACTION'
}

function stepTitle(step: ExecutionStepRun) {
  const type = stepAction(step)
  return type === 'NAVIGATE' ? '페이지 이동' : type === 'FILL' ? '값 입력' : type === 'CLICK' ? '요소 클릭' : type === 'ASSERT' ? '화면 검증' : `단계 ${step.stepNo}`
}

function RunMonitor({state,execution,details,activeStep,start,stop,onResult}: {state:RunState; execution:Execution|null; details:ExecutionDetails|null; activeStep:number; start:()=>void; stop:()=>void; onResult:()=>void}) {
  const running = state === 'running' || state === 'paused'
  const terminal = state === 'done' || state === 'failed'
  const statusLabel = execution?.status ?? (state === 'idle' ? 'READY' : 'RUNNING')
  const latestArtifact = details?.artifacts[(details?.artifacts.length ?? 0) - 1]
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">LIVE EXECUTION</p><h1>실행 모니터</h1><p>{running ? `${execution?.id ?? '실행 준비 중'} · ${statusLabel}` : state==='done' ? '실행이 성공적으로 완료되었습니다.' : state==='failed' ? `실행이 ${statusLabel} 상태로 종료되었습니다.` : '현재 실행 중인 테스트가 없습니다.'}</p></div><div className="run-controls">{!running && !terminal && <button className="primary" onClick={start}><Play size={16}/> 실행 시작</button>}{running && <button className="danger" onClick={stop}><Square size={15}/> 중단 요청</button>}{terminal&&<><button className="secondary" onClick={start}><RefreshCw size={15}/> 다시 실행</button><button className="primary" onClick={onResult}>결과 상세 <ArrowRight size={15}/></button></>}</div></div>
    <div className="monitor-grid"><article className="panel browser-panel"><div className="browser-top"><span/><span/><span/><div>{latestArtifact?.objectKey??execution?.id??'Playwright 실행 세션 준비 중'}</div><ShieldCheck size={15}/></div><div className={`execution-surface ${latestArtifact?'has-artifact':''}`}>{latestArtifact&&execution?<><img className="monitor-artifact" src={api.artifactUrl(execution.id,latestArtifact.id)} alt="Worker가 저장한 최신 실행 화면"/><div className="monitor-evidence-label"><Eye size={14}/><b>Worker 최종 화면</b><span>{latestArtifact.type}</span></div></>:<div className={`execution-state ${state}`} >{running?<Activity className="spin"/>:state==='done'?<CheckCircle2/>:state==='failed'?<XCircle/>:<MonitorCheck/>}<h2>{running?'실제 브라우저를 실행하고 있습니다.':state==='done'?'실행은 완료됐지만 화면 증적이 없습니다.':state==='failed'?'실행에 실패했습니다.':'실행 대기 중입니다.'}</h2><p>{terminal?'이 실행은 화면 캡처 저장 이전 결과일 수 있습니다. 새 버전으로 다시 실행해 주세요.':'Worker가 단계를 완료하면 실제 테스트 페이지의 최종 화면을 표시합니다.'}</p><dl><div><dt>Execution</dt><dd>{execution?.id??'-'}</dd></div><div><dt>TC Version</dt><dd>{execution?.testCaseVersionId??'-'}</dd></div><div><dt>Status</dt><dd>{statusLabel}</dd></div><div><dt>기록된 단계</dt><dd>{details?.steps.length??0}개</dd></div></dl></div>}</div></article>
      <article className="panel timeline"><div className="panel-head"><div><h2>Worker 실행 단계</h2><p>실제 상태 · {statusLabel}</p></div><span className={`live ${state}`}>{statusLabel}</span></div><div className="step-list">{details?.steps.length ? details.steps.map((s,i)=>{const done=s.status==='PASS'; const failed=s.status==='FAIL'||Boolean(s.errorCode); return <div className={`step ${done?'done':''} ${failed?'failed':''}`} key={s.id}><span>{done?<Check/>:failed?<XCircle/>:i+1}</span><div><b>{stepTitle(s)}</b><p>{typeof s.action?.selector==='string'?s.action.selector:typeof s.action?.url==='string'?s.action.url:'구조화된 테스트 단계'}</p><small>{stepAction(s)} · {s.status}{s.errorCode&&` · ${s.errorCode}`}</small></div></div>}) : workerSteps.map((s,i)=>{const done=i<activeStep&&state!=='failed'; const active=i===activeStep&&running; return <div className={`step ${done?'done':''} ${active?'active':''}`} key={s.title}><span>{done?<Check/>:active?<Activity/>:i+1}</span><div><b>{s.title}</b><p>{s.note}</p><small>{s.type} {done&&'· 완료'}</small></div></div>})}</div><div className="budget"><div><span>완료 단계</span><b>{details?.steps.filter(s=>s.status==='PASS').length ?? activeStep} / {details?.steps.length || workerSteps.length}</b></div><div className="budget-bar"><i style={{width:`${details?.steps.length ? details.steps.filter(s=>s.status==='PASS').length/details.steps.length*100 : Math.min(activeStep*33,100)}%`}}/></div><div><span>증적 파일</span><b>{details?.artifacts.length ?? 0}개</b></div></div></article></div>
  </section>
}

function ResultDetail({execution,details,onBack,onRetry}:{execution:Execution|null;details:ExecutionDetails|null;onBack:()=>void;onRetry:()=>void}){
  const [selected,setSelected]=useState(0)
  const passed=execution?.status==='PASS'||!execution
  const selectedStep=details?.steps[selected]
  const selectedArtifact=details?.artifacts.find(a=>a.stepRunId===selectedStep?.id) ?? details?.artifacts[0]
  return <section className="page result-page"><div className="author-top"><button className="back-button" onClick={onBack}>← 대시보드</button><div className="author-actions"><button className="secondary" disabled><Download/> 내보내기 준비 중</button><button className="primary" onClick={onRetry}><RefreshCw/> 다시 실행</button></div></div>
    <div className={`result-hero ${passed?'':'result-failed'}`}><div className="result-check">{passed?<Check/>:<XCircle/>}</div><div><p className="eyebrow">EXECUTION COMPLETED</p><h1>{passed?'구조화 테스트를 통과했습니다.':'구조화 테스트 실행에 실패했습니다.'}</h1><p>{details?.steps.length ?? 0}개 단계 실행 · {execution?.id ?? 'EX-DEMO'}</p></div><div className="result-stats"><div><span>결과</span><b className={passed?'green-text':'red-text'}>{execution?.status ?? 'PASS'}</b></div><div><span>오류 코드</span><b>{details?.errorCode ?? '-'}</b></div><div><span>증적</span><b>{details?.artifacts.length ?? 0}개</b></div><div><span>완료 시각</span><b>{execution?.endedAt ? new Date(execution.endedAt).toLocaleTimeString('ko-KR') : '-'}</b></div></div></div>
    <div className="result-grid"><article className="panel evidence-list"><div className="panel-head"><div><h2>단계별 실행 결과</h2><p>{details?.steps.length ?? 0}개 단계 · {details?.artifacts.length ?? 0}개 증적</p></div><span className={`pill ${passed?'pass':'fail'}`}>{execution?.status ?? 'PASS'}</span></div>{details?.steps.length ? details.steps.map((step,i)=><button className={`evidence-row ${selected===i?'selected':''}`} onClick={()=>setSelected(i)} key={step.id}><span className="evidence-check">{step.status==='PASS'?<Check/>:<XCircle/>}</span><div><b>{step.stepNo}. {stepTitle(step)}</b><small><em>{stepAction(step)}</em> · {step.errorCode ?? step.status}</small></div><time>{step.endedAt?'완료':'-'}</time><ChevronRight/></button>) : <div className="empty-table">저장된 단계 결과가 없습니다.</div>}</article>
      <article className="panel evidence-detail"><div className="detail-tabs"><button className="active"><Eye/> 단계 상세</button><button><TerminalSquare/> 증적 정보</button></div><div className="evidence-screen"><div className="screen-toolbar"><i/><i/><i/><span>{selectedArtifact?.objectKey ?? '저장된 화면 증적이 없습니다.'}</span></div>{selectedArtifact&&execution?<img className="artifact-preview" src={api.artifactUrl(execution.id,selectedArtifact.id)} alt={`${selectedArtifact.type} 실행 증적`}/>:<div className="screen-content"><div className="mini-nav"><b>Playwright Worker</b><span/><span/><span/></div><div className="mini-welcome"><small>{selectedStep ? stepAction(selectedStep) : 'NO STEP'}</small><h2>{selectedStep ? stepTitle(selectedStep) : '단계를 선택해 주세요.'}</h2><p>{selectedStep?.errorCode ? `오류 코드: ${selectedStep.errorCode}` : selectedStep?.assertion ? `Assertion: ${String(selectedStep.assertion.operator ?? '검증 완료')}` : `상태: ${selectedStep?.status ?? '-'}`}</p><div><span/><span/><span/></div></div><div className="assert-highlight">{selectedStep?.status==='PASS'?<CheckCircle2/>:<XCircle/>}<b>{selectedStep?.status ?? '대기'}</b><span>{selectedArtifact ? `${selectedArtifact.type} · ${Math.ceil(selectedArtifact.sizeBytes/1024)} KB` : '증적 없음'}</span></div></div>}</div><div className="evidence-meta"><div><span>선택 단계</span><b>{selectedStep?.stepNo ?? '-'}. {selectedStep ? stepTitle(selectedStep) : '-'}</b></div><div><span>Selector</span><b>{typeof selectedStep?.action?.selector==='string'?selectedStep.action.selector:'-'}</b></div><div><span>오류 코드</span><b>{selectedStep?.errorCode ?? details?.errorCode ?? '-'}</b></div></div></article>
    </div>
  </section>
}

export default App
