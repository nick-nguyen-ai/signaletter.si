#!/usr/bin/env python3
"""Export each day's Markets and AI posts as plain, unbranded JSON.

Usage: python3 scripts/export_feed.py OUT_DIR

Writes (overwriting) for every date found in _posts/:
  OUT_DIR/days/YYYY-MM-DD/markets.json   markets briefing (+ close wrap) and watchlist data
  OUT_DIR/days/YYYY-MM-DD/ai.json        AI report cards
  OUT_DIR/latest/markets.json            newest markets.json
  OUT_DIR/latest/ai.json                 newest ai.json
  OUT_DIR/index.json                     dates and files available
Files for dates no longer in _posts/ are left untouched.
Branding, site links and build metadata are removed; the export fails if any remain.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
DISCLAIMER = "Information only, not financial advice. Prices are delayed and unofficial."

# Anything matching this must never reach the export.
FORBIDDEN = re.compile(r"signa\s*letter|signaletter|little\s*made|briefing@|workers\.dev", re.I)
# Markdown links whose target is the site itself (relative or own domain): keep the label only.
SITE_LINK = re.compile(r"\[([^\]]*)\]\((?:/[^)]*|https?://(?:www\.)?signaletter\.si[^)]*)\)", re.I)

DROP_KEYS = {
    "generated_by", "rerendered_from", "format", "dropped", "long_run_charts",
    "reviewed", "from", "schema", "layout", "permalink", "section",
}


def clean(x):
    """Recursively drop build-only keys and site links; normalise dates."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items() if k not in DROP_KEYS}
    if isinstance(x, list):
        return [clean(v) for v in x]
    if isinstance(x, (dt.datetime, dt.date)):
        return x.isoformat()
    if isinstance(x, str):
        return SITE_LINK.sub(r"\1", x)
    return x


def assert_unbranded(obj, where):
    blob = json.dumps(obj, ensure_ascii=False)
    m = FORBIDDEN.search(blob)
    if m:
        raise SystemExit(f"export_feed: forbidden text {m.group(0)!r} in {where}")


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path}: no front matter")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def edition_block(fm: dict) -> dict:
    snap = fm.get("snapshot") or {}
    return clean({
        "cutoff_local": fm.get("cutoff_local"),
        "session_note": fm.get("session_note"),
        "summary": fm.get("summary") or [],
        "prices": {
            "retrieved_at_utc": snap.get("retrieved_at_utc"),
            "cutoff_utc": snap.get("cutoff_utc"),
            "quotes": snap.get("quotes") or [],
        },
        "sections": fm.get("sections") or [],
        "rates": fm.get("rates") or {},
        "watchlist": fm.get("watchlist") or [],
        "calendar": fm.get("calendar") or [],
    })


def watchlist_data(date: str):
    p = ROOT / "assets" / "issues" / date / "watchlist.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for name, ed in (d.get("editions") or {}).items():
        out[name] = clean({
            "cutoff_local": ed.get("cutoff_local"),
            "session_date": ed.get("session_date"),
            "stocks": ed.get("items") or {},
        })
    return {"retrieved_at_utc": d.get("retrieved_at_utc"), "editions": out}


def export_markets(date: str, fm: dict, now: str) -> dict:
    close = fm.get("close")
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "markets",
        "date": date,
        "generated_at_utc": now,
        "title": fm.get("title"),
        "edition": fm.get("edition"),
        "morning": edition_block(fm),
        "close": edition_block(close) if close else None,
        "watchlist_data": watchlist_data(date),
        "disclaimer": DISCLAIMER,
    }


def export_ai(date: str, fm: dict, now: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "ai",
        "date": date,
        "generated_at_utc": now,
        "title": fm.get("title"),
        "top_stories": clean(fm.get("signal") or []),
        "sections": clean(fm.get("sections") or []),
    }


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = Path(argv[1])
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    built: dict[str, dict] = {}
    for post in sorted((ROOT / "_posts").glob("*.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(markets|ai)\.md$", post.name)
        if not m:
            continue
        date, kind = m.groups()
        fm = front_matter(post)
        obj = export_markets(date, fm, now) if kind == "markets" else export_ai(date, fm, now)
        assert_unbranded(obj, post.name)
        built.setdefault(date, {})[kind] = obj

    for date, kinds in built.items():
        for kind, obj in kinds.items():
            target = out / "days" / date / f"{kind}.json"
            # Keep the file byte-identical when content hasn't changed (no timestamp-only commits).
            if target.exists():
                old = json.loads(target.read_text(encoding="utf-8"))
                if {**old, "generated_at_utc": None} == {**obj, "generated_at_utc": None}:
                    obj["generated_at_utc"] = old.get("generated_at_utc")
            write_json(target, obj)

    # Index covers everything present in OUT_DIR (including days kept from earlier runs).
    days = []
    for d in sorted((out / "days").glob("????-??-??"), reverse=True):
        files = sorted(p.name for p in d.glob("*.json"))
        if files:
            days.append({"date": d.name, "files": files})
    latest = {}
    for kind in ("markets", "ai"):
        newest = next((x["date"] for x in days if f"{kind}.json" in x["files"]), None)
        latest[kind] = newest
        if newest:
            src = out / "days" / newest / f"{kind}.json"
            write_json(out / "latest" / f"{kind}.json", json.loads(src.read_text(encoding="utf-8")))
    index = {"schema_version": SCHEMA_VERSION, "latest": latest, "days": days}
    assert_unbranded(index, "index.json")
    write_json(out / "index.json", index)
    print(f"export_feed: {len(built)} day(s) exported; latest markets={latest['markets']} ai={latest['ai']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
