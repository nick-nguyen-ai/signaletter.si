/* "My shares": per-reader watchlist.
 * - Markets pages: only the watchlist section changes for a signed-in reader. It is rebuilt from
 *   /assets/issues/<day>/watchlist.json (published by the daily routine). Everything else is untouched.
 * - /watchlist/: passwordless sign-in (magic link via the SignaLetter API Worker) and the share picker.
 * Session: a signed bearer token in localStorage (the API lives on another domain, so no cookies).
 */
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="sl-watchlist-api"]');
  var API = meta ? String(meta.content || "").replace(/\/+$/, "") : "";
  if (!API) return;
  var KEY = "sl.wl.session";
  var tmeta = document.querySelector('meta[name="sl-watchlist-tier"]');
  var TIERS = ["basic", "full"];
  // Reader's tier (from GET /me, later their subscription) wins; else the site default; else full.
  function resolveTier(readerTier, siteTier) {
    if (TIERS.indexOf(readerTier) >= 0) return readerTier;
    if (TIERS.indexOf(siteTier) >= 0) return siteTier;
    return "full";
  }
  var SITE_TIER = tmeta ? String(tmeta.content || "").trim() : "";
  var tier = resolveTier(null, SITE_TIER);
  var TICKERS_URL = "/assets/data/asx-tickers.json";

  function getSession() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY) || "null");
      if (s && s.token && s.exp && s.exp * 1000 > Date.now()) return s;
    } catch (e) { /* ignore */ }
    localStorage.removeItem(KEY);
    return null;
  }
  function setSession(token, email, expiresIn) {
    localStorage.setItem(KEY, JSON.stringify({ token: token, email: email, exp: Math.floor(Date.now() / 1000) + expiresIn }));
  }
  function clearSession() { localStorage.removeItem(KEY); }
  var PKEY = "sl_wl_pending";
  function savePending(date, list) {
    if (!date || !list || !list.length) return;
    localStorage.setItem(PKEY, JSON.stringify({ date: date, tickers: list, at: Date.now() }));
  }
  function getPending() { // tickers a quick-add run is building, for 5 minutes after saving
    try { var p = JSON.parse(localStorage.getItem(PKEY) || "null"); return p && Date.now() - p.at < 5 * 60000 ? p : null; }
    catch (e) { return null; }
  }

  function api(method, path, body, token) {
    var opts = { method: method, headers: {} };
    if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    if (token) opts.headers.Authorization = "Bearer " + token;
    return fetch(API + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { j._status = r.status; return j; });
    });
  }
  function getJson(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function fmtSession(iso) {
    var d = new Date(iso + "T12:00:00Z");
    return d.toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).replace(/,/g, "");
  }

  // ---------- Markets page: watchlist section ----------
  function renderRow(code, name, item, updating) {
    var li = el("li", "mk-watch__row");
    var head = el("div", "mk-watch__head");
    head.appendChild(el("span", "mk-watch__ticker", code));
    head.appendChild(el("span", "mk-watch__name", name || ""));
    var px = item && item.price;
    if (px && px.status === "ok") {
      var s = el("span", "mk-watch__px");
      s.appendChild(el("b", null, "A$" + px.display_value));
      s.appendChild(document.createTextNode(" "));
      s.appendChild(el("span", "mk-chg", px.display_change));
      head.appendChild(s);
    } else if (!item && updating) {
      head.appendChild(el("span", "mk-watch__px mk-unavail", "Updating…"));
    } else {
      head.appendChild(el("span", "mk-watch__px mk-unavail", "Price unavailable"));
    }
    li.appendChild(head);
    if (px && px.status === "ok") {
      var m = el("p", "mk-micro", fmtSession(px.session_date) + " close · " + px.provider + " · ");
      m.appendChild(el("span", "mk-flag", "delayed, unofficial"));
      li.appendChild(m);
    }
    var basic = tier === "basic";
    var text = item ? (basic && item.price_note ? item.price_note : item.note) : updating ? "Updating your shares, check back in a minute." : "Not in our data for this edition.";
    var note = el("p", "mk-watch__note", text);
    if (item && (basic || item.reviewed === false)) note.appendChild(el("span", "mk-wl-tag", "auto: price + ASX feed"));
    li.appendChild(note);
    if (item && !basic && item.insight) {
      var ins = el("p", "mk-watch__note mk-watch__insight", item.insight);
      li.appendChild(ins);
      sourcesLine(li, item.insight_sources);
    }
    if (item && !basic && item.next_catalyst) {
      var nx = el("p", "mk-watch__next");
      nx.appendChild(el("b", null, "Next:"));
      nx.appendChild(document.createTextNode(" " + item.next_catalyst));
      li.appendChild(nx);
    }
    if (item && !(basic && item.reviewed)) sourcesLine(li, item.sources);
    return li;
  }
  function sourcesLine(li, list) {
    if (!list || !list.length) return;
    var src = el("p", "mk-sources-inline"), n = 0;
    list.forEach(function (sObj) {
      if (!/^https:\/\//.test(sObj.url || "")) return;
      if (n++) src.appendChild(document.createTextNode(" · "));
      var a = el("a", null, sObj.label);
      a.href = sObj.url; a.rel = "noopener";
      src.appendChild(a);
    });
    if (n) li.appendChild(src);
  }

  function setBar(section, parts) {
    var bar = section.querySelector("[data-wl-bar]");
    if (!bar) return;
    bar.textContent = "";
    parts.forEach(function (p) { bar.appendChild(typeof p === "string" ? document.createTextNode(p) : p); });
  }
  function link(text, href) { var a = el("a", null, text); a.href = href; return a; }
  function signOutBtn() {
    var b = el("button", null, "Sign out");
    b.type = "button";
    b.addEventListener("click", function () { clearSession(); location.reload(); });
    return b;
  }

  // Re-check the day's file every 20 s for up to 3 minutes and swap rows in as they arrive.
  function pollUpdates(sec, day, scope, waiting, names) {
    var tries = 0;
    sec._wlPoll = setInterval(function () {
      tries++;
      getJson("/assets/issues/" + day + "/watchlist.json?t=" + Date.now()).then(function (d) {
        var items = (d && d.editions && d.editions[scope] && d.editions[scope].items) || {};
        sec.querySelectorAll(".mk-watch__row").forEach(function (row) {
          var code = row.querySelector(".mk-watch__ticker").textContent, i = waiting.indexOf(code);
          if (i >= 0 && items[code]) { row.replaceWith(renderRow(code, names[code], items[code])); waiting.splice(i, 1); }
        });
        if (!waiting.length || tries >= 9) {
          clearInterval(sec._wlPoll);
          sec.querySelectorAll(".mk-watch__row").forEach(function (row) {
            var code = row.querySelector(".mk-watch__ticker").textContent;
            if (waiting.indexOf(code) >= 0) row.replaceWith(renderRow(code, names[code], null, false));
          });
        }
      }).catch(function () {});
    }, 20000);
  }

  function initMarkets(sections) {
    var s = getSession();
    if (!s) return;
    var article = sections[0].closest("[data-day]");
    var day = article && article.getAttribute("data-day");
    var editHref = "/watchlist/?next=" + encodeURIComponent(location.pathname);
    sections.forEach(function (sec) { sec.setAttribute("data-wl-loading", ""); });
    Promise.all([
      api("GET", "/me", null, s.token),
      day ? getJson("/assets/issues/" + day + "/watchlist.json").catch(function () { return null; }) : Promise.resolve(null),
      getJson(TICKERS_URL).catch(function () { return { tickers: [] }; }),
    ]).then(function (res) {
      var me = res[0], data = res[1], names = {};
      (res[2].tickers || []).forEach(function (t) { names[t.code] = t.name; });
      sections.forEach(function (sec) { sec.removeAttribute("data-wl-loading"); });
      if (me._status === 401) { clearSession(); return; }
      if (!me.ok) return;
      tier = resolveTier(me.tier, SITE_TIER);
      var who = me.email;
      if (!me.tickers.length) {
        sections.forEach(function (sec) {
          setBar(sec, ["Signed in as " + who + ". You haven't picked any shares yet, so this is the default list. ", link("Pick your shares", editHref), " · ", signOutBtn()]);
        });
        return;
      }
      sections.forEach(function (sec) {
        var scope = sec.getAttribute("data-wl-scope") || "morning";
        var ed = data && data.editions && data.editions[scope];
        if (!ed) {
          setBar(sec, ["Your shares aren't available for this edition, so this is the default list. ", link("Edit your shares", editHref), " · ", signOutBtn()]);
          return;
        }
        var ul = sec.querySelector(".mk-watch");
        ul.textContent = "";
        var pend = getPending(), waiting = [];
        me.tickers.forEach(function (code) {
          var upd = !ed.items[code] && pend && pend.date === day && pend.tickers.indexOf(code) >= 0;
          if (upd) waiting.push(code);
          ul.appendChild(renderRow(code, names[code], ed.items[code], upd));
        });
        if (waiting.length && !sec._wlPoll) pollUpdates(sec, day, scope, waiting, names);
        sec.setAttribute("data-count", String(me.tickers.length));
        sec.setAttribute("data-wl-personal", "");
        setBar(sec, ["Your shares (" + who + "). ", link("Edit", editHref), " · ", signOutBtn()]);
      });
    }).catch(function () {
      sections.forEach(function (sec) { sec.removeAttribute("data-wl-loading"); });
    });
  }

  // ---------- Shared: "email me a link" form (watchlist page + landing box) ----------
  function bindSigninForm(form, next, onSent) {
    if (!form) return;
    var msg = form.querySelector("[data-wl-msg]");
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var email = form.email.value.trim();
      if (!email || !form.email.checkValidity()) { msg.className = "wl-msg wl-msg--err"; msg.textContent = "Enter a valid email address."; return; }
      msg.className = "wl-msg"; msg.textContent = "Sending…";
      var btn = form.querySelector("button"); btn.disabled = true;
      api("POST", "/auth/request", { email: email, next: next || "" }).then(function (r) {
        btn.disabled = false;
        if (!r.ok) { msg.className = "wl-msg wl-msg--err"; msg.textContent = r.error || "Something went wrong."; return; }
        msg.textContent = "";
        onSent(email, r);
      }).catch(function () { btn.disabled = false; msg.className = "wl-msg wl-msg--err"; msg.textContent = "Couldn't reach the server. Try again."; });
    });
  }

  // ---------- Header (every page) + landing box ----------
  function initHeader() {
    var signedIn = !!getSession();
    document.querySelectorAll("[data-wl-auth-out]").forEach(function (n) { n.hidden = signedIn; });
    document.querySelectorAll("[data-wl-auth-in]").forEach(function (n) { n.hidden = !signedIn; });
    document.querySelectorAll("[data-wl-auth-signout]").forEach(function (b) {
      b.addEventListener("click", function () { clearSession(); location.reload(); });
    });
    var promo = document.querySelector("[data-wl-promo]");
    if (!promo) return;
    var form = promo.querySelector("[data-wl-quick-form]");
    if (signedIn) { form.hidden = true; promo.querySelector("[data-wl-promo-in]").hidden = false; return; }
    bindSigninForm(form, "", function () {
      var msg = form.querySelector("[data-wl-msg]");
      msg.className = "wl-msg wl-msg--ok";
      msg.textContent = "Check your inbox (and Junk) for a sign-in link.";
      form.email.value = "";
    });
  }

  // ---------- /watchlist/ page ----------
  function initPage(root) {
    var states = {};
    root.querySelectorAll("[data-wl-state]").forEach(function (n) { states[n.getAttribute("data-wl-state")] = n; });
    function show(name) { Object.keys(states).forEach(function (k) { states[k].hidden = k !== name; }); }
    var params = new URLSearchParams(location.search);
    var next = params.get("next") || "";
    if (!/^\/(?!\/)/.test(next)) next = "";
    if (next) root.querySelector("[data-wl-back]").href = next;

    var msg = root.querySelector("[data-wl-msg]");
    bindSigninForm(root.querySelector("[data-wl-signin-form]"), next, function (email, r) {
      root.querySelector("[data-wl-sent-to]").textContent = email;
      var dev = root.querySelector("[data-wl-dev]");
      if (r.dev_link) { dev.hidden = false; dev.querySelector("a").href = r.dev_link; }
      show("sent");
    });
    root.querySelector("[data-wl-restart]").addEventListener("click", function () { show("signin"); });

    function startPicker(sess) {
      Promise.all([api("GET", "/me", null, sess.token), getJson(TICKERS_URL)]).then(function (res) {
        var me = res[0], all = res[1].tickers || [], max = me.max || 10;
        if (me._status === 401) { clearSession(); show("signin"); return; }
        var names = {}; all.forEach(function (t) { names[t.code] = t.name; });
        var picked = (me.tickers || []).slice();
        root.querySelector("[data-wl-email]").textContent = me.email;
        var chips = root.querySelector("[data-wl-chips]"), count = root.querySelector("[data-wl-count]");
        var search = root.querySelector("[data-wl-search]"), results = root.querySelector("[data-wl-results]");
        var saveMsg = root.querySelector("[data-wl-save-msg]");
        function drawChips() {
          chips.textContent = "";
          count.textContent = picked.length + " of " + max;
          if (!picked.length) chips.appendChild(el("li", "wl-empty", "No shares yet. Search below to add some."));
          picked.forEach(function (code) {
            var li = el("li", "wl-chip"); li.title = names[code] || code;
            li.appendChild(document.createTextNode(code));
            var x = el("button", null, "×"); x.type = "button"; x.setAttribute("aria-label", "Remove " + code);
            x.addEventListener("click", function () { picked = picked.filter(function (c) { return c !== code; }); drawChips(); drawResults(); });
            li.appendChild(x); chips.appendChild(li);
          });
        }
        function drawResults() {
          var q = search.value.trim().toLowerCase();
          results.textContent = "";
          if (!q) return;
          all.filter(function (t) { return t.code.toLowerCase().indexOf(q) === 0 || t.name.toLowerCase().indexOf(q) !== -1; })
            .slice(0, 12).forEach(function (t) {
              var li = el("li"), b = el("button"); b.type = "button";
              b.appendChild(el("b", null, t.code)); b.appendChild(el("span", null, t.name));
              var has = picked.indexOf(t.code) !== -1;
              if (has || picked.length >= max) b.disabled = true;
              if (has) b.appendChild(el("span", null, "· added"));
              b.addEventListener("click", function () { picked.push(t.code); search.value = ""; drawChips(); drawResults(); search.focus(); });
              li.appendChild(b); results.appendChild(li);
            });
          if (!results.children.length) results.appendChild(el("li", "wl-empty", "No ASX 300 match."));
        }
        search.addEventListener("input", drawResults);
        root.querySelector("[data-wl-save]").addEventListener("click", function () {
          saveMsg.className = "wl-msg"; saveMsg.textContent = "Saving…";
          api("PUT", "/me/tickers", { tickers: picked }, sess.token).then(function (r) {
            if (!r.ok) { saveMsg.className = "wl-msg wl-msg--err"; saveMsg.textContent = r.error || "Couldn't save."; return; }
            saveMsg.textContent = "Saved. Your Markets pages now show " + (r.tickers.join(", ") || "the default list") + ".";
            if (r.pending && r.pending.length) {
              savePending(r.issue_date, r.pending);
              saveMsg.textContent += " Updating " + r.pending.join(", ") + " for the " + r.issue_date + " issue, check back in a minute.";
            }
          });
        });
        root.querySelector("[data-wl-signout]").addEventListener("click", function () { clearSession(); show("signin"); });
        drawChips();
        show("picker");
      }).catch(function () { show("signin"); msg.textContent = "Couldn't reach the server. Try again."; });
    }

    var token = params.get("token");
    if (token) {
      // Remove the one-time token from the address bar and history straight away.
      params.delete("token");
      history.replaceState(null, "", location.pathname + (params.toString() ? "?" + params : ""));
      api("POST", "/auth/verify", { token: token }).then(function (r) {
        if (!r.ok) { show("signin"); msg.className = "wl-msg wl-msg--err"; msg.textContent = r.error || "That link didn't work. Request a new one."; return; }
        setSession(r.session, r.email, r.expires_in);
        startPicker(getSession());
      }).catch(function () { show("signin"); msg.textContent = "Couldn't reach the server. Try again."; });
      return;
    }
    var s = getSession();
    if (s) startPicker(s); else show("signin");
  }

  // Test hook (scripts/tests/test_watchlist_tier.mjs): pure helpers only, no session access.
  window.SLWatchlist = { resolveTier: resolveTier, renderRow: renderRow, setTier: function (t) { tier = resolveTier(t, SITE_TIER); } };

  function boot() {
    initHeader();
    var page = document.querySelector("[data-wl-page]");
    if (page) initPage(page);
    var secs = Array.prototype.slice.call(document.querySelectorAll("[data-wl-section]"));
    if (secs.length) initMarkets(secs);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
