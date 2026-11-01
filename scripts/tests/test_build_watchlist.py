#!/usr/bin/env python3
"""Insight merge for reader picks in scripts/build_watchlist_json.py (run directly)."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build_watchlist_json as b  # noqa: E402


def _write(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
    f.write(text); f.close()
    return f.name


GOOD = """
morning:
  bhp:
    insight: "Miners rose   with iron ore."
    sources: [{label: Reuters, url: "https://www.reuters.com/x"}]
  CBA:
    insight: "Banks fell."
    sources: [{label: Blog, url: "http://insecure.example"}]
  WES:
    insight: ""
    sources: [{label: X, url: "https://x.example"}]
close:
  BHP:
    insight: "%s"
    sources: [{label: R, url: "https://r.example"}]
""" % ("x" * 700)


def test_load_insights_requires_text_and_https_source():
    ins = b.load_insights(_write(GOOD))
    assert ins["morning"]["BHP"]["insight"] == "Miners rose with iron ore."
    assert ins["morning"]["BHP"]["insight_sources"][0]["url"] == "https://www.reuters.com/x"
    assert "CBA" not in ins["morning"], "no https source -> dropped"
    assert "WES" not in ins["morning"], "empty text -> dropped"
    assert "close" not in ins, "over length -> dropped"


def test_missing_or_absent_file():
    assert b.load_insights(None) == {}
    assert b.load_insights("/nonexistent/insights.yml") == {}


def test_apply_insight_only_on_unreviewed():
    ins = {"insight": "a", "insight_sources": [{"label": "s", "url": "https://s"}]}
    assert b.apply_insight({"reviewed": False}, ins)["insight"] == "a"
    assert "insight" not in b.apply_insight({"reviewed": True}, ins)
    assert "insight" not in b.apply_insight({"reviewed": False}, None)


def test_merge_into_existing():
    d = Path(tempfile.mkdtemp()) / "watchlist.json"
    d.write_text(json.dumps({"editions": {"morning": {"items": {
        "BHP": {"reviewed": False, "note": "n", "price_note": "n"},
        "ZIP": {"reviewed": True, "note": "r", "price_note": "p"}}}}}))
    ins = {"morning": {"BHP": {"insight": "i", "insight_sources": [{"label": "s", "url": "https://s"}]},
                       "ZIP": {"insight": "j", "insight_sources": [{"label": "s", "url": "https://s"}]}}}
    assert b.merge_into_existing(d, ins) == ["morning:BHP"]
    out = json.loads(d.read_text())["editions"]["morning"]["items"]
    assert out["BHP"]["insight"] == "i" and "insight" not in out["ZIP"]


def test_basic_tier_note_is_price_and_filings_only():
    px = {"status": "ok", "display_change": "+2.3%", "display_value": "45.10"}
    n = b.note_from_announcements("BHP", [], b.dt.datetime(2026, 10, 30, tzinfo=b.SYD),
                                  b.dt.datetime(2026, 10, 31, tzinfo=b.SYD), px, "on Friday")
    assert n["note"] == "Rose 2.3% to A$45.10 on Friday. No new ASX announcement."


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                failed += 1; print("FAIL", name, repr(e))
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
