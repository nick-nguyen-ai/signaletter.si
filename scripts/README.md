# Asset generation (Direction C)

Requires **Pillow** and **librsvg2-bin** (`rsvg-convert`).
OG generation uses TTFs under `scripts/fonts/` (Source Serif 4 + IBM Plex Mono).

```bash
pip install Pillow
python3 scripts/generate_brand.py   # favicon.ico, apple-touch, icon-192/512
python3 scripts/generate_og.py      # assets/og/*-v2.png (+ legacy name copies)
```

# Markets v2 pipeline

```bash
pip install pyyaml jsonschema
python3 scripts/fetch_markets.py --issue-date 2026-10-19 --edition weekday --out snapshot.json
python3 scripts/build_markets_post.py --content markets-content.yml --snapshot snapshot.json --out _posts/2026-10-19-markets.md
python3 scripts/qa_markets.py --fix _posts/2026-10-19-markets.md
python3 scripts/tests/test_qa_markets.py

# After the ASX close (~16:30 Sydney): close snapshot + merge into the same post
python3 scripts/fetch_markets.py --issue-date 2026-10-19 --edition weekday --close --out assets/issues/2026-10-19/close-snapshot.json
python3 scripts/build_markets_post.py --close close-content.yml --snapshot assets/issues/2026-10-19/close-snapshot.json --out _posts/2026-10-19-markets.md
python3 scripts/qa_markets.py --fix _posts/2026-10-19-markets.md
```
`qa_markets.py` exits 0 = no unresolved errors (warnings OK), 1 = errors remain (after `--fix`, errors it
cannot drop), 2 = unparseable. The auto-merge gate runs it report-only and blocks on 1 or 2, so always run
`--fix` before committing and fix anything it reports as UNRESOLVED.

# Long-run chart CSVs (Brent + Gold)

Updates `_data/brent.csv` (FRED `DCOILBRENTEU`) and `_data/gold.csv` (Yahoo `GC=F`)
with new settled daily closes. Idempotent; skips missing/`.` values and Yahoo's
in-progress same-day bar until the COMEX session close (~17:00 America/New_York).

```bash
# Daily publish routine (after session closes; safe to re-run):
python3 scripts/update_charts.py

python3 scripts/update_charts.py --series brent          # one series
python3 scripts/update_charts.py --dry-run               # fetch/merge, no write
python3 scripts/tests/test_update_charts.py
```

# Auto-merge path gate

```bash
python3 scripts/check_pr_paths.py origin/main HEAD      # deletions + renames included; _posts/**, assets/issues/**, _data/*.csv only
python3 scripts/tests/test_check_pr_paths.py
```
Daily `cursor/issue-*` PRs may include chart CSV updates (`_data/brent.csv`, `_data/gold.csv`).
See docs/markets-post-format.md.
