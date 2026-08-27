import { useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, Bot, Check, CheckCircle2,
  ChevronDown, CircleDot, Clock3, FileText, Gauge, LayoutDashboard,
  ListChecks, MoreHorizontal, Pause, Play, Plus, Search, Settings,
  ShieldCheck, Sparkles, Square, TerminalSquare, TestTube2, Users, XCircle,
  Upload, WandSparkles, Save, Database, KeyRound, MonitorCheck,
  Download, ExternalLink, RefreshCw, Eye, ChevronRight,
} from 'lucide-react'
import { api } from './api/client'
import { mockSteps } from './api/mockData'
import type { TestCaseSummary } from './api/types'

type View = 'dashboard' | 'cases' | 'author' | 'configure' | 'run' | 'result'
type RunState = 'idle' | 'running' | 'paused' | 'done'
type AuthorStage = 'draft' | 'structuring' | 'review' | 'ready'

const steps = mockSteps.map((step) => ({ ...step, type: step.action }))

function App() {
  const [view, setView] = useState<View>('dashboard')
  const [runState, setRunState] = useState<RunState>('idle')
  const [activeStep, setActiveStep] = useState(0)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [authorStage, setAuthorStage] = useState<AuthorStage>('draft')
  const [testCases, setTestCases] = useState<TestCaseSummary[]>([])

  useEffect(() => { api.listTestCases().then(setTestCases).catch(() => setNotice('테스트 케이스를 불러오지 못했습니다.')) }, [])

  const filtered = useMemo(() => testCases.filter((t) => `${t.id} ${t.title} ${t.group}`.toLowerCase().includes(query.toLowerCase())), [query])

  const startRun = async () => {
    await api.createExecution({ testCaseVersionId:'tcv-new-v1', environmentId:'env-staging', browser:'Chromium', accountId:'qa-runner-01', viewport:'1440x900', locale:'ko-KR', limits:{timeoutMinutes:15,maxAiCalls:20,retryCount:2}, requireRiskApproval:true })
    setRunState('running'); setActiveStep(1); setView('run')
    window.setTimeout(() => setActiveStep(2), 900)
    window.setTimeout(() => setActiveStep(3), 1800)
    window.setTimeout(() => { setActiveStep(4); setRunState('done') }, 2800)
  }

  const toast = (message: string) => { setNotice(message); window.setTimeout(() => setNotice(''), 2200) }

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
          <Nav icon={<TerminalSquare/>} label="실행 환경" onClick={() => toast('환경 관리 화면은 다음 단계에서 연결합니다.')}/>
          <Nav icon={<Users/>} label="계정 및 데이터" onClick={() => toast('테스트 계정은 별칭으로 안전하게 관리됩니다.')}/>
          <Nav icon={<ShieldCheck/>} label="정책 및 승인" onClick={() => toast('위험 행동 승인 정책을 준비 중입니다.')}/>
        </nav>
        <div className="project-card">
          <div className="project-dot">S</div><div><b>Storefront QA</b><small>Staging · Chromium</small></div><ChevronDown size={16}/>
        </div>
        <button className="user-card"><span className="avatar">김</span><span><b>김민준</b><small>QA Lead</small></span><Settings size={17}/></button>
      </aside>

      <main>
        <header className="topbar">
          <div><span className="environment"><CircleDot size={13}/> Staging</span><span className="sync"><span/> 모든 시스템 정상</span></div>
          <div className="top-actions"><button className="icon-button" aria-label="알림"><AlertTriangle size={18}/><i/></button><button className="primary" onClick={startRun}><Play size={16} fill="currentColor"/> 새 실행</button></div>
        </header>

        {view === 'dashboard' && <Dashboard onRun={startRun} onCases={() => setView('cases')}/>} 
        {view === 'cases' && <Cases query={query} setQuery={setQuery} rows={filtered} onRun={startRun} onCreate={() => {setAuthorStage('draft'); setView('author')}} onToast={toast}/>} 
        {view === 'author' && <Author stage={authorStage} setStage={setAuthorStage} onBack={() => setView('cases')} onRun={() => setView('configure')} onToast={toast}/>} 
        {view === 'configure' && <RunConfigure onBack={() => setView('author')} onStart={startRun}/>} 
        {view === 'run' && <RunMonitor state={runState} activeStep={activeStep} start={startRun} pause={() => setRunState(runState === 'paused' ? 'running' : 'paused')} stop={() => {setRunState('idle'); setActiveStep(0)}} onResult={() => setView('result')}/>}
        {view === 'result' && <ResultDetail onBack={() => setView('dashboard')} onRetry={startRun}/>} 
      </main>
      {notice && <div className="toast"><Check size={16}/>{notice}</div>}
    </div>
  )
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
      <Metric icon={<Gauge/>} label="AI 비용" value="$18.42" delta="예산의 37%" tone="amber"/>
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
        <div className="orb"><Bot size={27}/></div><p className="eyebrow">QUICK RUN</p><h2>검증할 흐름을<br/>바로 실행하세요.</h2><p>AI가 자연어 TC를 분석하고 화면 요소를 찾아 단계별 증적을 남깁니다.</p><button className="primary wide" onClick={onRun}><Play size={16} fill="currentColor"/> 테스트 실행</button>
        <div className="limits"><span><b>20</b> 최대 AI 호출</span><span><b>15m</b> 실행 제한</span></div>
      </article>
    </div>
    <div className="dashboard-grid lower">
      <article className="panel chart-panel"><div className="panel-head"><div><h2>품질 추이</h2><p>최근 7일 실행 결과</p></div><div className="legend"><span className="green-dot"/> Pass <span className="red-dot"/> Fail</div></div><div className="chart"><div style={{height:'48%'}}/><div style={{height:'62%'}}/><div style={{height:'55%'}}/><div style={{height:'80%'}}/><div style={{height:'68%'}}/><div style={{height:'88%'}}/><div className="today" style={{height:'94%'}}/></div><div className="days"><span>금</span><span>토</span><span>일</span><span>월</span><span>화</span><span>수</span><span>오늘</span></div></article>
      <article className="panel insight"><div className="insight-title"><Sparkles size={18}/><b>AI 인사이트</b><span>NEW</span></div><h3>검색 필터 TC의 실패가 증가했어요.</h3><p>최근 UI 변경 후 가격 슬라이더 탐색 성공률이 18% 감소했습니다. selector 후보를 재검토해 보세요.</p><button className="text-button">상세 분석 보기 <ArrowRight size={15}/></button></article>
    </div>
  </section>
}

function Metric({icon,label,value,delta,tone}: {icon: React.ReactNode; label:string; value:string; delta:string; tone:string}) { return <article className="metric"><div className={`metric-icon ${tone}`}>{icon}</div><div><p>{label}</p><strong>{value}</strong><small className={tone}>{delta}</small></div></article> }
function StatusIcon({type}: {type:'pass'|'running'|'fail'}) { return <span className={`status-icon ${type}`}>{type==='pass'?<Check/>:type==='fail'?<XCircle/>:<Activity/>}</span> }

function Cases({query,setQuery,rows,onRun,onCreate}: {query:string; setQuery:(s:string)=>void; rows:TestCaseSummary[]; onRun:()=>void; onCreate:()=>void; onToast:(s:string)=>void}) {
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">TEST LIBRARY</p><h1>테스트 케이스</h1><p>자연어 TC를 구조화하고 실행 준비 상태를 관리합니다.</p></div><button className="primary" onClick={onCreate}><Plus size={16}/> 새 테스트 케이스</button></div>
    <div className="toolbar"><div className="search"><Search size={17}/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="ID, 이름 또는 그룹 검색"/></div><button className="secondary">상태: 전체 <ChevronDown size={15}/></button><button className="secondary">그룹: 전체 <ChevronDown size={15}/></button></div>
    <article className="panel table-panel"><table><thead><tr><th>테스트 케이스</th><th>그룹</th><th>준비 상태</th><th>최근 성공률</th><th>마지막 실행</th><th/></tr></thead><tbody>{rows.map((row)=><tr key={row.id}><td><span className="file-icon"><FileText/></span><span><b>{row.title}</b><small>{row.id}</small></span></td><td>{row.group}</td><td><span className={`pill ${row.status==='READY'?'pass':'review'}`}>{row.status.replace('_',' ')}</span></td><td><div className="rate"><span><i style={{width:`${row.passRate}%`}}/></span>{row.passRate}%</div></td><td>{row.lastExecutedAt}</td><td><button className="row-play" onClick={onRun}><Play size={14}/></button></td></tr>)}</tbody></table></article>
  </section>
}

function Author({stage,setStage,onBack,onRun,onToast}: {stage:AuthorStage; setStage:(s:AuthorStage)=>void; onBack:()=>void; onRun:()=>void; onToast:(s:string)=>void}) {
  const [title,setTitle] = useState('신규 사용자 이메일 회원가입')
  const [raw,setRaw] = useState('Staging 환경에 접속한다.\n회원가입 버튼을 누르고 사용하지 않은 이메일과 안전한 비밀번호를 입력한다.\n약관에 동의한 뒤 가입을 완료한다.\n가입 완료 후 환영 메시지와 대시보드가 표시되는지 확인한다.')
  const structure = async () => { setStage('structuring'); try { await api.structureTestCase(title,raw); setStage('review') } catch { setStage('draft'); onToast('TC 구조화에 실패했습니다. 다시 시도해 주세요.') } }
  return <section className="page author-page">
    <div className="author-top"><button className="back-button" onClick={onBack}>← 테스트 케이스</button><div className="author-actions"><button className="secondary" onClick={()=>onToast('초안을 저장했습니다.')}><Save size={15}/> 초안 저장</button>{stage==='review'&&<button className="primary" onClick={()=>setStage('ready')}><Check size={15}/> 검토 승인</button>}{stage==='ready'&&<button className="primary" onClick={onRun}><Play size={15}/> 실행 설정</button>}</div></div>
    <div className="author-heading"><div><span className={`stage-badge ${stage}`}>{stage==='draft'?'DRAFT':stage==='structuring'?'ANALYZING':stage==='review'?'REVIEW REQUIRED':'READY'}</span><h1>{title}</h1><p>TC-NEW · Storefront QA · Version 1</p></div><div className="progress-steps"><span className="complete"><Check/>원문 작성</span><i/><span className={stage!=='draft'?'complete':''}><WandSparkles/>AI 구조화</span><i/><span className={stage==='ready'?'complete':''}><ShieldCheck/>검토 승인</span></div></div>
    <div className="author-grid">
      <article className="panel editor-panel"><div className="section-head"><div><h2>자연어 테스트 케이스</h2><p>사람이 이해하기 쉬운 방식으로 수행 조건과 기대 결과를 작성하세요.</p></div><button className="secondary"><Upload size={15}/> 파일 가져오기</button></div><label className="field-label">테스트 이름</label><input className="field-input" value={title} onChange={e=>setTitle(e.target.value)}/><label className="field-label">원문 TC</label><textarea className="tc-editor" value={raw} onChange={e=>setRaw(e.target.value)}/><div className="editor-meta"><span>{raw.length}자</span><span>CSV · XLSX · DOCX · TXT 지원</span></div><button className="ai-button" onClick={structure} disabled={stage==='structuring'}>{stage==='structuring'?<><Activity className="spin"/> TC를 분석하고 있습니다...</>:<><WandSparkles/> AI로 구조화하기 <ArrowRight/></>}</button></article>
      <article className={`panel review-panel ${stage==='draft'?'empty-review':''}`}>
        {stage==='draft'&&<div className="review-empty"><div><Bot/></div><h2>구조화 결과가 여기에 표시됩니다.</h2><p>AI가 전제조건, 실행 단계와 기대 결과를 분리하고 모호한 부분을 알려드립니다.</p><ul><li><Check/> 허용된 action으로 변환</li><li><Check/> 규칙 기반 assertion 생성</li><li><Check/> 위험 행동 자동 감지</li></ul></div>}
        {stage==='structuring'&&<div className="review-empty"><div className="pulse"><WandSparkles/></div><h2>TC 구조를 분석하는 중입니다.</h2><p>단계와 검증 조건을 안전한 실행 명령으로 변환하고 있습니다.</p><div className="skeleton-lines"><i/><i/><i/><i/></div></div>}
        {(stage==='review'||stage==='ready')&&<><div className="section-head"><div><h2>구조화 검토</h2><p>AI 생성 결과를 실행 전에 확인하세요.</p></div><span className="confidence">신뢰도 <b>94%</b></span></div><div className="review-block"><label>전제조건</label><div className="condition"><CheckCircle2/> Staging 환경과 미사용 이메일 계정이 준비되어 있다.</div></div><div className="review-block"><label>실행 단계 · 4</label>{steps.map((s,i)=><div className="structured-step" key={s.title}><span>{i+1}</span><div><b>{i===0?'Staging 회원가입 페이지로 이동':i===1?'회원가입 버튼을 선택':i===2?'이메일과 비밀번호를 입력하고 약관에 동의': '가입 완료 버튼을 선택'}</b><small><em>{i===0?'NAVIGATE':i===2?'FILL':'CLICK'}</em> {i===2?'secret_ref: test_user':'후보 요소 기반 탐색'}</small></div><button><MoreHorizontal/></button></div>)}</div><div className="review-block"><label>기대 결과 · 2</label><div className="assertion"><ShieldCheck/><div><b>환영 메시지가 표시된다.</b><small>TEXT · CONTAINS · timeout 10s</small></div></div><div className="assertion"><ShieldCheck/><div><b>대시보드 URL로 이동한다.</b><small>URL · MATCHES · /dashboard</small></div></div></div>{stage==='review'&&<div className="ambiguity"><AlertTriangle/><div><b>확인이 필요한 가정 1개</b><p>‘안전한 비밀번호’는 테스트 데이터 변수 <code>test_password</code>를 사용하도록 해석했습니다.</p></div></div>}{stage==='ready'&&<div className="ready-box"><CheckCircle2/><div><b>실행 준비가 완료되었습니다.</b><p>승인된 Version 1은 수정할 수 없으며 변경 시 새 버전이 생성됩니다.</p></div></div>}</>}
      </article>
    </div>
  </section>
}

function RunConfigure({onBack,onStart}: {onBack:()=>void; onStart:()=>void}) {
  const [browser,setBrowser]=useState('Chromium')
  const [account,setAccount]=useState('qa-runner-01')
  const [duration,setDuration]=useState('15분')
  const [approval,setApproval]=useState(true)
  return <section className="page config-page">
    <div className="author-top"><button className="back-button" onClick={onBack}>← 구조화 검토</button><span className="config-id">TC-NEW · Version 1 · READY</span></div>
    <div className="page-heading compact"><div><p className="eyebrow">EXECUTION SETUP</p><h1>실행 설정</h1><p>격리된 브라우저에서 사용할 환경, 계정과 안전 한도를 확인하세요.</p></div></div>
    <div className="config-grid"><div className="config-main">
      <ConfigCard icon={<MonitorCheck/>} title="실행 환경" caption="테스트 대상과 브라우저 조건">
        <div className="form-grid"><Field label="환경"><Select value="Staging" options={['Staging','Development']}/></Field><Field label="브라우저"><Select value={browser} setValue={setBrowser} options={['Chromium','Firefox','WebKit']}/></Field><Field label="화면 크기"><Select value="1440 × 900" options={['1440 × 900','1920 × 1080','1280 × 720']}/></Field><Field label="언어"><Select value="ko-KR" options={['ko-KR','en-US']}/></Field></div><div className="safe-domain"><ShieldCheck/><div><b>허용 도메인</b><span>staging.storefront.test 및 하위 경로만 접근할 수 있습니다.</span></div></div>
      </ConfigCard>
      <ConfigCard icon={<KeyRound/>} title="테스트 계정과 데이터" caption="비밀값은 실행 시에만 Worker 메모리에 주입됩니다." tone="violet">
        <div className="form-grid"><Field label="테스트 계정"><Select value={account} setValue={setAccount} options={['qa-runner-01','qa-runner-02','신규 계정 자동 생성']}/></Field><Field label="데이터 세트"><Select value="signup-default-v2" options={['signup-default-v2','empty-account-pool']}/></Field></div><div className="account-status"><span/><div><b>{account}</b><small>사용 가능 · 마지막 초기화 8분 전</small></div><button>계정 상세 <ExternalLink/></button></div>
      </ConfigCard>
      <ConfigCard icon={<Gauge/>} title="실행 한도" caption="무한 반복과 예상치 못한 비용을 방지합니다." tone="amber">
        <div className="form-grid triple"><Field label="최대 실행 시간"><Select value={duration} setValue={setDuration} options={['10분','15분','30분']}/></Field><Field label="최대 AI 호출"><Select value="20회" options={['10회','20회','30회']}/></Field><Field label="오류 재시도"><Select value="최대 2회" options={['사용 안 함','최대 1회','최대 2회']}/></Field></div><div className="toggle-row"><div><b>위험 행동 시 사람 승인</b><span>삭제·결제·계정 변경을 감지하면 실행을 일시정지합니다.</span></div><button className={`toggle ${approval?'on':''}`} onClick={()=>setApproval(!approval)}><i/></button></div>
      </ConfigCard>
    </div><aside className="panel launch-summary"><p className="eyebrow">EXECUTION SUMMARY</p><h2>신규 사용자 이메일 회원가입</h2><span className="summary-ready"><CheckCircle2/> 실행 준비 완료</span><dl><div><dt>환경</dt><dd>Staging</dd></div><div><dt>브라우저</dt><dd>{browser}</dd></div><div><dt>계정</dt><dd>{account}</dd></div><div><dt>실행 단계</dt><dd>4 steps</dd></div><div><dt>Assertion</dt><dd>2 rules</dd></div><div><dt>시간 제한</dt><dd>{duration}</dd></div></dl><div className="cost-estimate"><Sparkles/><div><span>예상 AI 비용</span><b>$0.08 – $0.14</b></div></div><button className="primary wide launch" onClick={onStart}><Play fill="currentColor"/> 격리 세션에서 실행</button><p className="launch-note"><ShieldCheck/> 허용된 action만 정책 검사 후 수행됩니다.</p></aside></div>
  </section>
}

function ConfigCard({icon,title,caption,tone='',children}:{icon:React.ReactNode;title:string;caption:string;tone?:string;children:React.ReactNode}){return <article className="panel config-card"><div className="config-card-title"><span className={tone}>{icon}</span><div><h2>{title}</h2><p>{caption}</p></div></div>{children}</article>}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="config-field"><span>{label}</span>{children}</label>}
function Select({value,options,setValue}:{value:string;options:string[];setValue?:(v:string)=>void}){return <div className="select-wrap"><select value={value} onChange={e=>setValue?.(e.target.value)}>{options.map(o=><option key={o}>{o}</option>)}</select><ChevronDown/></div>}

function RunMonitor({state,activeStep,start,pause,stop,onResult}: {state:RunState; activeStep:number; start:()=>void; pause:()=>void; stop:()=>void; onResult:()=>void}) {
  const running = state === 'running' || state === 'paused'
  return <section className="page"><div className="page-heading compact"><div><p className="eyebrow">LIVE EXECUTION</p><h1>실행 모니터</h1><p>{running ? 'TC-142 · 신규 사용자 이메일 회원가입' : state==='done' ? '실행이 성공적으로 완료되었습니다.' : '현재 실행 중인 테스트가 없습니다.'}</p></div><div className="run-controls">{!running && state!=='done' && <button className="primary" onClick={start}><Play size={16}/> 실행 시작</button>}{running && <><button className="secondary" onClick={pause}>{state==='paused'?<Play size={16}/>:<Pause size={16}/>} {state==='paused'?'재개':'일시정지'}</button><button className="danger" onClick={stop}><Square size={15}/> 중단</button></>}{state==='done'&&<><button className="secondary" onClick={start}><RefreshCw size={15}/> 다시 실행</button><button className="primary" onClick={onResult}>결과 상세 <ArrowRight size={15}/></button></>}</div></div>
    <div className="monitor-grid"><article className="panel browser-panel"><div className="browser-top"><span/><span/><span/><div>https://staging.storefront.test/login</div><ShieldCheck size={15}/></div><div className="mock-site"><div className="mock-logo">storefront</div><div className="mock-login"><h2>다시 만나서 반가워요</h2><p>테스트 계정으로 안전하게 로그인합니다.</p><label>이메일</label><div className="mock-input">qa.runner@company.test</div><label>비밀번호</label><div className="mock-input">••••••••••••</div><div className={`mock-button ${activeStep===3?'targeted':''}`}>로그인</div></div>{state==='done'&&<div className="success-overlay"><CheckCircle2/><b>검증 완료</b><span>대시보드가 정상적으로 표시되었습니다.</span></div>}</div></article>
      <article className="panel timeline"><div className="panel-head"><div><h2>실행 타임라인</h2><p>Step {Math.min(activeStep+1,4)} of 4</p></div><span className={`live ${state}`}>{state==='running'?'LIVE':state==='done'?'PASS':state==='paused'?'PAUSED':'READY'}</span></div><div className="step-list">{steps.map((s,i)=>{const done=i<activeStep; const active=i===activeStep&&running; return <div className={`step ${done?'done':''} ${active?'active':''}`} key={s.title}><span>{done?<Check/>:active?<Activity/>:i+1}</span><div><b>{s.title}</b><p>{s.note}</p><small>{s.type.toUpperCase()} {done&&'· 완료'}</small></div></div>})}</div><div className="budget"><div><span>AI 호출</span><b>{Math.min(activeStep*2,7)} / 20</b></div><div className="budget-bar"><i style={{width:`${Math.min(activeStep*10,35)}%`}}/></div><div><span>예상 비용</span><b>${(activeStep*0.031).toFixed(3)}</b></div></div></article></div>
  </section>
}

function ResultDetail({onBack,onRetry}:{onBack:()=>void;onRetry:()=>void}){
  const [selected,setSelected]=useState(3)
  const evidence=[
    {title:'로그인 페이지 진입',action:'NAVIGATE',time:'1.2s',detail:'허용 URL 이동 및 로그인 폼 확인'},
    {title:'테스트 계정 입력',action:'FILL',time:'0.8s',detail:'마스킹된 secret_ref 입력'},
    {title:'로그인 버튼 선택',action:'CLICK',time:'1.1s',detail:'접근성 후보 기반 요소 선택'},
    {title:'대시보드 노출 검증',action:'ASSERT',time:'1.9s',detail:'URL과 환영 문구 규칙 검증'},
  ]
  return <section className="page result-page"><div className="author-top"><button className="back-button" onClick={onBack}>← 대시보드</button><div className="author-actions"><button className="secondary"><Download/> 결과 내보내기</button><button className="primary" onClick={onRetry}><RefreshCw/> 다시 실행</button></div></div>
    <div className="result-hero"><div className="result-check"><Check/></div><div><p className="eyebrow">EXECUTION COMPLETED</p><h1>모든 검증을 통과했습니다.</h1><p>신규 사용자 이메일 회원가입 · EX-20260827-0184</p></div><div className="result-stats"><div><span>결과</span><b className="green-text">PASS</b></div><div><span>소요 시간</span><b>4.8s</b></div><div><span>AI 비용</span><b>$0.093</b></div><div><span>완료 시각</span><b>16:42:18</b></div></div></div>
    <div className="result-grid"><article className="panel evidence-list"><div className="panel-head"><div><h2>단계별 증적</h2><p>4개 단계 · 2개 assertion</p></div><span className="pill pass">ALL PASS</span></div>{evidence.map((e,i)=><button className={`evidence-row ${selected===i?'selected':''}`} onClick={()=>setSelected(i)} key={e.title}><span className="evidence-check"><Check/></span><div><b>{e.title}</b><small><em>{e.action}</em> · {e.detail}</small></div><time>{e.time}</time><ChevronRight/></button>)}</article>
      <article className="panel evidence-detail"><div className="detail-tabs"><button className="active"><Eye/> 화면 증적</button><button><TerminalSquare/> 실행 로그</button></div><div className="evidence-screen"><div className="screen-toolbar"><i/><i/><i/><span>staging.storefront.test/dashboard</span></div><div className="screen-content"><div className="mini-nav"><b>storefront</b><span/><span/><span/></div><div className="mini-welcome"><small>WELCOME BACK</small><h2>안녕하세요, QA Runner님.</h2><p>오늘의 테스트 환경이 정상적으로 준비되었습니다.</p><div><span/><span/><span/></div></div><div className="assert-highlight"><CheckCircle2/><b>Assertion matched</b><span>“안녕하세요” 텍스트가 화면에 표시됨</span></div></div></div><div className="evidence-meta"><div><span>선택한 단계</span><b>{selected+1}. {evidence[selected].title}</b></div><div><span>판정 방식</span><b>{selected===3?'URL + TEXT assertion':'DOM / Accessibility tree'}</b></div><div><span>AI 신뢰도</span><b>{selected===3?'규칙 기반':'96%'}</b></div></div></article>
    </div>
  </section>
}

export default App
