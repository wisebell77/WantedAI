const roleData = {
  data: {
    signal: "문제 정의 · 분석 과정 · 사업적 영향",
    questions: [
      "데이터로 문제를 정의하고 해결했던 경험을 설명해 주세요.",
      "분석 결과가 예상과 달랐을 때 어떻게 검증했나요?",
      "이해관계자에게 복잡한 분석을 설득력 있게 전달한 경험이 있나요?"
    ],
    rubric: ["문제와 목표를 구분해 설명했는가", "본인의 분석 판단과 행동이 드러나는가", "결과를 수치나 변화로 입증했는가"],
    keywords: ["데이터", "분석", "가설", "검증", "지표", "결과"]
  },
  pm: {
    signal: "사용자 문제 · 우선순위 · 협업 결과",
    questions: [
      "사용자 문제를 발견하고 해결 방향을 결정했던 경험을 설명해 주세요.",
      "제한된 자원 안에서 우선순위를 정했던 기준은 무엇인가요?",
      "개발자·디자이너와 의견이 달랐을 때 어떻게 합의했나요?"
    ],
    rubric: ["사용자 문제와 맥락이 구체적인가", "우선순위 기준과 본인의 판단이 드러나는가", "협업 결과나 학습을 근거로 제시했는가"],
    keywords: ["사용자", "문제", "우선순위", "요구사항", "협업", "결과"]
  },
  marketing: {
    signal: "목표 고객 · 실험 설계 · 성과 지표",
    questions: [
      "고객 반응을 바탕으로 캠페인을 개선했던 경험을 설명해 주세요.",
      "성과가 낮았던 캠페인의 원인을 어떻게 찾아냈나요?",
      "브랜드 목표와 단기 성과가 충돌할 때 무엇을 우선하겠습니까?"
    ],
    rubric: ["목표 고객과 과제가 명확한가", "실험 또는 실행 과정에서 본인의 역할이 드러나는가", "전환율 등 성과 지표로 결과를 설명했는가"],
    keywords: ["고객", "캠페인", "실험", "전환", "성과", "지표"]
  }
};

const $ = (id) => document.getElementById(id);
const state = {
  stream: null, recorder: null, chunks: [], recording: false, startedAt: 0, timerId: null,
  recognition: null, transcript: "", finalTranscript: "", audioContext: null, analyser: null,
  audioSamples: [], silenceRuns: [], silenceStartedAt: null, sampleId: null, question: 0, duration: 1
};

function updateRole() {
  const data = roleData[$("role-select").value];
  $("signal-title").textContent = data.signal;
  $("question-text").textContent = data.questions[state.question];
  $("question-number").textContent = state.question + 1;
  $("rubric-list").innerHTML = data.rubric.map((item, i) => `<li><span>0${i + 1}</span>${item}</li>`).join("");
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

function setupRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return;
  state.recognition = new Recognition();
  state.recognition.lang = "ko-KR";
  state.recognition.continuous = true;
  state.recognition.interimResults = true;
  state.recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) state.finalTranscript += `${text} `;
      else interim += text;
    }
    state.transcript = `${state.finalTranscript}${interim}`.trim();
    $("live-caption").textContent = interim;
  };
  state.recognition.onerror = () => { $("live-caption").textContent = "자동 전사를 사용할 수 없어 녹화 후 직접 입력할 수 있어요."; };
  try { state.recognition.start(); } catch (_) {}
}

function startRecording() {
  state.chunks = [];
  state.transcript = "";
  state.finalTranscript = "";
  state.recorder = new MediaRecorder(state.stream);
  state.recorder.ondataavailable = (event) => { if (event.data.size) state.chunks.push(event.data); };
  state.recorder.start();
  state.recording = true;
  state.startedAt = Date.now();
  $("record-button").classList.add("recording");
  $("record-label").textContent = "답변 녹화 종료";
  $("recording-badge").style.display = "block";
  $("finish-button").disabled = true;
  state.timerId = setInterval(updateTimer, 250);
  startSampling();
  setupRecognition();
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
  try { state.recognition?.stop(); } catch (_) {}
  $("record-button").classList.remove("recording");
  $("record-label").textContent = "한 번 더 녹화";
  $("recording-badge").style.display = "none";
  $("finish-button").disabled = false;
  $("live-caption").textContent = "녹화가 끝났습니다. 분석 결과를 확인해 보세요.";
}

function updateTimer() {
  const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
  $("timer").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function analyze() {
  const text = $("transcript-input").value.trim() || state.transcript.trim();
  if (!$("transcript-input").value) $("transcript-input").value = text;
  const duration = state.duration;
  const compact = text.replace(/\s/g, "");
  const pace = Math.round((compact.length / duration) * 60);
  const fillerPattern = /(음|어|그니까|그러니까|약간|뭔가|사실은|아무튼)/g;
  const fillers = text.match(fillerPattern) || [];
  const data = roleData[$("role-select").value];
  const keywordHits = data.keywords.filter((word) => text.includes(word));
  const structureSignals = [/(상황|당시|문제)/.test(text), /(목표|과제)/.test(text), /(제가|저는|진행|분석|실행|결정)/.test(text), /(결과|성과|개선|증가|감소|배웠)/.test(text)];
  const structureScore = structureSignals.filter(Boolean).length;
  const hasNumber = /\d|퍼센트|배|명|건/.test(text);
  const volumeValues = state.audioSamples.filter((v) => v >= 0.018);
  const volumeMean = volumeValues.reduce((a, b) => a + b, 0) / Math.max(1, volumeValues.length);
  const volumeVariance = volumeValues.reduce((sum, value) => sum + (value - volumeMean) ** 2, 0) / Math.max(1, volumeValues.length);
  const voiceVariation = Math.sqrt(volumeVariance);
  const textAvailable = compact.length > 0;
  const paceHealthy = pace >= 250 && pace <= 420;
  const score = textAvailable ? Math.min(92, 38 + structureScore * 9 + keywordHits.length * 3 + (hasNumber ? 8 : 0) + (paceHealthy ? 5 : 0) - Math.min(8, fillers.length * 2)) : 24;

  $("total-score").textContent = `${score}`;
  $("score-fill").style.width = `${score}%`;
  $("pace-value").textContent = textAvailable ? `${pace}자` : "—";
  $("pace-note").textContent = textAvailable ? (paceHealthy ? "안정 범위 / 분" : pace < 250 ? "조금 느림 / 분" : "조금 빠름 / 분") : "전사 입력 필요";
  $("pause-value").textContent = `${state.silenceRuns.length}회`;
  $("filler-value").textContent = `${fillers.length}회`;
  $("voice-value").textContent = volumeValues.length ? (voiceVariation > .025 ? "충분" : "낮음") : "—";
  $("voice-note").textContent = volumeValues.length ? "음량 변화 기준" : "음성 데이터 없음";
  $("transcript-source").textContent = state.transcript ? "브라우저 자동 전사" : "직접 입력";

  const strengths = [];
  if (structureScore >= 3) strengths.push(["구조", "답변의 상황·행동·결과 흐름이 확인됩니다."]);
  if (keywordHits.length) strengths.push(["직무 연결", `‘${keywordHits.slice(0, 3).join(" · ")}’ 근거가 직무 평가 기준과 연결됩니다.`]);
  if (hasNumber) strengths.push(["결과 근거", "수치나 규모가 포함되어 결과를 구체적으로 전달했습니다."]);
  if (!strengths.length) strengths.push(["시작점", "답변 내용이 아직 짧습니다. 경험의 상황과 본인의 행동부터 한 문장씩 추가해 보세요."]);

  const improvements = [];
  if (structureScore < 3) improvements.push(["답변 구조", "상황 → 내가 맡은 목표 → 구체적 행동 → 결과 순서로 다시 말해 보세요."]);
  if (!hasNumber) improvements.push(["근거", "결과에 기간, 규모, 전후 변화 중 하나를 덧붙이면 판단 근거가 선명해집니다."]);
  if (!keywordHits.length) improvements.push(["직무 연결", `이번 질문의 핵심인 ${data.signal} 중 하나를 실제 행동과 연결해 보세요.`]);
  if (fillers.length >= 3) improvements.push(["전달 습관", `습관어가 ${fillers.length}회 감지됐습니다. 문장 사이에 짧게 멈추는 편이 더 또렷합니다.`]);
  if (state.silenceRuns.length >= 2) improvements.push(["침묵", `1.5초 이상의 침묵이 ${state.silenceRuns.length}회 있었습니다. 첫 문장을 미리 정해 두면 시작이 안정됩니다.`]);
  if (!improvements.length) improvements.push(["다음 단계", "현재 구조는 안정적입니다. 본인의 판단 기준과 대안 비교를 한 문장 추가해 깊이를 높여 보세요."]);

  $("feedback-list").innerHTML = [
    ...strengths.slice(0, 2).map(([title, body]) => feedbackItem("잘 드러난 점", title, body, "good")),
    ...improvements.slice(0, 3).map(([title, body]) => feedbackItem("보완할 점", title, body, "improve"))
  ].join("");
}

function feedbackItem(label, title, body, type) {
  return `<article class="feedback-item ${type}"><span>${label}</span><div><strong>${title}</strong><p>${body}</p></div></article>`;
}

function showResults() {
  $("practice-view").hidden = true;
  $("result-view").hidden = false;
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
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("role-select").addEventListener("change", () => { state.question = 0; updateRole(); });
$("next-question").addEventListener("click", () => { state.question = (state.question + 1) % 3; updateRole(); });
$("enable-camera").addEventListener("click", enableCamera);
$("record-button").addEventListener("click", () => state.recording ? stopRecording() : startRecording());
$("finish-button").addEventListener("click", showResults);
$("retry-button").addEventListener("click", resetPractice);
$("reanalyze-button").addEventListener("click", analyze);
updateRole();

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
