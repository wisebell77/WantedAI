// 사용자 데이터 저장소 (Postgres).
//
// **없어도 서비스는 돈다.** DATABASE_URL 이 없거나 연결이 안 되면 available() 이
// false 를 돌려주고, 로그인·저장 기능만 503 이 된다. 진단·공고·코치는 그대로다.
// 심사 기간에 DB 하나 때문에 전체가 죽는 건 말이 안 된다.
//
// 세션은 여기 안 넣는다. 서명 쿠키(auth.mjs)라 세션 테이블이 필요 없다 —
// 테이블이 하나 줄고, 만료 청소도 필요 없다.
//
// pg 를 **정적 import 하지 않는다.** 최상단에서 불러오면 컨테이너에 모듈이
// 없을 때 ERR_MODULE_NOT_FOUND 로 서버가 기동조차 못 한다 — DB 부가 기능
// 하나 때문에 진단·공고·코치가 전부 죽는다. 늦게 불러오고, 실패하면 삼킨다.

let pgMod = null;
let pool = null;
let ready = null;        // 스키마 준비 Promise. 여러 요청이 동시에 와도 한 번만 돈다.
let lastError = null;

export function configured() {
  return Boolean(process.env.DATABASE_URL);
}

async function loadPg() {
  if (pgMod) return pgMod;
  try {
    pgMod = (await import("pg")).default;
  } catch (e) {
    lastError = new Error(`pg 모듈을 못 불러왔다 (npm 설치 누락?): ${e.message}`);
    return null;
  }
  return pgMod;
}

/** 사설망인가 — Railway 내부 DNS, localhost, 루프백. */
function isPrivateHost(url) {
  let raw = null;
  try { raw = new URL(url).hostname; } catch { return false; }
  const host = raw.startsWith("[") ? raw.slice(1, -1) : raw;   // [::1] 의 대괄호
  return host.endsWith(".railway.internal")
      || host === "localhost" || host === "127.0.0.1" || host === "::1";
}

async function getPool() {
  if (pool) return pool;
  if (!configured()) return null;
  const pg = await loadPg();
  if (!pg) return null;
  pool = new pg.Pool({
    connectionString: process.env.DATABASE_URL,
    // 사설망(Railway 내부망 · 로컬)은 SSL 을 안 받는다. 여기에 ssl 을 주면 pg 가
    // "The server does not support SSL connections" 로 죽는다. 공개망으로 붙을
    // 때만 켜고, 그때도 자체 서명 인증서라 검증은 끈다.
    ssl: isPrivateHost(process.env.DATABASE_URL) ? false : { rejectUnauthorized: false },
    max: 4,                       // 앱 컨테이너 하나뿐이라 넉넉하다
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 8_000,
  });
  pool.on("error", (e) => { lastError = e; });   // 유휴 연결이 끊겨도 프로세스를 죽이지 않는다
  return pool;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id          BIGSERIAL PRIMARY KEY,
  google_sub  TEXT UNIQUE NOT NULL,
  email       TEXT,
  name        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 프로필·초안은 사용자당 하나의 문서로 둔다. 필드가 자주 바뀌는 쪽이라
-- 컬럼을 쪼개면 마이그레이션이 계속 붙는다.
CREATE TABLE IF NOT EXISTS profiles (
  user_id     BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  data        JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS saved_postings (
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  posting_id  TEXT   NOT NULL,
  data        JSONB  NOT NULL DEFAULT '{}'::jsonb,
  saved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, posting_id)
);
CREATE TABLE IF NOT EXISTS drafts (
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  posting_id  TEXT   NOT NULL,
  data        JSONB  NOT NULL DEFAULT '{}'::jsonb,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, posting_id)
);
`;

async function ensureSchema() {
  const p = await getPool();
  if (!p) throw new Error(lastErrorMessage() || "DATABASE_URL_MISSING");
  await p.query(SCHEMA);
  return true;
}

/** 준비됐는지. 실패해도 예외를 던지지 않는다 — 호출부가 503 으로 처리한다. */
export async function available() {
  if (!configured()) return false;
  if (!ready) {
    ready = ensureSchema().catch((e) => {
      lastError = e;
      ready = null;                 // 다음 요청에서 다시 시도한다
      return false;
    });
  }
  return Boolean(await ready);
}

export function lastErrorMessage() {
  return lastError ? String(lastError.message || lastError) : "";
}

/**
 * JSONB 파라미터. **반드시 거쳐야 한다.**
 * pg 는 JS 객체는 JSON 으로 보내지만 **배열은 Postgres 배열 리터럴**로 보낸다.
 * 자소서 초안(sections)처럼 최상위가 배열이면 jsonb 컬럼에서
 * "invalid input syntax for type json" 으로 죽는다.
 */
const asJson = (v) => JSON.stringify(v ?? {});

async function q(text, params) {
  const p = await getPool();
  if (!p) throw new Error(lastErrorMessage() || "DATABASE_URL_MISSING");
  return p.query(text, params);
}

/** 구글 sub 로 사용자를 찾거나 만든다. 이메일·이름은 매번 갱신한다(바뀔 수 있다). */
export async function upsertUser({ sub, email, name }) {
  const { rows } = await q(
    `INSERT INTO users (google_sub, email, name)
          VALUES ($1, $2, $3)
     ON CONFLICT (google_sub) DO UPDATE
        SET email = EXCLUDED.email, name = EXCLUDED.name, last_seen = now()
     RETURNING id, google_sub, email, name`,
    [sub, email || null, name || null]);
  return rows[0];
}

export async function getProfile(userId) {
  const { rows } = await q(`SELECT data FROM profiles WHERE user_id = $1`, [userId]);
  return rows[0]?.data ?? null;
}

export async function putProfile(userId, data) {
  await q(
    `INSERT INTO profiles (user_id, data) VALUES ($1, $2)
     ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()`,
    [userId, asJson(data)]);
}

export async function listSaved(userId) {
  const { rows } = await q(
    `SELECT posting_id, data, saved_at FROM saved_postings
      WHERE user_id = $1 ORDER BY saved_at DESC`, [userId]);
  return rows.map((r) => ({ postingId: r.posting_id, ...r.data, savedAt: r.saved_at }));
}

export async function addSaved(userId, postingId, data) {
  await q(
    `INSERT INTO saved_postings (user_id, posting_id, data) VALUES ($1, $2, $3)
     ON CONFLICT (user_id, posting_id) DO UPDATE SET data = EXCLUDED.data`,
    [userId, String(postingId), asJson(data)]);
}

export async function removeSaved(userId, postingId) {
  await q(`DELETE FROM saved_postings WHERE user_id = $1 AND posting_id = $2`,
          [userId, String(postingId)]);
}

export async function listDrafts(userId) {
  const { rows } = await q(
    `SELECT posting_id, data, updated_at FROM drafts WHERE user_id = $1`, [userId]);
  return Object.fromEntries(rows.map((r) => [r.posting_id, r.data]));
}

export async function putDraft(userId, postingId, data) {
  await q(
    `INSERT INTO drafts (user_id, posting_id, data) VALUES ($1, $2, $3)
     ON CONFLICT (user_id, posting_id) DO UPDATE
        SET data = EXCLUDED.data, updated_at = now()`,
    [userId, String(postingId), asJson(data)]);
}

/** 사용자가 지우기를 요청하면 전부 지운다. ON DELETE CASCADE 가 나머지를 따라 지운다. */
export async function deleteUser(userId) {
  await q(`DELETE FROM users WHERE id = $1`, [userId]);
}
