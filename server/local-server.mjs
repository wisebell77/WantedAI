import { createServer } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { spawn } from "node:child_process";
import { runCareerCoachAgent } from "./upstage-career-coach.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = join(root, "dist");
const dataDir = process.env.OVERLAP_DATA_DIR || join(root, "data", "overlap");
const recommendationBase = process.env.RECOMMENDATION_BASE_URL || "http://127.0.0.1:8000";
const pythonBin = process.env.PYTHON_BIN || (existsSync(join(root, ".venv", "bin", "python")) ? join(root, ".venv", "bin", "python") : "python3");

// LLM 제공자는 환경변수로 고른다. 요청 본문이 OpenAI 호환이라 URL·키·모델명만
// 바꾸면 Upstage 든 OpenAI 든 그대로 돈다. UPSTAGE_* 는 폴백으로 남긴다.
const llmKey = () => process.env.LLM_API_KEY || process.env.UPSTAGE_API_KEY || "";
const llmFastModel = () => process.env.LLM_FAST_MODEL || process.env.UPSTAGE_FAST_MODEL || "solar-mini";
const llmCoachModel = () => process.env.LLM_COACH_MODEL || process.env.UPSTAGE_COACH_MODEL || "solar-pro4";

try {
  const raw = await readFile(join(root, ".env"), "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (match && !process.env[match[1]]) process.env[match[1]] = match[2].replace(/^['"]|['"]$/g, "");
  }
} catch {}

const roles = JSON.parse(await readFile(join(dataDir, "roles.json"), "utf8"));
const postings = JSON.parse(await readFile(join(dataDir, "jd_tiered.json"), "utf8"));
const liveSource = JSON.parse(await readFile(join(dataDir, "gongchae_all.json"), "utf8"));
const postingByUrl = new Map(postings.map((item) => [item.url, item]));
const liveByUrl = new Map();
for (const item of liveSource) {
  for (const url of [item.empWantedHomepgDetail, item.empWantedMobileUrl].filter(Boolean)) {
    const list = liveByUrl.get(url) || [];
    list.push(item);
    liveByUrl.set(url, list);
  }
}
const personaRoleIndexes = new Map();
function roleExcerpt(text = "", roleName = "") {
  const index = roleName ? text.indexOf(roleName) : -1;
  const start = index >= 0 ? Math.max(0, index - 120) : 0;
  return text.slice(start, start + 2200);
}
function extractDeadline(text = "") {
  const dates = [...text.matchAll(/(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일/g)].map((match) => ({
    value: `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`,
    index: match.index
  }));
  const ranked = dates.map((date) => {
    const context = text.slice(Math.max(0, date.index - 120), date.index + 40);
    const score = (/(마감|접수|지원)/.test(context) ? 2 : 0) - (/(유효|경력|입사|졸업)/.test(context) ? 2 : 0);
    return { ...date, score };
  }).sort((a, b) => b.score - a.score || b.index - a.index);
  return ranked[0]?.score > 0 ? ranked[0].value : null;
}
const contexts = roles.map((role, index) => {
  const posting = postingByUrl.get(role.url) || {};
  const personaRoleIndex = personaRoleIndexes.get(role.url) || 0;
  personaRoleIndexes.set(role.url, personaRoleIndex + 1);
  return {
    postingId: `role-${index + 1}`,
    companyName: role.corp,
    positionTitle: role.role || role.post_title,
    postingTitle: role.post_title,
    jobFamily: role.job,
    tier: role.post_tier || "",
    responsibilities: posting.clean ? [roleExcerpt(posting.clean, role.role)] : [],
    requiredSkills: role.techs || [],
    preferredSkills: [],
    sourceUrl: role.url,
    personaRoleIndex,
    deadline: null,
    sourceType: role.src,
    sourceUpdatedAt: "2026-09-11"
  };
});

function ymd(value = "") {
  const match = String(value).match(/^(\d{4})(\d{2})(\d{2})$/);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : null;
}
function seoulDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const value = Object.fromEntries(parts.filter(({ type }) => type !== "literal").map(({ type, value }) => [type, value]));
  return `${value.year}-${value.month}-${value.day}`;
}
const contextByUrl = new Map();
for (const item of contexts) {
  const rows = contextByUrl.get(item.sourceUrl) || [];
  rows.push(item);
  contextByUrl.set(item.sourceUrl, rows);
}
const livePostings = liveSource.map((item) => {
  const url = item.empWantedHomepgDetail || item.empWantedMobileUrl || "";
  const matches = contextByUrl.get(url) || [];
  const exact = matches.find((row) => item.empWantedTitle?.includes(row.positionTitle) && row.requiredSkills.length)
    || matches.find((row) => row.requiredSkills.length)
    || matches.find((row) => item.empWantedTitle?.includes(row.positionTitle))
    || matches[0];
  const deadline = ymd(item.empWantedEndt);
  if (exact && deadline) exact.deadline = deadline;
  return {
    postingId: exact?.postingId || null,
    externalId: String(item.empSeqno || ""),
    companyName: item.empBusiNm || exact?.companyName || "기업명 미확인",
    positionTitle: item.empWantedTitle || exact?.positionTitle || "채용 공고",
    jobFamily: exact?.jobFamily || "직무 미분류",
    employmentType: item.empWantedTypeNm || "",
    companyType: item.coClcdNm || "",
    startDate: ymd(item.empWantedStdt),
    startTime: item.empWantedStdtTime || null,
    deadline,
    deadlineTime: item.empWantedEndtTime || null,
    sourceUrl: url,
    coachReady: Boolean(exact?.requiredSkills.length && exact?.responsibilities.length),
    requiredSkills: exact?.requiredSkills || []
  };
}).sort((a, b) => String(a.deadline || "9999").localeCompare(String(b.deadline || "9999")));

// ── 경험 ↔ 모집 중 공고 대조 ────────────────────────────────────────────────
// 직무 추천(NCS)과 실시간 공고의 축이 달라, 추천 결과로 실제 지원할 공고를 찾을 수 없었다.
// 여기서는 실시간 공고 탭이 쓰는 바로 그 데이터(livePostings + contexts)로 대조해
// "지금 지원 가능한 공고" 를 근거와 함께 돌려준다. 축이 같으므로 이름이 어긋나지 않는다.
const contextById = new Map(contexts.map((row) => [row.postingId, row]));
const SKILL_DF = new Map();
for (const row of contexts) {
  for (const skill of new Set((row.requiredSkills || []).map((s) => s.toLowerCase()))) {
    SKILL_DF.set(skill, (SKILL_DF.get(skill) || 0) + 1);
  }
}
const SKILL_VOCAB = [...SKILL_DF.keys()].sort((a, b) => b.length - a.length);
const SKILL_ALIAS = { "파이썬": "python", "엑셀": "excel", "자바": "java", "리액트": "react", "깃": "git", "깃허브": "git", "오라클": "oracle", "리눅스": "linux" };
const skillIdf = (skill) => Math.log(1 + contexts.length / (1 + (SKILL_DF.get(skill) || 0)));
const CAREER_RE = /경력\s*(\d+)\s*년|(\d+)\s*년\s*이상/;
const GRADUATE_RE = /(석사|박사)\s*(학위)?\s*(이상|소지|보유|취득)/;

function hasTerm(term, text) {
  if (term.length <= 2 && /^[\x20-\x7e]+$/.test(term)) {
    return new RegExp(`(?<![A-Za-z&+#])${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![A-Za-z&+#])`, "i").test(text);
  }
  return text.toLowerCase().includes(term);
}
function bigrams(text) {
  const clean = (text || "").toLowerCase().replace(/\s+/g, "");
  const out = new Set();
  for (let i = 0; i < clean.length - 1; i += 1) out.add(clean.slice(i, i + 2));
  return out;
}
function similarity(a, b) {
  const left = bigrams(a); const right = bigrams(b);
  if (!left.size || !right.size) return 0;
  let shared = 0;
  for (const gram of left) if (right.has(gram)) shared += 1;
  return shared / (left.size + right.size - shared);
}
function requirementLines(context) {
  return (context?.responsibilities || []).join("\n").split(/\n|·|•|\u2219/)
    .map((line) => line.replace(/^[\s\-*■□▶ㆍ]+/, "").trim())
    .filter((line) => line.length >= 6 && line.length <= 70).slice(0, 12);
}
function eligibility(context, text) {
  const body = (context?.responsibilities || []).join("\n").split("\n")
    .filter((line) => !line.includes("우대")).join("\n");
  const reasons = [];
  const career = body.match(CAREER_RE);
  if (career && !text.includes("신입")) reasons.push(`경력 ${career[1] || career[2]}년 이상 요구`);
  const graduate = body.match(GRADUATE_RE);
  if (graduate) reasons.push(`${graduate[1]} 학위 요구`);
  return reasons;
}

function matchPostings({ texts = [], families = [], today = seoulDate(), limit = 5 }) {
  const userText = texts.join("\n");
  if (!userText.trim()) return { items: [], userSkills: [] };
  const userSentences = userText.split(/[.\n]/).map((s) => s.trim()).filter((s) => s.length >= 5);
  const userSkills = SKILL_VOCAB.filter((skill) => hasTerm(skill, userText))
    .concat(Object.entries(SKILL_ALIAS).filter(([ko]) => userText.includes(ko)).map(([, en]) => en));
  const skillSet = new Set(userSkills);

  const scored = [];
  for (const posting of livePostings) {
    if (posting.deadline && posting.deadline < today) continue;
    const context = contextById.get(posting.postingId);
    const skills = (posting.requiredSkills || []).map((s) => s.toLowerCase());
    const shared = skills.filter((skill) => skillSet.has(skill));
    const skillScore = skills.length
      ? shared.reduce((sum, s) => sum + skillIdf(s), 0) / skills.reduce((sum, s) => sum + skillIdf(s), 0) : 0;
    const lines = requirementLines(context);
    const evidence = [];
    for (const line of lines) {
      let best = { score: 0, sentence: "" };
      for (const sentence of userSentences) {
        const score = similarity(sentence, line);
        if (score > best.score) best = { score, sentence };
      }
      const skillHit = shared.some((skill) => hasTerm(skill, line));
      if (best.score >= 0.12 || skillHit) evidence.push({ jdQuote: line, userQuote: best.sentence, score: Number(best.score.toFixed(2)) });
    }
    const requirementScore = lines.length ? evidence.length / lines.length : 0;
    const familyScore = families.includes(posting.jobFamily) ? 1 : 0;
    let score = 0.5 * skillScore + 0.35 * requirementScore + 0.15 * familyScore;
    if (score <= 0) continue;
    const reasons = eligibility(context, userText);
    if (reasons.length) score *= 0.7;
    scored.push({
      postingId: posting.postingId, externalId: posting.externalId,
      companyName: posting.companyName, positionTitle: posting.positionTitle,
      jobFamily: posting.jobFamily, deadline: posting.deadline, sourceUrl: posting.sourceUrl,
      coachReady: posting.coachReady, score: Number(score.toFixed(3)),
      sharedSkills: shared, evidence: evidence.slice(0, 2),
      status: reasons.length ? "준비 필요" : "지금 지원 가능", reasons
    });
  }
  const seen = new Set();
  const items = scored.sort((a, b) => b.score - a.score || String(a.deadline || "9999").localeCompare(String(b.deadline || "9999")))
    .filter((row) => { const key = row.sourceUrl || row.postingId; if (seen.has(key)) return false; seen.add(key); return true; })
    .slice(0, limit);
  return { items, userSkills: [...new Set(userSkills)],
    note: "겹침 정도이며 합격 가능성이 아닙니다. 자격 요건은 공고 원문에서 확인하세요." };
}

const mime = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp" };
const sendJson = (res, status, body) => { res.writeHead(status, { "Content-Type": mime[".json"] }); res.end(JSON.stringify(body)); };
async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"); }
  catch { const error = new Error("INVALID_JSON"); error.code = "INVALID_JSON"; throw error; }
}
async function readBody(req, limit = 120 * 1024 * 1024, tooLargeCode = "AUDIO_TOO_LARGE") {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) { const error = new Error(tooLargeCode); error.code = tooLargeCode; throw error; }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}
async function proxyRecommendation(req, res, path) {
  const options = { method: req.method, headers: { Accept: "application/json" } };
  if (req.method === "POST") {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(await readJson(req));
  }
  try {
    const response = await fetch(`${recommendationBase}${path}`, options);
    return sendJson(res, response.status, await response.json());
  } catch {
    return sendJson(res, 503, { error: "RECOMMENDATION_ENGINE_UNAVAILABLE" });
  }
}
function transcriptionPrompt(job) {
  if (!job) return "";
  const terms = [job.companyName, job.positionTitle, ...(job.requiredSkills || []), ...(job.preferredSkills || []), ...(job.responsibilities || [])]
    .filter(Boolean).join(" ").replace(/\s+/g, " ");
  return `다음은 지원 면접의 회사 및 직무 용어입니다. 발화에 나온 용어를 가능한 그대로 전사하세요. ${terms}`.slice(0, 900);
}
async function transcribeWithFasterWhisper(audio, prompt = "") {
  const workDir = await mkdtemp(join(tmpdir(), "overlap-stt-"));
  const audioPath = join(workDir, "answer.webm");
  const python = pythonBin;
  try {
    await writeFile(audioPath, audio);
    const output = await new Promise((resolve, reject) => {
      const child = spawn(python, [join(root, "server", "transcribe.py"), audioPath, prompt], { stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
      let stdout = "";
      let stderr = "";
      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", (chunk) => { stdout += chunk; });
      child.stderr.on("data", (chunk) => { stderr += chunk; });
      child.on("error", reject);
      child.on("close", (code) => code === 0 ? resolve(stdout) : reject(new Error(stderr || "FASTER_WHISPER_FAILED")));
    });
    return JSON.parse(output);
  } finally {
    await rm(workDir, { recursive: true, force: true });
  }
}
async function analyzeWithMediaPipe(video) {
  const workDir = await mkdtemp(join(tmpdir(), "overlap-video-"));
  const videoPath = join(workDir, "interview.webm");
  const python = pythonBin;
  try {
    await writeFile(videoPath, video);
    const output = await new Promise((resolve, reject) => {
      const child = spawn(python, [join(root, "server", "analyze_video.py"), videoPath], { stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
      let stdout = "";
      let stderr = "";
      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", (chunk) => { stdout += chunk; });
      child.stderr.on("data", (chunk) => { stderr += chunk; });
      child.on("error", reject);
      child.on("close", (code) => code === 0 ? resolve(stdout) : reject(new Error(stderr || stdout || "MEDIAPIPE_FAILED")));
    });
    return JSON.parse(output);
  } finally {
    await rm(workDir, { recursive: true, force: true });
  }
}
async function runPersonaBridge(input) {
  const python = pythonBin;
  return new Promise((resolve, reject) => {
    const child = spawn(python, [join(root, "server", "persona_bridge.py")], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, OVERLAP_DATA_DIR: dataDir, PYTHONIOENCODING: "utf-8" }
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      if (stderr.trim()) console.error("Persona bridge:", stderr.trim());
      if (code !== 0) return reject(new Error(stderr || "PERSONA_BRIDGE_FAILED"));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error("PERSONA_BRIDGE_INVALID_JSON")); }
    });
    child.stdin.end(JSON.stringify(input), "utf8");
  });
}
const validModes = new Set(["timeline", "task_prioritization", "jd_tagging", "cover_letter_guide", "consultation", "interview_feedback"]);
const interviewPersonas = new Map();
async function evaluateInterviewTranscript(postingId, job, question, itemId, transcript) {
  let persona = interviewPersonas.get(postingId);
  if (!persona) {
    persona = await runPersonaBridge({ action: "persona", posting: job });
    interviewPersonas.set(postingId, persona);
  }
  if (!persona.rubric.items.length || !persona.questions.length) throw new Error("JOB_RUBRIC_UNAVAILABLE");
  const selectedItemId = itemId || persona.questions[0]?.item_id;
  if (!persona.rubric.items.some((item) => item.id === selectedItemId)) throw new Error("VALID_RUBRIC_ITEM_REQUIRED");
  const result = await runPersonaBridge({
    action: "evaluate",
    rubric: persona.rubric,
    itemId: selectedItemId,
    answer: transcript
  });
  const selectedQuestion = question || persona.questions.find((item) => item.item_id === selectedItemId)?.question || "";
  return {
    feedback: [{ label: result.label, title: `${result.label} · ${result.score}/3`, body: result.feedback, type: result.score >= 2 ? "good" : "improve" }],
    followupQuestion: result.followupQuestion,
    evidence: [
      { source: "JD", quote: result.jdQuote },
      ...(result.answerEvidence ? [{ source: "답변", quote: result.answerEvidence }] : [])
    ],
    score: result.score,
    note: result.note,
    modelUsed: result.modelUsed,
    itemId: selectedItemId,
    question: selectedQuestion
  };
}
function fallbackActions(input) {
  const skills = input.jobContext.requiredSkills.slice(0, 3).join(", ") || "공고의 필수 조건";
  if (input.mode === "task_prioritization") return [
    { title: "공고 요구사항 확인", reason: `${skills}와 내 경험의 연결점을 정리합니다.`, priority: "high" },
    { title: "경험 근거 정리", reason: "수치, 역할, 결과가 드러나는 경험 한 가지를 정리합니다.", priority: "high" },
    { title: "자소서 초안 작성", reason: "정리한 경험을 바탕으로 지원 동기를 초안으로 작성합니다.", priority: "medium" }
  ];
  if (input.mode !== "timeline") return [];
  const days = input.jobContext.deadline ? daysUntilDeadline(input.jobContext.deadline) : null;
  const label = (ratio, fallback) => days === null ? fallback : (Math.max(0, Math.ceil(days * ratio)) ? `D-${Math.max(0, Math.ceil(days * ratio))}` : "마감일");
  return [
    { title: `${label(1, "1단계")} · 공고 요구사항 확인`, reason: `${skills}와 내 경험의 연결점을 정리합니다.`, priority: "high" },
    { title: `${label(0.65, "2단계")} · 경험 근거 정리`, reason: "수치, 역할, 결과가 드러나는 경험 한 가지를 정리합니다.", priority: "high" },
    { title: `${label(0.35, "3단계")} · 자소서 초안 작성`, reason: "정리한 경험을 바탕으로 지원 동기를 작성합니다.", priority: "medium" },
    { title: `${label(0, "4단계")} · 제출 전 확인`, reason: "지원서와 필수 제출 정보를 마지막으로 확인합니다.", priority: "low" }
  ];
}
function daysUntilDeadline(deadline) {
  const today = new Date(`${seoulDate()}T00:00:00`);
  const due = new Date(`${deadline}T00:00:00`);
  return Math.max(0, Math.round((due - today) / 86400000));
}
function addTimelineLabels(actions, input) {
  if (input.mode !== "timeline" || !input.jobContext.deadline) return actions;
  const days = daysUntilDeadline(input.jobContext.deadline);
  return actions.map((item, index) => {
    const title = String(item.title || "")
      .replace(/^(D-\d+|마감일)\s*[·:：-]\s*/i, "")
      .replace(/\s*\(D-\d+\)\s*$/i, "")
      .trim();
    const remaining = Math.max(0, Math.ceil(days * (1 - index / Math.max(1, actions.length - 1))));
    return { ...item, title: `${remaining ? `D-${remaining}` : "마감일"} · ${title}` };
  });
}
function normalizeAgentResult(result, input) {
  if (typeof result?.answer !== "string" || !result.answer.trim()) {
    const error = new Error("AGENT_RESPONSE_INVALID");
    error.code = "AGENT_RESPONSE_INVALID";
    throw error;
  }
  const asArray = (value) => Array.isArray(value) ? value : (typeof value === "string" && value.trim() ? [value] : []);
  const nextActions = asArray(result.nextActions).filter((item) => item?.title).slice(0, 5).map((item) => ({
    title: String(item.title), reason: String(item.reason || ""), priority: ["high", "medium", "low"].includes(item.priority) ? item.priority : "medium"
  }));
  return {
    answer: result.answer.trim(),
    evidence: asArray(result.evidence).filter((item) => item?.source && item?.quote).map((item) => ({ source: String(item.source), quote: String(item.quote) })),
    nextActions: addTimelineLabels(nextActions.length ? nextActions : fallbackActions(input), input),
    missingInformation: asArray(result.missingInformation).map(String),
    modelUsed: result.modelUsed
  };
}
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    if (req.method === "GET" && url.pathname === "/api/v1/agent/status") {
      return sendJson(res, 200, {
        configured: Boolean(llmKey()),
        fastModel: llmFastModel(),
        coachModel: llmCoachModel()
      });
    }
    if (req.method === "GET" && url.pathname === "/api/jobs") {
      return proxyRecommendation(req, res, "/api/jobs");
    }
    if (req.method === "POST" && url.pathname === "/api/v1/posting-matches") {
      const input = await readJson(req);
      const texts = Array.isArray(input.texts) ? input.texts : String(input.text || "").split(/\n+/);
      return sendJson(res, 200, matchPostings({
        texts: texts.filter(Boolean), families: input.families || [],
        today: input.asOf || seoulDate(), limit: Number(input.limit) || 5
      }));
    }
    if (req.method === "POST" && url.pathname === "/api/recommend") {
      return proxyRecommendation(req, res, "/api/recommend");
    }
    if (req.method === "GET" && url.pathname === "/api/v1/live-postings") {
      const today = url.searchParams.get("asOf") || seoulDate();
      const job = url.searchParams.get("job") || "";
      const q = (url.searchParams.get("q") || "").toLowerCase();
      const days = Number(url.searchParams.get("days") || 0);
      const until = days ? new Date(new Date(`${today}T00:00:00Z`).getTime() + days * 86400000).toISOString().slice(0, 10) : null;
      const items = livePostings.filter((item) => (!item.deadline || item.deadline >= today)
        && (!until || !item.deadline || item.deadline <= until)
        && (!job || item.jobFamily === job)
        && (!q || `${item.companyName} ${item.positionTitle} ${item.jobFamily}`.toLowerCase().includes(q)));
      return sendJson(res, 200, { items, total: items.length, coachReady: items.filter((item) => item.coachReady).length, source: "gongchae_all.json" });
    }
    if (req.method === "GET" && url.pathname === "/api/v1/job-contexts") {
      const job = url.searchParams.get("job");
      const items = contexts.filter((item) => !job || item.jobFamily === job).sort((a, b) => String(a.tier || "").localeCompare(String(b.tier || ""))).slice(0, 80).map(({ responsibilities, ...summary }) => summary);
      return sendJson(res, 200, { items, total: items.length, families: [...new Set(contexts.map((item) => item.jobFamily))].sort(), source: "Overlap_데이터_20260911" });
    }
    if (req.method === "GET" && url.pathname.startsWith("/api/v1/job-contexts/")) {
      const item = contexts.find((row) => row.postingId === decodeURIComponent(url.pathname.split("/").pop()));
      return item ? sendJson(res, 200, item) : sendJson(res, 404, { error: "JOB_CONTEXT_NOT_FOUND" });
    }
    if (req.method === "GET" && url.pathname === "/api/v1/agent/interview-persona") {
      const postingId = url.searchParams.get("postingId");
      const job = contexts.find((row) => row.postingId === postingId);
      if (!job) return sendJson(res, 422, { error: "VALID_POSTING_ID_REQUIRED" });
      try {
        let persona = interviewPersonas.get(postingId);
        if (!persona) {
          persona = await runPersonaBridge({ action: "persona", posting: job });
          interviewPersonas.set(postingId, persona);
        }
        if (!persona.rubric.items.length || !persona.questions.length) return sendJson(res, 422, { error: "JOB_RUBRIC_UNAVAILABLE" });
        return sendJson(res, 200, {
          persona: persona.rubric.persona,
          rubricId: persona.rubric.rubric_id,
          generatedBy: persona.rubric.generated_by,
          items: persona.rubric.items.map(({ id, label, jd_quote, kind, keywords, followup }) => ({ id, label, jdQuote: jd_quote, kind, keywords, followup })),
          questions: persona.questions
        });
      } catch (error) {
        console.error("Interview persona error:", error.message);
        return sendJson(res, 502, { error: "INTERVIEW_PERSONA_UNAVAILABLE" });
      }
    }
    if (req.method === "POST" && url.pathname === "/api/v1/agent/chat") {
      if (!llmKey()) return sendJson(res, 503, { error: "LLM_API_KEY_MISSING" });
      const input = await readJson(req);
      if (!validModes.has(input.mode)) return sendJson(res, 422, { error: "VALID_AGENT_MODE_REQUIRED" });
      const canonicalJob = contexts.find((row) => row.postingId === input.postingId);
      if (!canonicalJob) return sendJson(res, 422, { error: "VALID_POSTING_ID_REQUIRED" });
      if (!input.userProfile?.experience?.trim()) return sendJson(res, 422, { error: "USER_EXPERIENCE_REQUIRED" });
      if (!input.message?.trim()) return sendJson(res, 422, { error: "MESSAGE_REQUIRED" });
      try {
        const result = await runCareerCoachAgent({ ...input, jobContext: canonicalJob }, {
          apiKey: llmKey(),
          fastModel: llmFastModel(),
          coachModel: llmCoachModel()
        });
        return sendJson(res, 200, normalizeAgentResult(result, { ...input, jobContext: canonicalJob }));
      } catch (error) {
        console.error("Agent upstream error:", error.message);
        return sendJson(res, 502, { error: "AGENT_UPSTREAM_ERROR" });
      }
    }
    if (req.method === "POST" && url.pathname === "/api/v1/agent/interview-feedback") {
      const input = await readJson(req);
      const canonicalJob = contexts.find((row) => row.postingId === input.postingId);
      if (!canonicalJob) return sendJson(res, 422, { error: "VALID_POSTING_ID_REQUIRED" });
      if (!input.question?.trim()) return sendJson(res, 422, { error: "QUESTION_REQUIRED" });
      if (!input.transcript?.trim()) return sendJson(res, 422, { error: "TRANSCRIPT_REQUIRED" });
      try {
        let persona = interviewPersonas.get(input.postingId);
        if (!persona) {
          persona = await runPersonaBridge({ action: "persona", posting: canonicalJob });
          interviewPersonas.set(input.postingId, persona);
        }
        if (!persona.rubric.items.length || !persona.questions.length) return sendJson(res, 422, { error: "JOB_RUBRIC_UNAVAILABLE" });
        const itemId = input.itemId || persona.questions[0]?.item_id;
        if (!persona.rubric.items.some((item) => item.id === itemId)) return sendJson(res, 422, { error: "VALID_RUBRIC_ITEM_REQUIRED" });
        const result = await runPersonaBridge({
          action: "evaluate",
          rubric: persona.rubric,
          itemId,
          answer: input.transcript,
          followupAnswer: input.followupAnswer || ""
        });
        return sendJson(res, 200, {
          feedback: [{ label: result.label, title: `${result.label} · ${result.score}/3`, body: result.feedback, type: result.score >= 2 ? "good" : "improve" }],
          followupQuestion: result.followupQuestion,
          evidence: [
            { source: "JD", quote: result.jdQuote },
            ...(result.answerEvidence ? [{ source: "답변", quote: result.answerEvidence }] : [])
          ],
          score: result.score,
          note: result.note,
          modelUsed: result.modelUsed
        });
      } catch (error) {
        console.error("Interview persona evaluation error:", error.message);
        return sendJson(res, 502, { error: "INTERVIEW_AGENT_UPSTREAM_ERROR" });
      }
    }
    if (req.method === "POST" && url.pathname === "/api/v1/essays/review") {
      const input = await readJson(req);
      const canonicalJob = contexts.find((row) => row.postingId === input.postingId);
      if (!canonicalJob) return sendJson(res, 422, { error: "VALID_POSTING_ID_REQUIRED" });
      const letter = (input.sections || []).map((item) => `${item.question || ""}\n${item.answer || ""}`).join("\n\n").trim();
      if (!letter) return sendJson(res, 422, { error: "ESSAY_REQUIRED" });
      try {
        let persona = interviewPersonas.get(input.postingId);
        if (!persona) {
          persona = await runPersonaBridge({ action: "persona", posting: canonicalJob });
          interviewPersonas.set(input.postingId, persona);
        }
        const result = await runPersonaBridge({ action: "review", rubric: persona.rubric, letter, experiences: input.experiences || [] });
        return sendJson(res, 200, result);
      } catch (error) {
        console.error("Essay review error:", error.message);
        return sendJson(res, 502, { error: "ESSAY_REVIEW_UNAVAILABLE" });
      }
    }
    if (req.method === "POST" && url.pathname === "/api/v1/interview/transcribe") {
      const audio = await readBody(req);
      if (!audio.length) return sendJson(res, 422, { error: "AUDIO_REQUIRED" });
      const job = contexts.find((row) => row.postingId === url.searchParams.get("postingId"));
      try { return sendJson(res, 200, await transcribeWithFasterWhisper(audio, transcriptionPrompt(job))); }
      catch (error) {
        console.error("Faster-whisper error:", error.message);
        return sendJson(res, 503, { error: "FASTER_WHISPER_UNAVAILABLE" });
      }
    }
    if (req.method === "POST" && url.pathname === "/api/v1/interview/analyze") {
      const video = await readBody(req, 120 * 1024 * 1024, "VIDEO_TOO_LARGE");
      if (!video.length) return sendJson(res, 422, { error: "VIDEO_REQUIRED" });
      try {
        // The temporary video is deleted in analyzeWithMediaPipe's finally block.
        return sendJson(res, 200, await analyzeWithMediaPipe(video));
      } catch (error) {
        console.error("MediaPipe error:", error.message);
        return sendJson(res, 503, { error: error.message.startsWith("MEDIAPIPE_") ? error.message : "MEDIAPIPE_UNAVAILABLE" });
      }
    }
    if (req.method === "POST" && url.pathname === "/api/v1/interview/process") {
      const video = await readBody(req, 120 * 1024 * 1024, "VIDEO_TOO_LARGE");
      if (!video.length) return sendJson(res, 422, { error: "VIDEO_REQUIRED" });
      const job = contexts.find((row) => row.postingId === url.searchParams.get("postingId"));
      try {
        const [videoAnalysis, transcription] = await Promise.all([
          analyzeWithMediaPipe(video),
          transcribeWithFasterWhisper(video, transcriptionPrompt(job))
        ]);
        let personaEvaluation = null;
        if (job && transcription.text) {
          const persona = interviewPersonas.get(job.postingId);
          const selectedQuestion = url.searchParams.get("question") || persona?.questions?.[0]?.question || "";
          const selectedItemId = url.searchParams.get("itemId") || persona?.questions?.[0]?.item_id || "";
          try {
            personaEvaluation = await evaluateInterviewTranscript(job.postingId, job, selectedQuestion, selectedItemId, transcription.text);
          } catch (error) {
            personaEvaluation = { error: error.message === "JOB_RUBRIC_UNAVAILABLE" ? error.message : "INTERVIEW_PERSONA_EVALUATION_UNAVAILABLE" };
          }
        }
        return sendJson(res, 200, { videoAnalysis, transcription, personaEvaluation, retention: "deleted-after-processing" });
      } catch (error) {
        console.error("Interview processing error:", error.message);
        return sendJson(res, 503, { error: error.message.startsWith("MEDIAPIPE_") ? error.message : "INTERVIEW_PROCESSING_UNAVAILABLE" });
      }
    }
    const requested = url.pathname === "/" ? "/next-step.html" : url.pathname;
    const filePath = normalize(join(dist, requested));
    if (!filePath.startsWith(dist)) return sendJson(res, 403, { error: "FORBIDDEN" });
    const file = await readFile(filePath);
    res.writeHead(200, { "Content-Type": mime[extname(filePath)] || "application/octet-stream" });
    res.end(file);
  } catch (error) {
    if (error.code === "INVALID_JSON") return sendJson(res, 400, { error: "INVALID_JSON" });
    if (error.code === "AUDIO_TOO_LARGE") return sendJson(res, 413, { error: "AUDIO_TOO_LARGE" });
    if (error.code === "VIDEO_TOO_LARGE") return sendJson(res, 413, { error: "VIDEO_TOO_LARGE" });
    if (error.code === "ENOENT") return sendJson(res, 404, { error: "NOT_FOUND" });
    console.error(error);
    sendJson(res, 500, { error: "INTERNAL_ERROR" });
  }
});

// 컨테이너에서는 0.0.0.0 에 묶여야 외부에서 닿는다. 기본값은 127.0.0.1 로 두고
// 배포에서 HOST 를 넘긴다 — 로컬에서 실수로 외부에 열리는 쪽이 더 나쁘다.
const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 4173);
server.listen(port, host, () => console.log(`Overlap Career Coach: http://${host}:${port}`));
