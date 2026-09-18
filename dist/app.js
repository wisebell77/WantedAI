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
  transcript: "", audioContext: null, analyser: null, recordedBlob: null, recordingUrl: null, transcribing: false,
  audioSamples: [], silenceRuns: [], silenceStartedAt: null, sampleId: null, question: 0, duration: 1, followupText: "", jobContext: null, interviewPersona: null,
  preparing: false, preparationTimer: null, preparationEndsAt: 0, questionRevealed: false,
  vision: null, visionStatus: "대기", visionSampleId: null, visionLastAt: 0, visual: null, overlayVisible: false, overlayFrame: null, overlayLastTime: -1
};

// postingId comes from the query string when the real project serves
// /index.html?postingId=…, and from the standalone embed when the entry runs
// inside a srcdoc iframe that has no query string of its own.
function currentPostingId() {
  return new URLSearchParams(window.location.search).get("postingId") || window.NEXT_STEP_POSTING_ID || "";
}

async function loadJobContext() {
  const postingId = currentPostingId();
  if (!postingId || !window.JobContextAPI) {
    $("practice-job").textContent = "AI 코치에서 공고를 선택하면 그 공고 기준으로 연습할 수 있어요.";
    return;
  }

  $("job-context-status").textContent = "선택한 채용공고 정보를 불러오는 중";
  try {
    state.jobContext = await window.JobContextAPI.get(postingId);
    const { companyName, positionTitle, deadline } = state.jobContext;
    const summary = `${companyName} · ${positionTitle}${deadline ? ` · 마감 ${deadline}` : ""}`;
    $("job-context-status").textContent = summary;
    $("practice-job").textContent = summary;
  } catch (error) {
    $("job-context-status").textContent = "채용공고 정보를 불러오지 못해 데모 직무 루브릭을 사용합니다.";
    $("practice-job").textContent = "공고 정보를 불러오지 못해 기본 연습 기준을 사용해요.";
    console.error(error);
    return;
  }
  try {
    const persona = await window.CareerCoachAPI.getInterviewPersona(postingId);
    if (persona.items.length && persona.questions.length) state.interviewPersona = persona;
    else $("job-context-status").textContent += " · 공고 루브릭이 부족해 기본 연습 기준을 사용합니다.";
    updateRole();
  } catch (error) {
    $("job-context-status").textContent += " · 직무 루브릭을 불러오지 못해 기본 연습 기준을 사용합니다.";
    console.error(error);
  }
}

function updateRole() {
  const data = roleData[$("role-select").value];
  const items = state.interviewPersona?.items || data.rubric;
  const questions = state.interviewPersona?.questions.length ? state.interviewPersona.questions : data.questions.map((question) => ({ question, item_id: null }));
  const currentQuestion = questions[state.question % questions.length];
  $("signal-title").textContent = state.interviewPersona?.persona?.name || data.signal;
  $("question-text").textContent = state.questionRevealed ? currentQuestion.question : "면접 시작을 누르면 질문이 공개됩니다.";
  $("question-number").textContent = state.question + 1;
  $("rubric-list").innerHTML = items.map((item, i) => `<li><span>0${i + 1}</span>${item.label}</li>`).join("");
}

async function enableCamera() {
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: { echoCancellation: true, noiseSuppression: true }
    });
    $("camera").srcObject = state.stream;
    $("camera-placeholder").hidden = true;
    $("start-interview-button").disabled = false;
    $("device-label").textContent = "카메라 · 마이크 연결됨";
    $("device-label").parentElement.classList.add("connected");
    setupAudioMeter();
    setupVision();
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

async function transcribeWithFasterWhisper(blob) {
  try {
    const postingId = state.jobContext?.postingId || currentPostingId();
    const response = await fetch(`/api/v1/interview/transcribe?postingId=${encodeURIComponent(postingId)}`, { method: "POST", headers: { "Content-Type": blob.type || "video/webm" }, body: blob });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "TRANSCRIPTION_FAILED");
    state.transcript = result.text.trim();
    state.transcribing = false;
    $("record-label").textContent = "한 번 더 녹화";
    $("record-button").disabled = false;
    $("finish-button").disabled = false;
    $("live-caption").textContent = state.transcript ? "faster-whisper medium 전사가 완료됐습니다." : "전사된 텍스트가 없습니다. 직접 입력할 수 있어요.";
  } catch (error) {
    state.transcribing = false;
    $("record-label").textContent = "한 번 더 녹화";
    $("record-button").disabled = false;
    $("finish-button").disabled = false;
    $("live-caption").textContent = "faster-whisper 전사에 실패했습니다. 직접 입력할 수 있어요.";
    console.error(error);
  }
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

async function setupVision() {
  if (state.vision) return;
  state.visionStatus = "모델 불러오는 중";
  try {
    const { FilesetResolver, FaceLandmarker, HandLandmarker, GestureRecognizer, PoseLandmarker } = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/+esm");
    const files = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm");
    const baseOptions = (modelAssetPath) => ({ modelAssetPath });
    state.vision = {
      face: await FaceLandmarker.createFromOptions(files, { baseOptions: baseOptions("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"), runningMode: "VIDEO", outputFaceBlendshapes: true }),
      hand: await HandLandmarker.createFromOptions(files, { baseOptions: baseOptions("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"), runningMode: "VIDEO", numHands: 2 }),
      gesture: await GestureRecognizer.createFromOptions(files, { baseOptions: baseOptions("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task"), runningMode: "VIDEO", numHands: 2 }),
      pose: await PoseLandmarker.createFromOptions(files, { baseOptions: baseOptions("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"), runningMode: "VIDEO", numPoses: 1 }),
      faceConnections: FaceLandmarker.FACE_LANDMARKS_TESSELATION,
      poseConnections: PoseLandmarker.POSE_CONNECTIONS
    };
    state.visionStatus = "분석 완료 · 최대 10fps";
    if (state.recording) startVisionSampling();
  } catch (error) {
    state.visionStatus = "모델 로딩 실패";
    console.warn("MediaPipe를 불러오지 못했습니다.", error);
  }
}

function emptyVisual() {
  return { frames: 0, faceMissing: 0, offCenter: 0, handsVisible: 0, gestures: {}, poseMissing: 0, shouldersOffCenter: 0, shoulderTiltFrames: 0, armMoves: 0, lastWristCenter: null, lastArmMoveAt: 0, samples: [], blinks: 0, eyeFrames: 0, eyesClosed: false, mouthFrames: 0, mouthFrownFrames: 0, upperBodyMoves: 0, lastShoulderCenter: null, lastUpperBodyMoveAt: 0 };
}

function startVisionSampling() {
  state.visual ||= emptyVisual();
  if (!state.vision || state.visionSampleId) return;
  state.visionLastAt = 0;
  const sample = (now) => {
    if (!state.recording) { state.visionSampleId = null; return; }
    if (now - state.visionLastAt >= 100 && state.stream && $("camera").readyState >= 2) {
      state.visionLastAt = now;
      collectVisionFrame(now);
    }
    state.visionSampleId = requestAnimationFrame(sample);
  };
  state.visionSampleId = requestAnimationFrame(sample);
}

function collectVisionFrame(now) {
  const visual = state.visual;
  visual.frames += 1;
  const face = state.vision.face.detectForVideo($("camera"), now);
  const hand = state.vision.hand.detectForVideo($("camera"), now);
  const gesture = state.vision.gesture.recognizeForVideo($("camera"), now);
  const pose = state.vision.pose.detectForVideo($("camera"), now);
  const landmarks = face.faceLandmarks?.[0];
  if (!landmarks) visual.faceMissing += 1;
  else {
    if (Math.abs((landmarks[1]?.x ?? .5) - .5) > .22) visual.offCenter += 1;
    const eyeRatio = (eye) => (Math.hypot(landmarks[eye[1]].x - landmarks[eye[5]].x, landmarks[eye[1]].y - landmarks[eye[5]].y) + Math.hypot(landmarks[eye[2]].x - landmarks[eye[4]].x, landmarks[eye[2]].y - landmarks[eye[4]].y)) / (2 * Math.hypot(landmarks[eye[0]].x - landmarks[eye[3]].x, landmarks[eye[0]].y - landmarks[eye[3]].y));
    const openness = (eyeRatio([33, 160, 158, 133, 153, 144]) + eyeRatio([362, 385, 387, 263, 373, 380])) / 2;
    visual.eyeFrames += 1;
    if (openness < .19) visual.eyesClosed = true;
    if (openness > .22 && visual.eyesClosed) { visual.blinks += 1; visual.eyesClosed = false; }
    const frown = face.faceBlendshapes?.[0]?.categories?.filter((item) => item.categoryName.startsWith("mouthFrown")).reduce((highest, item) => Math.max(highest, item.score), 0) || 0;
    visual.mouthFrames += 1;
    if (frown > .2) visual.mouthFrownFrames += 1;
  }
  if (hand.handLandmarks?.length) visual.handsVisible += 1;
  const poseLandmarks = pose.landmarks?.[0];
  if (!poseLandmarks) visual.poseMissing += 1;
  else {
    const shoulderCenter = ((poseLandmarks[11]?.x ?? .5) + (poseLandmarks[12]?.x ?? .5)) / 2;
    if (Math.abs(shoulderCenter - .5) > .22) visual.shouldersOffCenter += 1;
    const shoulderPoint = [shoulderCenter, ((poseLandmarks[11]?.y ?? .5) + (poseLandmarks[12]?.y ?? .5)) / 2];
    const moved = visual.lastShoulderCenter && Math.hypot(shoulderPoint[0] - visual.lastShoulderCenter[0], shoulderPoint[1] - visual.lastShoulderCenter[1]) > .035;
    if (moved && now - visual.lastUpperBodyMoveAt > 700) { visual.upperBodyMoves += 1; visual.lastUpperBodyMoveAt = now; }
    visual.lastShoulderCenter = shoulderPoint;
    if (Math.abs((poseLandmarks[11]?.y ?? .5) - (poseLandmarks[12]?.y ?? .5)) > .055) visual.shoulderTiltFrames += 1;
    const wristCenter = [((poseLandmarks[15]?.x ?? .5) + (poseLandmarks[16]?.x ?? .5)) / 2, ((poseLandmarks[15]?.y ?? .5) + (poseLandmarks[16]?.y ?? .5)) / 2];
    const armsMoved = visual.lastWristCenter && Math.hypot(wristCenter[0] - visual.lastWristCenter[0], wristCenter[1] - visual.lastWristCenter[1]) > .05;
    if (armsMoved && now - visual.lastArmMoveAt > 500) { visual.armMoves += 1; visual.lastArmMoveAt = now; }
    visual.lastWristCenter = wristCenter;
  }
  gesture.gestures?.forEach((items) => {
    const name = items[0]?.categoryName;
    if (name && name !== "None") visual.gestures[name] = (visual.gestures[name] || 0) + 1;
  });
  visual.samples.push({
    time: (Date.now() - state.startedAt) / 1000,
    face: landmarks?.map(({ x, y, z }) => [x, y, z]),
    hands: hand.handLandmarks?.map((points) => points.map(({ x, y }) => [x, y])),
    pose: poseLandmarks?.map(({ x, y }) => [x, y]),
    faceCentered: Boolean(landmarks) && Math.abs((landmarks[1]?.x ?? .5) - .5) <= .22,
    handCount: hand.handLandmarks?.length || 0,
    shoulderTilt: Boolean(poseLandmarks) && Math.abs((poseLandmarks[11]?.y ?? .5) - (poseLandmarks[12]?.y ?? .5)) > .055,
    blinks: visual.blinks,
    blinkRate: Math.round((visual.blinks / Math.max(.1, (Date.now() - state.startedAt) / 1000)) * 60),
    upperBodyMoves: visual.upperBodyMoves,
    mouthFrownPercent: Math.round((visual.mouthFrownFrames / Math.max(1, visual.mouthFrames)) * 100)
  });
}

function videoFeedback() {
  const visual = state.visual;
  if (!visual?.frames) return [];
  const percent = (value) => Math.round((value / visual.frames) * 100);
  const result = [];
  if (visual.faceMissing) result.push(["화면 유지", `얼굴이 감지되지 않은 구간이 ${percent(visual.faceMissing)}%입니다. 해당 시점의 영상을 다시 확인해 보세요.`]);
  if (visual.offCenter) result.push(["프레임 위치", `얼굴이 화면 중심에서 벗어난 구간이 ${percent(visual.offCenter)}%입니다.`]);
  if (visual.poseMissing) result.push(["상체 감지", `상체가 감지되지 않은 구간이 ${percent(visual.poseMissing)}%입니다. 카메라 높이와 거리를 확인해 보세요.`]);
  else if (visual.shouldersOffCenter) result.push(["상체 위치", `어깨 중심이 화면 중앙에서 벗어난 구간이 ${percent(visual.shouldersOffCenter)}%입니다.`]);
  if (visual.eyeFrames) result.push(["눈 깜빡임", `랜드마크 기준으로 눈 깜빡임이 ${visual.blinks}회(${Math.round((visual.blinks / Math.max(1, state.duration)) * 60)}회/분) 감지됐습니다. 조명·안경·카메라 각도에 따라 달라질 수 있습니다.`]);
  if (visual.mouthFrames) result.push(["입꼬리 방향", `입꼬리 아래 방향 랜드마크 신호가 ${percent(visual.mouthFrownFrames)}% 구간에서 나타났습니다. 표정의 좋고 나쁨이 아닌 녹화 확인용 신호입니다.`]);
  if (visual.upperBodyMoves) result.push(["상체 움직임", `어깨 중심이 크게 이동한 구간이 ${visual.upperBodyMoves}회 감지됐습니다. 녹화본과 오버레이를 함께 확인해 보세요.`]);
  if (visual.shoulderTiltFrames) result.push(["어깨 기울기", `양쪽 어깨 높이 차이가 큰 구간이 ${percent(visual.shoulderTiltFrames)}%입니다.`]);
  if (visual.armMoves) result.push(["팔 움직임", `양쪽 손목 중심이 크게 이동한 구간이 ${visual.armMoves}회 감지됐습니다.`]);
  result.push(["손 노출", `손이 화면에 보인 구간은 ${percent(visual.handsVisible)}%입니다.`]);
  const gestures = Object.entries(visual.gestures).sort((a, b) => b[1] - a[1]).slice(0, 2);
  if (gestures.length) result.push(["손동작", `감지된 손동작: ${gestures.map(([name, count]) => `${name} ${count}회`).join(", ")}`]);
  return result;
}

function drawPoints(context, points, color, radius = 2) {
  context.fillStyle = color;
  points?.forEach(([x, y, z = 0]) => {
    context.globalAlpha = Math.max(.3, Math.min(1, 1 - z));
    context.beginPath();
    context.arc(x * context.canvas.width, y * context.canvas.height, radius, 0, Math.PI * 2);
    context.fill();
  });
  context.globalAlpha = 1;
}

function drawLines(context, points, links, color) {
  if (!points) return;
  context.strokeStyle = color;
  context.lineWidth = 2;
  links?.forEach((link) => {
    const [a, b] = Array.isArray(link) ? link : [link.start, link.end];
    if (!points[a] || !points[b]) return;
    context.beginPath();
    context.moveTo(points[a][0] * context.canvas.width, points[a][1] * context.canvas.height);
    context.lineTo(points[b][0] * context.canvas.width, points[b][1] * context.canvas.height);
    context.stroke();
  });
}

function drawOverlayMetrics(context, sample) {
  const lines = [`눈 깜빡임  ${sample.blinks}회 · ${sample.blinkRate}회/분`, `상체 이동  ${sample.upperBodyMoves}회`, `입꼬리 아래 방향 신호  ${sample.mouthFrownPercent}%`];
  const size = Math.max(14, Math.round(context.canvas.width / 52));
  context.fillStyle = "rgba(0, 0, 0, .68)";
  context.fillRect(16, 16, Math.min(context.canvas.width - 32, size * 20), size * 4.6);
  context.fillStyle = "#fff";
  context.font = `600 ${size}px Arial, sans-serif`;
  lines.forEach((line, index) => context.fillText(line, 16 + size, 16 + size * (1.15 + index * 1.1)));
}

function renderLiveIndicators(sample) {
  $("video-live-indicators").innerHTML = [
    ["얼굴 위치", sample.faceCentered ? "중앙 유지" : "위치 확인"],
    ["눈", `${sample.blinks}회 · ${sample.blinkRate}회/분`],
    ["상체", `${sample.upperBodyMoves}회 이동${sample.shoulderTilt ? " · 기울어짐" : ""}`],
    ["손", sample.handCount ? `${sample.handCount}개 감지` : "화면 밖"],
    ["입 주변", `아래 방향 ${sample.mouthFrownPercent}%`]
  ].map(([label, value]) => `<article><span>${label}</span><b>${value}</b></article>`).join("");
}

function renderOverlay() {
  const video = $("recording-playback");
  const canvas = $("landmark-overlay");
  if (!video.videoWidth || !state.visual?.samples?.length) return;
  let sample = state.visual.samples[0];
  for (const item of state.visual.samples) {
    if (item.time > video.currentTime) break;
    sample = item;
  }
  renderLiveIndicators(sample);
  if (!state.overlayVisible) return;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  drawPoints(context, sample.face, "#35d4ff", 1.5);
  drawLines(context, sample.face, state.vision?.faceConnections, "rgba(53, 212, 255, .5)");
  sample.hands?.forEach((hand) => {
    drawLines(context, hand, [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [0, 9], [9, 10], [10, 11], [11, 12], [0, 13], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20]], "#ffbf3f");
    drawPoints(context, hand, "#ffbf3f", 3);
  });
  drawLines(context, sample.pose, state.vision?.poseConnections, "#9aff77");
  drawPoints(context, sample.pose, "#9aff77", 3);
  drawOverlayMetrics(context, sample);
}

function syncPlaybackOverlay() {
  const video = $("recording-playback");
  if (video.videoWidth && video.videoHeight) $("playback-wrap").style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
  state.overlayLastTime = -1;
  renderOverlay();
}

function runOverlayLoop() {
  cancelAnimationFrame(state.overlayFrame);
  const draw = () => {
    const time = $("recording-playback").currentTime;
    if (state.overlayLastTime < 0 || Math.abs(time - state.overlayLastTime) >= .09) {
      state.overlayLastTime = time;
      renderOverlay();
    }
    if (state.overlayVisible && !$("recording-playback").paused) state.overlayFrame = requestAnimationFrame(draw);
  };
  draw();
}

function toggleOverlay() {
  state.overlayVisible = !state.overlayVisible;
  $("landmark-overlay").hidden = !state.overlayVisible;
  $("overlay-toggle").textContent = state.overlayVisible ? "랜드마크 숨기기" : "랜드마크 표시";
  if (state.overlayVisible) runOverlayLoop();
  else cancelAnimationFrame(state.overlayFrame);
}

function beginInterview() {
  if (!state.stream) return;
  state.questionRevealed = true;
  state.preparing = true;
  state.preparationEndsAt = Date.now() + 20000;
  $("start-interview-button").disabled = true;
  $("record-button").disabled = false;
  $("record-label").textContent = "준비되면 녹화 시작";
  $("recording-checklist").hidden = false;
  updateRole();
  updatePreparationTimer();
  state.preparationTimer = setInterval(updatePreparationTimer, 250);
}

function updatePreparationTimer() {
  const remaining = Math.max(0, Math.ceil((state.preparationEndsAt - Date.now()) / 1000));
  $("timer").textContent = `00:${String(remaining).padStart(2, "0")}`;
  $("live-caption").textContent = `질문을 확인하세요. ${remaining}초 후 녹화가 자동 시작됩니다.`;
  if (!remaining) {
    clearInterval(state.preparationTimer);
    state.preparing = false;
    startRecording();
  }
}

function startRecording() {
  if (!state.stream) return;
  if (state.preparing) {
    clearInterval(state.preparationTimer);
    state.preparing = false;
  }
  if (state.recordingUrl) {
    URL.revokeObjectURL(state.recordingUrl);
    state.recordingUrl = null;
  }
  state.chunks = [];
  state.transcript = "";
  state.followupText = "";
  state.recordedBlob = null;
  state.visual = emptyVisual();
  state.recorder = new MediaRecorder(state.stream);
  $("recording-checklist").hidden = true;
  state.recorder.ondataavailable = (event) => { if (event.data.size) state.chunks.push(event.data); };
  state.recorder.onstop = () => {
    state.recordedBlob = new Blob(state.chunks, { type: state.recorder.mimeType || "video/webm" });
    state.recordingUrl = URL.createObjectURL(state.recordedBlob);
    transcribeWithFasterWhisper(state.recordedBlob);
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
  startVisionSampling();
}

function stopRecording() {
  if (state.recorder?.state !== "inactive") state.recorder.stop();
  state.recording = false;
  clearInterval(state.timerId);
  clearInterval(state.sampleId);
  cancelAnimationFrame(state.visionSampleId);
  state.visionSampleId = null;
  state.duration = Math.max(1, Math.floor((Date.now() - state.startedAt) / 1000));
  if (state.silenceStartedAt !== null) {
    const finalSilence = performance.now() - state.silenceStartedAt;
    if (finalSilence >= 1500) state.silenceRuns.push(finalSilence);
    state.silenceStartedAt = null;
  }
  $("record-button").classList.remove("recording");
  $("record-label").textContent = "faster-whisper medium 전사 중";
  $("record-button").disabled = true;
  $("recording-badge").style.display = "none";
  $("finish-button").disabled = true;
  state.transcribing = true;
  $("live-caption").textContent = "녹화가 끝났습니다. faster-whisper medium 전사를 시작합니다.";
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
  const rubric = state.interviewPersona?.items.map((item) => ({
    ...item,
    checks: (item.keywords || []).map((word) => new RegExp(escapeRegex(word), "i"))
  })) || data.rubric;
  const keywords = state.interviewPersona?.items.flatMap((item) => item.keywords || []) || data.keywords;
  const keywordHits = [...new Set(keywords)].filter((word) => new RegExp(escapeRegex(word), "i").test(text));
  const rubricResults = rubric.map((item) => evaluateRubric(item, text));
  const rubricTotal = rubricResults.reduce((total, item) => total + item.score, 0);
  const hasNumber = /\d|퍼센트|배|명|건/.test(text);
  const volumeValues = state.audioSamples.filter((v) => v >= 0.018);
  const volumeMean = volumeValues.reduce((a, b) => a + b, 0) / Math.max(1, volumeValues.length);
  const volumeVariance = volumeValues.reduce((sum, value) => sum + (value - volumeMean) ** 2, 0) / Math.max(1, volumeValues.length);
  const voiceVariation = Math.sqrt(volumeVariance);
  const textAvailable = compact.length > 0;
  const paceHealthy = pace >= 250 && pace <= 420;
  const rubricMax = Math.max(3, rubricResults.length * 3);
  const score = textAvailable ? Math.min(95, Math.max(15, Math.round(18 + (rubricTotal / rubricMax) * 70 + (paceHealthy ? 5 : 0) - Math.min(8, fillers.length * 2)))) : 0;

  $("total-score").textContent = `${score}`;
  $("score-fill").style.width = `${score}%`;
  $("pace-value").textContent = textAvailable ? `${pace}자` : "—";
  $("pace-note").textContent = textAvailable ? (paceHealthy ? "안정 범위 / 분" : pace < 250 ? "조금 느림 / 분" : "조금 빠름 / 분") : "전사 입력 필요";
  $("pause-value").textContent = `${state.silenceRuns.length}회`;
  $("filler-value").textContent = `${fillers.length}회`;
  $("voice-value").textContent = volumeValues.length ? (voiceVariation > .025 ? "충분" : "낮음") : "—";
  $("voice-note").textContent = volumeValues.length ? "음량 변화 기준" : "음성 데이터 없음";
  $("transcript-source").textContent = state.transcript ? "faster-whisper medium · beam 5" : "직접 입력";
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
  if (!keywordHits.length) improvements.push(["직무 연결", `이번 질문의 핵심인 ${state.interviewPersona?.persona?.focus?.join(" · ") || data.signal} 중 하나를 실제 행동과 연결해 보세요.`]);
  if (fillers.length >= 3) improvements.push(["전달 습관", `습관어가 ${fillers.length}회 감지됐습니다. 문장 사이에 짧게 멈추는 편이 더 또렷합니다.`]);
  if (state.silenceRuns.length >= 2) improvements.push(["침묵", `1.5초 이상의 침묵이 ${state.silenceRuns.length}회 있었습니다. 첫 문장을 미리 정해 두면 시작이 안정됩니다.`]);
  if (!improvements.length) improvements.push(["다음 단계", "현재 구조는 안정적입니다. 본인의 판단 기준과 대안 비교를 한 문장 추가해 깊이를 높여 보세요."]);

  $("feedback-list").innerHTML = [
    ...strengths.slice(0, 2).map(([title, body]) => feedbackItem("잘 드러난 점", title, body, "good")),
    ...improvements.slice(0, 3).map(([title, body]) => feedbackItem("보완할 점", title, body, "improve"))
  ].join("");
  renderVideoFeedback();

  const followupTarget = [...rubricResults].sort((a, b) => a.score - b.score)[0];
  renderFollowup(followupTarget, Boolean(state.followupText));
}

function renderVideoFeedback() {
  const list = $("video-feedback-list");
  const status = $("vision-status");
  const items = videoFeedback();
  status.textContent = state.visionStatus;
  list.innerHTML = items.length
    ? items.map(([title, body]) => feedbackItem("영상 신호", title, body, "improve")).join("")
    : `<p class="card-intro">${state.visionStatus.startsWith("분석 완료") ? "녹화 중 수집된 영상 데이터가 없습니다. 다음 녹화에서 카메라가 보이는지 확인해 주세요." : `영상 분석을 완료하지 못했습니다. 상태: ${state.visionStatus}`}</p>`;
}

function evaluateRubric(item, text) {
  const evidence = item.checks.map((pattern) => findEvidence(text, pattern)).filter(Boolean);
  const score = Math.min(3, evidence.length);
  const missing = score === 0
    ? `현재 답변에서 ${item.label}의 근거를 찾지 못했습니다. ${item.followup}`
    : score === 1
      ? `${item.label}에 대한 단서가 하나 있습니다. 행동 또는 결과를 더해 근거를 완성해 보세요.`
      : `${item.label}의 근거가 더 선명해지도록 판단 이유나 회고를 한 문장 덧붙여 보세요.`;
  return { ...item, score, evidence, missing };
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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
    const questions = state.interviewPersona?.questions || [];
    const currentQuestion = questions[state.question % Math.max(1, questions.length)];
    const result = await window.CareerCoachAPI.evaluateInterview({
      postingId: state.jobContext?.postingId || null,
      question: $("question-text").textContent,
      itemId: currentQuestion?.item_id,
      transcript,
      followupAnswer: state.followupText,
      deliveryMetrics: { durationSeconds: state.duration, longPauses: state.silenceRuns.length }
    });
    const evidence = result.evidence?.map((item) => `${item.source}: “${item.quote}”`).join(" · ");
    $("feedback-list").innerHTML = result.feedback.map((item) => feedbackItem(item.label, item.title, `${item.body}${evidence ? ` 근거: ${evidence}` : ""}`, item.type)).join("");
    $("followup-context").textContent = result.followupQuestion || "이 기준에 대한 추가 질문은 없습니다.";
    $("agent-feedback-status").textContent = `직무 AI 코치 피드백이 반영됐습니다. (${result.modelUsed})`;
  } catch (error) {
    $("agent-feedback-status").textContent = "AI 코치 피드백을 불러오지 못해 규칙 기반 피드백을 유지합니다.";
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
    state.overlayVisible = false;
    $("landmark-overlay").hidden = true;
    $("overlay-toggle").textContent = "랜드마크 표시";
    $("overlay-toggle").disabled = !state.visual?.samples?.length;
  } else {
    playback.removeAttribute("src");
    recordingCard.hidden = true;
  }
  if (!state.transcript) $("transcript-input").value = "";
  analyze();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetPractice() {
  clearInterval(state.preparationTimer);
  $("result-view").hidden = true;
  $("practice-view").hidden = false;
  $("timer").textContent = "00:00";
  $("live-caption").textContent = "";
  $("recording-checklist").hidden = true;
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
  state.overlayVisible = false;
  cancelAnimationFrame(state.overlayFrame);
  $("landmark-overlay").hidden = true;
  $("overlay-toggle").disabled = true;
  state.preparing = false;
  state.questionRevealed = false;
  $("start-interview-button").disabled = !state.stream;
  $("record-button").disabled = true;
  $("record-label").textContent = "답변 녹화 시작";
  updateRole();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("role-select").addEventListener("change", () => { state.question = 0; state.followupText = ""; updateRole(); });
$("next-question").addEventListener("click", () => { const count = state.interviewPersona?.questions.length || 3; state.question = (state.question + 1) % count; state.followupText = ""; updateRole(); });
$("enable-camera").addEventListener("click", enableCamera);
$("start-interview-button").addEventListener("click", beginInterview);
$("overlay-toggle").addEventListener("click", toggleOverlay);
$("recording-playback").addEventListener("loadedmetadata", syncPlaybackOverlay);
$("recording-playback").addEventListener("timeupdate", renderOverlay);
$("recording-playback").addEventListener("seeked", renderOverlay);
$("recording-playback").addEventListener("play", runOverlayLoop);
$("recording-playback").addEventListener("pause", () => cancelAnimationFrame(state.overlayFrame));
$("record-button").addEventListener("click", () => {
  if (state.recording) stopRecording();
  else if (state.preparing) startRecording();
  else if (!state.transcribing) beginInterview();
});
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
  requestAgentFeedback();
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
