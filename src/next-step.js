import { animate, stagger } from "motion";
import { createBrowserStore, fetchMe, loadCareerData, pullUserData, pushUserData, requestCoach, requestEssayReview, requestRecommendation } from "./services.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const app = $("#app");
const storage = createBrowserStore("local");
const session = createBrowserStore("session");
const emptyProfile = { age:"",major:"",school:"",status:"재학",experiences:"" };
const storedAuth = storage.get("auth", null);
const initialProfile = storedAuth ? storage.get("profile", emptyProfile) : session.get("guestProfile", emptyProfile);
const emptyExperienceInputs = { certificate:"", activity:"", project:"" };
const experienceCategories = {
  certificate:{label:"자격증",example:"예: ADsP를 취득하며 데이터 전처리와 통계 분석의 기초를 익혔다.",placeholder:"취득한 자격증과 준비 과정에서 익힌 역량을 적어주세요."},
  activity:{label:"대외활동",example:"예: 학회 프로젝트에서 분석을 맡아 데이터를 정리하고 결과를 발표했다.",placeholder:"동아리·학회·공모전·봉사·인턴에서 맡은 역할과 결과를 적어주세요."},
  project:{label:"수업·프로젝트",example:"예: 수업 프로젝트에서 Python으로 데이터를 분석하고 결과를 시각화했다.",placeholder:"사용한 기술, 직접 수행한 작업과 결과를 적어주세요."}
};
const storedExperienceInputs = (storedAuth ? storage : session).get("experienceInputs", null);
const state = {
  auth: storedAuth, guest: sessionStorage.getItem("nextstep.guest") === "1",
  // server: 구글 세션으로 들어왔는가. loginAvailable: 서버에 인증이 설정돼 있는가.
  // 둘 다 false 면 예전처럼 브라우저 저장소만 쓴다 — 그래야 설정 전에도 화면이 그대로다.
  server: false, loginAvailable: false,
  profile: initialProfile,
  experienceInputs: storedExperienceInputs || {...emptyExperienceInputs,project:initialProfile.experiences || ""},
  experienceCategory:"certificate",
  saved: storage.get("saved", []), drafts: storage.get("drafts", {}), tasks: storage.get("tasks", {}),
  guestSaved: session.get("guestSaved", []), guestDrafts: session.get("guestDrafts", {}), guestTasks: session.get("guestTasks", {}),
  live: [], contexts: [], dataSource:"loading", loadError:"", selected: null, recommendation: null,
  recommendationMode:"fit", targetRole:"", route: location.hash.slice(1) || "landing",
  // 직무 추천에서 넘어온 NCS 코드. 공고 목록을 그 계열로 좁힌다.
  ncsFilter: null,
  calendarCursor:new Date(new Date().getFullYear(),new Date().getMonth(),1), selectedCalendarDate:null
};
const icon = { home:"⌂", recommend:"✦", jobs:"▤", coach:"◈", profile:"○" };
const safe = (value="") => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const initials = (name="N") => name.replace(/[^A-Za-z가-힣]/g,"").slice(0,2).toUpperCase() || "N";
const daysLeft = (date) => { if(!date)return null;const today=new Date(),due=new Date(`${date}T00:00:00`);today.setHours(0,0,0,0);return Math.round((due-today)/86400000); };
const dday = (date) => { const d=daysLeft(date); return d===null?"마감일 확인":d<0?"마감":d===0?"오늘 마감":`D-${d}`; };
const dateTimeLabel = (date,time) => `${date ? String(date).replaceAll("-", ".") : "확인 필요"}${time ? ` ${time}` : ""}`;

function parseLocalDate(value) {
  if(!value) return null;
  const match=String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if(!match) return null;
  const date=new Date(Number(match[1]),Number(match[2])-1,Number(match[3]));
  return Number.isNaN(date.getTime())?null:date;
}
function taskDate(task,job) {
  const explicit=parseLocalDate(task?.date||task?.dueDate||task?.scheduledDate);
  if(explicit) return explicit;
  const deadline=parseLocalDate(job?.deadline);
  if(!deadline) return null;
  const offset=String(task?.title||"").match(/D-(\d+)/i);
  if(offset) { const date=new Date(deadline); date.setDate(date.getDate()-Number(offset[1])); return date; }
  if(/마감일/.test(task?.title||"")) return deadline;
  return null;
}
const dateKey=(date)=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
function calendarData(cursor=state.calendarCursor) {
  const today=new Date(), year=cursor.getFullYear(), month=cursor.getMonth();
  const events=new Map();
  const add=(date,label,type)=>{
    if(!date||date.getFullYear()!==year||date.getMonth()!==month)return;
    const day=date.getDate();
    events.set(day,[...(events.get(day)||[]),{label,type}]);
  };
  const saved=savedItems();
  saved.forEach(job=>add(parseLocalDate(job.deadline),`${job.companyName} 마감`,"deadline"));
  Object.entries(taskItems()).forEach(([postingId,tasks])=>{
    const job=saved.find(item=>keyOf(item)===postingId)||state.live.find(item=>keyOf(item)===postingId);
    (tasks||[]).forEach(task=>add(taskDate(task,job),task.title,"task"));
  });
  return { today:today.getFullYear()===year&&today.getMonth()===month?today.getDate():null, year, month, firstDay:new Date(year,month,1).getDay(), days:new Date(year,month+1,0).getDate(), events };
}

function renderCalendarModal() {
  const calendar=calendarData();
  const cells=[...Array(calendar.firstDay).fill(null),...Array.from({length:calendar.days},(_,i)=>i+1)];
  const currentMonthKey=`${calendar.year}-${String(calendar.month+1).padStart(2,"0")}`;
  if(!state.selectedCalendarDate?.startsWith(currentMonthKey)) {
    const firstEvent=[...calendar.events.keys()].sort((a,b)=>a-b)[0];
    const day=calendar.today||firstEvent||1;
    state.selectedCalendarDate=`${currentMonthKey}-${String(day).padStart(2,"0")}`;
  }
  const selectedDay=Number(state.selectedCalendarDate.slice(-2));
  const selectedEvents=calendar.events.get(selectedDay)||[];
  $("#modal-root").innerHTML=`<div class="modal-backdrop calendar-backdrop"><section class="modal calendar-modal" role="dialog" aria-modal="true" aria-labelledby="calendar-title"><div class="modal-head"><div><h2 id="calendar-title">통합 캘린더</h2><p>마감과 준비 일정을 한눈에 확인해요.</p></div><button id="close-calendar" type="button" aria-label="통합 캘린더 닫기">×</button></div>
    <div class="calendar-toolbar"><button type="button" data-calendar-month="-1" aria-label="이전 달">‹</button><strong>${calendar.year}년 ${calendar.month+1}월</strong><button type="button" data-calendar-month="1" aria-label="다음 달">›</button></div>
    <div class="full-calendar">${["일","월","화","수","목","금","토"].map(day=>`<span class="weekday">${day}</span>`).join("")}${cells.map(day=>day===null?'<span class="calendar-empty" aria-hidden="true"></span>':`<button type="button" class="calendar-date ${day===calendar.today?'today':''} ${day===selectedDay?'selected':''}" data-calendar-day="${day}"><b>${day}</b><span class="calendar-markers">${(calendar.events.get(day)||[]).slice(0,3).map(event=>`<i class="${event.type}" title="${safe(event.label)}"></i>`).join("")}</span></button>`).join("")}</div>
    <section class="calendar-detail"><div><span class="calendar-detail-date">${calendar.month+1}월 ${selectedDay}일</span><strong>선택한 날짜의 일정</strong></div><ul>${selectedEvents.length?selectedEvents.map(event=>`<li><span class="event-dot ${event.type}"></span><span>${safe(event.label)}</span></li>`).join(""):'<li class="calendar-no-event">등록된 일정이 없어요.</li>'}</ul></section>
  </section></div>`;
  $("#close-calendar").onclick=()=>$("#modal-root").innerHTML="";
  $(".calendar-backdrop").addEventListener("click",event=>{if(event.target.classList.contains("calendar-backdrop"))$("#modal-root").innerHTML="";});
  $$('[data-calendar-month]').forEach(button=>button.onclick=()=>{state.calendarCursor=new Date(calendar.year,calendar.month+Number(button.dataset.calendarMonth),1);state.selectedCalendarDate=null;renderCalendarModal();});
  $$('[data-calendar-day]').forEach(button=>button.onclick=()=>{state.selectedCalendarDate=`${currentMonthKey}-${String(button.dataset.calendarDay).padStart(2,"0")}`;renderCalendarModal();});
}
function openCalendarModal(){const today=new Date();state.calendarCursor=new Date(today.getFullYear(),today.getMonth(),1);state.selectedCalendarDate=dateKey(today);renderCalendarModal();}

function toast(message) {
  const el=$("#toast"); el.textContent=message;
  animate(el,{opacity:[0,1],transform:["translate(-50%,20px)","translate(-50%,0)"]},{duration:.2});
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>animate(el,{opacity:0,transform:"translate(-50%,10px)"},{duration:.18}),2200);
}
function canPersist() { if (state.auth || state.guest) return true; openAuth("기록을 저장하려면 로그인하거나 게스트 체험을 시작해 주세요."); return false; }
function savedItems() { return state.auth ? state.saved : state.guestSaved; }
function taskItems() { return state.auth ? state.tasks : state.guestTasks; }
function draftItems() { return state.auth ? state.drafts : state.guestDrafts; }
function persistForSession(key, value) { (state.auth ? storage : session).set(key, value); scheduleSync(); }
function historyFor(jobId) { return (state.auth ? storage : session).get(`history.${jobId}`, []); }
function saveHistory(jobId, value) { (state.auth ? storage : session).set(`history.${jobId}`, value); scheduleSync(); }

// ── 서버 동기화. 구글 세션으로 들어왔을 때만 돈다.
// 브라우저 저장소가 계속 화면의 원본이고 서버는 **사본**이다. 순서를 반대로 하면
// DB 가 잠깐 죽었을 때 화면이 같이 죽는다 — 심사 기간에 그러면 안 된다.
let syncTimer = null;
function snapshot() {
  const history = {};
  const prefix = "nextstep.history.";
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key?.startsWith(prefix)) continue;
    try { history[key.slice(prefix.length)] = JSON.parse(localStorage.getItem(key)); } catch {}
  }
  return { profile: state.profile, experienceInputs: state.experienceInputs,
           saved: state.saved, drafts: state.drafts, tasks: state.tasks, history };
}
function scheduleSync() {
  if (!state.server) return;
  // 한 글자 칠 때마다 보내지 않는다. 입력이 멎고 1초 뒤 한 번.
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => pushUserData(snapshot()), 1000);
}
async function hydrate() {
  const remote = await pullUserData();
  if (!remote) return;                         // 신규 계정이거나 DB 가 없다 → 로컬 그대로
  if (remote.profile) { state.profile = { ...emptyProfile, ...remote.profile }; storage.set("profile", state.profile); }
  if (remote.experienceInputs) { state.experienceInputs = { ...emptyExperienceInputs, ...remote.experienceInputs }; storage.set("experienceInputs", state.experienceInputs); }
  if (Array.isArray(remote.saved)) { state.saved = remote.saved; storage.set("saved", state.saved); }
  if (remote.drafts) { state.drafts = remote.drafts; storage.set("drafts", state.drafts); }
  if (remote.tasks) { state.tasks = remote.tasks; storage.set("tasks", state.tasks); }
  for (const [jobId, value] of Object.entries(remote.history || {})) storage.set(`history.${jobId}`, value);
}
function go(route) { location.hash=route; }
function setRoute(route) { state.route=route; render(); window.scrollTo({top:0,behavior:"smooth"}); }
window.addEventListener("hashchange",()=>setRoute(location.hash.slice(1)||"landing"));

function nav() {
  if (state.route === "landing") return "";
  const contextNav=state.route==="coach"
    ? `<button class="nav-link context-nav" data-go="home">홈으로 돌아가기</button>`
    : state.route==="essay"
      ? `<button class="nav-link context-nav" data-go="coach">AI 코치로 돌아가기</button>`
      : "";
  return `<header class="topbar"><div class="nav-wrap">
    <a class="brand" href="#home" aria-label="Next Step 홈 화면으로 이동"><span class="brand-mark">N</span>Next Step</a>
    <nav class="main-nav ${contextNav?'contextual':''}">${contextNav || [["home","홈"],["recommend","직무 추천"],["jobs","실시간 공고"]].map(([r,l])=>`<button class="nav-link ${state.route===r?'active':''}" data-go="${r}">${l}</button>`).join("")}</nav>
    <div class="nav-end"><span class="mode-pill">${state.auth?`${safe(state.auth.id)} 님`:`게스트 · 임시 저장`}</span><button class="profile-button" data-go="profile" aria-label="프로필">${state.auth?initials(state.auth.id):"G"}</button></div>
  </div></header>`;
}
function shell(content) { return `${nav()}${content}`; }
function bindCommon() {
  $$('[data-go]').forEach(el=>el.addEventListener('click',()=>go(el.dataset.go)));
  $('.brand')?.addEventListener('click',event=>{event.preventDefault();go('home');});
  $$('button').forEach(el=>{ el.addEventListener('pointerdown',()=>animate(el,{scale:.975},{duration:.08})); el.addEventListener('pointerup',()=>animate(el,{scale:1},{duration:.12})); });
  const page=$(".page"); if(page) animate(page,{opacity:[0,1],y:[10,0]},{duration:.28,easing:"ease-out"});
  const cards=$$(".posting-card,.panel"); if(cards.length) animate(cards,{opacity:[0,1],y:[8,0]},{duration:.28,delay:stagger(.025)});
}

function landing() {
  return `<main class="landing"><div class="landing-inner"><div class="landing-brand"><span class="brand-step">N</span><span>Next Step</span></div>
    <section class="landing-copy">
      <h1><span class="landing-line">내 경험에서 시작하는</span><span class="landing-line accent">커리어의 다음 단계</span></h1>
      <p>흩어진 경험을 직무와 연결하고, 마음에 둔 공고부터<br>자소서와 면접까지 한 흐름으로 준비해요.</p>
      <div class="landing-actions"><button class="button primary" id="login-button">로그인하기</button><button class="button secondary" id="guest-button">로그인 없이 둘러보기</button></div>
      <p class="landing-note">게스트도 모든 화면을 둘러볼 수 있어요. 기록 저장은 로그인 후 가능해요.<br><a href="/privacy" style="color:inherit">개인정보처리방침</a> · <a href="/terms" style="color:inherit">이용약관</a><br><span style="opacity:.78">Published by 남궁현종, 김소연, 나예린, 배승민, 이근하</span></p>
    </section></div></main>`;
}
function openAuth(message="") {
  $("#modal-root").innerHTML=`<div class="modal-backdrop"><section class="modal"><div class="modal-head"><div><p class="eyebrow">WELCOME TO NEXT STEP</p><h2>나의 커리어 준비 시작하기</h2></div><button id="close-modal">×</button></div>
    ${message?`<div class="alert info">${safe(message)}</div>`:""}
    ${state.loginAvailable?`<button type="button" id="google-login" class="button primary" style="width:100%">G&nbsp; Google 계정으로 계속하기</button>
      <p class="landing-note" style="margin-top:14px">구글 계정으로 들어오면 프로필과 담아둔 공고, 준비 기록이 계정에 저장돼 다른 기기에서도 이어집니다.</p>`
    :`<form id="auth-form"><div class="form-grid">
      <div class="field"><label>아이디</label><input class="input" name="id" required placeholder="nextstep24"></div><div class="field"><label>비밀번호</label><input class="input" name="password" type="password" minlength="4" required></div>
      <div class="field full"><label>이메일</label><input class="input" name="email" type="email" required placeholder="student@univ.ac.kr"></div>
      <div class="field"><label>연령</label><input class="input" name="age" inputmode="numeric" placeholder=""></div><div class="field"><label>재적 상태</label><select class="select" name="status"><option>재학</option><option>휴학</option><option>졸업 예정</option><option>졸업</option></select></div>
      <div class="field"><label>학교</label><input class="input" name="school" placeholder="예: ○○대학교"></div><div class="field"><label>전공</label><input class="input" name="major" placeholder="예: 컴퓨터공학과"></div>
    </div><button class="button primary" style="width:100%;margin-top:16px">로그인하고 시작하기</button></form>
    <div class="social-row"><button type="button" data-social="Google">G&nbsp; Google로 계속</button><button type="button" data-social="Kakao">●&nbsp; 카카오로 계속</button></div>`}</section></div>`;
  $("#close-modal").onclick=()=>$("#modal-root").innerHTML="";
  $(".modal-backdrop").addEventListener("click",e=>{if(e.target.classList.contains("modal-backdrop"))$("#modal-root").innerHTML=""});
  // 인증이 켜졌으면 진짜 구글로 보낸다. 안 켜졌으면 예전 데모 폼이 그대로 뜬다.
  $("#google-login")?.addEventListener("click",()=>{location.href=`/auth/google?next=${encodeURIComponent("/"+(location.hash||"#home"))}`;});
  if($("#auth-form"))$("#auth-form").onsubmit=e=>{e.preventDefault(); const f=Object.fromEntries(new FormData(e.target)); state.auth={id:f.id,email:f.email}; state.guest=false; sessionStorage.removeItem("nextstep.guest"); state.profile={...emptyProfile,age:f.age,status:f.status,school:f.school,major:f.major};state.experienceInputs={...emptyExperienceInputs};state.experienceCategory="certificate";storage.set("auth",state.auth);storage.set("profile",state.profile);storage.set("experienceInputs",state.experienceInputs);$("#modal-root").innerHTML="";go("home");};
  $$('[data-social]').forEach(b=>b.onclick=()=>toast(`${b.dataset.social} 로그인은 인증 서버 연결 후 사용할 수 있어요.`));
}

// 공고 직접 등록.
//
// **OCR 커버리지가 낮은 것을 사용자가 직접 우회하는 길이다.** 이미지로만 된
// 공고는 본문을 못 읽어 AI 코치가 안 붙는데, 원문을 붙여 넣으면 같은 엔진으로
// 역량을 뽑아 코치·자소서까지 그대로 이어진다.
//
// 서버에 따로 저장하지 않는다. 담아둔 공고가 이미 사용자 문서로 동기화되고,
// 요청할 때 공고 내용을 같이 보내면 서버가 그걸로 답한다.
function openManualPosting() {
  $("#modal-root").innerHTML=`<div class="modal-backdrop"><section class="modal"><div class="modal-head"><div><p class="eyebrow">ADD POSTING</p><h2>공고 직접 등록</h2></div><button id="close-modal">×</button></div>
    <div class="hint">공고 원문을 붙여 넣으면 요구 역량을 뽑아 AI 코치와 자소서 검토까지 이어집니다. 이미지로만 올라온 공고도 이렇게 쓸 수 있어요. 등록한 공고는 내 공고함에만 있고 다른 사람에게 보이지 않습니다.</div>
    <form id="manual-form"><div class="form-grid">
      <div class="field"><label>회사명</label><input class="input" name="companyName" required placeholder="예: ○○전자"></div>
      <div class="field"><label>직무명</label><input class="input" name="positionTitle" required placeholder="예: 데이터 분석"></div>
      <div class="field"><label>마감일</label><input class="input" name="deadline" type="date"></div>
      <div class="field"><label>원문 링크 (선택)</label><input class="input" name="sourceUrl" type="url" placeholder="https://"></div>
      <div class="field full"><label>공고 원문</label><textarea class="textarea" name="body" required placeholder="주요 업무와 자격 요건을 그대로 붙여 넣으세요. 길수록 역량을 더 정확히 뽑습니다."></textarea></div>
    </div><button class="button primary" style="width:100%;margin-top:16px" id="manual-submit">등록하고 역량 뽑기</button></form></section></div>`;
  $("#close-modal").onclick=()=>$("#modal-root").innerHTML="";
  $(".modal-backdrop").addEventListener("click",e=>{if(e.target.classList.contains("modal-backdrop"))$("#modal-root").innerHTML=""});
  $("#manual-form").onsubmit=async e=>{
    e.preventDefault();
    if(!canPersist())return;
    const f=Object.fromEntries(new FormData(e.target));
    const body=(f.body||"").trim(); if(!body)return;
    const button=$("#manual-submit"); button.disabled=true; button.textContent="역량을 뽑는 중…";
    // 사용자 경험을 읽는 것과 같은 엔진이다. 공고 본문을 넣으면 요구 역량이 나온다.
    let skills=[];
    try{ skills=((await requestRecommendation(body)).nodes||[]).slice(0,8); }
    catch(error){ toast(`역량 추출에 실패했어요 (${error.code||error.message}). 공고는 그대로 담을게요.`); }
    const id=`user-${Date.now()}-${Math.random().toString(36).slice(2,8)}`;
    const item={postingId:id,externalId:id,userAdded:true,coachReady:true,
      companyName:f.companyName.trim(),positionTitle:f.positionTitle.trim(),
      postingTitle:f.positionTitle.trim(),jobFamily:"직접 등록",
      deadline:f.deadline||"",sourceUrl:f.sourceUrl||"",
      requiredSkills:skills,preferredSkills:[],responsibilities:[body]};
    const items=savedItems(); items.push(item);
    persistForSession(state.auth?"saved":"guestSaved",items);
    $("#modal-root").innerHTML="";
    toast(skills.length?`요구 역량 ${skills.length}개를 뽑아 내 공고함에 담았어요.`:"내 공고함에 담았어요.");
    state.selected=item; go("coach");
  };
}

function postingCard(item,{save=true,prepare=false,remove=false}={}) {
  const isSaved=savedItems().some(x=>keyOf(x)===keyOf(item));
  const status=item.coachReady?{tone:"mint",label:"AI 코치 준비 완료",title:"JD의 업무와 요구 역량이 연결되어 AI 코치·자소서·면접 기능을 사용할 수 있어요."}:item.postingId?{tone:"sun",label:"JD 상세 없음",title:"공고는 연결됐지만 AI 코치에 필요한 업무·요구 역량 정보가 부족해요."}:{tone:"coral",label:"직무 정보 미연결",title:"수집 공고와 직무 JD를 아직 연결하지 못해 AI 코치 준비를 시작할 수 없어요."};
  return `<article class="posting-card" data-posting="${safe(keyOf(item))}"><div class="card-top"><div class="company-logo">${initials(item.companyName)}</div><div><strong>${safe(item.companyName)}</strong><small>${safe(item.companyType||item.jobFamily||"")}</small></div><span class="badge ${status.tone}" title="${safe(status.title)}" style="margin-left:auto">${status.label}</span>${remove?`<button class="card-remove" data-remove type="button" aria-label="내 공고함에서 빼기" title="내 공고함에서 빼기">×</button>`:""}</div>
    <h3>${safe(item.positionTitle)}</h3><p class="meta">${safe(item.jobFamily||"직무 미분류")} · ${dday(item.deadline)}</p>
    <p class="meta">모집 일정 · ${dateTimeLabel(item.startDate,item.startTime)} ~ ${dateTimeLabel(item.deadline,item.deadlineTime)}</p>
    <div class="skill-row">${(item.requiredSkills||[]).slice(0,3).map(x=>`<span class="skill">${safe(x)}</span>`).join("")}</div>
    ${prepare&&!item.coachReady?`<p class="card-note">직무 요구 역량·업무 정보가 없는 공고라 AI 코치 준비는 지원하지 않아요. 마감일은 캘린더에 함께 표시돼요.</p>`:""}
    <div class="card-actions">${save?`<button class="button small ${isSaved?'ghost':'secondary'}" data-save>${isSaved?'담아둠 ✓':'공고 담기'}</button>`:""}${prepare&&item.coachReady?`<button class="button small primary" data-coach>공고 준비하기</button>`:`<a class="button small ghost" href="${safe(item.sourceUrl)}" target="_blank" rel="noreferrer">원문 보기</a>`}</div></article>`;
}
function focusJob() {
  const items=savedItems();
  if(!items.length) return null;
  const ranked=items.map(job=>({job,days:daysLeft(job.deadline)}));
  const upcoming=ranked.filter(x=>x.days!==null&&x.days>=0).sort((a,b)=>a.days-b.days);
  return (upcoming[0]||ranked.find(x=>x.days===null)||ranked[0]).job;
}
function jobTasks(job){ return job?(taskItems()[keyOf(job)]||[]):[]; }
function jobProgress(job) {
  const list=jobTasks(job);
  if(!list.length) return null;
  return Math.round(list.filter(t=>t.done).length/list.length*100);
}
function jobFit(job) {
  const value=job?.fitScore??job?.fit??job?.matchScore;
  return Number.isFinite(Number(value))?Math.round(Number(value)):null;
}
function todayItems() {
  const key=dateKey(new Date()), saved=savedItems(), dated=[], pending=[];
  saved.forEach(job=>{ const date=parseLocalDate(job.deadline); if(date&&dateKey(date)===key) dated.push({label:`${job.companyName} 마감일`,job}); });
  Object.entries(taskItems()).forEach(([postingId,list])=>{
    const job=saved.find(x=>keyOf(x)===postingId)||state.live.find(x=>keyOf(x)===postingId);
    (list||[]).forEach(task=>{
      const date=taskDate(task,job);
      const entry={label:`${job?.companyName?`(${job.companyName}) `:""}${task.title}`,task,job};
      if(date&&dateKey(date)===key) dated.push(entry);
      else if(!task.done) pending.push(entry);
    });
  });
  return dated.length?{items:dated.slice(0,4),source:"오늘 날짜의 준비 일정"}:{items:pending.slice(0,4),source:pending.length?"AI 코치가 정리한 준비 일정":""};
}
function home() {
  const items=savedItems(); const focus=focusJob();
  const action=jobTasks(focus).find(t=>!t.done)||null;
  const progress=jobProgress(focus), fit=jobFit(focus);
  const meta=focus?[dday(focus.deadline),fit===null?"":`적합도 ${fit}%`,progress===null?"":`진행률 ${progress}%`].filter(Boolean).join(" · "):"";
  const today=todayItems();
  return shell(`<main class="page"><div class="page-head"><div><h1>${state.auth?`${safe(state.auth.id)} 님의`:"미리 보는"} Next Step</h1><p>오늘 해야 할 일과 담아둔 공고를 한눈에 확인해요.</p></div><button class="button secondary" data-go="recommend">+ 경험 추가하기</button></div>
    <div class="home-priority-cards"><section class="panel priority-card next-step-card"><h2>${focus?"오늘의 NEXT STEP":"첫 번째 공고를 담아보세요"}</h2><div class="priority-card-content">${focus
      ? `<strong class="next-step-target">${safe(focus.companyName)} ${safe(focus.positionTitle)}</strong><p class="next-step-action">${action?safe(action.title):"AI 코치에서 준비 일정을 만들면 오늘 집중할 행동을 정리해 드려요."}</p>${action?.reason?`<p class="next-step-reason">${safe(action.reason)}</p>`:""}`
      : `<p class="next-step-action">추천 공고를 살펴보고 마음에 드는 공고부터 준비를 시작해요.</p>`}</div><div class="priority-card-meta">${safe(meta)}</div><div class="priority-card-action"><button class="calendar-entry" type="button" ${focus?'data-focus':'data-go="jobs"'}>${focus?"준비 이어가기 →":"추천 공고 보기"}</button></div></section>
    <section class="panel priority-card todo-summary-card" id="open-calendar" role="button" tabindex="0" aria-label="오늘의 할 일과 통합 캘린더 열기"><h2>오늘의 할 일</h2><div class="priority-card-content">${today.items.length
      ? `<ul class="todo-list">${today.items.map(x=>`<li><input type="checkbox" ${x.task?.done?'checked':''} tabindex="-1"><span>${safe(x.label)}</span></li>`).join("")}</ul>`
      : `<p class="todo-empty">오늘 예정된 준비 일정이 없어요.<br>AI 코치에서 준비 일정을 만들면 여기에 모여요.</p>`}</div><div class="priority-card-meta">${safe(today.source)}</div><div class="priority-card-action"><span class="calendar-entry">캘린더 보기 →</span></div></section></div>
    ${!state.auth?'<div class="guest-guide"><span>둘러보기 모드</span> 현재 브라우저 세션에만 임시 저장돼요. 로그인하면 관심 공고와 준비 기록을 계속 보관할 수 있어요.</div>':''}
    <section><div class="section-head"><div><h2>내 공고함</h2><p>${state.auth?"내가 담아둔 공고":"이 세션에서 담아둔 공고"}</p></div><button class="text-link" data-go="jobs">전체 공고 보기</button></div><div class="posting-grid">${items.length?items.map(x=>postingCard(x,{save:false,prepare:true,remove:true})).join(""):`<div class="empty empty-action"><strong>아직 담아둔 공고가 없어요.</strong><span>추천 공고에서 관심 공고를 담으면 AI 코치까지 이어서 체험할 수 있어요.</span><button class="button secondary" data-go="jobs">추천 공고 보러가기</button></div>`}</div></section>
  </main>`);
}
function jobs() {
  return shell(`<main class="page"><div class="page-head"><div><h1>실시간 공고</h1><p>실제 수집 공고 중 지금 지원 가능한 공고를 확인하고, 관심 공고를 내 공고함에 담아보세요.</p></div><button class="button secondary" id="manual-posting">+ 공고 직접 등록</button></div>${state.loadError?`<div class="alert error">${safe(state.loadError)}</div>`:""}${state.ncsFilter?`<div class="alert info" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span><strong>${safe(state.ncsFilter.name)}</strong> 추천에서 넘어온 목록이에요 · ${safe(ncsMajorName(state.ncsFilter.code))} 계열 ${visibleJobs().length}건</span><button class="text-link" id="clear-ncs" style="margin-left:auto">전체 공고 보기</button></div>`:""}
    <section class="panel featured-jobs"><div class="section-head"><div><h2>추천 공고</h2><p>마감이 가깝고 AI 코치까지 연결되는 공고예요.</p></div><span class="badge ${state.dataSource==='api'?'mint':'sun'}">${state.dataSource==='api'?'실제 공고 API':'실제 공고 기반 체험 데이터'}</span></div><div class="posting-grid" id="featured-postings">${visibleJobs().filter(x=>x.coachReady).slice(0,3).map(postingCard).join("")}</div></section>
    <div class="section-head"><div><h2>전체 공고</h2><p>직무명과 요구 역량까지 검색하고, 마음에 드는 공고만 내 공고함에 담아보세요.</p></div></div><div class="filterbar"><input class="input" id="job-search" placeholder="기업명 · 공고명 · 직무 · 요구 역량 검색"><select class="select" id="job-filter"><option value="">전체 직무</option>${[...new Set(visibleJobs().map(x=>x.jobFamily))].sort().map(x=>`<option>${safe(x)}</option>`).join("")}</select><select class="select" id="deadline-filter"><option value="0">전체 마감</option><option value="7">7일 이내</option><option value="14">14일 이내</option><option value="30">30일 이내</option></select><span class="result-count">${visibleJobs().length}건</span></div><div class="posting-grid" id="all-postings">${visibleJobs().slice(0,60).map(postingCard).join("")}</div>
  </main>`);
}
function recommend() {
  const r=state.recommendation;
  const category=experienceCategories[state.experienceCategory];
  return shell(`<main class="page"><div class="page-head"><div><h1>내 경험과 닿는 직무 찾기</h1><p>경험의 근거를 읽고, 예상하지 못했던 직무까지 연결해요.</p></div></div>${r
    ? `<section class="panel recommendation-stage result-stage"><div id="recommend-results">${renderRecommendation(r)}</div></section>`
    : `<section class="panel recommendation-stage input-stage"><div class="experience-layout">
      <aside class="experience-side"><div class="experience-col-head"><h2>경험 유형 선택</h2><p>작성할 경험을 선택해주세요.</p></div>
        <div class="experience-tabs" role="tablist" aria-label="경험 카테고리">${Object.entries(experienceCategories).map(([key,item])=>`<button class="experience-tab ${state.experienceCategory===key?'active':''}" role="tab" aria-selected="${state.experienceCategory===key}" data-experience-category="${key}">${item.label}</button>`).join("")}</div></aside>
      <div class="experience-main"><div class="experience-col-head"><h2>경험 내용 입력</h2><p>선택한 경험에 대해 구체적으로 작성해주세요.</p></div>
        <div class="hint">이렇게 써보세요: “${category.example.replace(/^예: /,"") }”</div>
        <textarea class="textarea" id="experience-input" aria-label="${category.label} 경험 입력" placeholder="${category.placeholder}">${safe(state.experienceInputs[state.experienceCategory] || "")}</textarea>
        <div class="form-foot"><small>카테고리별 입력 내용은 전환 후에도 유지돼요.</small><button class="button primary" id="run-recommend">직무 연결 분석하기</button></div></div>
    </div></section>`}</main>`);
}
function renderRecommendation(result) {
  if(!result) return "";
  if(result.error) return `<div class="alert error">${safe(result.error)}</div>`;
  const matches=(result.matches||[]).slice(0,5);
  const target=matches.find(m=>m.name===state.targetRole)||matches[0];
  const cards=state.recommendationMode==="target"&&target?[target]:matches;
  return `<div class="section-head"><div><h2>${state.recommendationMode==="target"?'목표 직무와 내 경험 비교':'경험에서 발견한 직무 연결'}</h2><p>${state.recommendationMode==="target"?'목표 직무를 선택해 연결된 경험 근거를 확인해요.':'점수 대신 실제로 겹친 역량과 근거를 보여드려요.'}</p></div><button class="text-link" data-edit-experience>경험 다시 입력</button></div><div class="segmented"><button class="${state.recommendationMode==='fit'?'active':''}" data-recommend-mode="fit">나에게 맞는 직무 찾기</button><button class="${state.recommendationMode==='target'?'active':''}" data-recommend-mode="target">목표 직무와 비교하기</button></div>${state.recommendationMode==="target"?`<label class="target-role-label">목표 직무<select class="select" id="target-role">${matches.map(m=>`<option ${m.name===target?.name?'selected':''}>${safe(m.name)}</option>`).join('')}</select></label>`:''}<div class="result-list">${cards.map(m=>`<article class="match-card"><h3>${safe(m.name)}</h3><p>${safe(m.sentence||m.description||"")}</p><div class="skill-row">${(m.have||[]).slice(0,5).map(h=>`<span class="skill">${safe(h.competency)}</span>`).join("")}</div>${m.have?.[0]?.quotes?.[0]?`<div class="evidence">근거 · ${safe(m.have[0].quotes[0].text)}</div>`:""}${(()=>{const n=ncsCount(m.code);return n?`<div style="margin-top:12px"><button class="button small secondary" data-ncs="${safe(m.code)}" data-ncs-name="${safe(m.name)}">이 직무 공고 ${n}건 보기</button><small style="margin-left:9px;color:var(--muted)">${safe(ncsMajorName(m.code))} 계열</small></div>`:`<div style="margin-top:12px"><small style="color:var(--muted)">연결된 민간 공고가 아직 없어요</small></div>`;})()}</article>`).join("")}</div><div class="form-foot"><small>지원 가능한 공고는 실시간 공고에서 확인할 수 있어요.</small><button class="button secondary" data-go="jobs">실시간 공고로 이동</button></div>`;
}
function coach() {
  const job=state.selected||savedItems()[0];
  if(!job) return shell(`<main class="page"><div class="empty">먼저 공고를 선택해 주세요.</div></main>`);
  const history=historyFor(keyOf(job)), tasks=taskItems()[keyOf(job)]||[];
  return shell(`<main class="page"><section class="panel coach-context"><div class="company-logo">${initials(job.companyName)}</div><div><h2>${safe(job.companyName)} · ${safe(job.positionTitle)}</h2><p>${safe(job.jobFamily||"")} · ${dday(job.deadline)}</p></div><a class="button small ghost" href="${safe(job.sourceUrl||'#')}" target="_blank" rel="noreferrer">공고 원문</a></section>
    <div class="coach-grid"><section class="panel"><div class="coach-welcome"><div class="coach-orb">N</div><div><h2>이 공고의 준비 흐름을 함께 정리할게요.</h2><p>공고 JD와 입력한 경험을 근거로 답해요. 우선 자소서에 쓸 경험을 고르고 면접 질문까지 이어가 보세요.</p></div></div><div class="quick-actions"><button class="quick-action" data-agent="timeline">준비 일정 짜기</button><button class="quick-action" data-go="essay">자소서 준비</button><button class="quick-action" type="button" data-interview-mode="text">텍스트 면접</button><button class="quick-action" type="button" data-interview-mode="video">화상 면접</button></div>
      <div class="messages" id="messages">${history.length?history.map(m=>`<div class="message ${m.role}">${m.demo?'<span class="demo-label">체험 응답</span>':''}${safe(m.content)}</div>`).join(""):`<div class="message assistant">지금은 공고 요구사항을 확인하고, 가장 가까운 경험 하나를 정리할 때예요. 무엇부터 시작할까요?</div>`}</div><form class="chat-form" id="chat-form"><input class="input" id="chat-input" placeholder="이 공고에 맞는 경험부터 추천해줘"><button class="button primary">보내기</button></form></section>
      <aside class="panel"><div class="section-head"><div><h2>준비 체크리스트</h2><p>준비 일정 짜기 결과만 여기에 반영돼요.</p></div></div><div class="aside-list" id="coach-tasks">${tasks.length?tasks.map(t=>`<label class="aside-item"><input type="checkbox" ${t.done?'checked':''}> <strong>${safe(t.title)}</strong>${safe(t.reason||"")}</label>`).join(""):`<div class="aside-item">준비 일정을 만들면 할 일이 여기에 정리돼요.</div>`}</div></aside></div></main>`);
}
function essay() {
  const job=state.selected||savedItems()[0]; if(!job) return home(); const draft=draftItems()[keyOf(job)]||[{question:"지원 동기와 직무 관련 경험을 작성해 주세요.",answer:""},{question:"협업 과정에서 문제를 해결한 경험을 작성해 주세요.",answer:""}];
  return shell(`<main class="page"><div class="page-head"><div><p class="eyebrow">ESSAY REVIEW</p><h1>${safe(job.companyName)} 자소서 준비</h1><p>작성 중에는 가벼운 신호를, 심사 후에는 AI 채용담당자의 정식 평가를 보여줘요.</p></div><span class="badge">작성 중</span></div><div class="essay-grid"><section class="panel"><form id="essay-form">${draft.map((x,i)=>`<div class="essay-section"><label>문항 ${i+1}</label><input class="input essay-question" value="${safe(x.question)}"><textarea class="textarea essay-answer" placeholder="내 행동과 결과가 드러나도록 작성해 보세요.">${safe(x.answer)}</textarea></div>`).join("")}<button class="button primary">AI 채용담당자에게 심사받기</button></form></section><aside class="panel"><div class="section-head"><div><h2>심사 결과</h2><p>강점 · 보완 필요 · 추가 작성 필요</p></div></div><div id="essay-review"><div class="aside-item">초안을 작성하고 심사하면 공고별 채점 기준으로 결과를 보여드려요.</div></div></aside></div></main>`);
}
function profile() {
  const p=state.profile;
  return shell(`<main class="page"><div class="page-head"><div><p class="eyebrow">MY PROFILE</p><h1>나의 경험과 기본 정보</h1><p>여기서 수정한 내용은 직무 추천과 AI 코치에 함께 반영돼요.</p></div>${state.auth?`<button class="button ghost" id="logout">로그아웃</button>${state.server?`<button class="button ghost" id="delete-account" style="margin-left:8px">계정 삭제</button>`:""}`:"<button class=\"button primary\" id=\"profile-login\">로그인하기</button>"}</div><div class="profile-grid"><section class="panel"><form id="profile-form"><div class="form-grid"><div class="field"><label>학교</label><input class="input" name="school" value="${safe(p.school)}"></div><div class="field"><label>전공</label><input class="input" name="major" value="${safe(p.major)}"></div><div class="field"><label>연령</label><input class="input" name="age" value="${safe(p.age)}"></div><div class="field"><label>재적 상태</label><select class="select" name="status">${["재학","휴학","졸업 예정","졸업"].map(x=>`<option ${p.status===x?'selected':''}>${x}</option>`).join("")}</select></div><div class="field full"><label>직무 추천에 사용하는 경험</label><textarea class="textarea" name="experiences">${safe(p.experiences)}</textarea></div></div><button class="button primary" style="margin-top:15px">프로필 저장</button></form></section><aside class="panel profile-note"><h3>하나의 경험, 하나의 데이터</h3><p>프로필과 직무 추천의 경험 입력은 같은 값을 사용해요. 어느 화면에서 고쳐도 다음 분석과 AI 코치에 최신 내용이 반영됩니다.</p></aside></div></main>`);
}

function render() {
  if(state.route!=="landing"&&!state.auth&&!state.guest){state.route="landing";history.replaceState(null,"","#landing");}
  const views={landing,home,jobs,recommend,coach,essay,profile}; app.innerHTML=(views[state.route]||home)(); bindCommon(); bindPage();
}
// 공고 하나를 가리키는 키. **postingId 를 쓰면 안 된다.**
// 한 공채 공고가 여러 직무로 쪼개질 때 postingId 가 같이 붙는다 —
// 에이치디한국조선해양은 7장, 코오롱생명과학은 서로 다른 세 직무가 role-79 하나를 쓴다.
// 그래서 카드를 눌렀을 때 그 그룹의 첫 번째가 잡혀 엉뚱한 공고가 담기고
// AI 코치도 다른 공고로 열렸다. externalId 는 347건 전부에 있고 고유하다.
const keyOf = (item) => String(item?.externalId ?? item?.postingId ?? "");
// 추천 직무(NCS 코드)로 공고를 좁힌다.
// 공고마다 ncsMajors 가 서버에서 같이 오므로 다시 부르지 않는다.
// **대분류까지만 이어진다** — 02 경영·회계·사무 안에서 마케팅과 재무를
// 가르지 못한다. 그래서 화면에 계열 이름을 같이 띄워 오해를 막는다.
const ncsMajorOf = (code) => String(code||"").slice(0,2);
function ncsMatch(item){ const f=state.ncsFilter; if(!f) return true;
  return (item.ncsMajors||[]).includes(ncsMajorOf(f.code)); }
const visibleJobs = () => state.live.filter(ncsMatch);
function ncsCount(code){ const m=ncsMajorOf(code);
  return state.live.filter(x=>(x.ncsMajors||[]).includes(m)).length; }
function ncsMajorName(code){ const m=ncsMajorOf(code);
  const s=state.live.find(x=>(x.ncsMajors||[]).includes(m));
  return s?(s.ncsMajorNames||[])[(s.ncsMajors||[]).indexOf(m)]||"":""; }
function findPosting(card){const id=card?.dataset.posting;if(!id)return undefined;return state.live.find(x=>keyOf(x)===id)||savedItems().find(x=>keyOf(x)===id);}
function bindPostingCards(root=document){$$('.posting-card',root).forEach(card=>{const item=findPosting(card); $('[data-save]',card)?.addEventListener('click',()=>{if(!item)return toast('이 공고는 직무 상세 정보가 아직 연결되지 않아 담아둘 수 없어요. 공고 원문은 바로 확인할 수 있어요.');if(!canPersist())return; const items=savedItems();const idx=items.findIndex(x=>keyOf(x)===keyOf(item));if(idx>=0)items.splice(idx,1);else items.push(item);persistForSession(state.auth?'saved':'guestSaved',items);toast(idx>=0?'내 공고함에서 뺐어요.':state.auth?'내 공고함에 담았어요.':'체험용 내 공고함에 담았어요.');render();});$('[data-coach]',card)?.addEventListener('click',()=>{state.selected=item;go('coach')});$('[data-remove]',card)?.addEventListener('click',()=>{if(!item)return;const items=savedItems();const idx=items.findIndex(x=>keyOf(x)===keyOf(item));if(idx<0)return;items.splice(idx,1);persistForSession(state.auth?'saved':'guestSaved',items);toast('내 공고함에서 뺐어요.');render();});});}
function bindPage(){
  if(state.route==='landing'){animate($('.landing-copy'),{opacity:[0,1],y:[18,0]},{duration:.55});$('#login-button').onclick=()=>openAuth();$('#guest-button').onclick=()=>{state.guest=true;state.auth=null;state.profile=session.get('guestProfile',emptyProfile);state.experienceInputs=session.get('experienceInputs',{...emptyExperienceInputs,project:state.profile.experiences || ''});state.experienceCategory='certificate';sessionStorage.setItem('nextstep.guest','1');go('home')};return;}
  bindPostingCards(); $('#home-login')?.addEventListener('click',()=>openAuth()); $('#profile-login')?.addEventListener('click',()=>openAuth()); $('[data-focus]')?.addEventListener('click',()=>{state.selected=focusJob();go('coach')});
  const calendarCard=$('#open-calendar'); if(calendarCard){calendarCard.addEventListener('click',event=>{if(event.target.matches('input'))event.preventDefault();openCalendarModal();});calendarCard.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openCalendarModal();}});}
  if(state.route==='jobs'){const apply=()=>{const terms=$('#job-search').value.toLowerCase().split(/\s+/).filter(Boolean),job=$('#job-filter').value,days=Number($('#deadline-filter').value);const list=visibleJobs().filter(x=>{const searchable=`${x.companyName||""} ${x.positionTitle||""} ${x.jobFamily||""} ${(x.requiredSkills||[]).join(" ")}`.toLowerCase();return terms.every(term=>searchable.includes(term))&&(!job||x.jobFamily===job)&&(!days||daysLeft(x.deadline)<=days);});$('#all-postings').innerHTML=list.slice(0,60).map(postingCard).join('');$('.result-count').textContent=`${list.length}건`;bindPostingCards($('#all-postings'));};['#job-search','#job-filter','#deadline-filter'].forEach(s=>$(s).addEventListener('input',apply));$('#clear-ncs')?.addEventListener('click',()=>{state.ncsFilter=null;render();});$('#manual-posting').onclick=()=>openManualPosting();}
  if(state.route==='recommend'){
    $('#experience-input')?.addEventListener('input',event=>{state.experienceInputs[state.experienceCategory]=event.target.value;persistForSession('experienceInputs',state.experienceInputs);});
    $$('[data-experience-category]').forEach(button=>button.addEventListener('click',()=>{state.experienceInputs[state.experienceCategory]=$('#experience-input').value;persistForSession('experienceInputs',state.experienceInputs);state.experienceCategory=button.dataset.experienceCategory;render();}));
    $('#run-recommend')?.addEventListener('click',async()=>{state.experienceInputs[state.experienceCategory]=$('#experience-input').value;persistForSession('experienceInputs',state.experienceInputs);const text=Object.entries(experienceCategories).map(([key,item])=>({label:item.label,value:(state.experienceInputs[key]||'').trim()})).filter(item=>item.value).map(item=>`[${item.label}]\n${item.value}`).join('\n\n');if(!text)return toast('경험을 한 가지 이상 입력해 주세요.');state.profile.experiences=text;persistForSession(state.auth?'profile':'guestProfile',state.profile);$('.input-stage').innerHTML='<div class="alert info">경험의 근거를 분석하고 있어요.</div>';try{state.recommendation=await requestRecommendation(text);state.recommendationMode='fit';state.targetRole='';}catch(error){state.recommendation={error:`직무 추천 요청 실패: ${error.code||error.message}`};}render();});
    $$('[data-recommend-mode]').forEach(button=>button.addEventListener('click',()=>{state.recommendationMode=button.dataset.recommendMode;render();}));
    $$('[data-ncs]').forEach(b=>b.addEventListener('click',()=>{state.ncsFilter={code:b.dataset.ncs,name:b.dataset.ncsName};go('jobs');}));
    $('#target-role')?.addEventListener('change',event=>{state.targetRole=event.target.value;render();});
    $('[data-edit-experience]')?.addEventListener('click',()=>{state.recommendation=null;state.recommendationMode='fit';state.targetRole='';render();});
  }
  if(state.route==='coach')bindCoach(); if(state.route==='essay')bindEssay();
  if(state.route==='profile'){$('#profile-form').onsubmit=e=>{e.preventDefault();if(!canPersist())return;state.profile={...state.profile,...Object.fromEntries(new FormData(e.target))};persistForSession(state.auth?'profile':'guestProfile',state.profile);toast(state.auth?'프로필과 직무 추천 경험을 함께 저장했어요.':'이 브라우저 세션에 임시 저장했어요.');};$('#delete-account')?.addEventListener('click',async()=>{if(!confirm('계정과 저장된 기록(프로필 · 담아둔 공고 · 초안 · 대화)을 모두 지웁니다. 되돌릴 수 없습니다. 계속할까요?'))return;try{await fetch('/api/v1/me',{method:'DELETE'});}catch{}for(const k of Object.keys(localStorage))if(k.startsWith('nextstep.'))localStorage.removeItem(k);sessionStorage.clear();location.href='/';});$('#logout')?.addEventListener('click',()=>{if(state.server){location.href='/auth/logout';return;}storage.remove('auth');state.auth=null;state.guest=false;state.profile=emptyProfile;state.experienceInputs={...emptyExperienceInputs};state.experienceCategory='certificate';go('landing')});}
}
function bindTaskToggles(job){$$('#coach-tasks input[type="checkbox"]').forEach((input,index)=>input.onchange=()=>{const tasks=taskItems();const k=keyOf(job);if(!tasks[k]?.[index])return;tasks[k][index].done=input.checked;persistForSession(state.auth?'tasks':'guestTasks',tasks);render();});}
function bindCoach(){const job=state.selected||savedItems()[0];if(!job)return;if(job.userAdded)$$('[data-interview-mode]').forEach(b=>b.closest('.quick-action')?.remove()||b.remove());$$('[data-interview-mode]').forEach(button=>button.onclick=()=>{if(location.protocol==='file:')return toast('면접은 프로젝트 서버에서 실행해야 실제 분석 API를 사용할 수 있어요.');const url=new URL('/index.html',window.location.origin);url.searchParams.set('postingId',job.postingId);url.searchParams.set('mode',button.dataset.interviewMode);window.location.assign(url.href);});bindTaskToggles(job);const ask=async(mode,message)=>{const box=$('#messages');box.insertAdjacentHTML('beforeend',`<div class="message user">${safe(message)}</div><div class="message assistant" data-wait>공고 근거를 확인하고 있어요…</div>`);const wait=$('[data-wait]');try{const history=historyFor(keyOf(job));const tasks=taskItems();const out=await requestCoach({job,mode,message,profile:state.profile,currentTasks:tasks[keyOf(job)]||[],history});wait.textContent=out.answer;history.push({role:'user',content:message},{role:'assistant',content:out.answer});saveHistory(keyOf(job),history);if(mode==='timeline'){const next=(out.nextActions||[]).map((x,i)=>({...x,id:`${Date.now()}-${i}`,done:false}));tasks[keyOf(job)]=next;persistForSession(state.auth?'tasks':'guestTasks',tasks);$('#coach-tasks').innerHTML=next.map(t=>`<label class="aside-item"><input type="checkbox" ${t.done?'checked':''}> <strong>${safe(t.title)}</strong>${safe(t.reason||'')}</label>`).join('');bindTaskToggles(job);}}catch(error){wait.textContent=`AI 코치 요청 실패: ${error.code||error.message}`;}box.scrollTop=box.scrollHeight;};$$('[data-agent]').forEach(b=>b.onclick=()=>ask(b.dataset.agent,'마감일까지의 준비 일정을 제안해 줘.'));$('#chat-form').onsubmit=e=>{e.preventDefault();const input=$('#chat-input'),value=input.value.trim();if(value){input.value='';ask('consultation',value);}};}
function bindEssay(){const job=state.selected||savedItems()[0];$('#essay-form').onsubmit=async e=>{e.preventDefault();const sections=$$('.essay-question').map((q,i)=>({question:q.value,answer:$$('.essay-answer')[i].value}));const drafts=draftItems();drafts[keyOf(job)]=sections;persistForSession(state.auth?'drafts':'guestDrafts',drafts);$('#essay-review').innerHTML='<div class="aside-item">AI 채용담당자가 초안을 읽고 있어요…</div>';try{const out=await requestEssayReview({job,sections,experiences:(state.profile.experiences||'').split(/\n+/)});const labels={strong:['강점','mint'],weak:['보완 필요','sun'],missing:['추가 작성 필요','coral']};$('#essay-review').innerHTML=out.items.map(x=>`<article class="review-item"><span class="badge ${labels[x.status]?.[1]||'sun'}">${labels[x.status]?.[0]||'검토'}</span><h4>${safe(x.label)}</h4><p>${safe(x.feedback)} ${safe(x.suggestion||'')}</p></article>`).join('');}catch(error){$('#essay-review').innerHTML=`<div class="alert error">자소서 심사 요청 실패: ${safe(error.code||error.message)}</div>`;}};}

async function loadData(){try{const data=await loadCareerData();state.live=data.postings;state.contexts=data.contexts;state.dataSource=data.source;state.loadError='';}catch(error){state.live=[];state.contexts=[];state.dataSource='error';state.loadError=`공고 데이터를 불러오지 못했습니다: ${error.code||error.message}`;}render();}
// 첫 화면을 그리기 전에 로그인 상태부터 확인한다. 나중에 확인하면 로그인한 사람이
// 랜딩으로 한 번 튕겼다가 들어오게 된다(262번 줄의 가드 때문).
async function boot(){
  const me=await fetchMe();
  state.loginAvailable=!!me.login;
  if(me.user){
    state.auth={id:me.user.name||(me.user.email||"").split("@")[0]||"회원",email:me.user.email||""};
    state.server=true; state.guest=false;
    sessionStorage.removeItem("nextstep.guest");
    storage.set("auth",state.auth);
    await hydrate();
  }
  // 인증 실패는 /?auth_error=... 로 돌아온다. 한 번 보여주고 주소에서 지운다.
  const failed=new URL(location.href).searchParams.get("auth_error");
  render(); loadData();
  if(failed){toast(failed);history.replaceState(null,"",location.pathname+location.hash);}
}
boot();
