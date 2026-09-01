import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, Bot, Check, CheckCircle2,
  ChevronDown, CircleDot, Clock3, FileText, Gauge, LayoutDashboard,
  ListChecks, MoreHorizontal, Play, Plus, Search, Settings,
  ShieldCheck, Sparkles, Square, TerminalSquare, TestTube2, Users, XCircle,
  Upload, WandSparkles, Save, Database, KeyRound, MonitorCheck,
  Download, ExternalLink, RefreshCw, Eye, ChevronRight,
} from 'lucide-react'
import { api, apiConfig, ApiError } from './api/client'
import type { AuthenticatedUser, CreateExecutionRequest, EnvironmentSummary, Execution, ExecutionDetails, ExecutionPolicy, ExecutionStepRun, StructuredTestCase, TestAccountSummary, TestCaseSummary } from './api/types'

type View = 'dashboard' | 'cases' | 'author' | 'configure' | 'run' | 'result' | 'environments' | 'accounts' | 'policies'
type RunState = 'idle' | 'running' | 'paused' | 'done' | 'failed'
type AuthorStage = 'draft' | 'structuring' | 'review' | 'ready'
type ApiConnection = 'mock' | 'checking' | 'online' | 'offline'
type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'
const ACTIVE_EXECUTION_KEY = 'tracepilot.activeExecutionId'

const workerSteps = [
  { title: '실행 대기열 등록', note: 'Redis Stream에서 Worker 할당을 기다립니다.', type: 'QUEUE' },
  { title: '격리 브라우저 준비', note: 'Chromium 컨텍스트와 viewport를 생성합니다.', type: 'PROVISION' },
  { title: '대상 페이지 접속', note: '허용 도메인을 검사하고 DOM 로드를 확인합니다.', type: 'NAVIGATE' },
]
const defaultExecution: CreateExecutionRequest = { testCaseVersionId:'tcv-new-v1', environmentId:'env-staging', browser:'Chromium', accountId:'qa-runner-01', viewport:'1440x900', locale:'ko-KR', limits:{timeoutMinutes:15,maxAiCalls:0,retryCount:2}, requireRiskApproval:true }

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
        window.setTimeout(() => { setExecution(current=>current?{...current,status:'PASS',endedAt:new Date().toISOString()}:current); setActiveStep(3); setRunState('done') }, 2800)
      }
    } catch (error) {
      toast(error instanceof ApiError ? error.body.message : '실행을 시작하지 못했습니다.')
    } finally { setStartingRun(false) }
  }
  const startRun = () => createRun(defaultExecution)
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

  const toast = (message: string) => { setNotice(message); window.setTimeout(() => setNotice(''), 2200) }

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
        {view === 'cases' && <Cases query={query} setQuery={setQuery} rows={filtered} loading={loadingCases} onRun={startRun} onCreate={() => {setAuthorStage('draft'); setView('author')}} onToast={toast}/>}
        {view === 'author' && <Author stage={authorStage} setStage={setAuthorStage} onBack={() => setView('cases')} onRun={() => setView('configure')} onToast={toast}/>} 
        {view === 'configure' && <RunConfigure onBack={() => setView('author')} onStart={createRun} starting={startingRun}/>}
        {view === 'run' && <RunMonitor state={runState} execution={execution} details={executionDetails} activeStep={activeStep} start={startRun} stop={cancelRun} onResult={() => setView('result')}/>}
        {view === 'result' && <ResultDetail execution={execution} details={executionDetails} onBack={() => setView('dashboard')} onRetry={retryRun}/>}
        {view === 'environments' && <ManagementPage kind="environment" onToast={toast}/>}
        {view === 'accounts' && <ManagementPage kind="account" onToast={toast}/>}
        {view === 'policies' && <ManagementPage kind="policy" onToast={toast}/>}
      </main>
      {notice && <div className="toast"><Check size={16}/>{notice}</div>}
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
  return <section className="page dashboard">
    <div className="page-heading"><div><p className="eyebrow">THURSDAY, AUGUST 27</p><h1>좋은 오후예요, 민준님.</h1><p>오늘도 안정적인 릴리스를 위한 테스트를 시작해 볼까요?</p></div><button className="secondary"><Clock3 size={16}/> 최근 7일 <ChevronDown size={15}/></button></div>
    <div className="metrics">
      <Metric icon={<TestTube2/>} label="전체 실행" value="184" delta="+12.5%" tone="blue"/>
      <Metric icon={<CheckCircle2/>} label="통과율" value="92.4%" delta="+3.2%" tone="green"/>
      <Metric icon={<Clock3/>} label="평균 실행 시간" value="2m 18s" delta="-18s" tone="violet"/>
      <Metric icon={<Gauge/>} label="AI API" value="OFF" delta="토큰 사용 없음" tone="amber"/>
    </div>
    <div className="dashboard-grid">
      <article className="panel runs-panel">
        <div className="panel-head"><div><h2>최근 실행</h2><p>프로젝트의 최신 자동화 결과입니다.</p></div><button className="text-button" onClick={onCases}>전체 보기 <ArrowRight size={15}/></button></div>
        <div className="run-row"><StatusIcon type="pass"/><div><b>신규 사용자 이메일 회원가입</b><small>TC-142 · Chrome · 12분 전</small></div><span className="pill pass">PASS</span><time>1m 42s</time><MoreHorizontal/></div>
        <div className="run-row"><StatusIcon type="running"/><div><b>상품 검색 및 필터 적용</b><small>TC-138 · Chrome · 실행 중</small></div><span className="pill running">RUNNING</span><time>00:48</time><MoreHorizontal/></div>
        <div className="run-row"><StatusIcon type="fail"/><div><b>장바구니 수량 변경</b><small>TC-131 · Chrome · 1시간 전</small></div><span className="pill fail">FAILED</span><time>2m 09s</time><MoreHorizontal/></div>
        <div className="run-row"><StatusIcon type="pass"/><div><b>만료 세션 리다이렉트</b><small>TC-127 · Chrome · 어제</small></div><span className="pill pass">PASS</span><time>0m 56s</time><MoreHorizontal/></div>
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

function Cases({query,setQuery,rows,loading,onRun,onCreate,onToast}: {query:string; setQuery:(s:string)=>void; rows:TestCaseSummary[]; loading:boolean; onRun:()=>void; onCreate:()=>void; onToast:(s:string)=>void}) {
  const [status,setStatus] = useState('ALL')
  const [group,setGroup] = useState('ALL')
  const visibleRows = rows.filter(row => (status === 'ALL' || row.status === status) && (group === 'ALL' || row.group === group))
  const groups = [...new Set(rows.map(row => row.group))]
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">TEST LIBRARY</p><h1>테스트 케이스</h1><p>자연어 TC를 구조화하고 실행 준비 상태를 관리합니다.</p></div><button className="primary" onClick={onCreate}><Plus size={16}/> 새 테스트 케이스</button></div>
    <div className="toolbar"><div className="search"><Search size={17}/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="ID, 이름 또는 그룹 검색"/></div><Select value={status} setValue={setStatus} options={['ALL','READY','REVIEW_REQUIRED']}/><Select value={group} setValue={setGroup} options={['ALL',...groups]}/><button className="secondary" onClick={()=>onToast('XLSX 가져오기는 백엔드 파서 연결 후 활성화됩니다.')}><Upload size={15}/> 파일 가져오기</button></div>
    <article className="panel table-panel"><table><thead><tr><th>테스트 케이스</th><th>그룹</th><th>준비 상태</th><th>최근 성공률</th><th>마지막 실행</th><th/></tr></thead><tbody>{visibleRows.map((row)=><tr key={row.id}><td><span className="file-icon"><FileText/></span><span><b>{row.title}</b><small>{row.id}</small></span></td><td>{row.group}</td><td><span className={`pill ${row.status==='READY'?'pass':'review'}`}>{row.status.replace('_',' ')}</span></td><td><div className="rate"><span><i style={{width:`${row.passRate}%`}}/></span>{row.passRate}%</div></td><td>{row.lastExecutedAt}</td><td><button className="row-play" onClick={onRun} aria-label={`${row.title} 실행`}><Play size={14}/></button></td></tr>)}</tbody></table>{loading&&<div className="empty-table"><Activity className="spin" size={16}/> 테스트 케이스를 불러오는 중입니다.</div>}{!loading&&visibleRows.length===0&&<div className="empty-table">조건에 맞는 테스트 케이스가 없습니다.</div>}</article>
  </section>
}

function Author({stage,setStage,onBack,onRun,onToast}: {stage:AuthorStage; setStage:(s:AuthorStage)=>void; onBack:()=>void; onRun:()=>void; onToast:(s:string)=>void}) {
  const [title,setTitle] = useState('신규 사용자 이메일 회원가입')
  const [raw,setRaw] = useState('Staging 환경에 접속한다.\n회원가입 버튼을 누르고 사용하지 않은 이메일과 안전한 비밀번호를 입력한다.\n약관에 동의한 뒤 가입을 완료한다.\n가입 완료 후 환영 메시지와 대시보드가 표시되는지 확인한다.')
  const [importedFile,setImportedFile] = useState('')
  const [structured,setStructured] = useState<StructuredTestCase | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const importFile = (file?: File) => {
    if (!file) return
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!['csv','xlsx','docx','txt'].includes(extension ?? '')) return onToast('지원하지 않는 파일 형식입니다.')
    setImportedFile(file.name)
    if (extension === 'txt' || extension === 'csv') file.text().then(text => { setRaw(text); setTitle(file.name.replace(/\.[^.]+$/, '')); onToast(`${file.name} 내용을 불러왔습니다.`) })
    else onToast(`${file.name}을 선택했습니다. 서버 파서 연결 후 분석할 수 있습니다.`)
  }
  const structure = async () => {
    if (!title.trim() || raw.trim().length < 10) return onToast('테스트 이름과 10자 이상의 원문을 입력해 주세요.')
    setStage('structuring')
    try { setStructured(await api.structureTestCase(title.trim(),raw.trim())); setStage('review') }
    catch (error) { setStage('draft'); onToast(error instanceof ApiError ? error.body.message : 'TC 구조화에 실패했습니다. 다시 시도해 주세요.') }
  }
  return <section className="page author-page">
    <div className="author-top"><button className="back-button" onClick={onBack}>← 테스트 케이스</button><div className="author-actions"><button className="secondary" onClick={()=>onToast('초안을 저장했습니다.')}><Save size={15}/> 초안 저장</button>{stage==='review'&&<button className="primary" onClick={()=>setStage('ready')}><Check size={15}/> 검토 승인</button>}{stage==='ready'&&<button className="primary" onClick={onRun}><Play size={15}/> 실행 설정</button>}</div></div>
    <div className="author-heading"><div><span className={`stage-badge ${stage}`}>{stage==='draft'?'DRAFT':stage==='structuring'?'STRUCTURING':stage==='review'?'REVIEW REQUIRED':'READY'}</span><h1>{title}</h1><p>TC-NEW · Storefront QA · Version 1</p></div><div className="progress-steps"><span className="complete"><Check/>원문 작성</span><i/><span className={stage!=='draft'?'complete':''}><WandSparkles/>규칙 기반 구조화</span><i/><span className={stage==='ready'?'complete':''}><ShieldCheck/>검토 승인</span></div></div>
    <div className="author-grid">
      <article className="panel editor-panel"><div className="section-head"><div><h2>자연어 테스트 케이스</h2><p>사람이 이해하기 쉬운 방식으로 수행 조건과 기대 결과를 작성하세요.</p></div><button className="secondary" onClick={()=>fileInput.current?.click()}><Upload size={15}/> 파일 가져오기</button><input ref={fileInput} className="file-input" type="file" accept=".csv,.xlsx,.docx,.txt" onChange={e=>importFile(e.target.files?.[0])}/></div>{importedFile&&<div className="imported-file"><FileText size={14}/><span>{importedFile}</span><button onClick={()=>{setImportedFile('');if(fileInput.current)fileInput.current.value=''}} aria-label="가져온 파일 제거"><XCircle size={14}/></button></div>}<label className="field-label">테스트 이름</label><input className="field-input" value={title} onChange={e=>setTitle(e.target.value)}/><label className="field-label">원문 TC</label><textarea className="tc-editor" value={raw} onChange={e=>setRaw(e.target.value)}/><div className="editor-meta"><span>{raw.length}자</span><span>CSV · XLSX · DOCX · TXT 지원</span></div><button className="ai-button" onClick={structure} disabled={stage==='structuring'}>{stage==='structuring'?<><Activity className="spin"/> TC를 구조화하고 있습니다...</>:<><WandSparkles/> 규칙 기반으로 구조화 <ArrowRight/></>}</button></article>
      <article className={`panel review-panel ${stage==='draft'?'empty-review':''}`}>
        {stage==='draft'&&<div className="review-empty"><div><Bot/></div><h2>구조화 결과가 여기에 표시됩니다.</h2><p>현재는 AI 토큰 없이 전제조건, 실행 단계와 기대 결과를 안전한 규칙으로 분리합니다.</p><ul><li><Check/> 허용된 action으로 변환</li><li><Check/> 규칙 기반 assertion 생성</li><li><Check/> 위험 행동 자동 감지</li></ul></div>}
        {stage==='structuring'&&<div className="review-empty"><div className="pulse"><WandSparkles/></div><h2>TC 구조를 분석하는 중입니다.</h2><p>단계와 검증 조건을 안전한 실행 명령으로 변환하고 있습니다.</p><div className="skeleton-lines"><i/><i/><i/><i/></div></div>}
        {(stage==='review'||stage==='ready')&&structured&&<><div className="section-head"><div><h2>구조화 검토</h2><p>AI 생성 결과를 실행 전에 확인하세요.</p></div><span className="confidence">신뢰도 <b>{Math.round(structured.confidence*100)}%</b></span></div><div className="review-block"><label>전제조건 · {structured.preconditions.length}</label>{structured.preconditions.map(item=><div className="condition" key={item}><CheckCircle2/> {item}</div>)}</div><div className="review-block"><label>실행 단계 · {structured.steps.length}</label>{structured.steps.map((step,i)=><div className="structured-step" key={step.id}><span>{i+1}</span><div><b>{step.title}</b><small><em>{step.action.toUpperCase()}</em> {step.note}</small></div><button aria-label={`${step.title} 추가 메뉴`}><MoreHorizontal/></button></div>)}</div><div className="review-block"><label>기대 결과 · {structured.assertions.length}</label>{structured.assertions.map((assertion,i)=><div className="assertion" key={`${assertion.type}-${i}`}><ShieldCheck/><div><b>{assertion.expected}</b><small>{assertion.type.toUpperCase()} · {assertion.operator.toUpperCase()} · timeout {assertion.timeoutMs/1000}s</small></div></div>)}</div>{stage==='review'&&structured.assumptions.length>0&&<div className="ambiguity"><AlertTriangle/><div><b>확인이 필요한 가정 {structured.assumptions.length}개</b>{structured.assumptions.map(item=><p key={item}>{item}</p>)}</div></div>}{stage==='ready'&&<div className="ready-box"><CheckCircle2/><div><b>실행 준비가 완료되었습니다.</b><p>승인된 {structured.versionId}은 수정할 수 없으며 변경 시 새 버전이 생성됩니다.</p></div></div>}</>}
      </article>
    </div>
  </section>
}

function RunConfigure({onBack,onStart,starting}: {onBack:()=>void; onStart:(input:CreateExecutionRequest)=>void; starting:boolean}) {
  const [environment,setEnvironment]=useState('env-staging')
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
    if(nextEnvironments[0]){setEnvironment(nextEnvironments[0].id);setViewport(nextEnvironments[0].defaultViewport)}
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
  const submit = () => onStart({ testCaseVersionId:'tcv-new-v1', environmentId:environment, browser, accountId:account, viewport, locale, limits:{timeoutMinutes:Number(duration),maxAiCalls:Math.min(Number(maxAiCalls),allowedMaxAiCalls),retryCount:Number(retryCount)}, requireRiskApproval:approval })
  return <section className="page config-page">
    <div className="author-top"><button className="back-button" onClick={onBack}>← 구조화 검토</button><span className="config-id">TC-NEW · Version 1 · READY</span></div>
    <div className="page-heading compact"><div><p className="eyebrow">EXECUTION SETUP</p><h1>실행 설정</h1><p>격리된 브라우저에서 사용할 환경, 계정과 안전 한도를 확인하세요.</p></div></div>
    {resourceError&&<div className="config-error"><AlertTriangle size={15}/>{resourceError}</div>}
    <div className="config-grid"><div className="config-main">
      <ConfigCard icon={<MonitorCheck/>} title="실행 환경" caption="테스트 대상과 브라우저 조건">
        <div className="form-grid"><Field label="환경"><Select value={environment} setValue={value=>{setEnvironment(value);const target=environments.find(item=>item.id===value);if(target)setViewport(target.defaultViewport)}} options={environments.map(item=>({value:item.id,label:item.name}))}/></Field><Field label="브라우저"><Select value={browser} setValue={value=>setBrowser(value as CreateExecutionRequest['browser'])} options={policy?.supportedBrowsers??['Chromium']}/></Field><Field label="화면 크기"><Select value={viewport} setValue={setViewport} options={[...new Set([selectedEnvironment?.defaultViewport??'1440x900','1920x1080','1280x720'])]}/></Field><Field label="언어"><Select value={locale} setValue={setLocale} options={['ko-KR','en-US']}/></Field></div><div className="safe-domain"><ShieldCheck/><div><b>허용 도메인</b><span>{selectedEnvironment?.allowedDomains.join(', ')||'환경을 불러오는 중입니다.'}</span></div></div>
      </ConfigCard>
      <ConfigCard icon={<KeyRound/>} title="테스트 계정과 데이터" caption="비밀값은 실행 시에만 Worker 메모리에 주입됩니다." tone="violet">
        <div className="form-grid"><Field label="테스트 계정"><Select value={account} setValue={setAccount} options={accounts.map(item=>({value:item.id,label:item.name}))}/></Field><Field label="데이터 세트"><Select value="signup-default-v2" options={['signup-default-v2']}/></Field></div><div className="account-status"><span/><div><b>{selectedAccount?.name??'계정 로딩 중'}</b><small>{selectedAccount?.status??'-'}</small></div><button>계정 상세 <ExternalLink/></button></div>
      </ConfigCard>
      <ConfigCard icon={<Gauge/>} title="실행 한도" caption="무한 반복과 예상치 못한 비용을 방지합니다." tone="amber">
        <div className="form-grid triple"><Field label="최대 실행 시간"><Select value={duration} setValue={setDuration} options={durationOptions}/></Field><Field label="최대 AI 호출"><Select value={maxAiCalls} setValue={setMaxAiCalls} options={aiCallOptions}/></Field><Field label="오류 재시도"><Select value={retryCount} setValue={setRetryCount} options={retryOptions}/></Field></div><div className="toggle-row"><div><b>위험 행동 시 사람 승인</b><span>서버 정책에 따라 위험 행동에서 실행을 일시정지합니다.</span></div><button className={`toggle ${approval?'on':''}`} onClick={()=>setApproval(!approval)} aria-pressed={approval}><i/></button></div>
      </ConfigCard>
    </div><aside className="panel launch-summary"><p className="eyebrow">EXECUTION SUMMARY</p><h2>신규 사용자 이메일 회원가입</h2><span className="summary-ready"><CheckCircle2/> {loadingResources?'설정 확인 중':'실행 준비 완료'}</span><dl><div><dt>환경</dt><dd>{selectedEnvironment?.name??environment}</dd></div><div><dt>브라우저</dt><dd>{browser}</dd></div><div><dt>계정</dt><dd>{selectedAccount?.name??account}</dd></div><div><dt>화면</dt><dd>{viewport}</dd></div><div><dt>AI 호출</dt><dd>{maxAiCalls}회</dd></div><div><dt>시간 제한</dt><dd>{duration}분</dd></div></dl><div className="cost-estimate"><Sparkles/><div><span>AI API 상태</span><b>{Number(maxAiCalls)===0?'비활성 · 토큰 사용 없음':`최대 ${maxAiCalls}회`}</b></div></div><button className="primary wide launch" onClick={submit} disabled={starting||loadingResources||Boolean(resourceError)||!environment||!account}>{starting?<Activity className="spin"/>:<Play fill="currentColor"/>} {starting?'실행 생성 중':'격리 세션에서 실행'}</button><p className="launch-note"><ShieldCheck/> 허용된 action만 정책 검사 후 수행됩니다.</p></aside></div>
  </section>
}

function ConfigCard({icon,title,caption,tone='',children}:{icon:React.ReactNode;title:string;caption:string;tone?:string;children:React.ReactNode}){return <article className="panel config-card"><div className="config-card-title"><span className={tone}>{icon}</span><div><h2>{title}</h2><p>{caption}</p></div></div>{children}</article>}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="config-field"><span>{label}</span>{children}</label>}
type SelectOption=string|{value:string;label:string}
function Select({value,options,setValue}:{value:string;options:SelectOption[];setValue?:(v:string)=>void}){return <div className="select-wrap"><select value={value} onChange={e=>setValue?.(e.target.value)}>{options.map(option=>{const item=typeof option==='string'?{value:option,label:option}:option;return <option value={item.value} key={item.value}>{item.label}</option>})}</select><ChevronDown/></div>}

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
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">LIVE EXECUTION</p><h1>실행 모니터</h1><p>{running ? `${execution?.id ?? '실행 준비 중'} · ${statusLabel}` : state==='done' ? '실행이 성공적으로 완료되었습니다.' : state==='failed' ? `실행이 ${statusLabel} 상태로 종료되었습니다.` : '현재 실행 중인 테스트가 없습니다.'}</p></div><div className="run-controls">{!running && !terminal && <button className="primary" onClick={start}><Play size={16}/> 실행 시작</button>}{running && <button className="danger" onClick={stop}><Square size={15}/> 중단 요청</button>}{terminal&&<><button className="secondary" onClick={start}><RefreshCw size={15}/> 다시 실행</button><button className="primary" onClick={onResult}>결과 상세 <ArrowRight size={15}/></button></>}</div></div>
    <div className="monitor-grid"><article className="panel browser-panel"><div className="browser-top"><span/><span/><span/><div>Playwright Chromium smoke test</div><ShieldCheck size={15}/></div><div className="mock-site"><div className="mock-logo">storefront</div><div className="mock-login"><h2>다시 만나서 반가워요</h2><p>테스트 계정으로 안전하게 로그인합니다.</p><label>이메일</label><div className="mock-input">qa.runner@company.test</div><label>비밀번호</label><div className="mock-input">••••••••••••</div><div className={`mock-button ${activeStep===3?'targeted':''}`}>로그인</div></div>{state==='done'&&<div className="success-overlay"><CheckCircle2/><b>페이지 접속 성공</b><span>Chromium smoke test가 정상적으로 완료되었습니다.</span></div>}{state==='failed'&&<div className="success-overlay failed-overlay"><XCircle/><b>페이지 접속 실패</b><span>{statusLabel} · 실행 결과 상세를 확인해 주세요.</span></div>}</div></article>
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
