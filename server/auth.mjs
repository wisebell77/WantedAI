// 구글 로그인 (OAuth 2.0 authorization code).
//
// **세션을 서버에 저장하지 않는다.** 서명 쿠키 하나로 끝낸다 — 세션 테이블도,
// 만료 청소도, 재배포 때 전부 로그아웃되는 문제도 없다. 담는 건 sub·email·name 뿐이고
// 개인 이력은 쿠키에 넣지 않는다(DB 에 있고, 쿠키는 4KB 제한이 있다).
//
// 외부 패키지를 쓰지 않는다. node:crypto 와 fetch 면 된다.
//
// 필요한 환경변수
//   GOOGLE_CLIENT_ID · GOOGLE_CLIENT_SECRET   Google Cloud Console
//   SESSION_SECRET                            임의의 긴 문자열. 바뀌면 전원 로그아웃된다
//   PUBLIC_BASE_URL                           https://nextstep.up.railway.app
//                                             (없으면 요청 헤더로 추정하지만 명시가 안전하다)

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SESSION_COOKIE = "ns_session";
const STATE_COOKIE = "ns_oauth_state";
const MAX_AGE = 60 * 60 * 24 * 30;        // 30일

export function configured() {
  return Boolean(process.env.GOOGLE_CLIENT_ID
                 && process.env.GOOGLE_CLIENT_SECRET
                 && process.env.SESSION_SECRET);
}

// ── 쿠키

function parseCookies(req) {
  const out = {};
  for (const part of (req.headers.cookie || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

function setCookie(res, name, value, { maxAge, secure }) {
  const bits = [`${name}=${encodeURIComponent(value)}`, "Path=/", "HttpOnly", "SameSite=Lax"];
  if (maxAge === 0) bits.push("Max-Age=0");
  else if (maxAge) bits.push(`Max-Age=${maxAge}`);
  if (secure) bits.push("Secure");
  const prev = res.getHeader("Set-Cookie");
  res.setHeader("Set-Cookie", prev ? [].concat(prev, bits.join("; ")) : bits.join("; "));
}

// ── 서명 (HMAC-SHA256)

const b64 = (buf) => Buffer.from(buf).toString("base64url");

function sign(payload) {
  const body = b64(JSON.stringify(payload));
  const mac = createHmac("sha256", process.env.SESSION_SECRET).update(body).digest("base64url");
  return `${body}.${mac}`;
}

function verify(token) {
  const dot = String(token || "").lastIndexOf(".");
  if (dot < 1) return null;
  const body = token.slice(0, dot), mac = token.slice(dot + 1);
  const want = createHmac("sha256", process.env.SESSION_SECRET).update(body).digest("base64url");
  // 길이가 다르면 timingSafeEqual 이 던진다. 먼저 걸러 낸다.
  if (mac.length !== want.length) return null;
  if (!timingSafeEqual(Buffer.from(mac), Buffer.from(want))) return null;
  try {
    const data = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
    if (!data.exp || data.exp < Math.floor(Date.now() / 1000)) return null;   // 만료
    return data;
  } catch { return null; }
}

// ── 주소

function baseUrl(req) {
  if (process.env.PUBLIC_BASE_URL) return process.env.PUBLIC_BASE_URL.replace(/\/+$/, "");
  // Railway 는 프록시 뒤라 x-forwarded-* 를 봐야 https 를 안다.
  const proto = req.headers["x-forwarded-proto"] || "http";
  const host = req.headers["x-forwarded-host"] || req.headers.host || "127.0.0.1:4173";
  return `${proto}://${host}`;
}

const redirectUri = (req) => `${baseUrl(req)}/auth/google/callback`;
const isSecure = (req) => baseUrl(req).startsWith("https:");

/**
 * 로그인 뒤 돌아갈 곳. **우리 사이트 안이어야 한다.**
 * 안 막으면 /auth/google?next=https://남의사이트 로 열린 리디렉션이 된다 —
 * 우리 도메인 링크를 눌렀는데 로그인 직후 남의 로그인 화면에 떨어지는 수법이다.
 * 슬래시로 시작해도 두 번째 글자가 슬래시나 역슬래시면 브라우저는 그것을 다른
 * 호스트 주소로 읽는다. 그래서 첫 두 글자를 같이 본다.
 */
function safeNext(value) {
  const v = String(value || "");
  // 문자 코드로 본다. 정규식에 역슬래시를 넣으면 옮겨 적다 한 겹 벗겨지기 쉽다.
  //   47 = 슬래시,  92 = 역슬래시
  // 첫 글자가 슬래시가 아니면 절대 주소이고, 두 번째까지 슬래시/역슬래시면
  // "//남의사이트" 처럼 브라우저가 다른 호스트로 읽는다. 둘 다 거른다.
  const second = v.charCodeAt(1);
  if (v.charCodeAt(0) !== 47 || second === 47 || second === 92) return "/";
  return v;
}

// ── 흐름

/** 구글 동의 화면으로 보낸다. state 로 CSRF 를 막는다. */
export function begin(req, res) {
  const state = randomBytes(16).toString("base64url");
  const next = safeNext(new URL(req.url, "http://x").searchParams.get("next"));
  setCookie(res, STATE_COOKIE, sign({ state, next, exp: Math.floor(Date.now() / 1000) + 600 }),
            { maxAge: 600, secure: isSecure(req) });
  const u = new URL(AUTH_URL);
  u.searchParams.set("client_id", process.env.GOOGLE_CLIENT_ID);
  u.searchParams.set("redirect_uri", redirectUri(req));
  u.searchParams.set("response_type", "code");
  u.searchParams.set("scope", "openid email profile");   // 기본 범위만. 심사 없이 게시된다
  u.searchParams.set("state", state);
  u.searchParams.set("prompt", "select_account");
  res.writeHead(302, { Location: u.toString() });
  res.end();
}

/**
 * 구글이 돌려보낸 code 를 토큰으로 바꾸고 세션 쿠키를 심는다.
 *
 * id_token 의 서명은 따로 검증하지 않는다 — 우리 client_secret 으로 구글 토큰
 * 엔드포인트에 **직접** TLS 로 요청해 받은 응답이라 중간에 낄 수 없다.
 * (구글 문서도 서버 흐름에서는 검증이 필요 없다고 안내한다.)
 */
export async function callback(req, res, onUser) {
  const url = new URL(req.url, "http://x");
  const err = url.searchParams.get("error");
  if (err) return fail(res, `구글 인증이 취소되었습니다 (${err})`);

  const saved = verify(parseCookies(req)[STATE_COOKIE]);
  const state = url.searchParams.get("state");
  if (!saved || !state || saved.state !== state) return fail(res, "인증 상태가 맞지 않습니다. 다시 시도해 주세요.");
  setCookie(res, STATE_COOKIE, "", { maxAge: 0, secure: isSecure(req) });

  const code = url.searchParams.get("code");
  if (!code) return fail(res, "인증 코드가 없습니다.");

  const body = new URLSearchParams({
    code, client_id: process.env.GOOGLE_CLIENT_ID,
    client_secret: process.env.GOOGLE_CLIENT_SECRET,
    redirect_uri: redirectUri(req), grant_type: "authorization_code",
  });
  const r = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!r.ok) return fail(res, `토큰 교환 실패 (${r.status}) ${(await r.text()).slice(0, 160)}`);

  const { id_token } = await r.json();
  if (!id_token) return fail(res, "id_token 이 없습니다.");
  const claims = JSON.parse(Buffer.from(id_token.split(".")[1], "base64url").toString("utf8"));
  if (!claims.sub) return fail(res, "sub 이 없습니다.");

  const user = await onUser({ sub: claims.sub, email: claims.email, name: claims.name });
  setCookie(res, SESSION_COOKIE,
            sign({ uid: user.id, sub: claims.sub, email: user.email, name: user.name,
                   exp: Math.floor(Date.now() / 1000) + MAX_AGE }),
            { maxAge: MAX_AGE, secure: isSecure(req) });
  res.writeHead(302, { Location: saved.next || "/" });
  res.end();
}

export function logout(req, res) {
  setCookie(res, SESSION_COOKIE, "", { maxAge: 0, secure: isSecure(req) });
  res.writeHead(302, { Location: "/" });
  res.end();
}

/** 세션이 있으면 {uid, sub, email, name}, 없으면 null. */
export function session(req) {
  if (!configured()) return null;
  return verify(parseCookies(req)[SESSION_COOKIE]);
}

function fail(res, message) {
  // 실패를 화면으로 돌려보낸다. 사용자에게 JSON 을 보여 줄 이유가 없다.
  res.writeHead(302, { Location: `/?auth_error=${encodeURIComponent(message)}` });
  res.end();
}
