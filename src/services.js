import { DEMO_CONTEXTS, DEMO_POSTINGS } from "./demo-fixtures.js";

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
  try {
    const [live, contexts] = await Promise.all([
      fetchJson("/api/v1/live-postings"),
      fetchJson("/api/v1/job-contexts")
    ]);
    if (!live.items?.length) throw new Error("LIVE_POSTINGS_EMPTY");
    return { postings:live.items, contexts:contexts.items || [], source:"api" };
  } catch (error) {
    console.info("Next Step demo fixture activated:", error.message);
    return { postings:DEMO_POSTINGS, contexts:DEMO_CONTEXTS, source:"fixture", error:error.message };
  }
}

function demoRecommendation(text) {
  const hasData = /(데이터|분석|통계|파이썬|python|sql|엑셀)/i.test(text);
  const hasProject = /(프로젝트|협업|기획|사용자|문제|개선)/i.test(text);
  return {
    demo:true,
    matches:[
      { name:hasData?"데이터 분석":"서비스 기획",sentence:"입력한 경험에서 문제를 정의하고 결과를 설명한 근거가 확인돼요.",have:[{competency:"문제 정의",quotes:[{text:text.slice(0,90)}]},{competency:hasData?"데이터 활용":"기획·협업",quotes:[]}] },
      { name:hasProject?"프로젝트 운영":"품질 관리",sentence:"경험을 단계별로 정리하고 실행한 과정이 이 직무와 연결돼요.",have:[{competency:"실행력",quotes:[]},{competency:"협업",quotes:[]}] },
      { name:"직무 리서치·사업 지원",sentence:"자료를 정리하고 핵심 내용을 전달하는 역량을 확장해볼 수 있어요.",have:[{competency:"정보 구조화",quotes:[]}] }
    ]
  };
}

export async function requestRecommendation(text) {
  try {
    return await fetchJson("/api/recommend", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ texts:text.split(/\n+/).filter(Boolean),target:"",limit:5 }) });
  } catch (error) {
    return { ...demoRecommendation(text), fallbackReason:error.code };
  }
}

function demoActions(job) {
  return [
    { title:"공고 핵심 요구사항 확인",reason:`${(job.requiredSkills || []).slice(0,3).join(", ") || job.jobFamily}과 연결되는 경험을 찾아보세요.`,priority:"high" },
    { title:"대표 경험 한 가지 정리",reason:"상황·행동·결과가 드러나도록 세 문장으로 정리해요.",priority:"high" },
    { title:"자소서 초안 작성",reason:"정리한 경험을 지원 동기와 연결해요.",priority:"medium" },
    { title:"면접 질문으로 말해보기",reason:"공고 Persona 질문에 1분 안으로 답해봐요.",priority:"medium" }
  ];
}

export async function requestCoach({ job, mode, message, profile, currentTasks, history }) {
  try {
    return await fetchJson("/api/v1/agent/chat", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ postingId:job.postingId,mode,message,userProfile:{ experience:profile.experiences || "경험 미입력",deadline:job.deadline },currentTasks,history }) });
  } catch (error) {
    return {
      demo:true,
      answer:`체험 모드로 안내할게요. ${job.companyName} ${job.positionTitle} 공고에서는 ${(job.requiredSkills || []).slice(0,3).join(", ") || job.jobFamily} 관련 경험을 먼저 고르는 것이 좋아요. 한 가지 경험을 상황, 내가 한 행동, 결과 순서로 정리해 보세요.`,
      evidence:[{ source:"실제 공고 fixture",quote:`${job.positionTitle} · ${(job.requiredSkills || []).join(", ")}` }],
      nextActions:demoActions(job),
      missingInformation:[],
      modelUsed:"frontend-demo",
      fallbackReason:error.code
    };
  }
}

export async function requestEssayReview({ job, sections, experiences }) {
  try {
    return await fetchJson("/api/v1/essays/review", { method:"POST",headers:jsonHeaders,body:JSON.stringify({ postingId:job.postingId,sections,experiences }) });
  } catch (error) {
    const answer = sections.map((item) => item.answer).join(" ");
    const detailed = answer.length >= 180;
    return { demo:true,generated_by:"frontend-demo",fallbackReason:error.code,items:[
      { status:detailed?"strong":"weak",label:"경험의 구체성",feedback:detailed?"행동과 결과가 비교적 구체적으로 드러나요.":"경험의 상황은 보이지만 본인의 행동이 조금 더 필요해요.",suggestion:"본인이 직접 판단하고 실행한 행동을 한 문장 추가해 보세요." },
      { status:/\d|%|명|건|배/.test(answer)?"strong":"missing",label:"결과 근거",feedback:"성과를 확인할 수 있는 변화나 결과가 필요해요.",suggestion:"수치가 없다면 전후 변화나 팀의 반응을 구체적으로 적어보세요." },
      { status:"weak",label:"공고 연결",feedback:`${job.positionTitle} 업무와 경험의 연결을 한 번 더 설명하면 좋아요.`,suggestion:`${(job.requiredSkills || [job.jobFamily])[0]} 역량을 어떻게 활용할지 마지막 문장에 덧붙여 보세요.` }
    ]};
  }
}

export function createBrowserStore(type) {
  const target = type === "session" ? sessionStorage : localStorage;
  return {
    get(key, fallback) { try { return JSON.parse(target.getItem(`nextstep.${key}`)) ?? fallback; } catch { return fallback; } },
    set(key, value) { target.setItem(`nextstep.${key}`, JSON.stringify(value)); },
    remove(key) { target.removeItem(`nextstep.${key}`); }
  };
}
