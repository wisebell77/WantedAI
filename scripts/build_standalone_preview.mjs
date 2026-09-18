import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (relativePath) => readFile(resolve(root, relativePath), "utf8");

const [html, css, js, image, interviewHtml, interviewCss, overlayCss, jobContextApi, agentApi, interviewApp] = await Promise.all([
  read("dist/next-step.html"),
  read("dist/next-step.css"),
  read("dist/next-step.js"),
  readFile(resolve(root, "dist/assets/campus-start.png")),
  read("dist/index.html"),
  read("dist/styles.css"),
  read("dist/overlay.css"),
  read("dist/job-context-api.js"),
  read("dist/agent-api.js"),
  read("dist/app.js")
]);

// String.replace() interprets $&, $`, $', $1 … inside a replacement STRING.
// Every replacement here injects bundled JS/CSS that may contain those sequences,
// so all replacements use the function form, which is passed through verbatim.
const insert = (value) => () => value;
// Embeds an HTML document inside a <script> string literal without letting the
// HTML parser see a closing tag, and without tripping on JS line separators.
const asScriptSafeLiteral = (value) => JSON.stringify(value)
  .replace(/<\//g, insert("<\\/"))
  .split("\u2028").join("\\u2028")
  .split("\u2029").join("\\u2029");

const POSTING_ID_TOKEN = "__NEXT_STEP_POSTING_ID__";
const JOB_JSON_TOKEN = "__NEXT_STEP_JOB_JSON__";

const imageUrl = `data:image/png;base64,${image.toString("base64")}`;
const inlineCss = `${css.replace("./assets/campus-start.png", insert(imageUrl))}
.standalone-preview-badge{position:fixed;right:16px;bottom:16px;z-index:9999;padding:8px 12px;border:1px solid rgba(37,99,235,.16);border-radius:999px;background:rgba(255,255,255,.9);box-shadow:0 8px 30px rgba(15,23,42,.12);backdrop-filter:blur(12px);color:#1d4ed8;font:600 12px/1.2 system-ui,sans-serif}
.interview-preview-overlay{position:fixed;inset:0;z-index:9998;display:flex;flex-direction:column;background:#f4f8ff;color:#17243b}.interview-preview-topbar{flex:none;min-height:70px;padding:12px max(20px,calc((100vw - 1280px)/2 + 20px));display:flex;align-items:center;gap:16px;border-bottom:1px solid #d8e6fb;background:rgba(255,255,255,.96)}.interview-preview-topbar strong{font-size:17px}.interview-preview-topjob{color:#5d7396;font-size:13px;line-height:1.5;word-break:keep-all}.interview-preview-back{margin-left:auto;flex:none;min-height:42px;padding:0 17px;border:1px solid #d7e5fa;border-radius:12px;background:#f5f9ff;color:#246bfd;font-weight:700;cursor:pointer}.interview-preview-frame{flex:1;width:100%;border:0;background:#f7f7f7}@media(max-width:800px){.interview-preview-topbar{min-height:62px;padding:10px 16px;gap:10px}.interview-preview-topjob{display:none}}
`;
const inlineJs = js.replace(/\n?\/\/# sourceMappingURL=.*$/m, insert(""));

const postings = [
  { postingId:"role-235",externalId:"177598",companyName:"DB Inc.",positionTitle:"2026 하반기 신입 · AX 엔지니어",jobFamily:"정보기술개발",employmentType:"정규직",companyType:"대기업",deadline:"2026-09-24",sourceUrl:"#",coachReady:true,requiredSkills:["Python","SQL","AI Agent"] },
  { postingId:"role-236",externalId:"177102",companyName:"현대로템",positionTitle:"우주발사체 유도·제어 기술 개발",jobFamily:"기계·연구개발",employmentType:"정규직",companyType:"대기업",deadline:"2026-09-27",sourceUrl:"#",coachReady:true,requiredSkills:["Python","C++","데이터 분석"] },
  { postingId:"role-112",externalId:"176904",companyName:"한국교통연구원",positionTitle:"교통 빅데이터 연구원",jobFamily:"연구",employmentType:"기간제",companyType:"공공기관",deadline:"2026-09-30",sourceUrl:"#",coachReady:true,requiredSkills:["통계분석","GIS","Python"] },
  { postingId:null,externalId:"178001",companyName:"서울디자인재단",positionTitle:"사업운영 인턴",jobFamily:"사업관리",employmentType:"인턴",companyType:"공공기관",deadline:"2026-10-03",sourceUrl:"#",coachReady:false,requiredSkills:[] },
  { postingId:"role-301",externalId:"178101",companyName:"네이버클라우드",positionTitle:"데이터 분석 체험형 인턴",jobFamily:"데이터",employmentType:"인턴",companyType:"대기업",deadline:"2026-10-08",sourceUrl:"#",coachReady:true,requiredSkills:["SQL","Python","시각화"] },
  { postingId:null,externalId:"178211",companyName:"국립생태원",positionTitle:"환경 데이터 조사 지원",jobFamily:"환경·에너지·안전",employmentType:"기간제",companyType:"공공기관",deadline:"2026-10-12",sourceUrl:"#",coachReady:false,requiredSkills:[] }
];
const contexts = postings.filter((item) => item.postingId).map((item) => ({ ...item, tier:"A", responsibilities:[`${item.positionTitle} 관련 프로젝트 수행 및 데이터 기반 문제 해결`], preferredSkills:[] }));

/* ------------------------------------------------------------------ *
 * Interview entry, embedded whole.
 * The standalone build ships the same dist/index.html + app.js the real
 * project serves at /index.html?postingId=…  Only the calls that need a
 * server (job context, persona, interview feedback, transcription) are
 * answered by a demo shim inside the iframe; the screen and the flow are
 * the real ones.
 * ------------------------------------------------------------------ */
const interviewShim = `
window.NEXT_STEP_POSTING_ID = "${POSTING_ID_TOKEN}";
window.NEXT_STEP_JOB = ${JOB_JSON_TOKEN};
(() => {
  const contexts = ${JSON.stringify(contexts)};
  const json = (body, status=200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers:{"Content-Type":"application/json"}}));
  const job = () => {
    const id = window.NEXT_STEP_POSTING_ID;
    const found = contexts.find((item) => item.postingId === id);
    if (found) return found;
    const passed = window.NEXT_STEP_JOB;
    if (!passed) return null;
    return {
      postingId: String(passed.postingId || id || "preview"),
      companyName: String(passed.companyName || "선택 공고"),
      positionTitle: String(passed.positionTitle || "지원 직무"),
      jobFamily: String(passed.jobFamily || "직무 미분류"),
      responsibilities: [String(passed.positionTitle || "지원 직무") + " 관련 업무 수행"],
      requiredSkills: Array.isArray(passed.requiredSkills) ? passed.requiredSkills.map(String) : [],
      preferredSkills: [],
      deadline: passed.deadline || null
    };
  };
  const persona = () => {
    const item = job();
    const skills = (item?.requiredSkills || []).filter(Boolean);
    const first = skills[0] || "직무 역량";
    return {
      persona: { name: (item?.jobFamily || "직무") + " 면접관", focus: skills.slice(0, 3) },
      items: [
        { id:"r1", label:"문제 정의", keywords:["문제","목표","배경","원인"], missing:"어떤 문제를 왜 풀었는지 상황과 목표를 먼저 구분해 주세요." },
        { id:"r2", label:"내 행동", keywords:["분석","설계","구현","조사","협업","제안"], missing:"팀의 성과가 아니라 본인이 직접 판단하고 실행한 부분을 드러내 주세요." },
        { id:"r3", label:"결과·회고", keywords:["결과","개선","감소","증가","배운"], missing:"결과를 수치나 전후 변화로 보여주고 무엇을 배웠는지 덧붙여 주세요." }
      ],
      questions: [
        { question: first + "을(를) 활용해 문제를 해결한 경험을 설명해 주세요.", item_id:"r1" },
        { question: "팀에서 의견이 갈렸을 때 본인이 어떤 기준으로 판단했는지 말씀해 주세요.", item_id:"r2" },
        { question: (item?.companyName || "이 회사") + "의 이 직무에서 본인의 경험을 어떻게 쓸 수 있을지 설명해 주세요.", item_id:"r3" }
      ]
    };
  };
  const feedback = (payload) => {
    const text = String(payload?.transcript || "");
    const compact = text.replace(/\\s/g, "");
    const hasNumber = /\\d|퍼센트|배|명|건/.test(text);
    const items = [
      { label:"잘 드러난 점", title:"경험 선택", body: compact.length > 120 ? "질문에 맞는 경험을 고르고 상황을 설명하려는 흐름이 보입니다." : "경험을 고르긴 했지만 분량이 짧아 판단 근거가 아직 부족합니다.", type:"good" },
      { label:"보완할 점", title:"본인의 행동", body:"팀이 한 일과 본인이 직접 결정하고 실행한 일을 문장으로 나눠 주세요.", type:"improve" },
      { label:"보완할 점", title:"결과 근거", body: hasNumber ? "수치가 있어 좋습니다. 그 수치가 왜 의미 있는지 한 문장만 덧붙여 보세요." : "결과에 기간·규모·전후 변화 중 하나를 붙이면 설득력이 올라갑니다.", type:"improve" }
    ];
    return {
      feedback: items,
      evidence: [{ source:"JD", quote:(job()?.requiredSkills || []).slice(0, 2).join(" · ") || "직무 요구 역량" }],
      followupQuestion: "그 판단을 내릴 때 검토했지만 선택하지 않은 다른 방법은 무엇이었나요?",
      modelUsed: "standalone-preview"
    };
  };
  const originalFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = async (input, options = {}) => {
    const url = String(typeof input === "string" ? input : input?.url || "");
    if (url.includes("/api/v1/job-contexts")) {
      const item = job();
      return item ? json(item) : json({ error:"JOB_CONTEXT_NOT_FOUND" }, 404);
    }
    if (url.includes("/api/v1/agent/interview-persona")) return json(persona());
    if (url.includes("/api/v1/agent/interview-feedback")) {
      let payload = {};
      try { payload = JSON.parse(options?.body || "{}"); } catch (error) { payload = {}; }
      return json(feedback(payload));
    }
    if (url.includes("/api/v1/interview/transcribe")) {
      return json({ error:"STANDALONE_PREVIEW_NO_SERVER" }, 503);
    }
    if (originalFetch) return originalFetch(input, options);
    return json({ error:"PREVIEW_ONLY" }, 404);
  };
  // Camera: the entry's own enableCamera() handler runs untouched. Because the
  // standalone page is opened from file://, this srcdoc iframe has an opaque
  // origin and Permissions Policy refuses camera/microphone delegation, so the
  // real getUserMedia() rejects and the entry's own catch runs as it always has.
  // This only makes that rejection visible instead of a silent no-op. Served
  // over http(s) the real call succeeds and none of this ever appears.
  const media = navigator.mediaDevices;
  if (media && typeof media.getUserMedia === "function") {
    const realGetUserMedia = media.getUserMedia.bind(media);
    media.getUserMedia = (constraints) => realGetUserMedia(constraints).catch((error) => {
      const frame = document.getElementById("camera-frame");
      if (frame && !frame.querySelector(".standalone-camera-notice")) {
        const notice = document.createElement("p");
        notice.className = "standalone-camera-notice";
        notice.setAttribute("role", "status");
        notice.textContent = "이 미리보기 파일(file://)에서는 브라우저 보안 정책상 카메라·마이크를 열 수 없어요. 프로젝트 서버를 실행하면 같은 화면에서 실제 카메라·녹화·전사가 그대로 동작합니다. (" + (error && error.name ? error.name : "NotAllowedError") + ")";
        frame.appendChild(notice);
      }
      const label = document.getElementById("device-label");
      if (label) label.textContent = "카메라 연결 실패 · 브라우저 보안 정책";
      throw error; // the entry's existing catch still handles it, unchanged
    });
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-close-interview]");
    if (!link) return;
    event.preventDefault();
    parent.postMessage({ type:"NEXT_STEP_CLOSE_INTERVIEW" }, "*");
  });
})();
`;

const interviewDoc = interviewHtml
  // The standalone file must stay offline-only, so the entry's webfont links are
  // stripped here exactly as they are for the main page above.
  .replace(/\s*<link rel="preconnect"[^>]*>/g, insert(""))
  .replace(/\s*<link href="https:\/\/fonts\.googleapis\.com[^>]*>/g, insert(""))
  // The standalone overlay supplies its own top bar (brand + selected job +
  // "AI 코치로 돌아가기"), so the entry's own top bar would be a duplicate here.
  // Hidden for the embed only — dist/index.html keeps it for the real project.
  .replace(/<link rel="stylesheet" href="\.\/styles\.css" \/>/, insert(`<style>${interviewCss}</style><style>.topbar{display:none}.practice-layout,.result-view{padding-top:28px}.standalone-camera-notice{position:absolute;left:12px;right:12px;bottom:12px;margin:0;padding:12px 14px;border:1px solid #f0cfa8;border-radius:12px;background:rgba(255,248,238,.97);color:#8a5a22;font-size:.82rem;line-height:1.6;word-break:keep-all}</style>`))
  .replace(/<link rel="stylesheet" href="\.\/overlay\.css" \/>/, insert(`<style>${overlayCss}</style>`))
  .replace(/href="\.\/next-step\.html#landing"/g, insert('href="#" data-close-interview'))
  .replace(/href="\.\/next-step\.html#coach"/g, insert('href="#" data-close-interview'))
  .replace(/<script src="\.\/job-context-api\.js"><\/script>/, insert(`<script>${interviewShim}<\/script>\n    <script>${jobContextApi}<\/script>`))
  .replace(/<script src="\.\/agent-api\.js"><\/script>/, insert(`<script>${agentApi}<\/script>`))
  .replace(/<script src="\.\/app\.js"><\/script>/, insert(`<script>${interviewApp}<\/script>`));

for (const leftover of ["./styles.css", "./overlay.css", "./job-context-api.js", "./agent-api.js", "./app.js"]) {
  if (interviewDoc.includes(leftover)) throw new Error(`Interview entry still references an external file: ${leftover}`);
}

const previewApi = `
<script>
(() => {
  const postings = ${JSON.stringify(postings)};
  const contexts = ${JSON.stringify(contexts)};
  const json = (body, status=200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers:{"Content-Type":"application/json"}}));
  window.fetch = async (input, options={}) => {
    const url = String(input);
    if (url.includes("/api/v1/live-postings")) return json({items:postings,total:postings.length,coachReady:postings.filter(x=>x.coachReady).length,source:"standalone-preview"});
    if (url.includes("/api/v1/job-contexts/")) {
      const id=decodeURIComponent(url.split("/").pop()); const item=contexts.find(x=>x.postingId===id);
      return item?json(item):json({error:"JOB_CONTEXT_NOT_FOUND"},404);
    }
    if (url.includes("/api/v1/job-contexts")) return json({items:contexts,total:contexts.length,families:[...new Set(contexts.map(x=>x.jobFamily))],source:"standalone-preview"});
    if (url.includes("/api/v1/agent/status")) return json({configured:true,fastModel:"preview",coachModel:"preview"});
    if (url.includes("/api/recommend")) return json({mode:"reverse",matches:[
      {name:"데이터 분석",sentence:"프로젝트에서 데이터를 정리하고 결과를 설명한 경험과 연결돼요.",have:[{competency:"데이터 전처리",quotes:[{text:"공공데이터를 정리하고 시각화한 경험"}]},{competency:"분석 결과 해석",quotes:[]}]},
      {name:"도시·교통 데이터 연구",sentence:"공간정보와 통계를 활용한 경험을 도시 문제 해결에 적용할 수 있어요.",have:[{competency:"공간 데이터 분석",quotes:[{text:"GIS를 활용해 입지와 접근성을 분석한 경험"}]}]},
      {name:"서비스 기획",sentence:"사용자 문제를 정의하고 팀과 해결안을 구체화한 경험이 닿아 있어요.",have:[{competency:"문제 정의",quotes:[{text:"문제 원인을 구조화하고 해결 흐름을 설계한 경험"}]}]}
    ]});
    if (url.includes("/api/v1/agent/chat")) return json({answer:"이 공고는 Python·SQL로 데이터를 다룬 경험을 중요하게 보고 있어요. 먼저 가장 구체적인 프로젝트 하나를 골라 문제, 본인의 행동, 결과 순서로 정리해 보세요.",evidence:[{source:"JD",quote:"데이터 기반 문제 해결 경험"}],nextActions:[{title:"대표 프로젝트 한 가지 고르기",reason:"공고의 핵심 역량과 연결할 근거를 정리해요.",priority:"high"},{title:"성과 수치 보완하기",reason:"결과의 변화를 구체적으로 보여줘요.",priority:"medium"}],missingInformation:[],modelUsed:"preview"});
    if (url.includes("/api/v1/essays/review")) return json({generated_by:"preview",items:[{status:"strong",label:"데이터 분석 경험",feedback:"본인이 수행한 분석 행동과 결과가 구체적으로 드러나요.",suggestion:"핵심 결과를 첫 문장에 배치하면 더 선명해져요."},{status:"weak",label:"협업과 전달",feedback:"협업 과정은 보이지만 본인의 판단 기준이 다소 흐려요.",suggestion:"의견 차이를 해결한 기준을 한 문장 추가해 보세요."},{status:"missing",label:"지원 직무 연결",feedback:"경험이 해당 공고 업무에 어떻게 이어지는지 직접적인 문장이 필요해요.",suggestion:"마지막에 입사 후 활용 방향을 덧붙여 보세요."}]});
    if (url.includes("/api/v1/agent/interview-persona")) return json({persona:{name:"데이터 직무 면접관"},items:[{id:"r1",label:"문제 정의"}],questions:[{question:"데이터로 문제를 해결한 경험을 설명해 주세요.",item_id:"r1"}]});
    return json({error:"PREVIEW_ONLY"},404);
  };
  const escapeHtml = (value="") => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
  const INTERVIEW_DOC = ${asScriptSafeLiteral(interviewDoc)};
  const buildDoc = (job) => INTERVIEW_DOC
    .split(${JSON.stringify(POSTING_ID_TOKEN)}).join(String(job?.postingId || ""))
    .split(${JSON.stringify(JOB_JSON_TOKEN)}).join(JSON.stringify(job || null).split("<").join("\\\\u003c"));
  window.NextStepPreview = {
    openInterview(job) {
      document.querySelector(".interview-preview-overlay")?.remove();
      const overlay = document.createElement("section");
      overlay.className = "interview-preview-overlay";
      overlay.dataset.postingId = job?.postingId || "";
      overlay.setAttribute("aria-label", "면접 연습");
      overlay.innerHTML = '<header class="interview-preview-topbar"><strong>Next Step</strong>'+
        '<span class="interview-preview-topjob">' + escapeHtml(job?.companyName || "") + ' · ' + escapeHtml(job?.positionTitle || "") + '</span>'+
        '<button class="interview-preview-back" type="button">AI 코치로 돌아가기</button></header>'+
        '<iframe class="interview-preview-frame" title="면접 연습" allow="camera; microphone"></iframe>';
      const close = () => { window.removeEventListener("message", onMessage); overlay.remove(); };
      const onMessage = (event) => { if (event.data?.type === "NEXT_STEP_CLOSE_INTERVIEW") close(); };
      document.body.appendChild(overlay);
      overlay.querySelector(".interview-preview-frame").srcdoc = buildDoc(job);
      overlay.querySelector(".interview-preview-back").addEventListener("click", close);
      window.addEventListener("message", onMessage);
    }
  };
})();
<\/script>`;

const output = html
  .replace(/\s*<link rel="preconnect"[^>]*>/g, insert(""))
  .replace(/\s*<link href="https:\/\/fonts\.googleapis\.com[^>]*>/g, insert(""))
  .replace(/\s*<link rel="stylesheet" href="\.\/next-step\.css" \/>/, insert(`\n<style>${inlineCss}</style>`))
  .replace("</body>", insert('<div class="standalone-preview-badge">Next Step · 미리보기 데이터</div></body>'))
  .replace(/\s*<script type="module" src="\.\/next-step\.js"><\/script>/, insert(`${previewApi}\n<script>${inlineJs}<\/script>`))
  .replace("<title>Next Step · 나의 다음 커리어</title>", insert("<title>Next Step · Standalone Preview</title>"));

const previewDefinitionIndex = output.indexOf("window.NextStepPreview =");
const previewHandlerIndex = output.indexOf("window.NextStepPreview?.openInterview");
if (previewDefinitionIndex < 0 || previewHandlerIndex < 0 || previewDefinitionIndex > previewHandlerIndex) {
  throw new Error("Standalone interview entry must be defined before the bundled click handler.");
}

const requiredPreviewContent = [
  "openInterview(job)",
  "interview-preview-overlay",
  "interview-preview-frame",
  "data-interview",
  "id=\\\"practice-view\\\"",
  "면접 연습",
  "id=\\\"camera\\\"",
  "id=\\\"enable-camera\\\"",
  "id=\\\"record-button\\\"",
  "id=\\\"feedback-list\\\"",
  "id=\\\"rubric-map\\\"",
  POSTING_ID_TOKEN
];
for (const required of requiredPreviewContent) {
  if (!output.includes(required)) throw new Error(`Standalone preview is missing: ${required}`);
}
if (output.includes("ERR_FILE_NOT_FOUND")) throw new Error("Standalone preview must not reference missing files.");

const target = resolve(root, "NextStep-preview.html");
await writeFile(target, output);
console.log(target);
