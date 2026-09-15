const $ = (id) => document.getElementById(id);
const state = { jobs: [], job: null, history: [], tasks: [], session: null };

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;" })[c]); }
function profile() { return { experience: $("experience").value.trim(), deadline: $("deadline").value || null }; }
function sessionKey(postingId) { return `overlap.session.${postingId}`; }
function emptySession(postingId) { return { postingId, profile: { experience: "", deadline: null }, history: [], tasks: [] }; }
function readSession(postingId) {
  try {
    const saved = JSON.parse(localStorage.getItem(sessionKey(postingId)) || "null");
    return saved?.postingId === postingId ? { ...emptySession(postingId), ...saved, profile: { ...emptySession(postingId).profile, ...saved.profile } } : emptySession(postingId);
  } catch { return emptySession(postingId); }
}
function saveSession() {
  if (!state.session) return;
  state.session.profile = profile();
  state.session.history = state.history;
  state.session.tasks = state.tasks;
  localStorage.setItem(sessionKey(state.session.postingId), JSON.stringify(state.session));
}
function resetMessages() { $("messages").innerHTML = '<article class="message assistant">공고와 경험을 입력한 뒤 요청하세요.</article>'; }
function renderHistory() { resetMessages(); state.history.forEach((item) => addMessage(item.role, item.content, [], "", false)); }
function resetWork(message) {
  state.history = [];
  state.tasks = [];
  resetMessages();
  renderTasks();
  saveSession();
  if (message) $("data-status").textContent = message;
}
function syncProfile() {
  if (!state.session) return;
  const current = profile();
  const previous = state.session.profile;
  if (current.experience !== previous.experience || current.deadline !== previous.deadline) {
    state.session.profile = current;
    if (state.history.length || state.tasks.length) resetWork("입력이 바뀌어 이전 대화와 할 일을 초기화했습니다.");
    else saveSession();
  }
}

async function loadJobs(job = "") {
  const response = await fetch(`/api/v1/job-contexts${job ? `?job=${encodeURIComponent(job)}` : ""}`);
  if (!response.ok) throw new Error("수집 데이터를 불러오지 못했습니다.");
  const data = await response.json();
  state.jobs = data.items;
  if (!job && data.families) $("job-filter").innerHTML = '<option value="">전체 직무</option>' + data.families.map((family) => `<option value="${escapeHtml(family)}">${escapeHtml(family)}</option>`).join("");
  $("posting-select").innerHTML = state.jobs.map((item) => `<option value="${item.postingId}">[${item.tier}] ${escapeHtml(item.companyName)} · ${escapeHtml(item.positionTitle)}</option>`).join("");
  if (state.jobs.length) await selectJob(state.jobs[0].postingId);
  $("data-status").textContent = `직무 데이터 ${data.total}건`;
}
function activateSession(postingId) {
  state.session = readSession(postingId);
  state.history = state.session.history.filter((item) => item?.postingId === postingId && ["user", "assistant"].includes(item.role) && typeof item.content === "string");
  state.tasks = state.session.tasks.filter((item) => item?.postingId === postingId && item?.title);
  $("experience").value = state.session.profile.experience || "";
  const deadline = state.job.deadline || state.session.profile.deadline || "";
  $("deadline").value = deadline;
  $("deadline").disabled = Boolean(state.job.deadline);
  $("deadline-note").textContent = state.job.deadline ? "공고에서 자동 입력" : "직접 입력";
  state.session.profile.deadline = deadline || null;
  renderHistory();
  renderTasks();
}
async function selectJob(id) {
  const response = await fetch(`/api/v1/job-contexts/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error("선택 공고의 상세 데이터를 불러오지 못했습니다.");
  state.job = await response.json();
  $("job-card").hidden = false;
  $("job-tier").textContent = state.job.tier;
  $("job-title").textContent = state.job.positionTitle;
  $("job-company").textContent = `${state.job.companyName} · ${state.job.jobFamily}`;
  $("job-skills").innerHTML = state.job.requiredSkills.length ? state.job.requiredSkills.map((skill) => `<span>${escapeHtml(skill)}</span>`).join("") : "<span>명시된 기술 없음</span>";
  $("job-source").href = state.job.sourceUrl;
  $("job-source").textContent = "원문 보기";
  activateSession(state.job.postingId);
}

async function askAgent(mode, message) {
  if (!state.job) return;
  syncProfile();
  const userProfile = profile();
  if (!userProfile.experience) {
    $("experience").focus();
    $("data-status").textContent = "경험을 입력해 주세요.";
    return;
  }
  addMessage("user", message);
  setBusy(true);
  try {
    const response = await fetch("/api/v1/agent/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, message, postingId: state.job.postingId, userProfile, currentTasks: state.tasks, history: state.history })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "AGENT_REQUEST_FAILED");
    addMessage("assistant", result.answer, result.evidence, result.modelUsed);
    if (result.nextActions.length) {
      state.tasks = result.nextActions.map((item, index) => ({ ...item, id: `${Date.now()}-${index}`, postingId: state.job.postingId, done: false }));
      saveSession();
      renderTasks();
      if (["timeline", "task_prioritization"].includes(mode)) {
        addMessage("assistant", `추천 준비 순서:\n${result.nextActions.map((item) => `- ${item.title}: ${item.reason}`).join("\n")}`, [], "", false);
      }
    }
    if (result.missingInformation.length) addMessage("assistant", `추가로 필요한 정보:\n- ${result.missingInformation.join("\n- ")}`);
  } catch (error) {
    addMessage("assistant", error.message === "UPSTAGE_API_KEY_MISSING" ? "API 키가 설정되지 않았습니다." : "Agent 요청에 실패했습니다.");
  } finally { setBusy(false); }
}
function addMessage(role, text, evidence = [], model = "", record = true) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.textContent = text;
  if (evidence.length) {
    const detail = document.createElement("div");
    detail.className = "evidence";
    detail.textContent = `근거 · ${evidence.map((item) => `${item.source}: “${item.quote}”`).join(" / ")}`;
    article.append(detail);
  }
  $("messages").append(article);
  $("messages").scrollTop = $("messages").scrollHeight;
  if (record && state.job) {
    state.history.push({ role, content: text, postingId: state.job.postingId });
    saveSession();
  }
  if (model) $("agent-state").textContent = `${model} 응답`;
}
function renderTasks() {
  $("task-list").innerHTML = state.tasks.length ? state.tasks.map((task) => `<li class="${task.done ? "done" : ""}"><input class="task-check" type="checkbox" data-id="${task.id}" ${task.done ? "checked" : ""}><div><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.reason || "")}</small></div><span class="priority">${task.priority || "medium"}</span></li>`).join("") : '<li class="empty">아직 할 일이 없습니다.</li>';
}
function setBusy(busy) { $("send-button").disabled = busy; $("agent-state").textContent = busy ? "JD 근거 확인 중" : "Agent 준비됨"; }

$("job-filter").addEventListener("change", (event) => loadJobs(event.target.value).catch(showLoadError));
$("posting-select").addEventListener("change", (event) => selectJob(event.target.value).catch(showLoadError));
$("save-profile").addEventListener("click", () => { syncProfile(); saveSession(); $("data-status").textContent = "저장됨"; });
document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
  const prompts = { timeline: "선택한 공고 마감일까지의 지원 준비 타임라인을 만들어줘.", cover_letter_guide: "이 JD에 맞춰 자소서를 어떤 경험부터 어떤 순서로 시작하면 좋을지 안내해줘.", task_prioritization: "현재 준비 상태에서 이번 주에 해야 할 일을 우선순위로 정리해줘." };
  askAgent(button.dataset.mode, prompts[button.dataset.mode]);
}));
$("chat-form").addEventListener("submit", (event) => { event.preventDefault(); const text = $("chat-input").value.trim(); if (!text) return; $("chat-input").value = ""; askAgent("consultation", text); });
$("task-list").addEventListener("change", (event) => { const task = state.tasks.find((item) => item.id === event.target.dataset.id); if (task) { task.done = event.target.checked; saveSession(); renderTasks(); } });

renderTasks();
Promise.all([loadJobs(), fetch("/api/v1/agent/status").then((response) => response.json())]).then(([, agent]) => {
  $("agent-state").textContent = agent.configured ? `${agent.fastModel} · ${agent.coachModel}` : "API 키 연결 필요";
}).catch(showLoadError);
function showLoadError(error) { $("data-status").textContent = error.message; $("agent-state").textContent = "데이터 연결 실패"; }
