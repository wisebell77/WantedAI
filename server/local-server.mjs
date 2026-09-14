import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { runCareerCoachAgent } from "./upstage-career-coach.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = join(root, "dist");
const dataDir = join(root, "Overlap_데이터_20260911", "data");

try {
  const raw = await readFile(join(root, ".env"), "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (match && !process.env[match[1]]) process.env[match[1]] = match[2].replace(/^['"]|['"]$/g, "");
  }
} catch {}

const roles = JSON.parse(await readFile(join(dataDir, "roles.json"), "utf8"));
const postings = JSON.parse(await readFile(join(dataDir, "jd_tiered.json"), "utf8"));
const postingByUrl = new Map(postings.map((item) => [item.url, item]));
function roleExcerpt(text = "", roleName = "") {
  const index = roleName ? text.indexOf(roleName) : -1;
  const start = index >= 0 ? Math.max(0, index - 120) : 0;
  return text.slice(start, start + 2200);
}
const contexts = roles.map((role, index) => {
  const posting = postingByUrl.get(role.url) || {};
  return {
    postingId: `role-${index + 1}`,
    companyName: role.corp,
    positionTitle: role.role || role.post_title,
    postingTitle: role.post_title,
    jobFamily: role.job,
    tier: role.post_tier,
    responsibilities: posting.clean ? [roleExcerpt(posting.clean, role.role)] : [],
    requiredSkills: role.techs || [],
    preferredSkills: [],
    sourceUrl: role.url,
    sourceType: role.src,
    sourceUpdatedAt: "2026-09-11"
  };
});

const mime = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8" };
const sendJson = (res, status, body) => { res.writeHead(status, { "Content-Type": mime[".json"] }); res.end(JSON.stringify(body)); };
async function readJson(req) { const chunks = []; for await (const chunk of req) chunks.push(chunk); return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"); }

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    if (req.method === "GET" && url.pathname === "/api/v1/agent/status") {
      return sendJson(res, 200, {
        configured: Boolean(process.env.UPSTAGE_API_KEY),
        fastModel: process.env.UPSTAGE_FAST_MODEL || "solar-mini",
        coachModel: process.env.UPSTAGE_COACH_MODEL || "solar-pro4"
      });
    }
    if (req.method === "GET" && url.pathname === "/api/v1/job-contexts") {
      const job = url.searchParams.get("job");
      const items = contexts.filter((item) => !job || item.jobFamily === job).sort((a, b) => a.tier.localeCompare(b.tier)).slice(0, 80).map(({ responsibilities, ...summary }) => summary);
      return sendJson(res, 200, { items, total: items.length, families: [...new Set(contexts.map((item) => item.jobFamily))].sort(), source: "Overlap_데이터_20260911" });
    }
    if (req.method === "GET" && url.pathname.startsWith("/api/v1/job-contexts/")) {
      const item = contexts.find((row) => row.postingId === decodeURIComponent(url.pathname.split("/").pop()));
      return item ? sendJson(res, 200, item) : sendJson(res, 404, { error: "JOB_CONTEXT_NOT_FOUND" });
    }
    if (req.method === "POST" && url.pathname === "/api/v1/agent/chat") {
      if (!process.env.UPSTAGE_API_KEY) return sendJson(res, 503, { error: "UPSTAGE_API_KEY_MISSING" });
      const input = await readJson(req);
      const canonicalJob = contexts.find((row) => row.postingId === input.postingId);
      if (!canonicalJob) return sendJson(res, 422, { error: "VALID_POSTING_ID_REQUIRED" });
      const result = await runCareerCoachAgent({ ...input, jobContext: canonicalJob }, {
        apiKey: process.env.UPSTAGE_API_KEY,
        fastModel: process.env.UPSTAGE_FAST_MODEL || "solar-mini",
        coachModel: process.env.UPSTAGE_COACH_MODEL || "solar-pro4"
      });
      return sendJson(res, 200, result);
    }
    const requested = url.pathname === "/" ? "/coach.html" : url.pathname;
    const filePath = normalize(join(dist, requested));
    if (!filePath.startsWith(dist)) return sendJson(res, 403, { error: "FORBIDDEN" });
    const file = await readFile(filePath);
    res.writeHead(200, { "Content-Type": mime[extname(filePath)] || "application/octet-stream" });
    res.end(file);
  } catch (error) {
    if (error.code === "ENOENT") return sendJson(res, 404, { error: "NOT_FOUND" });
    console.error(error);
    sendJson(res, 500, { error: "INTERNAL_ERROR", message: error.message });
  }
});

server.listen(Number(process.env.PORT || 4173), "127.0.0.1", () => console.log(`Overlap Career Coach: http://127.0.0.1:${process.env.PORT || 4173}`));
