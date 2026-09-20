const jsonHeaders = { "Content-Type":"application/json" };

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || `HTTP_${response.status}`);
    error.code = body.error || `HTTP_${response.status}`;
    throw error;
  }
  return body;
}

export async function loadCareerData() {
  const [live, contexts] = await Promise.all([
    fetchJson("/api/v1/live-postings"),
    fetchJson("/api/v1/job-contexts")
  ]);
  if (!live.items?.length) throw new Error("LIVE_POSTINGS_EMPTY");
  return { postings:live.items, contexts:contexts.items || [], source:"api" };
}

export async function requestRecommendation(text) {
  return fetchJson("/api/recommend", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ texts:text.split(/\n+/).filter(Boolean),target:"",limit:5 }) });
}

// 직접 등록한 공고는 서버의 수집본에 없다. 공고 내용을 같이 보내야
// AI 코치가 무엇을 보고 답하는지 알 수 있다. 서버가 크기를 잘라 받는다.
const jobContextOf = (job) => job?.userAdded ? {
  companyName:job.companyName, positionTitle:job.positionTitle, postingTitle:job.postingTitle,
  jobFamily:job.jobFamily, deadline:job.deadline, sourceUrl:job.sourceUrl,
  requiredSkills:job.requiredSkills||[], responsibilities:job.responsibilities||[]
} : undefined;

export async function requestCoach({ job, mode, message, profile, currentTasks, history }) {
  return fetchJson("/api/v1/agent/chat", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ postingId:job.postingId,jobContext:jobContextOf(job),mode,message,userProfile:{ experience:profile.experiences || "경험 미입력",deadline:job.deadline },currentTasks,history }) });
}

export async function requestEssayReview({ job, sections, experiences }) {
  return fetchJson("/api/v1/essays/review", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ postingId:job.postingId,jobContext:jobContextOf(job),sections,experiences }) });
}

export function createBrowserStore(type) {
  const target = type === "session" ? sessionStorage : localStorage;
  return {
    get(key, fallback) { try { return JSON.parse(target.getItem(`nextstep.${key}`)) ?? fallback; } catch { return fallback; } },
    set(key, value) { target.setItem(`nextstep.${key}`, JSON.stringify(value)); },
    remove(key) { target.removeItem(`nextstep.${key}`); }
  };
}

// ── 로그인한 사용자의 데이터. **절대 예외를 던지지 않는다.**
// 서버에 인증이 안 붙었거나 DB 가 죽어도 화면은 브라우저 저장소로 그대로 돌아야 한다.
// 그래서 실패는 전부 "없음"으로 바꿔 돌려준다.

export async function fetchMe() {
  try {
    // 첫 화면이 이 요청에 막히면 안 된다. 4초 넘으면 비로그인으로 보고 진행한다.
    const stop = new AbortController();
    const timer = setTimeout(() => stop.abort(), 4000);
    const response = await fetch("/api/v1/me", { signal: stop.signal });
    clearTimeout(timer);
    return response.ok ? await response.json() : { user: null, login: false };
  } catch { return { user: null, login: false }; }
}

/** 계정에 저장된 문서 하나. 없거나(신규) 못 가져오면 null → 로컬을 그대로 쓴다. */
export async function pullUserData() {
  try {
    const response = await fetch("/api/v1/me/profile");
    if (!response.ok) return null;                 // 401(로그아웃) · 503(DB 없음)
    return (await response.json()).profile || null;
  } catch { return null; }
}

export async function pushUserData(data) {
  try {
    const response = await fetch("/api/v1/me/profile",
      { method: "PUT", headers: jsonHeaders, body: JSON.stringify(data) });
    return response.ok;
  } catch { return false; }
}
