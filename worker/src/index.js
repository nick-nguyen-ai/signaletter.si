// SignaLetter API: passwordless sign-in, per-reader "My shares" watchlist, email signup stub.
// Storage:
//   Workers KV (binding WATCHLIST), eventually consistent, for data:
//     user:<email>        -> {"tickers":[...],"created":iso,"updated":iso,"tier"?:"basic"|"full"}
//     rl:<email>:<hour>   -> count (TTL 1h; sign-in email rate limit, best effort)
//     sub:<email>         -> {"lists":[...],"status":"pending"|"confirmed","updated":iso}
//     used:<nonce>        -> legacy (pre-Durable-Object) used-link markers; read only, expire by TTL
//   Durable Object AuthState (binding AUTH_STATE), one per account (named by SHA-256 of the email),
//   strongly consistent, for security state:
//     nonces  -> magic-link nonces consumed so far (atomic insert = each link redeems exactly once)
//     meta.sv -> session version; DELETE /me bumps it, which invalidates every earlier session and
//                every unused sign-in link for that email.
// Tokens are HMAC-SHA256 signed with AUTH_SECRET and carry the session version they were issued at.
import { DurableObject } from "cloudflare:workers";
import asx from "../../assets/data/asx-tickers.json";

const ALLOWED = new Map(asx.tickers.map((t) => [t.code, t.name]));
const LOGIN_TTL = 15 * 60; // magic link: 15 minutes
const SESSION_TTL = 30 * 24 * 3600; // session: 30 days
const CONFIRM_TTL = 3 * 24 * 3600; // subscribe confirmation: 3 days
const SIGNIN_PER_HOUR = 5;
const LISTS = ["markets", "ai"];
const enc = new TextEncoder();

// ---------- helpers ----------
const b64u = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64uText = (s) => b64u(enc.encode(s));
const unb64uText = (s) => {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
};
const now = () => Math.floor(Date.now() / 1000);
const nonce = () => b64u(crypto.getRandomValues(new Uint8Array(16)));

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}
async function sign(env, payload) {
  const body = b64uText(JSON.stringify(payload));
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(env.AUTH_SECRET), enc.encode(body));
  return `${body}.${b64u(sig)}`;
}
async function verify(env, token, purpose) {
  if (typeof token !== "string" || token.length > 2048) return null;
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  let sigBytes;
  try {
    sigBytes = Uint8Array.from(atob(sig.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
  const ok = await crypto.subtle.verify("HMAC", await hmacKey(env.AUTH_SECRET), sigBytes, enc.encode(body));
  if (!ok) return null;
  let p;
  try {
    p = JSON.parse(unb64uText(body));
  } catch {
    return null;
  }
  if (p.p !== purpose || typeof p.exp !== "number" || p.exp < now()) return null;
  return p;
}

// ---------- per-account auth state (Durable Object, SQLite storage) ----------
export class AuthState extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS nonces (n TEXT PRIMARY KEY, exp INTEGER NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v INTEGER NOT NULL)");
  }
  version() {
    const rows = this.sql.exec("SELECT v FROM meta WHERE k = 'sv'").toArray();
    return rows.length ? rows[0].v : 0;
  }
  // Redeem a magic link. The body is synchronous SQLite work inside one Durable Object, so two
  // concurrent calls for the same nonce are serialised: exactly one INSERT returns a row.
  async redeem(n, exp, v) {
    if ((v || 0) !== this.version()) return "revoked";
    this.sql.exec("DELETE FROM nonces WHERE exp < ?", now());
    const inserted = this.sql
      .exec("INSERT INTO nonces (n, exp) VALUES (?, ?) ON CONFLICT(n) DO NOTHING RETURNING n", n, exp)
      .toArray().length;
    if (inserted !== 1) return "used";
    if ((await this.ctx.storage.getAlarm()) === null) await this.ctx.storage.setAlarm((exp + 60) * 1000);
    return "ok";
  }
  // Account deletion: every session and sign-in link issued before now stops working.
  // Consumed nonces are kept (until they expire) so an already-used link can't be replayed.
  revoke() {
    const v = this.version() + 1;
    this.sql.exec("INSERT INTO meta (k, v) VALUES ('sv', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", v);
    return v;
  }
  async alarm() {
    this.sql.exec("DELETE FROM nonces WHERE exp < ?", now());
    const next = this.sql.exec("SELECT MIN(exp) AS e FROM nonces").toArray()[0].e;
    if (next) await this.ctx.storage.setAlarm((next + 60) * 1000);
  }
}
async function account(env, email) {
  const h = b64u(await crypto.subtle.digest("SHA-256", enc.encode(email)));
  return env.AUTH_STATE.get(env.AUTH_STATE.idFromName(h));
}

const EMAIL_RE = /^[^\s@<>()",;:]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$/;
const normEmail = (e) => (typeof e === "string" ? e.trim().toLowerCase() : "");
const validEmail = (e) => e.length <= 254 && EMAIL_RE.test(e);
const safeNext = (n) => (typeof n === "string" && /^\/(?!\/)[\w\-./#%?=&]*$/.test(n) && n.length < 300 ? n : "");
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function corsHeaders(env, req) {
  const origin = req.headers.get("Origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  const h = { Vary: "Origin" };
  if (allowed.includes(origin)) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS";
    h["Access-Control-Allow-Headers"] = "Authorization,Content-Type";
    h["Access-Control-Max-Age"] = "600";
  }
  return h;
}
const json = (env, req, data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...corsHeaders(env, req) },
  });
const html = (body, status = 200) =>
  new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SignaLetter</title><body style="font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;line-height:1.5">${body}</body>`,
    { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } },
  );

async function readJson(req) {
  if (!(req.headers.get("Content-Type") || "").includes("application/json")) return null;
  try {
    const t = await req.text();
    return t.length > 4096 ? null : JSON.parse(t);
  } catch {
    return null;
  }
}

async function sendEmail(env, { to, subject, text, htmlBody }) {
  if (!env.RESEND_API_KEY) {
    console.log(`[mock email] to=${to} subject=${JSON.stringify(subject)}\n${text}`);
    return { mocked: true };
  }
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env.FROM_EMAIL, to: [to], subject, text, html: htmlBody }),
  });
  if (!r.ok) {
    console.log(`resend error ${r.status}: ${await r.text()}`);
    throw new Error("email_failed");
  }
  return { mocked: false };
}

// Valid signature, not expired, and issued at the account's current session version.
// Sessions minted before versions existed carry no `v` and count as version 0, so they keep
// working until the account is deleted (or they expire).
async function session(env, req) {
  const m = (req.headers.get("Authorization") || "").match(/^Bearer (.+)$/);
  if (!m) return null;
  const p = await verify(env, m[1], "session");
  if (!p || typeof p.e !== "string") return null;
  if ((p.v || 0) !== (await (await account(env, p.e)).version())) return null;
  return p;
}

function cleanTickers(list, max) {
  if (!Array.isArray(list)) return { error: "tickers must be a list" };
  const out = [];
  for (const raw of list) {
    const t = String(raw || "").trim().toUpperCase().replace(/\.AX$/, "");
    if (!t) continue;
    if (!ALLOWED.has(t)) return { error: `${t} is not in the supported ASX list` };
    if (!out.includes(t)) out.push(t);
  }
  if (out.length > max) return { error: `Pick up to ${max} shares` };
  return { tickers: out };
}

// ---------- routes ----------
async function authRequest(env, req) {
  const body = await readJson(req);
  const email = normEmail(body && body.email);
  if (!validEmail(email)) return json(env, req, { ok: false, error: "Enter a valid email address." }, 400);
  const next = safeNext(body.next);
  const hour = Math.floor(now() / 3600);
  const rlKey = `rl:${email}:${hour}`;
  const count = parseInt((await env.WATCHLIST.get(rlKey)) || "0", 10);
  if (count >= SIGNIN_PER_HOUR)
    return json(env, req, { ok: false, error: "Too many sign-in emails. Try again in an hour." }, 429);
  await env.WATCHLIST.put(rlKey, String(count + 1), { expirationTtl: 3600 });

  const v = await (await account(env, email)).version();
  const token = await sign(env, { p: "login", e: email, v, exp: now() + LOGIN_TTL, n: nonce() });
  const url = new URL("/watchlist/", env.SITE_ORIGIN);
  url.searchParams.set("token", token);
  if (next) url.searchParams.set("next", next);
  const link = url.toString();
  const text = `Sign in to SignaLetter to track your own shares:\n\n${link}\n\nThis link works once and expires in 15 minutes. If you didn't ask for it, ignore this email.\n\nSignaLetter · https://signaletter.si`;
  const htmlBody = `<p>Sign in to SignaLetter to track your own shares:</p><p><a href="${escapeHtml(link)}">Sign in to SignaLetter</a></p><p>This link works once and expires in 15 minutes. If you didn't ask for it, ignore this email.</p><p>SignaLetter · <a href="https://signaletter.si">signaletter.si</a></p>`;
  let mocked;
  try {
    ({ mocked } = await sendEmail(env, { to: email, subject: "Your SignaLetter sign-in link", text, htmlBody }));
  } catch {
    return json(env, req, { ok: false, error: "We couldn't send the email. Try again shortly." }, 502);
  }
  const res = { ok: true };
  if (mocked && env.DEV_RETURN_LINK === "1") res.dev_link = link;
  return json(env, req, res);
}

async function authVerify(env, req) {
  const body = await readJson(req);
  const p = await verify(env, body && body.token, "login");
  if (!p) return json(env, req, { ok: false, error: "This sign-in link is invalid or has expired." }, 401);
  if (typeof p.n !== "string" || typeof p.e !== "string")
    return json(env, req, { ok: false, error: "This sign-in link is invalid or has expired." }, 401);
  // Links issued before the Durable Object existed were marked used in KV; honour those markers
  // until they expire (at most LOGIN_TTL after deploy). Never written any more.
  if (await env.WATCHLIST.get(`used:${p.n}`))
    return json(env, req, { ok: false, error: "This sign-in link has already been used." }, 401);
  const st = await account(env, p.e);
  const r = await st.redeem(p.n, p.exp, p.v);
  if (r === "used") return json(env, req, { ok: false, error: "This sign-in link has already been used." }, 401);
  if (r !== "ok") return json(env, req, { ok: false, error: "This sign-in link is invalid or has expired." }, 401);
  const userKey = `user:${p.e}`;
  if (!(await env.WATCHLIST.get(userKey))) {
    const t = new Date().toISOString();
    await env.WATCHLIST.put(userKey, JSON.stringify({ tickers: [], created: t, updated: t }));
  }
  const s = await sign(env, { p: "session", e: p.e, v: p.v || 0, exp: now() + SESSION_TTL });
  return json(env, req, { ok: true, session: s, email: p.e, expires_in: SESSION_TTL });
}

async function getMe(env, req) {
  const s = await session(env, req);
  if (!s) return json(env, req, { ok: false, error: "signed_out" }, 401);
  const u = JSON.parse((await env.WATCHLIST.get(`user:${s.e}`)) || '{"tickers":[]}');
  // Info tier override (later set from the reader's subscription): "basic" | "full", else null = site default.
  const tier = ["basic", "full"].includes(u.tier) ? u.tier : null;
  return json(env, req, { ok: true, email: s.e, tickers: u.tickers || [], max: parseInt(env.MAX_TICKERS || "10", 10), tier });
}

async function putTickers(env, req) {
  const s = await session(env, req);
  if (!s) return json(env, req, { ok: false, error: "signed_out" }, 401);
  const body = await readJson(req);
  const r = cleanTickers(body && body.tickers, parseInt(env.MAX_TICKERS || "10", 10));
  if (r.error) return json(env, req, { ok: false, error: r.error }, 400);
  const key = `user:${s.e}`;
  const u = JSON.parse((await env.WATCHLIST.get(key)) || "{}");
  const t = new Date().toISOString();
  // Tickers are mirrored into key metadata so GET /admin/tickers can build the union from one KV list call.
  await env.WATCHLIST.put(key, JSON.stringify({ created: u.created || t, ...u, tickers: r.tickers, updated: t }), {
    metadata: { t: r.tickers },
  });
  // If the account was deleted while this request was in flight, undo the write.
  if ((s.v || 0) !== (await (await account(env, s.e)).version())) {
    await env.WATCHLIST.delete(key);
    return json(env, req, { ok: false, error: "signed_out" }, 401);
  }
  const q = await queueMissing(env, r.tickers);
  return json(env, req, { ok: true, tickers: r.tickers, pending: q.pending, issue_date: q.date });
}

// ---------- instant add: picks missing from the day's watchlist.json ----------
const sydneyDate = (d = new Date()) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Sydney", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);

async function latestIssue(env) {
  // today's Sydney date, else the most recent issue in the last 7 days
  for (let i = 0; i < 7; i++) {
    const d = sydneyDate(new Date(Date.now() - i * 86400000));
    const r = await fetch(`${env.SITE_ORIGIN}/assets/issues/${d}/watchlist.json`, { cf: { cacheTtl: 0 }, headers: { "Cache-Control": "no-cache" } });
    if (r.ok) return { date: d, data: await r.json() };
  }
  return null;
}

async function dispatchAdd(env, date, tickers) {
  if (env.DEV_DISPATCH_MOCK === "1") return true;
  if (!env.GITHUB_DISPATCH_TOKEN) return false;
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/watchlist-add.yml/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "signaletter-watchlist",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ ref: "main", inputs: { date, tickers: tickers.join(",") } }),
  });
  if (!r.ok) console.log(`dispatch error ${r.status}: ${await r.text()}`);
  return r.ok;
}

// Returns {date, pending}: tickers missing from the latest issue file that a quick-add run is
// building (dispatched now, or within the last 10 minutes). Never throws: saving picks must not fail.
async function queueMissing(env, tickers) {
  try {
    if (!tickers.length || (!env.GITHUB_DISPATCH_TOKEN && env.DEV_DISPATCH_MOCK !== "1")) return { date: null, pending: [] };
    const issue = await latestIssue(env);
    if (!issue) return { date: null, pending: [] };
    const eds = Object.values((issue.data && issue.data.editions) || {});
    if (!eds.length) return { date: issue.date, pending: [] };
    const missing = tickers.filter((t) => eds.some((e) => !(e.items && e.items[t])));
    const fresh = [], pending = [];
    for (const t of missing) {
      if (await env.WATCHLIST.get(`qa:${issue.date}:${t}`)) pending.push(t);
      else fresh.push(t);
    }
    if (fresh.length && (await dispatchAdd(env, issue.date, fresh))) {
      for (const t of fresh) await env.WATCHLIST.put(`qa:${issue.date}:${t}`, "1", { expirationTtl: 600 });
      pending.push(...fresh);
    }
    return { date: issue.date, pending: pending.sort() };
  } catch (e) {
    console.log(`queueMissing: ${e && e.stack}`);
    return { date: null, pending: [] };
  }
}

async function deleteMe(env, req) {
  const s = await session(env, req);
  if (!s) return json(env, req, { ok: false, error: "signed_out" }, 401);
  // Revoke first (strongly consistent), then delete the data, so no old session can recreate it.
  await (await account(env, s.e)).revoke();
  await env.WATCHLIST.delete(`user:${s.e}`);
  await env.WATCHLIST.delete(`sub:${s.e}`);
  return json(env, req, { ok: true });
}

// Union of every reader's tickers, for the daily watchlist.json build. Codes only, never emails.
async function timingSafeEqual(a, b) {
  const k = await crypto.subtle.importKey("raw", crypto.getRandomValues(new Uint8Array(32)), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const [x, y] = await Promise.all([crypto.subtle.sign("HMAC", k, enc.encode(a)), crypto.subtle.sign("HMAC", k, enc.encode(b))]);
  const ua = new Uint8Array(x), ub = new Uint8Array(y);
  let d = 0;
  for (let i = 0; i < ua.length; i++) d |= ua[i] ^ ub[i];
  return d === 0;
}
async function adminTickers(env, req) {
  const m = (req.headers.get("Authorization") || "").match(/^Bearer (.+)$/);
  if (!env.ADMIN_TOKEN || env.ADMIN_TOKEN.length < 32 || !m || !(await timingSafeEqual(m[1], env.ADMIN_TOKEN)))
    return json(env, req, { ok: false, error: "unauthorized" }, 401);
  const set = new Set();
  let cursor, readers = 0;
  do {
    const page = await env.WATCHLIST.list({ prefix: "user:", cursor });
    for (const k of page.keys) {
      let t = k.metadata && Array.isArray(k.metadata.t) ? k.metadata.t : null;
      if (!t) t = (JSON.parse((await env.WATCHLIST.get(k.name)) || "{}").tickers) || []; // pre-metadata records
      if (t.length) readers++;
      for (const x of t) if (ALLOWED.has(x)) set.add(x);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  const tickers = [...set].sort();
  return json(env, req, { ok: true, tickers, count: tickers.length, readers });
}

// Email-only subscription (stub): double opt-in, stored in KV. Sending the daily notice
// (e.g. via Resend Broadcasts/contacts) is not wired up yet.
async function subscribe(env, req) {
  const body = await readJson(req);
  const email = normEmail(body && body.email);
  if (!validEmail(email)) return json(env, req, { ok: false, error: "Enter a valid email address." }, 400);
  const lists = Array.isArray(body.lists) ? body.lists.filter((l) => LISTS.includes(l)) : [];
  if (!lists.length) return json(env, req, { ok: false, error: "Choose Markets, AI or both." }, 400);
  const hour = Math.floor(now() / 3600);
  const rlKey = `rl:${email}:${hour}`;
  const count = parseInt((await env.WATCHLIST.get(rlKey)) || "0", 10);
  if (count >= SIGNIN_PER_HOUR) return json(env, req, { ok: false, error: "Too many requests. Try later." }, 429);
  await env.WATCHLIST.put(rlKey, String(count + 1), { expirationTtl: 3600 });
  const prev = JSON.parse((await env.WATCHLIST.get(`sub:${email}`)) || "null");
  if (!prev || prev.status !== "confirmed")
    await env.WATCHLIST.put(`sub:${email}`, JSON.stringify({ lists, status: "pending", updated: new Date().toISOString() }));
  const token = await sign(env, { p: "confirm", e: email, l: lists, exp: now() + CONFIRM_TTL });
  const link = `${new URL(req.url).origin}/subscribe/confirm?token=${encodeURIComponent(token)}`;
  const names = lists.map((l) => (l === "ai" ? "AI" : "Markets")).join(" and ");
  const text = `Confirm your SignaLetter subscription (${names}):\n\n${link}\n\nIf you didn't sign up, ignore this email and you won't hear from us.\n\nSignaLetter · https://signaletter.si`;
  let mocked;
  try {
    ({ mocked } = await sendEmail(env, {
      to: email,
      subject: "Confirm your SignaLetter subscription",
      text,
      htmlBody: `<p>Confirm your SignaLetter subscription (${escapeHtml(names)}):</p><p><a href="${escapeHtml(link)}">Confirm subscription</a></p><p>If you didn't sign up, ignore this email.</p>`,
    }));
  } catch {
    return json(env, req, { ok: false, error: "We couldn't send the email. Try again shortly." }, 502);
  }
  const res = { ok: true };
  if (mocked && env.DEV_RETURN_LINK === "1") res.dev_link = link;
  return json(env, req, res);
}

async function confirmSub(env, url) {
  const p = await verify(env, url.searchParams.get("token"), "confirm");
  if (!p) return html("<h1>Link expired</h1><p>Please sign up again on <a href='https://signaletter.si'>SignaLetter</a>.</p>", 400);
  await env.WATCHLIST.put(`sub:${p.e}`, JSON.stringify({ lists: p.l, status: "confirmed", updated: new Date().toISOString() }));
  const unsub = await sign(env, { p: "unsub", e: p.e, exp: now() + 10 * 365 * 24 * 3600 });
  return html(
    `<h1>You're subscribed</h1><p>${escapeHtml(p.e)} will get the SignaLetter ${p.l.map((l) => (l === "ai" ? "AI" : "Markets")).join(" and ")} email.</p><p><a href="${escapeHtml(env.SITE_ORIGIN)}">Back to SignaLetter</a> · <a href="/unsubscribe?token=${encodeURIComponent(unsub)}">Unsubscribe</a></p>`,
  );
}

async function unsubscribe(env, req, url) {
  const p = await verify(env, url.searchParams.get("token"), "unsub");
  if (!p) return html("<h1>Invalid link</h1>", 400);
  // GET shows a confirm button (mail scanners prefetch links); POST is RFC 8058 one-click.
  if (req.method === "GET")
    return html(
      `<h1>Unsubscribe?</h1><form method="post"><button type="submit">Unsubscribe ${escapeHtml(p.e)}</button></form>`,
    );
  await env.WATCHLIST.delete(`sub:${p.e}`);
  return html("<h1>Unsubscribed</h1><p>You won't get SignaLetter emails any more.</p>");
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (!env.AUTH_SECRET || env.AUTH_SECRET.length < 32)
      return json(env, req, { ok: false, error: "server_not_configured" }, 500);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(env, req) });
    const route = `${req.method} ${url.pathname}`;
    try {
      switch (route) {
        case "GET /":
        case "GET /health":
          return json(env, req, { ok: true, service: "signaletter-api", tickers: ALLOWED.size });
        case "POST /auth/request":
          return await authRequest(env, req);
        case "POST /auth/verify":
          return await authVerify(env, req);
        case "GET /me":
          return await getMe(env, req);
        case "PUT /me/tickers":
          return await putTickers(env, req);
        case "DELETE /me":
          return await deleteMe(env, req);
        case "GET /admin/tickers":
          return await adminTickers(env, req);
        case "POST /subscribe":
          return await subscribe(env, req);
        case "GET /subscribe/confirm":
          return await confirmSub(env, url);
        case "GET /unsubscribe":
        case "POST /unsubscribe":
          return await unsubscribe(env, req, url);
        default:
          return json(env, req, { ok: false, error: "not_found" }, 404);
      }
    } catch (e) {
      console.log(`error ${route}: ${e && e.stack}`);
      return json(env, req, { ok: false, error: "server_error" }, 500);
    }
  },
};
