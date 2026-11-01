#!/usr/bin/env python3
"""Build assets/issues/YYYY-MM-DD/watchlist.json for the per-reader "My shares" view.

One entry per ticker that any reader follows, for each edition the day's Markets
post has (morning; close when the post has a close block). Facts only:

* Price and change: if the post's own snapshot has a wl_<ticker> quote, that exact
  quote is reused (so the default watchlist matches the page). Otherwise the
  Yahoo Finance chart API daily close (delayed, unofficial), compared with the
  previous session's close. Morning = previous ASX session; close = the post date.
* Note: if the post's reviewed watchlist block has the ticker, its note,
  next_catalyst and sources are reused verbatim. Otherwise the note lists ASX
  announcement headlines (ASX/Markit announcements feed) released in the edition
  window, or says there were none. If a source fails, the entry says the data
  is not available rather than guessing.

Insight (reader picks): rows not in the post's reviewed watchlist block can carry an
"insight": a short, neutral, sourced explanation of the move (company news, sector or
index move, peers, macro), written by the routine agent into an insights YAML file and
merged with --insights FILE. Each insight needs at least one https source; entries
without one are dropped, never shown unsourced. File shape:
  morning:
    BHP: {insight: "...", sources: [{label: "...", url: "https://..."}]}
  close:
    BHP: {...}
Use --list-picks to print the reader picks (beyond the defaults) that need an insight.

Info tier: every item also carries "price_note" (price move plus ASX filings only), so the
page can render the "basic" tier from the same file; "full" adds note/insight. The site
default is watchlist_info_tier in _config.yml; a reader's KV record can override it.

Ticker set = the default list (assets/data/watchlist-default-tickers.txt, or
--tickers/--tickers-file when given) plus the union of every reader's picks from
the Worker's GET /admin/tickers (codes only), authenticated with the token in
$SIGNALETTER_ADMIN_TOKEN or ~/.config/signaletter/admin_token. Use --no-readers
to skip. If the Worker can't be reached the build continues with a warning.

Usage (daily):
  python3 scripts/build_watchlist_json.py --date 2026-10-23
Other:
  python3 scripts/build_watchlist_json.py --date 2026-10-22 --tickers ZIP,CSL,BHP,CBA
  python3 scripts/build_watchlist_json.py --date 2026-10-22 --tickers-file subscribers_tickers.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
SYD = ZoneInfo("Australia/Sydney")
UA = {"User-Agent": "Mozilla/5.0 (SignaLetter watchlist builder)"}
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}.AX?range=1mo&interval=1d"
ANN = "https://asx.api.markitdigital.com/asx-research/1.0/companies/{t}/announcements"
ASX_PAGE = "https://www.asx.com.au/markets/trade-our-cash-market/announcements.{t}"
DEFAULT_TICKERS = ROOT / "assets" / "data" / "watchlist-default-tickers.txt"
API = "https://signaletter-watchlist.signaletter.workers.dev"
TOKEN_FILE = Path.home() / ".config" / "signaletter" / "admin_token"
YAHOO_LICENCE = "Yahoo Finance chart data: delayed, unofficial; Yahoo terms restrict redistribution. Shown as a cited single quote only."


def get_json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def signed(v: float, decimals: int) -> str:
    s = f"{abs(v):,.{decimals}f}"
    return ("+" if v > 0 else "−" if v < 0 else "±") + s


def load_post(day: str) -> dict:
    p = ROOT / "_posts" / f"{day}-markets.md"
    text = p.read_text()
    return yaml.safe_load(text.split("---", 2)[1])


def yahoo_closes(t: str) -> dict[str, float]:
    d = get_json(YAHOO.format(sym=t))["chart"]["result"][0]
    out: dict[str, float] = {}
    for ts, c in zip(d.get("timestamp") or [], d["indicators"]["quote"][0].get("close") or []):
        if c is None:
            continue
        out[dt.datetime.fromtimestamp(ts, SYD).date().isoformat()] = c  # last value per date wins
    return out


def announcements(t: str) -> list[dict]:
    return get_json(ANN.format(t=t))["data"].get("items") or []


def price_block(t: str, closes: dict[str, float] | None, session: str, quote: dict | None) -> dict:
    if quote and quote.get("status") == "ok" and quote.get("market_session_date") == session:
        return {
            "status": "ok", "session_date": session, "value": quote["value"],
            "display_value": quote["display_value"], "change_pct": quote.get("change_pct"),
            "display_change": quote["display_change"], "provider": quote["provider"],
            "provider_url": quote["provider_url"], "licence_note": quote.get("licence_note"),
            "from": "post snapshot",
        }
    if not closes or session not in closes:
        return {"status": "unavailable", "session_date": session}
    prev = [d for d in sorted(closes) if d < session]
    if not prev:
        return {"status": "unavailable", "session_date": session}
    v, pv = closes[session], closes[prev[-1]]
    pct = (v / pv - 1) * 100
    dec = 3 if v < 1 else 2
    return {
        "status": "ok", "session_date": session, "value": round(v, 4),
        "display_value": f"{v:,.{dec}f}", "comparison_date": prev[-1], "comparison_value": round(pv, 4),
        "change_pct": round(pct, 2), "display_change": signed(round(pct, 1), 1) + "%",
        "provider": f"Yahoo Finance ({t}.AX)", "provider_url": f"https://finance.yahoo.com/quote/{t}.AX/",
        "licence_note": YAHOO_LICENCE, "from": "yahoo chart api",
    }


def note_from_announcements(t: str, anns: list[dict] | None, start: dt.datetime, end: dt.datetime,
                            px: dict, session_word: str) -> dict:
    move = ""
    if px["status"] == "ok":
        shown = px["display_change"].rstrip("%")  # e.g. "+0.4", "−2.4", "±0.0": reuse the displayed figure
        sign, mag = shown[0], shown[1:]
        if float(mag) == 0:
            move = f"Little changed at A${px['display_value']} {session_word}."
        else:
            verb = "Rose" if sign == "+" else "Fell"
            move = f"{verb} {mag}% to A${px['display_value']} {session_word}."
    if anns is None:
        return {"note": (move + " ASX announcements not in our data.").strip(), "sources": []}
    # The feed returns only the latest 5 items; if even the oldest is inside or after the
    # window, earlier ones in the window may be missing, so say so instead of "none".
    dates = [dt.datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(SYD) for a in anns]
    truncated = len(anns) >= 5 and min(dates) > start
    hits = []
    for a in anns:
        when = dt.datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(SYD)
        if start <= when <= end:
            hits.append((when, a))
    if not hits and truncated:
        return {"note": (move + " ASX announcements for this window not fully in our data.").strip(),
                "sources": [{"label": f"ASX announcements ({t})", "url": ASX_PAGE.format(t=t.lower()),
                             "claim_type": "official_statement"}]}
    if not hits:
        return {"note": (move + " No new ASX announcement.").strip(),
                "sources": [{"label": f"ASX announcements ({t})", "url": ASX_PAGE.format(t=t.lower()),
                             "claim_type": "official_statement"}]}
    parts = []
    for when, a in sorted(hits, key=lambda x: x[0])[:3]:
        ps = " (price sensitive)" if a.get("isPriceSensitive") else ""
        parts.append(f"“{a['headline'].strip()}”{ps}, {when.strftime('%-d %b %-I:%M%p').replace('AM', 'am').replace('PM', 'pm')} {when.strftime('%Z')}")
    more = f" and {len(hits) - 3} more" if len(hits) > 3 else ""
    word = "announcement" if len(hits) == 1 else "announcements"
    lead = f" ASX {word} include: " if truncated else f" ASX {word}: "
    note = (move + lead + "; ".join(parts) + more + ".").strip()
    return {"note": note, "sources": [{"label": f"ASX announcements ({t})", "url": ASX_PAGE.format(t=t.lower()),
                                       "claim_type": "official_statement"}]}


INSIGHT_MAX_CHARS = 600


def load_insights(path: str | None) -> dict[str, dict[str, dict]]:
    """Read the routine's insights file; keep only well-formed, sourced entries."""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        print(f"warning: insights file {p} not found; rows get price and ASX filings only", file=sys.stderr)
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    out: dict[str, dict[str, dict]] = {}
    for scope in ("morning", "close"):
        for t, e in (raw.get(scope) or {}).items():
            t = str(t).upper()
            if not isinstance(e, dict):
                continue
            text = " ".join(str(e.get("insight") or "").split())
            srcs = [{"label": str(s.get("label") or "Source").strip(), "url": str(s["url"]).strip(),
                     **({"claim_type": s["claim_type"]} if s.get("claim_type") else {})}
                    for s in (e.get("sources") or [])
                    if isinstance(s, dict) and str(s.get("url") or "").startswith("https://")]
            if not text or not srcs:
                print(f"warning: insight {scope}:{t} dropped (needs text and an https source)", file=sys.stderr)
                continue
            if len(text) > INSIGHT_MAX_CHARS:
                print(f"warning: insight {scope}:{t} dropped (over {INSIGHT_MAX_CHARS} chars)", file=sys.stderr)
                continue
            out.setdefault(scope, {})[t] = {"insight": text, "insight_sources": srcs}
    return out


def apply_insight(item: dict, ins: dict | None) -> dict:
    """Merge a sourced insight into an unreviewed row (reviewed rows already carry their note)."""
    if ins and not item.get("reviewed"):
        item["insight"] = ins["insight"]
        item["insight_sources"] = ins["insight_sources"]
    return item


def merge_into_existing(dest: Path, insights: dict) -> list[str]:
    data = json.loads(dest.read_text())
    done = []
    for scope, ed in (data.get("editions") or {}).items():
        for t, item in (ed.get("items") or {}).items():
            ins = insights.get(scope, {}).get(t)
            if ins and not item.get("reviewed"):
                apply_insight(item, ins)
                done.append(f"{scope}:{t}")
    dest.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"insights merged into {dest}: {done or 'none'}")
    return done


def reader_tickers(api: str) -> list[str] | None:
    """Union of all readers' picked codes from the Worker, or None if unavailable."""
    import os
    tok = os.environ.get("SIGNALETTER_ADMIN_TOKEN") or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "")
    if not tok:
        print(f"warning: no admin token ({TOKEN_FILE}); reader picks not included", file=sys.stderr)
        return None
    req = urllib.request.Request(api.rstrip("/") + "/admin/tickers", headers={**UA, "Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        return [str(t).upper() for t in data.get("tickers", [])]
    except Exception as e:  # noqa: BLE001
        print(f"warning: reader tickers unavailable ({e}); reader picks not included", file=sys.stderr)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--tickers-file")
    ap.add_argument("--no-readers", action="store_true", help="don't add readers' picks from the Worker")
    ap.add_argument("--api", default=API)
    ap.add_argument("--add", default="", help="additive mode: comma list of tickers to add to the existing "
                    "file; existing entries are never changed or removed; new entries get quick: true")
    ap.add_argument("--insights", help="YAML of sourced insights for reader picks (see module doc)")
    ap.add_argument("--list-picks", action="store_true",
                    help="print reader picks beyond the default list (they need insights) and exit")
    ap.add_argument("--merge-only", action="store_true",
                    help="with --insights: merge insights into the existing watchlist.json (no refetch) and exit")
    args = ap.parse_args()
    if args.merge_only:
        merge_into_existing(ROOT / "assets" / "issues" / args.date / "watchlist.json", load_insights(args.insights))
        return
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    if args.tickers_file:
        tickers += [x.strip().upper() for x in Path(args.tickers_file).read_text().split() if x.strip()]
    add_mode = bool(args.add.strip())
    if add_mode:
        tickers = [x.strip().upper() for x in args.add.split(",") if x.strip()]
        args.no_readers = True
    if not tickers:
        tickers = DEFAULT_TICKERS.read_text().split()
    readers = None if args.no_readers else reader_tickers(args.api)
    allowed = {r["code"]: r["name"] for r in json.loads((ROOT / "assets/data/asx-tickers.json").read_text())["tickers"]}
    if readers:
        skipped = [t for t in readers if t not in allowed]
        if skipped:
            print(f"warning: reader picks not in allowed list, skipped: {skipped}", file=sys.stderr)
        tickers += [t for t in readers if t in allowed]
    bad = [t for t in tickers if t not in allowed]
    if bad:
        sys.exit(f"not in allowed list: {bad}")
    tickers = sorted(set(tickers))
    if args.list_picks:
        defaults = set(DEFAULT_TICKERS.read_text().split())
        print(" ".join(t for t in tickers if t not in defaults))
        return
    insights = load_insights(args.insights)

    post = load_post(args.date)
    editions = {"morning": post}
    if post.get("close"):
        editions["close"] = post["close"]

    closes, anns = {}, {}
    for t in tickers:
        try:
            closes[t] = yahoo_closes(t)
        except Exception as e:  # noqa: BLE001
            print(f"yahoo {t}: {e}", file=sys.stderr); closes[t] = None
        try:
            anns[t] = announcements(t)
        except Exception as e:  # noqa: BLE001
            print(f"asx {t}: {e}", file=sys.stderr); anns[t] = None

    day = dt.date.fromisoformat(args.date)
    out = {
        "schema": "signaletter.watchlist/v1",
        "date": args.date,
        "generated_by": "scripts/build_watchlist_json.py",
        "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "disclaimer": "Information only, not financial advice. Prices delayed and unofficial.",
        "editions": {},
    }
    for scope, ed in editions.items():
        cutoff = dt.datetime.fromisoformat(str(ed["cutoff_local"]))
        quotes = {q["id"]: q for q in (ed.get("snapshot") or {}).get("quotes", [])}
        reviewed = {w["ticker"]: w for w in (ed.get("watchlist") or [])}
        if scope == "morning":
            # previous ASX session = the session of the post's ASX 200 quote, else the latest close before today
            asx = quotes.get("asx200") or {}
            session = asx.get("market_session_date")
            if not session:
                any_c = next((c for c in closes.values() if c), {})
                session = max(d for d in any_c if d < args.date)
            start = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(0, 0), SYD)
            session_word = "on " + dt.date.fromisoformat(session).strftime("%A")
        else:
            session = args.date
            start = dt.datetime.combine(day, dt.time(0, 0), SYD)
            session_word = "on " + day.strftime("%A")
        items = {}
        for t in tickers:
            px = price_block(t, closes.get(t), session, quotes.get(f"wl_{t.lower()}"))
            auto = note_from_announcements(t, anns.get(t), start, cutoff, px, session_word)
            if t in reviewed:
                r = reviewed[t]
                body = {"note": r["note"], "sources": r.get("sources") or [], "reviewed": True}
                if r.get("next_catalyst"):
                    body["next_catalyst"] = r["next_catalyst"]
            else:
                body = dict(auto)
                body["reviewed"] = False
            body["price_note"] = auto["note"]
            items[t] = apply_insight({"ticker": t, "name": allowed[t], "price": px, **body},
                                     insights.get(scope, {}).get(t))
        out["editions"][scope] = {
            "cutoff_local": str(ed["cutoff_local"]), "session_date": session,
            "announcement_window_local": [start.isoformat(), cutoff.isoformat()], "items": items,
        }
    dest = ROOT / "assets" / "issues" / args.date / "watchlist.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if add_mode and dest.exists():
        cur = json.loads(dest.read_text())
        added = []
        for scope, ed in out["editions"].items():
            tgt = cur.setdefault("editions", {}).setdefault(scope, {k: v for k, v in ed.items() if k != "items"} | {"items": {}})
            for t, item in ed["items"].items():
                if t not in tgt["items"]:
                    tgt["items"][t] = {**item, "quick": True, "added_at_utc": out["retrieved_at_utc"]}
                    added.append(f"{scope}:{t}")
        dest.write_text(json.dumps(cur, indent=1, ensure_ascii=False) + "\n")
        print(f"added to {dest}: {added or 'nothing (already present)'}")
        return
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    extra = sorted(set(readers or []) - set(DEFAULT_TICKERS.read_text().split()))
    print(f"wrote {dest}: {len(tickers)} tickers x {list(out['editions'])}; reader picks "
          f"{'unavailable' if readers is None else len(readers)}; added beyond defaults: {extra}")


if __name__ == "__main__":
    main()
