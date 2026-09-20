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

export async function requestPostingMatches(text, families = []) {
  return fetchJson("/api/v1/posting-matches", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ texts:text.split(/\n+/).filter(Boolean),families,limit:5 }) });
}

export async function requestCoach({ job, mode, message, profile, currentTasks, history }) {
  return fetchJson("/api/v1/agent/chat", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ postingId:job.postingId,mode,message,userProfile:{ experience:profile.experiences || "경험 미입력",deadline:job.deadline },currentTasks,history }) });
}

export async function requestEssayReview({ job, sections, experiences }) {
  return fetchJson("/api/v1/essays/review", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ postingId:job.postingId,sections,experiences }) });
}

export function createBrowserStore(type) {
  const target = type === "session" ? sessionStorage : localStorage;
  return {
    get(key, fallback) { try { return JSON.parse(target.getItem(`nextstep.${key}`)) ?? fallback; } catch { return fallback; } },
    set(key, value) { target.setItem(`nextstep.${key}`, JSON.stringify(value)); },
    remove(key) { target.removeItem(`nextstep.${key}`); }
  };
}
