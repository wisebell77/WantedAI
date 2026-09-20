// 사용자 데이터 저장소 (Postgres).
//
// **없어도 서비스는 돈다.** DATABASE_URL 이 없거나 연결이 안 되면 available() 이
// false 를 돌려주고, 로그인·저장 기능만 503 이 된다. 진단·공고·코치는 그대로다.
// 심사 기간에 DB 하나 때문에 전체가 죽는 건 말이 안 된다.
//
// 세션은 여기 안 넣는다. 서명 쿠키(auth.mjs)라 세션 테이블이 필요 없다 —
// 테이블이 하나 줄고, 만료 청소도 필요 없다.

import pg from "pg";

let pool = null;
let ready = null;        // 스키마 준비 Promise. 여러 요청이 동시에 와도 한 번만 돈다.
let lastError = null;

export function configured() {
  return Boolean(process.env.DATABASE_URL);
}

function getPool() {
  if (pool) return pool;
  if (!configured()) return null;
  pool = new pg.Pool({
    connectionString: process.env.DATABASE_URL,
    // Railway 내부망은 인증서를 따로 주지 않는다. 외부에서 붙을 때만 SSL 이 필요하고
    // 그때도 자체 서명이라 검증을 끈다.
    ssl: /\brailway\.internal\b/.test(process.env.DATABASE_URL)
      ? false : { rejectUnauthorized: false },
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
  const p = getPool();
  if (!p) throw new Error("DATABASE_URL_MISSING");
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

async function q(text, params) {
  const p = getPool();
  if (!p) throw new Error("DATABASE_URL_MISSING");
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
    [userId, data]);
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
    [userId, String(postingId), data || {}]);
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
    [userId, String(postingId), data || {}]);
}

/** 사용자가 지우기를 요청하면 전부 지운다. ON DELETE CASCADE 가 나머지를 따라 지운다. */
export async function deleteUser(userId) {
  await q(`DELETE FROM users WHERE id = $1`, [userId]);
}
