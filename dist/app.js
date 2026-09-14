const roleData = {
  data: {
    signal: "문제 정의 · 분석 과정 · 사업적 영향",
    questions: [
      "데이터로 문제를 정의하고 해결했던 경험을 설명해 주세요.",
      "분석 결과가 예상과 달랐을 때 어떻게 검증했나요?",
      "이해관계자에게 복잡한 분석을 설득력 있게 전달한 경험이 있나요?"
    ],
    rubric: [
      { label: "문제·목표 정의", checks: [/(문제|이탈|상황|과제)/, /(목표|지표|정확도|전환율|비율)/, /(사용자|사업|고객|서비스|매출)/], followup: "문제의 영향을 무엇으로 판단했고, 왜 그 지표를 목표로 삼았는지 설명해 주세요." },
      { label: "분석 판단", checks: [/(제가|저는|직접|담당)/, /(가설|분석|검증|비교|쿼리|모델)/, /(선택|판단|결정|기준|이유)/], followup: "여러 분석 방법 중 어떤 기준으로 현재 방법을 선택했고, 다른 가능성은 어떻게 검증했나요?" },
      { label: "결과·회고", checks: [/(결과|성과|개선|증가|감소|달성)/, /\d|퍼센트|배|명|건/, /(배웠|한계|다음|보완|회고)/], followup: "결과를 보여주는 수치와, 그 결과가 기대와 달랐을 때 얻은 배움을 함께 설명해 주세요." }
    ],
    keywords: ["데이터", "분석", "가설", "검증", "지표", "결과"]
  },
  pm: {
    signal: "사용자 문제 · 우선순위 · 협업 결과",
    questions: [
      "사용자 문제를 발견하고 해결 방향을 결정했던 경험을 설명해 주세요.",
      "제한된 자원 안에서 우선순위를 정했던 기준은 무엇인가요?",
      "개발자·디자이너와 의견이 달랐을 때 어떻게 합의했나요?"
    ],
    rubric: [
      { label: "사용자 문제", checks: [/(사용자|고객|페르소나|인터뷰)/, /(문제|불편|이탈|요구)/, /(상황|당시|맥락|과제)/], followup: "사용자가 실제로 겪은 문제를 어떤 근거로 확인했고, 왜 중요한 문제라고 판단했나요?" },
      { label: "우선순위 판단", checks: [/(제가|저는|직접|담당)/, /(우선순위|기준|결정|선택|트레이드오프)/, /(가설|데이터|요구사항|검증)/], followup: "제한된 시간이나 자원 안에서 무엇을 포기하고 무엇을 우선했는지, 그 기준을 설명해 주세요." },
      { label: "협업 결과", checks: [/(개발|디자인|팀원|이해관계자|협업)/, /(결과|성과|개선|출시|반영)/, /(배웠|한계|다음|보완|회고)/], followup: "협업 과정에서 의견 차이를 어떻게 조율했고, 그 결정이 결과에 어떤 영향을 줬나요?" }
    ],
    keywords: ["사용자", "문제", "우선순위", "요구사항", "협업", "결과"]
  },
  marketing: {
    signal: "목표 고객 · 실험 설계 · 성과 지표",
    questions: [
      "고객 반응을 바탕으로 캠페인을 개선했던 경험을 설명해 주세요.",
      "성과가 낮았던 캠페인의 원인을 어떻게 찾아냈나요?",
      "브랜드 목표와 단기 성과가 충돌할 때 무엇을 우선하겠습니까?"
    ],
    rubric: [
      { label: "고객·과제 정의", checks: [/(고객|타깃|타겟|잠재고객|세그먼트)/, /(문제|과제|목표|인지|전환)/, /(상황|당시|시장|캠페인)/], followup: "누구를 대상으로 한 과제였고, 그 고객에게 어떤 변화를 만들고자 했는지 설명해 주세요." },
      { label: "실험·실행 판단", checks: [/(제가|저는|직접|담당)/, /(실험|가설|캠페인|소재|채널|분석)/, /(선택|판단|결정|기준|비교)/], followup: "실험한 변수와 성공 기준은 무엇이었으며, 그 기준을 선택한 이유는 무엇인가요?" },
      { label: "성과·회고", checks: [/(결과|성과|개선|증가|감소|전환)/, /\d|퍼센트|배|명|건/, /(배웠|한계|다음|보완|회고)/], followup: "성과 수치가 단순 노출이 아니라 실제 목표 달성으로 이어졌는지 어떻게 해석했나요?" }
    ],
    keywords: ["고객", "캠페인", "실험", "전환", "성과", "지표"]
  }
};

const $ = (id) => document.getElementById(id);
const state = {
  stream: null, recorder: null, chunks: [], recording: false, startedAt: 0, timerId: null,
  transcript: "", audioContext: null, analyser: null, recordedBlob: null, recordingUrl: null, whisperWorker: null, transcribing: false,
  audioSamples: [], silenceRuns: [], silenceStartedAt: null, sampleId: null, question: 0, duration: 1, followupText: "", jobContext: null
};

async function loadJobContext() {
  const postingId = new URLSearchParams(window.location.search).get("postingId");
  if (!postingId || !window.JobContextAPI) return;

  $("job-context-status").textContent = "선택한 채용공고 정보를 불러오는 중";
  try {
    state.jobContext = await window.JobContextAPI.get(postingId);
    const { companyName, positionTitle, deadline } = state.jobContext;
    $("job-context-status").textContent = `${companyName} · ${positionTitle}${deadline ? ` · 마감 ${deadline}` : ""}`;
  } catch (error) {
    $("job-context-status").textContent = "채용공고 정보를 불러오지 못해 데모 직무 루브릭을 사용합니다.";
    console.error(error);
  }
}

function updateRole() {
  const data = roleData[$("role-select").value];
  $("signal-title").textContent = data.signal;
  $("question-text").textContent = data.questions[state.question];
  $("question-number").textContent = state.question + 1;
  $("rubric-list").innerHTML = data.rubric.map((item, i) => `<li><span>0${i + 1}</span>${item.label}</li>`).join("");
}

async function enableCamera() {
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: { echoCancellation: true, noiseSuppression: true }
    });
    $("camera").srcObject = state.stream;
    $("camera-placeholder").hidden = true;
    $("record-button").disabled = false;
    $("device-label").textContent = "카메라 · 마이크 연결됨";
    $("device-label").parentElement.classList.add("connected");
    setupAudioMeter();
    setupWhisper();
  } catch (error) {
    $("camera-placeholder").querySelector("p").textContent = "권한을 확인할 수 없습니다. 브라우저 주소창에서 카메라와 마이크를 허용해 주세요.";
  }
}

function setupAudioMeter() {
  state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const source = state.audioContext.createMediaStreamSource(state.stream);
  state.analyser = state.audioContext.createAnalyser();
  state.analyser.fftSize = 512;
  source.connect(state.analyser);
}

function setupWhisper() {
  if (state.whisperWorker) return;
  state.whisperWorker = new Worker("./whisper-worker.js", { type: "module" });
  state.whisperWorker.onmessage = (event) => {
    const { type, progress, text, message } = event.data;
    if (type === "progress" && typeof progress?.progress === "number") {
      $("live-caption").textContent = `Whisper 모델 준비 중 ${Math.round(progress.progress)}%`;
    }
    if (type === "ready") {
      $("live-caption").textContent = "Whisper 준비 완료. 답변을 시작해 보세요.";
    }
    if (type === "transcribing") {
      $("live-caption").textContent = "Whisper가 답변을 전사하고 있습니다.";
    }
    if (type === "complete") {
      state.transcribing = false;
      state.transcript = text.trim();
      $("record-label").textContent = "한 번 더 녹화";
      $("record-button").disabled = false;
      $("finish-button").disabled = false;
      $("live-caption").textContent = state.transcript
        ? "Whisper 전사가 완료됐습니다. 분석 결과를 확인해 보세요."
        : "전사된 텍스트가 없습니다. 분석 화면에서 직접 입력할 수 있어요.";
    }
    if (type === "error") {
      state.transcribing = false;
      $("record-label").textContent = "한 번 더 녹화";
      $("record-button").disabled = false;
      $("finish-button").disabled = false;
      $("live-caption").textContent = `Whisper 전사에 실패했습니다. 분석 화면에서 직접 입력할 수 있어요.`;
      console.error(message);
    }
  };
  state.whisperWorker.postMessage({ type: "load" });
}

async function transcribeWithWhisper(blob) {
  try {
    if (!state.whisperWorker) setupWhisper();
    const audio = await blobToMono16k(blob);
    state.whisperWorker.postMessage({ type: "transcribe", audio: audio.buffer }, [audio.buffer]);
  } catch (error) {
    state.transcribing = false;
    $("record-label").textContent = "한 번 더 녹화";
    $("record-button").disabled = false;
    $("finish-button").disabled = false;
    $("live-caption").textContent = "오디오를 Whisper 전사용으로 준비하지 못했습니다. 분석 화면에서 직접 입력할 수 있어요.";
    console.error(error);
  }
}

async function blobToMono16k(blob) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const OfflineContextClass = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const decoder = new AudioContextClass();
  const decoded = await decoder.decodeAudioData(await blob.arrayBuffer());
  const offline = new OfflineContextClass(1, Math.ceil(decoded.duration * 16000), 16000);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  await decoder.close();
  return rendered.getChannelData(0);
}

function startSampling() {
  const buffer = new Uint8Array(state.analyser.fftSize);
  state.audioSamples = [];
  state.silenceRuns = [];
  state.silenceStartedAt = null;
  state.sampleId = setInterval(() => {
    state.analyser.getByteTimeDomainData(buffer);
    const rms = Math.sqrt(buffer.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / buffer.length);
    state.audioSamples.push(rms);
    const now = performance.now();
    if (rms < 0.018 && state.silenceStartedAt === null) state.silenceStartedAt = now;
    if (rms >= 0.018 && state.silenceStartedAt !== null) {
      const duration = now - state.silenceStartedAt;
      if (duration >= 1500) state.silenceRuns.push(duration);
      state.silenceStartedAt = null;
    }
  }, 120);
}

function startRecording() {
  if (state.recordingUrl) {
    URL.revokeObjectURL(state.recordingUrl);
    state.recordingUrl = null;
  }
  state.chunks = [];
  state.transcript = "";
  state.followupText = "";
  state.recordedBlob = null;
  state.recorder = new MediaRecorder(state.stream);
  state.recorder.ondataavailable = (event) => { if (event.data.size) state.chunks.push(event.data); };
  state.recorder.onstop = () => {
    state.recordedBlob = new Blob(state.chunks, { type: state.recorder.mimeType || "video/webm" });
    state.recordingUrl = URL.createObjectURL(state.recordedBlob);
    transcribeWithWhisper(state.recordedBlob);
  };
  state.recorder.start();
  state.recording = true;
  state.startedAt = Date.now();
  $("record-button").classList.add("recording");
  $("record-label").textContent = "답변 녹화 종료";
  $("recording-badge").style.display = "block";
  $("finish-button").disabled = true;
  state.timerId = setInterval(updateTimer, 250);
  startSampling();
}

function stopRecording() {
  if (state.recorder?.state !== "inactive") state.recorder.stop();
  state.recording = false;
  clearInterval(state.timerId);
  clearInterval(state.sampleId);
  state.duration = Math.max(1, Math.floor((Date.now() - state.startedAt) / 1000));
  if (state.silenceStartedAt !== null) {
    const finalSilence = performance.now() - state.silenceStartedAt;
    if (finalSilence >= 1500) state.silenceRuns.push(finalSilence);
    state.silenceStartedAt = null;
  }
  $("record-button").classList.remove("recording");
  $("record-label").textContent = "Whisper 전사 중";
  $("record-button").disabled = true;
  $("recording-badge").style.display = "none";
  $("finish-button").disabled = true;
  state.transcribing = true;
  $("live-caption").textContent = "녹화가 끝났습니다. Whisper 전사를 시작합니다.";
}

function updateTimer() {
  const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
  $("timer").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function analyze() {
  const baseText = $("transcript-input").value.trim() || state.transcript.trim();
  if (!$("transcript-input").value) $("transcript-input").value = baseText;
  const text = [baseText, state.followupText].filter(Boolean).join("\n");
  const duration = state.duration;
  const compact = text.replace(/\s/g, "");
  const pace = Math.round((compact.length / duration) * 60);
  const fillerPattern = /(음|어|그니까|그러니까|약간|뭔가|사실은|아무튼)/g;
  const fillers = text.match(fillerPattern) || [];
  const data = roleData[$("role-select").value];
  const keywordHits = data.keywords.filter((word) => text.includes(word));
  const rubricResults = data.rubric.map((item) => evaluateRubric(item, text));
  const rubricTotal = rubricResults.reduce((total, item) => total + item.score, 0);
  const hasNumber = /\d|퍼센트|배|명|건/.test(text);
  const volumeValues = state.audioSamples.filter((v) => v >= 0.018);
  const volumeMean = volumeValues.reduce((a, b) => a + b, 0) / Math.max(1, volumeValues.length);
  const volumeVariance = volumeValues.reduce((sum, value) => sum + (value - volumeMean) ** 2, 0) / Math.max(1, volumeValues.length);
  const voiceVariation = Math.sqrt(volumeVariance);
  const textAvailable = compact.length > 0;
  const paceHealthy = pace >= 250 && pace <= 420;
  const score = textAvailable ? Math.min(95, Math.max(15, Math.round(18 + (rubricTotal / 9) * 70 + (paceHealthy ? 5 : 0) - Math.min(8, fillers.length * 2)))) : 0;

  $("total-score").textContent = `${score}`;
  $("score-fill").style.width = `${score}%`;
  $("pace-value").textContent = textAvailable ? `${pace}자` : "—";
  $("pace-note").textContent = textAvailable ? (paceHealthy ? "안정 범위 / 분" : pace < 250 ? "조금 느림 / 분" : "조금 빠름 / 분") : "전사 입력 필요";
  $("pause-value").textContent = `${state.silenceRuns.length}회`;
  $("filler-value").textContent = `${fillers.length}회`;
  $("voice-value").textContent = volumeValues.length ? (voiceVariation > .025 ? "충분" : "낮음") : "—";
  $("voice-note").textContent = volumeValues.length ? "음량 변화 기준" : "음성 데이터 없음";
  $("transcript-source").textContent = state.transcript ? "로컬 Whisper 전사" : "직접 입력";
  renderRubricMap(rubricResults);

  const strengths = [];
  rubricResults.filter((item) => item.score >= 2).forEach((item) => {
    strengths.push([item.label, `${item.evidence[0] || "답변 근거"}가 확인됩니다.`]);
  });
  if (keywordHits.length) strengths.push(["직무 연결", `‘${keywordHits.slice(0, 3).join(" · ")}’ 근거가 직무 평가 기준과 연결됩니다.`]);
  if (hasNumber && !strengths.some(([title]) => title === "결과·회고")) strengths.push(["결과 근거", "수치나 규모가 포함되어 결과를 구체적으로 전달했습니다."]);
  if (!strengths.length) strengths.push(["시작점", "답변 내용이 아직 짧습니다. 경험의 상황과 본인의 행동부터 한 문장씩 추가해 보세요."]);

  const improvements = [];
  rubricResults.filter((item) => item.score < 2).forEach((item) => {
    improvements.push([item.label, item.missing]);
  });
  if (!hasNumber && !improvements.some(([title]) => title === "결과·회고")) improvements.push(["근거", "결과에 기간, 규모, 전후 변화 중 하나를 덧붙이면 판단 근거가 선명해집니다."]);
  if (!keywordHits.length) improvements.push(["직무 연결", `이번 질문의 핵심인 ${data.signal} 중 하나를 실제 행동과 연결해 보세요.`]);
  if (fillers.length >= 3) improvements.push(["전달 습관", `습관어가 ${fillers.length}회 감지됐습니다. 문장 사이에 짧게 멈추는 편이 더 또렷합니다.`]);
  if (state.silenceRuns.length >= 2) improvements.push(["침묵", `1.5초 이상의 침묵이 ${state.silenceRuns.length}회 있었습니다. 첫 문장을 미리 정해 두면 시작이 안정됩니다.`]);
  if (!improvements.length) improvements.push(["다음 단계", "현재 구조는 안정적입니다. 본인의 판단 기준과 대안 비교를 한 문장 추가해 깊이를 높여 보세요."]);

  $("feedback-list").innerHTML = [
    ...strengths.slice(0, 2).map(([title, body]) => feedbackItem("잘 드러난 점", title, body, "good")),
    ...improvements.slice(0, 3).map(([title, body]) => feedbackItem("보완할 점", title, body, "improve"))
  ].join("");

  const followupTarget = [...rubricResults].sort((a, b) => a.score - b.score)[0];
  renderFollowup(followupTarget, Boolean(state.followupText));
}

function evaluateRubric(item, text) {
  const evidence = item.checks.map((pattern) => findEvidence(text, pattern)).filter(Boolean);
  const score = evidence.length;
  const missing = score === 0
    ? `현재 답변에서 ${item.label}의 근거를 찾지 못했습니다. ${item.followup}`
    : score === 1
      ? `${item.label}에 대한 단서가 하나 있습니다. 행동 또는 결과를 더해 근거를 완성해 보세요.`
      : `${item.label}의 근거가 더 선명해지도록 판단 이유나 회고를 한 문장 덧붙여 보세요.`;
  return { ...item, score, evidence, missing };
}

function findEvidence(text, pattern) {
  const sentences = text.split(/(?:[.!?]|다\.|요\.)\s*|\n+/).map((sentence) => sentence.trim()).filter(Boolean);
  return sentences.find((sentence) => pattern.test(sentence)) || "";
}

function renderRubricMap(items) {
  $("rubric-map").innerHTML = items.map((item) => {
    const evidence = item.evidence.length ? item.evidence.slice(0, 2).map((line) => `“${escapeHtml(line)}”`).join(" · ") : "아직 확인된 근거 없음";
    return `<article class="rubric-item"><div class="rubric-item-head"><h3>${escapeHtml(item.label)}</h3><b class="rubric-score">${item.score}/3</b></div><div class="rubric-scale"><i style="width:${item.score * 33.333}%"></i></div><p class="rubric-evidence"><b>답변 근거</b><br>${evidence}</p></article>`;
  }).join("");
}

function renderFollowup(item, answered) {
  const input = $("followup-input");
  const button = $("submit-followup");
  $("followup-context").textContent = item
    ? `${item.label} 항목을 더 확인하고 싶어요. ${item.followup}`
    : "답변에서 더 확인할 근거를 고르고 있어요.";
  $("followup-status").textContent = answered ? "후속 답변 반영됨" : "답변 대기";
  input.value = state.followupText;
  input.disabled = answered;
  button.disabled = answered;
  button.textContent = answered ? "후속 답변이 평가에 반영되었습니다" : "후속 답변 반영하기 →";
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function feedbackItem(label, title, body, type) {
  return `<article class="feedback-item ${type}"><span>${escapeHtml(label)}</span><div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(body)}</p></div></article>`;
}

async function requestAgentFeedback() {
  const transcript = $("transcript-input").value.trim() || state.transcript.trim();
  if (!transcript) return;
  const button = $("agent-feedback-button");
  button.disabled = true;
  $("agent-feedback-status").textContent = "직무 AI 코치가 선택 공고와 답변 근거를 확인하고 있습니다.";
  try {
    const data = roleData[$("role-select").value];
    const result = await window.CareerCoachAPI.evaluateInterview({
      postingId: state.jobContext?.postingId || null,
      jobFamily: $("role-select").value,
      question: $("question-text").textContent,
      transcript,
      rubric: data.rubric.map(({ label, followup }) => ({ label, followup })),
      deliveryMetrics: { durationSeconds: state.duration, longPauses: state.silenceRuns.length }
    });
    $("feedback-list").innerHTML = result.feedback.map((item) => feedbackItem(item.label, item.title, item.body, item.type)).join("");
    if (result.followupQuestion) $("followup-context").textContent = result.followupQuestion;
    $("agent-feedback-status").textContent = "직무 AI 코치 피드백이 반영됐습니다.";
  } catch (error) {
    $("agent-feedback-status").textContent = "AI 코치 서버가 아직 연결되지 않아 MVP 규칙 기반 피드백을 유지합니다.";
    console.error(error);
  } finally {
    button.disabled = false;
  }
}

function showResults() {
  $("practice-view").hidden = true;
  $("result-view").hidden = false;
  const playback = $("recording-playback");
  const recordingCard = $("recording-card");
  if (state.recordingUrl) {
    playback.src = state.recordingUrl;
    recordingCard.hidden = false;
  } else {
    playback.removeAttribute("src");
    recordingCard.hidden = true;
  }
  if (!state.transcript) $("transcript-input").value = "";
  analyze();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetPractice() {
  $("result-view").hidden = true;
  $("practice-view").hidden = false;
  $("timer").textContent = "00:00";
  $("live-caption").textContent = "";
  $("finish-button").disabled = true;
  $("transcript-input").value = "";
  $("followup-input").value = "";
  $("recording-playback").pause();
  $("recording-playback").removeAttribute("src");
  $("recording-playback").load();
  $("recording-card").hidden = true;
  if (state.recordingUrl) URL.revokeObjectURL(state.recordingUrl);
  state.recordingUrl = null;
  state.recordedBlob = null;
  state.followupText = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("role-select").addEventListener("change", () => { state.question = 0; state.followupText = ""; updateRole(); });
$("next-question").addEventListener("click", () => { state.question = (state.question + 1) % 3; updateRole(); });
$("enable-camera").addEventListener("click", enableCamera);
$("record-button").addEventListener("click", () => state.recording ? stopRecording() : startRecording());
$("finish-button").addEventListener("click", showResults);
$("retry-button").addEventListener("click", resetPractice);
$("reanalyze-button").addEventListener("click", analyze);
$("agent-feedback-button").addEventListener("click", requestAgentFeedback);
$("submit-followup").addEventListener("click", () => {
  const answer = $("followup-input").value.trim();
  if (!answer) {
    $("followup-input").focus();
    return;
  }
  state.followupText = answer;
  analyze();
});
updateRole();
loadJobContext();

function registerWebMcp() {
  const context = document.modelContext;
  if (!context?.registerTool) return;
  try {
    context.registerTool({
      name: "configure_interview_practice",
      title: "면접 연습 설정",
      description: "지원 직무와 질문 번호를 선택하고 화면의 면접 연습 기준을 갱신합니다.",
      inputSchema: {
        type: "object",
        properties: {
          role: { type: "string", enum: Object.keys(roleData) },
          questionNumber: { type: "integer", minimum: 1, maximum: 3 }
        },
        required: ["role", "questionNumber"],
        additionalProperties: false
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute(input) {
        if (!input || !roleData[input.role] || !Number.isInteger(input.questionNumber) || input.questionNumber < 1 || input.questionNumber > 3) {
          throw new Error("role과 1~3 사이의 questionNumber가 필요합니다.");
        }
        $("role-select").value = input.role;
        state.question = input.questionNumber - 1;
        updateRole();
        return {
          role: input.role,
          questionNumber: input.questionNumber,
          question: roleData[input.role].questions[state.question]
        };
      }
    });
  } catch (_) {
    // WebMCP is optional; the visible interview flow remains fully usable.
  }
}

registerWebMcp();
