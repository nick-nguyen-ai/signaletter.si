#!/usr/bin/env python3
"""Acceptance tests for scripts/qa_markets.py (spec K: the QA must reject a
fabricated number, a conflicting same-contract quote, a biased/unsupported
claim and an invented market probability). Run: python3 scripts/tests/test_qa_markets.py"""
import copy
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import qa_markets as qa  # noqa: E402

POST = sorted(glob.glob(os.path.join(HERE, "..", "..", "_posts", "*-markets.md")))[-1]
BASE, _ = qa.split_front_matter(open(POST, encoding="utf-8").read())


def run(fm, fix=True):
    rep = qa.Report("test")
    qa.qa(fm, rep, fix)
    return rep


def quote(fm, qid):
    return next(q for q in fm["snapshot"]["quotes"] if q["id"] == qid)


def test_clean_post_passes():
    rep = run(copy.deepcopy(BASE), fix=False)
    assert not rep.errors, rep.errors


def test_fabricated_number_rejected():
    fm = copy.deepcopy(BASE)
    quote(fm, "asx200")["display_value"] = "9,999.9"  # number not backed by the record
    rep = run(fm)
    assert any("math" in e for e in rep.errors), rep.errors
    assert quote(fm, "asx200")["status"] == "unavailable"
    assert any(d["item"] == "snapshot:asx200" for d in fm["dropped"])


def test_bad_change_math_rejected():
    fm = copy.deepcopy(BASE)
    q = quote(fm, "us10y")
    q["change_bp"] = round(q["change_bp"] + 7.0, 1)  # always differs from the true change
    rep = run(fm)
    assert any("change_bp" in e for e in rep.errors), rep.errors


def test_percent_used_for_yield_rejected():
    fm = copy.deepcopy(BASE)
    quote(fm, "au10y")["change_unit"] = "pct"
    rep = run(fm)
    assert any(e.startswith("[units]") for e in rep.errors), rep.errors


def test_same_instrument_conflict_held():
    fm = copy.deepcopy(BASE)
    q = quote(fm, "sp500")
    q["cross_checks"] = [{"provider": "Second feed", "value": q["value"] * 1.02, "session_date": q["market_session_date"]}]
    rep = run(fm)
    assert any(e.startswith("[conflict]") for e in rep.errors), rep.errors
    assert quote(fm, "sp500")["status"] == "unavailable"


def test_observation_after_cutoff_rejected():
    fm = copy.deepcopy(BASE)
    quote(fm, "vix")["observation_timestamp_utc"] = "2099-01-01T00:00:00Z"
    rep = run(fm)
    assert any(e.startswith("[time]") for e in rep.errors), rep.errors


def test_demo_placeholder_rejected():
    fm = copy.deepcopy(BASE)
    fm["sections"][0]["cards"][0]["headline"] = "ILLUSTRATIVE ONLY example headline"
    rep = run(fm)
    assert any(e.startswith("[placeholder]") for e in rep.errors), rep.errors
    assert all(c["headline"].find("ILLUSTRATIVE") < 0 for s in fm["sections"] for c in s["cards"])


def test_invented_probability_rejected():
    fm = copy.deepcopy(BASE)
    fm["rates"]["rba"] = {"status": "available", "summary": "62% chance of a hike"}  # no source, no as-of
    rep = run(fm)
    assert any(e.startswith("[pricing]") or e.startswith("[schema]") for e in rep.errors), rep.errors
    assert fm["rates"]["rba"]["status"] == "unavailable"


def test_unsourced_claim_dropped():
    fm = copy.deepcopy(BASE)
    card = copy.deepcopy(fm["sections"][-1]["cards"][0])
    card["id"] = "unsourced"
    card["sources"] = [{"label": "Somebody", "url": "not-a-url"}]
    fm["sections"][-1]["cards"].append(card)
    run(fm)
    assert all(c["id"] != "unsourced" for c in fm["sections"][-1]["cards"])


def test_consensus_needs_named_source():
    fm = copy.deepcopy(BASE)
    # Don't depend on the live post: its first calendar row may already carry a
    # consensus_source (4 Nov did), which made this test fail intermittently.
    row = fm["calendar"][0]
    row.pop("consensus_source", None)
    row["consensus"] = "4.6%"
    rep = run(fm)
    assert any(e.startswith("[consensus]") for e in rep.errors), rep.errors
    assert "consensus" not in fm["calendar"][0], rep.errors


def test_consensus_with_named_source_kept():
    fm = copy.deepcopy(BASE)
    row = fm["calendar"][0]
    row["consensus"] = "4.6%"
    row["consensus_source"] = "Reuters poll"
    rep = run(fm)
    assert not any(e.startswith("[consensus]") for e in rep.errors), rep.errors
    assert row.get("consensus") == "4.6%"


def test_loaded_language_flagged():
    fm = copy.deepcopy(BASE)
    fm["sections"][-1]["cards"][0]["what_happened"] += " Critics slammed the move. Reuters reports more."
    rep = run(fm, fix=False)
    assert sum(w.startswith("[language]") for w in rep.warnings) >= 2, rep.warnings


# ---------- CLI exit codes: the auto-merge gate relies on these ----------
import subprocess  # noqa: E402
import tempfile  # noqa: E402

SCRIPT = os.path.join(HERE, "..", "qa_markets.py")
RECENT = [p for p in sorted(glob.glob(os.path.join(HERE, "..", "..", "_posts", "*-markets.md")))
          if os.path.basename(p) >= "2026-10-22"]


def cli(fm, *flags, raw=None):
    with tempfile.NamedTemporaryFile("w", suffix="-markets.md", delete=False, encoding="utf-8") as f:
        f.write(raw if raw is not None else qa.dump(fm, "\n"))
        path = f.name
    res = subprocess.run([sys.executable, SCRIPT, *flags, path], capture_output=True, text=True)
    return res, path


def test_recent_issues_pass_report_only():
    assert RECENT, "no recent posts found"
    for p in RECENT:
        res = subprocess.run([sys.executable, SCRIPT, p], capture_output=True, text=True)
        assert res.returncode == 0, (p, res.stdout)


def test_cli_invalid_number_exits_nonzero():
    fm = copy.deepcopy(BASE)
    quote(fm, "asx200")["display_value"] = "9,999.9"
    res, _ = cli(fm)
    assert res.returncode == 1 and "FAIL" in res.stdout, res.stdout


def test_cli_missing_source_exits_nonzero():
    fm = copy.deepcopy(BASE)
    fm["sections"][-1]["cards"][0]["sources"] = []
    res, _ = cli(fm)
    assert res.returncode == 1, res.stdout


def test_cli_bad_date_exits_nonzero():
    fm = copy.deepcopy(BASE)
    q = quote(fm, "us10y")
    q["comparison_date"] = q["market_session_date"]
    res, _ = cli(fm)
    assert res.returncode == 1, res.stdout


def test_cli_invalid_schema_exits_nonzero():
    fm = copy.deepcopy(BASE)
    fm["snapshot"]["quotes"][0]["status"] = "maybe"
    res, _ = cli(fm)
    assert res.returncode == 1 and "[schema]" in res.stdout, res.stdout


def test_cli_unsupported_probability_exits_nonzero():
    fm = copy.deepcopy(BASE)
    fm["rates"]["rba"] = {"status": "available", "summary": "62% chance of a hike"}
    res, _ = cli(fm)
    assert res.returncode == 1, res.stdout


def test_cli_malformed_front_matter_is_fatal():
    res, _ = cli(None, raw="---\nformat: markets-v2\n  bad: [unclosed\n---\nbody\n")
    assert res.returncode == 2 and "FATAL" in res.stdout, res.stdout
    res, _ = cli(None, raw="no front matter here\n")
    assert res.returncode == 2, res.stdout


def test_cli_fix_removes_fixable_errors_then_passes():
    fm = copy.deepcopy(BASE)
    quote(fm, "asx200")["display_value"] = "9,999.9"
    fm["calendar"][0]["consensus"] = "4.6%"
    fm["calendar"][0].pop("consensus_source", None)
    res, path = cli(fm, "--fix")
    assert res.returncode == 0 and "PASS_WITH_DROPS" in res.stdout, res.stdout
    again = subprocess.run([sys.executable, SCRIPT, path], capture_output=True, text=True)
    assert again.returncode == 0, again.stdout  # the fixed file is clean for the gate
    fixed, _ = qa.split_front_matter(open(path, encoding="utf-8").read())
    assert quote(fixed, "asx200")["status"] == "unavailable"
    assert any(d["item"] == "snapshot:asx200" for d in fixed["dropped"])


def test_cli_fix_cannot_hide_unfixable_errors():
    fm = copy.deepcopy(BASE)
    fm["summary"] = fm["summary"][:2]  # wrong bullet count: nothing to drop
    res, _ = cli(fm, "--fix")
    assert res.returncode == 1 and "UNRESOLVED" in res.stdout, res.stdout
    fm = copy.deepcopy(BASE)
    fm["summary"][0] = "TODO write this"
    res, _ = cli(fm, "--fix")
    assert res.returncode == 1, res.stdout


def test_warnings_alone_do_not_block():
    fm = copy.deepcopy(BASE)
    fm["sections"][-1]["cards"][0]["what_happened"] += " Critics slammed the move."
    res, _ = cli(fm)
    assert res.returncode == 0 and "[language]" in res.stdout, res.stdout


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
