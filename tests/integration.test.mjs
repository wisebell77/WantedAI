import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";

const port = 4199;
const base = `http://127.0.0.1:${port}`;
let server;
let live;
let jobs;
let coachJob;

before(async () => {
  server = spawn(process.execPath, ["server/local-server.mjs"], {
    env: { ...process.env, PORT: String(port) }, stdio: ["ignore", "pipe", "pipe"]
  });
  for (let i = 0; i < 40; i += 1) {
    try { if ((await fetch(`${base}/api/v1/agent/status`)).ok) return; } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("test server did not start");
});
after(() => server?.kill("SIGTERM"));

test("1. landing is served", async () => assert.equal((await fetch(base)).status, 200));
test("2. landing uses Next Step name", async () => assert.match(await (await fetch(base)).text(), /Next Step/));
test("3. campus asset is served", async () => assert.equal((await fetch(`${base}/assets/campus-start.png`)).status, 200));
test("4. bundled frontend is served", async () => assert.equal((await fetch(`${base}/next-step.js`)).status, 200));
test("5. frontend contains no WantedAI branding", async () => assert.doesNotMatch(await readFile("dist/next-step.html", "utf8"), /WantedAI/i));
test("6. live postings endpoint responds", async () => { const r=await fetch(`${base}/api/v1/live-postings`); assert.equal(r.status,200); live=await r.json(); });
test("7. live postings use real corpus", () => assert.ok(live.total > 200));
test("8. open postings are date filtered", () => assert.ok(live.items.every((x) => !x.deadline || x.deadline >= "2026-09-17")));
test("9. live postings include coach-ready matches", () => assert.ok(live.coachReady > 0));
test("10. live posting contract is complete", () => { const x=live.items[0]; for(const k of ["companyName","positionTitle","deadline","sourceUrl","coachReady"]) assert.ok(k in x); });
test("11. job contexts endpoint responds", async () => { const r=await fetch(`${base}/api/v1/job-contexts`); assert.equal(r.status,200); jobs=await r.json(); });
test("12. job contexts use actual role data", () => assert.ok(jobs.total >= 80));
test("13. job context families are populated", () => assert.ok(jobs.families.length > 5));
test("14. coach-ready posting resolves to detail", async () => { coachJob=live.items.find((x)=>x.coachReady); const r=await fetch(`${base}/api/v1/job-contexts/${coachJob.postingId}`); assert.equal(r.status,200); const x=await r.json(); assert.equal(x.postingId,coachJob.postingId); });
test("14a. interview entry is served with selected posting context", async () => { const r=await fetch(`${base}/index.html?postingId=${encodeURIComponent(coachJob.postingId)}`); assert.equal(r.status,200); assert.match(await r.text(), /Next Step · 면접 연습/); });
test("15. unknown job returns 404", async () => assert.equal((await fetch(`${base}/api/v1/job-contexts/not-found`)).status,404));
test("16. agent status never exposes API key", async () => { const x=await (await fetch(`${base}/api/v1/agent/status`)).json(); assert.ok("configured" in x); assert.equal("apiKey" in x,false); });
test("17. posting persona is generated", async () => { const r=await fetch(`${base}/api/v1/agent/interview-persona?postingId=${coachJob.postingId}`); assert.equal(r.status,200); const x=await r.json(); assert.ok(x.items.length>0); assert.ok(x.questions.length>0); });
test("18. invalid persona posting is rejected", async () => assert.equal((await fetch(`${base}/api/v1/agent/interview-persona?postingId=nope`)).status,422));
test("19. essay review uses posting persona", async () => { const r=await fetch(`${base}/api/v1/essays/review`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({postingId:coachJob.postingId,sections:[{question:"경험",answer:"저는 팀 프로젝트를 직접 분석하고 결과를 20% 개선했습니다."}],experiences:["데이터 분석 프로젝트"]})}); assert.equal(r.status,200); const x=await r.json(); assert.ok(x.items.length>0); assert.ok(["heuristic","llm"].includes(x.generated_by)); });
test("20. empty essay is rejected", async () => assert.equal((await fetch(`${base}/api/v1/essays/review`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({postingId:coachJob.postingId,sections:[]})})).status,422));
test("21. recommendation outage is explicit, never mocked", async () => { const r=await fetch(`${base}/api/recommend`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({texts:["데이터 분석 경험"]})}); assert.equal(r.status,503); assert.equal((await r.json()).error,"RECOMMENDATION_ENGINE_UNAVAILABLE"); });
