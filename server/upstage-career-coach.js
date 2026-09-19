// 제공자는 환경변수로 고른다. 요청 본문이 OpenAI 호환 형식이라 URL·키·모델명만
// 바꾸면 Upstage 든 OpenAI 든 그대로 돈다. persona/llm.py 도 같은 변수를 읽는다.
//
//   LLM_BASE_URL     기본 https://api.upstage.ai/v1/chat/completions
//   LLM_API_KEY      없으면 UPSTAGE_API_KEY
//   LLM_COACH_MODEL  판단이 필요한 곳 (자소서·상담·면접평가)
//   LLM_FAST_MODEL   가벼운 곳 (타임라인·할 일·태깅)
//
// 기존 UPSTAGE_* 는 폴백으로 남긴다 — 되돌릴 때 변수만 지우면 된다.
const UPSTAGE_URL = "https://api.upstage.ai/v1/chat/completions";
const llmUrl = () => process.env.LLM_BASE_URL || UPSTAGE_URL;
const llmKey = (given) => given || process.env.LLM_API_KEY || process.env.UPSTAGE_API_KEY || "";

function stripJsonFence(value) {
  return value.trim().replace(/^```json\s*/i, "").replace(/\s*```$/, "");
}

// temperature 는 기본적으로 보내지 않는다.
// gpt-5.6 계열은 기본값(1)만 받고 다른 값을 주면 400 을 낸다:
//   "Unsupported value: 'temperature' does not support 0.2 with this model."
// Upstage(solar)로 되돌릴 때는 LLM_TEMPERATURE=0.2 를 넣으면 예전대로 돈다.
function withTemperature(body) {
  const t = process.env.LLM_TEMPERATURE;
  if (t !== undefined && t !== "" && Number.isFinite(Number(t))) body.temperature = Number(t);
  return body;
}

async function callUpstage(messages, { apiKey, model, fetchImpl = fetch }) {
  const key = llmKey(apiKey);
  if (!key) throw new Error("LLM_API_KEY (or UPSTAGE_API_KEY) is required.");
  const response = await fetchImpl(llmUrl(), {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify(withTemperature({ model, stream: false, messages }))
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`LLM request failed (${model}): ${response.status} ${detail.slice(0, 180)}`);
  }
  const content = (await response.json()).choices?.[0]?.message?.content;
  if (!content) throw new Error("LLM returned no message content.");
  return JSON.parse(stripJsonFence(content));
}

export async function runCareerCoachAgent(input, options) {
  const fastModel = options.fastModel || process.env.LLM_FAST_MODEL || "solar-mini";
  const coachModel = options.coachModel || process.env.LLM_COACH_MODEL || "solar-pro4";
  const model = ["timeline", "task_prioritization", "jd_tagging"].includes(input.mode) ? fastModel : coachModel;
  const system = [
    "당신은 선택된 직무의 한국어 취업 준비 코치다.",
    "제공된 채용공고 데이터와 사용자가 직접 입력한 경험만 사실로 취급한다.",
    "공고에 없는 요구사항, 사용자에게 없는 경험, 마감일을 만들어내지 않는다.",
    "공고 품질이 B 또는 C이면 구체적인 직무 역량 판단을 제한하고 불확실성을 알린다.",
    "합격 가능성이나 민감한 개인 특성을 추론하지 않는다.",
    "조언마다 근거가 된 JD 필드 또는 사용자 입력을 evidence에 명시한다.",
    "반드시 JSON만 반환한다.",
    "형식: {answer:string,evidence:[{source:string,quote:string}],nextActions:[{title:string,reason:string,priority:'high'|'medium'|'low'}],missingInformation:string[]}.",
    "timeline과 task_prioritization 모드에서는 nextActions를 반드시 3~5개 반환한다. timeline 모드의 각 title에는 선택 공고 마감일 기준 D-며칠 또는 마감일 순서를 넣고, 마감일 이후의 행동은 넣지 않는다. evidence는 실제 입력의 짧은 인용만 사용한다."
  ].join(" ");
  const payload = {
    mode: input.mode,
    request: input.message,
    selectedJob: input.jobContext,
    userProfile: input.userProfile,
    currentTasks: (input.currentTasks || []).filter((item) => item?.postingId === input.jobContext.postingId),
    recentConversation: (input.history || []).filter((item) => item?.postingId === input.jobContext.postingId).slice(-6)
  };
  const result = await callUpstage([
    { role: "system", content: system },
    { role: "user", content: JSON.stringify(payload) }
  ], { ...options, model });
  return { ...result, modelUsed: model };
}

export async function evaluateInterviewWithUpstage(input, options) {
  const model = options.coachModel || process.env.LLM_COACH_MODEL || "solar-pro4";
  const system = [
    "당신은 선택된 직무의 한국어 면접 코치다.",
    "제공된 채용공고와 면접 답변만 사실로 취급한다.",
    "공고에 없는 요구사항이나 답변에 없는 경험을 만들어내지 않는다.",
    "합격 가능성, 성격, 외모, 민감한 개인 특성을 판단하지 않는다.",
    "전달 지표는 말하기 연습을 위한 참고 정보일 뿐 채용 판단 근거로 쓰지 않는다.",
    "반드시 JSON만 반환한다.",
    "형식: {feedback:[{label:string,title:string,body:string,type:'good'|'improve'}],followupQuestion:string,evidence:[{source:string,quote:string}],missingInformation:string[]}.",
    "feedback은 2~4개로 작성하고, JD와 답변의 연결을 가장 중요하게 평가한다. evidence에는 실제 JD 또는 답변의 짧은 인용만 넣는다."
  ].join(" ");
  const result = await callUpstage([
    { role: "system", content: system },
    { role: "user", content: JSON.stringify({
      selectedJob: input.jobContext,
      question: input.question,
      answer: input.transcript,
      deliveryMetrics: input.deliveryMetrics || {}
    }) }
  ], { ...options, model });
  return { ...result, modelUsed: model };
}
