#!/usr/bin/env python3
"""Export runs over every post, writes the expected layout, and leaks no branding."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import export_feed  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        subprocess.run([sys.executable, str(ROOT / "scripts/export_feed.py"), tmp], check=True)
        index = json.loads((out / "index.json").read_text())
        assert index["days"], "no days exported"
        for kind in ("markets", "ai"):
            latest = json.loads((out / "latest" / f"{kind}.json").read_text())
            assert latest["type"] == kind and latest["date"] == index["latest"][kind]
        posts = {p.name[:10] for p in (ROOT / "_posts").glob("*.md")}
        assert {d["date"] for d in index["days"]} >= posts
        blob = "\n".join(p.read_text() for p in out.rglob("*.json"))
        assert not re.search(r"signaletter|little made|briefing@|workers\.dev|\]\(/", blob, re.I)
        # Unchanged content keeps its timestamp (no churn commits).
        before = (out / "latest/markets.json").read_text()
        subprocess.run([sys.executable, str(ROOT / "scripts/export_feed.py"), tmp], check=True)
        assert (out / "latest/markets.json").read_text() == before
    # Site links collapse to their label; forbidden text fails the export.
    assert export_feed.clean("see [Markets](/2026/10/25/markets/)") == "see Markets"
    try:
        export_feed.assert_unbranded({"x": "SignaLetter"}, "t")
    except SystemExit:
        pass
    else:
        raise AssertionError("branding not caught")
    print("export_feed tests passed")


if __name__ == "__main__":
    main()
