import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile("src/next-step.js", "utf8");
const interview = await readFile("dist/index.html", "utf8");
const styles = await readFile("dist/next-step.css", "utf8");
const previewBuilder = await readFile("scripts/build_standalone_preview.mjs", "utf8");
const interviewApp = await readFile("dist/app.js", "utf8");
const styles2 = await readFile("dist/styles.css", "utf8");
const server = await readFile("server/local-server.mjs", "utf8");

test("Next Step brand returns to home without ending the session", () => {
  assert.match(source, /href="#home"/);
  assert.match(source, /\.brand'\)\?\.addEventListener\('click',event=>\{event\.preventDefault\(\);go\('home'\);\}\)/);
  assert.doesNotMatch(source, /class="brand" href="#landing"/);
});

test("3rd revision keeps preparation actions in saved jobs only", () => {
  assert.match(source, /prepare&&item\.coachReady/);
  assert.match(source, /postingCard\(x,\{save:false,prepare:true\}\)/);
});

test("3rd revision exposes working recommendation modes", () => {
  assert.match(source, /나에게 맞는 직무 찾기/);
  assert.match(source, /목표 직무와 비교하기/);
  assert.match(source, /data-recommend-mode/);
  assert.doesNotMatch(source, /역방향 추천|목표 직무 기준/);
});

test("3rd revision uses consistent coach navigation and recruiter wording", () => {
  assert.match(source, /AI 코치로 돌아가기/);
  assert.match(source, /AI 채용담당자에게 심사받기/);
  assert.match(interview, /class="session-id back-link"/);
});

test("experience categories switch independently and retain their drafts", () => {
  assert.match(source, /data-experience-category/);
  assert.match(source, /experienceInputs/);
  assert.match(source, /certificate:\{label:"자격증"/);
  assert.match(source, /activity:\{label:"대외활동"/);
  assert.match(source, /project:\{label:"수업·프로젝트"/);
  assert.doesNotMatch(source, /공공데이터 30만 행/);
});

test("recommendation keeps the existing request contract", () => {
  assert.match(source, /requestRecommendation\(text\)/);
});

test("coach quick actions share centered layout styles", () => {
  assert.match(styles, /\.quick-action\{display:flex;align-items:center;justify-content:center;min-height:48px/);
});

test("interview navigation preserves postingId and chooses an interview mode", () => {
  assert.match(source, /data-interview-mode="text"/);
  assert.match(source, /data-interview-mode="video"/);
  assert.doesNotMatch(source, /href="#interview-preview" data-interview/);
  assert.match(source, /new URL\('\/index\.html',window\.location\.origin\)/);
  assert.match(source, /url\.searchParams\.set\('postingId',job\.postingId\)/);
  assert.match(source, /url\.searchParams\.set\('mode',button\.dataset\.interviewMode\)/);
  assert.match(previewBuilder, /openInterview\(job\)/);
  assert.match(previewBuilder, /previewDefinitionIndex/);
  assert.match(previewBuilder, /previewDefinitionIndex > previewHandlerIndex/);
});

test("standalone embeds the whole interview entry instead of a shortened preview", () => {
  assert.match(previewBuilder, /read\("dist\/index\.html"\)/);
  assert.match(previewBuilder, /read\("dist\/app\.js"\)/);
  assert.match(previewBuilder, /interview-preview-frame/);
  assert.match(previewBuilder, /\.srcdoc = buildDoc\(job\)/);
  assert.match(previewBuilder, /asScriptSafeLiteral/);
  assert.doesNotMatch(previewBuilder, /Standalone UI preview/);
  assert.doesNotMatch(previewBuilder, /interview-preview-camera/);
});

test("standalone builder never lets replacement tokens corrupt embedded code", () => {
  // String.replace() would interpret $& inside a replacement string.
  assert.match(previewBuilder, /const insert = \(value\) => \(\) => value;/);
  const stringReplacements = previewBuilder.match(/\.replace\([^\n]*?,\s*`/g) || [];
  assert.equal(stringReplacements.length, 0, "every replacement must use the function form");
  assert.doesNotMatch(previewBuilder, /\.test\(url\)/);
  assert.match(previewBuilder, /url\.includes\("\/api\/v1\/job-contexts\/"\)/);
});

test("interview entry offers text and server-processed video interview", () => {
  assert.match(interview, /id="camera"/);
  assert.match(interview, /id="enable-camera"/);
  assert.match(interview, /id="record-button"/);
  assert.match(interview, /id="recording-playback"/);
  assert.match(interview, /id="landmark-overlay"/);
  assert.match(interview, /id="transcript-input"/);
  assert.match(interview, /id="text-answer-input"/);
  assert.match(interview, /id="submit-text-answer"/);
  assert.match(interviewApp, /function setInterviewMode/);
  assert.match(interviewApp, /function submitTextInterview/);
  assert.match(interviewApp, /\/api\/v1\/interview\/process/);
  assert.doesNotMatch(interviewApp, /cdn\.jsdelivr\.net\/npm\/@mediapipe/);
  assert.match(interviewApp, /CareerCoachAPI\.evaluateInterview/);
  // standalone posting context only
  assert.match(interviewApp, /function currentPostingId\(\)/);
  assert.match(interviewApp, /window\.NEXT_STEP_POSTING_ID/);
  assert.match(interview, /id="practice-job"/);
});

test("home keeps the two priority cards together and opens calendar as a modal", () => {
  assert.match(source, /class="home-priority-cards"/);
  assert.match(source, /id="open-calendar"/);
  assert.match(source, /class="modal calendar-modal"/);
  assert.match(source, /id="close-calendar"/);
  assert.match(source, /data-calendar-month/);
  assert.match(source, /data-calendar-day/);
  assert.doesNotMatch(source, /<h2>통합 캘린더<\/h2>.*<div class="mini-calendar">/s);
  assert.match(source, /class="panel priority-card next-step-card"/);
  assert.match(source, /class="panel priority-card todo-summary-card"/);
  assert.match(source, /준비 이어가기/);
  assert.match(source, /캘린더 보기 →/);
  assert.doesNotMatch(source, /todo-arrow|클릭해서 통합 캘린더 보기/);
  assert.match(styles, /grid-template-rows:auto minmax\(84px,1fr\) 24px auto/);
  assert.match(styles, /button\.calendar-entry\{margin:0;padding:0;border:0;background:none/);
});

test("home priority cards keep a 70:30 ratio in one white card system", () => {
  assert.match(styles, /\.home-priority-cards\{display:grid;grid-template-columns:minmax\(0,2\.3fr\) minmax\(0,1fr\)/);
  assert.doesNotMatch(styles, /\.home-priority-cards\{display:grid;grid-template-columns:1fr 1fr/);
  assert.match(styles, /\.home-priority-cards \.priority-card\{background:#fff\}/);
  assert.match(styles, /\.next-step-card\{background:linear-gradient\(150deg,#fdfeff,#f7fbff\)\}/);
  assert.match(styles, /\.priority-card-meta/);
});

test("NEXT STEP proposes a concrete action and never invents fit or progress", () => {
  assert.match(source, /function focusJob\(\)/);
  assert.match(source, /function jobProgress\(job\)/);
  assert.match(source, /function jobFit\(job\)/);
  assert.match(source, /if\(!list\.length\) return null/);
  assert.match(source, /Number\.isFinite\(Number\(value\)\)\?Math\.round\(Number\(value\)\):null/);
  assert.match(source, /fit===null\?"":`적합도 \$\{fit\}%`/);
  assert.match(source, /progress===null\?"":`진행률 \$\{progress\}%`/);
  assert.match(source, /next-step-target/);
  assert.match(source, /next-step-action/);
  assert.match(source, /next-step-reason/);
  assert.match(source, /class="calendar-entry" type="button" \$\{focus\?'data-focus'/);
  assert.match(source, /준비 이어가기 →/);
  assert.doesNotMatch(source, /class="button primary" \$\{focus/);
});

test("posting card shows the three states the server data actually produces", () => {
  // local-server.mjs: postingId is null when no JD context matched;
  // coachReady additionally requires requiredSkills AND responsibilities.
  assert.match(source, /AI 코치 준비 완료/);
  assert.match(source, /JD 상세 없음/);
  assert.match(source, /직무 정보 미연결/);
  assert.match(source, /모집 일정/);
  assert.match(server, /startTime: item\.empWantedStdtTime/);
  assert.match(server, /startDate: ymd\(item\.empWantedStdt\)/);
  assert.match(source, /prepare&&!item\.coachReady\?`<p class="card-note">/);
  assert.match(styles, /\.posting-card \.card-note/);
});

test("interview entry loads the Korean webfont its stylesheet asks for", () => {
  assert.match(interview, /fonts\.googleapis\.com\/css2\?family=Noto\+Sans\+KR/);
  // and a Hangul-capable system font so the page never falls back to tofu offline
  for (const declaration of styles2.match(/font-family:[^};]*/g) || []) {
    assert.match(declaration, /Malgun Gothic|Noto Sans CJK KR/, `no Hangul fallback in: ${declaration}`);
  }
});

test("server decodes python stdout as UTF-8 on every bridge", () => {
  // Buffer concatenation split a 3-byte Hangul character across chunks, and on
  // Windows python emits the ANSI codepage unless PYTHONIOENCODING is set.
  const spawns = server.match(/child\.stdout\.setEncoding\("utf8"\)/g) || [];
  assert.equal(spawns.length, 3);
  const envs = server.match(/PYTHONIOENCODING: "utf-8"/g) || [];
  assert.equal(envs.length, 3);
  assert.match(server, /child\.stdin\.end\(JSON\.stringify\(input\), "utf8"\)/);
  assert.match(server, /"\.json": "application\/json; charset=utf-8"/);
});

test("save button never fails silently on postings without a job context", () => {
  // server/local-server.mjs: postingId is null when no JD context matched,
  // so findPosting() returns undefined and the old handler threw on item.postingId.
  assert.match(source, /if\(!item\)return toast\(/);
  assert.match(source, /직무 상세 정보가 아직 연결되지 않아 담아둘 수 없어요/);
  assert.doesNotMatch(source, /addEventListener\('click',\(\)=>\{if\(!canPersist\(\)\)return; const items=savedItems\(\)/);
});

test("today card shows real dated schedule or an empty state", () => {
  assert.match(source, /function todayItems\(\)/);
  assert.match(source, /dateKey\(date\)===key/);
  assert.match(source, /todo-empty/);
  assert.match(source, /오늘 예정된 준비 일정이 없어요/);
  assert.match(source, /\(\$\{job\.companyName\}\) /);
  assert.match(source, /state\.selected=focusJob\(\)/);
});

test("calendar uses saved deadlines and only dated preparation tasks", () => {
  assert.match(source, /saved\.forEach\(job=>add\(parseLocalDate\(job\.deadline\),`\$\{job\.companyName\} 마감`/);
  assert.match(source, /task\?\.date\|\|task\?\.dueDate\|\|task\?\.scheduledDate/);
  assert.match(source, /match\(\/D-\(\\d\+\)\/i\)/);
  assert.match(source, /calendar\.events\.get\(day\)/);
  assert.match(styles, /\.calendar-date/);
});

test("live postings use the Korea date instead of UTC around midnight", () => {
  assert.match(server, /timeZone: "Asia\/Seoul"/);
  assert.match(server, /url\.searchParams\.get\("asOf"\) \|\| seoulDate\(\)/);
  assert.doesNotMatch(server, /url\.searchParams\.get\("asOf"\) \|\| new Date\(\)\.toISOString\(\)\.slice\(0, 10\)/);
});

test("coach keeps consultation as chat history without replacing the checklist", () => {
  assert.match(source, /history\.push\(\{role:'user',content:message\},\{role:'assistant',content:out\.answer\}\);saveHistory/);
  assert.match(source, /if\(mode==='timeline'\)\{const next=/);
  assert.match(source, /준비 일정 짜기 결과만 여기에 반영돼요/);
});
