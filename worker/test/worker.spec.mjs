// Regression tests for the SignaLetter Worker (run: npm test). Executed inside workerd.
import { exports, env } from "cloudflare:workers";
import { describe, it, expect } from "vitest";

const ORIGIN = "http://localhost:4000";
let n = 0;
const freshEmail = () => `t${Date.now()}-${n++}@example.com`;
async function call(method, path, body, token) {
  const headers = { Origin: ORIGIN };
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await exports.default.fetch(`https://api.test${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, body: await r.json().catch(() => ({})) };
}
async function loginToken(email) {
  const r = await call("POST", "/auth/request", { email });
  expect(r.status).toBe(200);
  return new URL(r.body.dev_link).searchParams.get("token");
}
async function signIn(email) {
  const v = await call("POST", "/auth/verify", { token: await loginToken(email) });
  expect(v.status).toBe(200);
  return v.body.session;
}
// Forge a token the way the Worker signs it (to simulate sessions minted before versioning).
async function forge(payload) {
  const enc = new TextEncoder();
  const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const body = b64u(enc.encode(JSON.stringify(payload)));
  const key = await crypto.subtle.importKey("raw", enc.encode("test-secret-0123456789abcdef0123456789abcdef"), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return `${body}.${b64u(await crypto.subtle.sign("HMAC", key, enc.encode(body)))}`;
}

describe("magic links", () => {
  it("rejects a tampered token and a second use", async () => {
    const token = await loginToken(freshEmail());
    expect((await call("POST", "/auth/verify", { token: token.slice(0, -2) + "xx" })).status).toBe(401);
    expect((await call("POST", "/auth/verify", { token })).status).toBe(200);
    const again = await call("POST", "/auth/verify", { token });
    expect(again.status).toBe(401);
    expect(again.body.error).toMatch(/already been used/);
  });

  it("two concurrent verifies of one link: exactly one success", async () => {
    const token = await loginToken(freshEmail());
    const rs = await Promise.all([call("POST", "/auth/verify", { token }), call("POST", "/auth/verify", { token })]);
    expect(rs.map((r) => r.status).sort()).toEqual([200, 401]);
  });

  it("twenty concurrent verifies of one link: exactly one success", async () => {
    const token = await loginToken(freshEmail());
    const rs = await Promise.all(Array.from({ length: 20 }, () => call("POST", "/auth/verify", { token })));
    expect(rs.filter((r) => r.status === 200).length).toBe(1);
    expect(rs.filter((r) => r.status === 401).length).toBe(19);
  });

  it("different links for the same email each work once", async () => {
    const email = freshEmail();
    const [a, b] = [await loginToken(email), await loginToken(email)];
    expect((await call("POST", "/auth/verify", { token: a })).status).toBe(200);
    expect((await call("POST", "/auth/verify", { token: b })).status).toBe(200);
    expect((await call("POST", "/auth/verify", { token: a })).status).toBe(401);
  });
});

describe("account deletion revokes sessions", () => {
  it("old session cannot read or write after DELETE /me, and cannot recreate the user", async () => {
    const email = freshEmail();
    const s1 = await signIn(email);
    const s2 = await signIn(email); // a second device
    expect((await call("PUT", "/me/tickers", { tickers: ["BHP", "CBA"] }, s1)).status).toBe(200);
    expect((await call("DELETE", "/me", null, s1)).status).toBe(200);
    for (const s of [s1, s2]) {
      expect((await call("GET", "/me", null, s)).status).toBe(401);
      expect((await call("PUT", "/me/tickers", { tickers: ["WES"] }, s)).status).toBe(401);
      expect((await call("DELETE", "/me", null, s)).status).toBe(401);
    }
    const admin = await call("GET", "/admin/tickers", null, "test-admin-token-0123456789abcdef0123456789");
    expect(admin.body.tickers).not.toContain("WES");
    // signing in again works and starts empty
    const s3 = await signIn(email);
    const me = await call("GET", "/me", null, s3);
    expect(me.status).toBe(200);
    expect(me.body.tickers).toEqual([]);
  });

  it("an unused sign-in link issued before deletion stops working", async () => {
    const email = freshEmail();
    const s = await signIn(email);
    const pending = await loginToken(email);
    expect((await call("DELETE", "/me", null, s)).status).toBe(200);
    expect((await call("POST", "/auth/verify", { token: pending })).status).toBe(401);
  });

  it("pre-versioning sessions (no v) keep working until the account is deleted", async () => {
    const email = freshEmail();
    await signIn(email);
    const legacy = await forge({ p: "session", e: email, exp: Math.floor(Date.now() / 1000) + 3600 });
    expect((await call("GET", "/me", null, legacy)).status).toBe(200);
    expect((await call("DELETE", "/me", null, legacy)).status).toBe(200);
    expect((await call("GET", "/me", null, legacy)).status).toBe(401);
  });

  it("expired or wrong-purpose tokens are rejected", async () => {
    const email = freshEmail();
    const expired = await forge({ p: "session", e: email, v: 0, exp: Math.floor(Date.now() / 1000) - 1 });
    expect((await call("GET", "/me", null, expired)).status).toBe(401);
    const login = await loginToken(email);
    expect((await call("GET", "/me", null, login)).status).toBe(401);
  });
});

describe("tickers and admin", () => {
  it("validates, caps, dedupes, persists; admin union has codes only", async () => {
    const s = await signIn(freshEmail());
    expect((await call("GET", "/me")).status).toBe(401);
    expect((await call("PUT", "/me/tickers", { tickers: ["BHP", "NOPE"] }, s)).status).toBe(400);
    const eleven = ["BHP", "CBA", "NAB", "WBC", "ANZ", "MQG", "WES", "RIO", "FMG", "TLS", "WOW"];
    expect((await call("PUT", "/me/tickers", { tickers: eleven }, s)).status).toBe(400);
    const ok = await call("PUT", "/me/tickers", { tickers: ["bhp", "CBA.AX", "BHP"] }, s);
    expect(ok.body.tickers).toEqual(["BHP", "CBA"]);
    expect((await call("GET", "/me", null, s)).body.tickers).toEqual(["BHP", "CBA"]);
    expect((await call("GET", "/admin/tickers", null, s)).status).toBe(401);
    const a = await call("GET", "/admin/tickers", null, "test-admin-token-0123456789abcdef0123456789");
    expect(a.status).toBe(200);
    expect(a.body.tickers).toEqual(expect.arrayContaining(["BHP", "CBA"]));
    expect(JSON.stringify(a.body)).not.toContain("@");
  });
});

describe("info tier", () => {
  it("GET /me returns null tier by default and the KV record's tier when set", async () => {
    const email = freshEmail();
    const s = await signIn(email);
    expect((await call("GET", "/me", null, s)).body.tier).toBeNull();
    const key = `user:${email}`;
    const u = JSON.parse(await env.WATCHLIST.get(key));
    await env.WATCHLIST.put(key, JSON.stringify({ ...u, tier: "basic" }));
    expect((await call("GET", "/me", null, s)).body.tier).toBe("basic");
    // saving picks keeps the tier
    expect((await call("PUT", "/me/tickers", { tickers: ["BHP"] }, s)).status).toBe(200);
    expect((await call("GET", "/me", null, s)).body.tier).toBe("basic");
    await env.WATCHLIST.put(key, JSON.stringify({ ...u, tier: "platinum" }));
    expect((await call("GET", "/me", null, s)).body.tier).toBeNull();
  });
});
