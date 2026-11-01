// Info-tier rendering of "My shares" rows (run: node --test scripts/tests/test_watchlist_tier.mjs).
// Loads assets/js/my-watchlist.js against a minimal DOM stub and checks basic vs full output.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

class Node_ {
  constructor(tag) { this.tag = tag; this.children = []; this.className = ""; this._text = ""; this.attrs = {}; }
  appendChild(c) { this.children.push(c); return c; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  setAttribute(k, v) { this.attrs[k] = v; }
  all(cls) { const out = []; const walk = (n) => { if ((n.className || "").split(" ").includes(cls)) out.push(n); (n.children || []).forEach(walk); }; walk(this); return out; }
  links() { const out = []; const walk = (n) => { if (n.tag === "a") out.push(n.href); (n.children || []).forEach(walk); }; walk(this); return out; }
}
function load(siteTier) {
  const metas = { "sl-watchlist-api": "https://api.example", "sl-watchlist-tier": siteTier };
  const document = {
    readyState: "loading", addEventListener() {},
    querySelector(sel) { const m = /name="([^"]+)"/.exec(sel); return m && metas[m[1]] != null ? { content: metas[m[1]] } : null; },
    querySelectorAll() { return []; },
    createElement: (t) => new Node_(t),
    createTextNode: (t) => { const n = new Node_("#text"); n._text = String(t); return n; },
  };
  const window = {};
  const store = {};
  const localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } };
  vm.runInNewContext(fs.readFileSync(new URL("../../assets/js/my-watchlist.js", import.meta.url), "utf8"),
    { window, document, localStorage, location: { pathname: "/" }, fetch: () => Promise.reject(), console });
  return window.SLWatchlist;
}
const PX = { status: "ok", display_value: "45.10", display_change: "+2.3%", session_date: "2026-10-30", provider: "Yahoo Finance (BHP.AX)" };
const PICK = {
  ticker: "BHP", price: PX, reviewed: false,
  note: "Rose 2.3% to A$45.10 on Friday. No new ASX announcement.",
  price_note: "Rose 2.3% to A$45.10 on Friday. No new ASX announcement.",
  sources: [{ label: "ASX announcements (BHP)", url: "https://www.asx.com.au/a" }],
  insight: "Miners rose with iron ore after China stimulus reports.",
  insight_sources: [{ label: "Reuters", url: "https://www.reuters.com/x" }],
};
const REVIEWED = { ticker: "ZIP", price: PX, reviewed: true, note: "UBS called the selloff an overreaction.",
  price_note: "Rose 2.3% to A$45.10 on Friday. No new ASX announcement.", next_catalyst: "AGM 19 Nov",
  sources: [{ label: "AFR", url: "https://www.afr.com/z" }] };

test("resolveTier: reader override wins, then site default, then full", () => {
  const w = load("full");
  assert.equal(w.resolveTier("basic", "full"), "basic");
  assert.equal(w.resolveTier(null, "basic"), "basic");
  assert.equal(w.resolveTier("gold", "nonsense"), "full");
  assert.equal(w.resolveTier(undefined, ""), "full");
});
test("full tier shows the sourced insight", () => {
  const w = load("full");
  const li = w.renderRow("BHP", "BHP Group", PICK);
  assert.match(li.textContent, /Miners rose with iron ore/);
  assert.ok(li.links().includes("https://www.reuters.com/x"));
  const z = w.renderRow("ZIP", "Zip", REVIEWED);
  assert.match(z.textContent, /overreaction/);
  assert.match(z.textContent, /AGM 19 Nov/);
});
test("basic tier (site default) shows price action only", () => {
  const w = load("basic");
  const li = w.renderRow("BHP", "BHP Group", PICK);
  assert.match(li.textContent, /A\$45\.10/);
  assert.doesNotMatch(li.textContent, /Miners rose/);
  assert.ok(!li.links().includes("https://www.reuters.com/x"));
  const z = w.renderRow("ZIP", "Zip", REVIEWED);
  assert.doesNotMatch(z.textContent, /overreaction|AGM/);
  assert.match(z.textContent, /Rose 2\.3%/);
});
test("reader tier overrides the site default", () => {
  const w = load("full");
  w.setTier("basic");
  assert.doesNotMatch(w.renderRow("BHP", "BHP Group", PICK).textContent, /Miners rose/);
  const b = load("basic");
  b.setTier("full");
  assert.match(b.renderRow("BHP", "BHP Group", PICK).textContent, /Miners rose/);
});
