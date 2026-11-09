# Changelog

All notable changes to SignaLetter (code, workflows, layout, scripts, Worker, docs).
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), newest first, dates in Sydney time.
Daily content PRs (`cursor/issue-*`) are not listed one by one.

**Every PR that changes non-content files must add an entry under `[Unreleased]`** (CI enforces this; see AGENTS.md).
Entry shape: what changed and why, key files, PR link.

## [Unreleased]

### Fixed (2026-11-09)
- Weekday Markets pages looked half-empty on laptops. Morning/Close tabs hide the
  left section sidebar (each tab has its own chip nav), and the CSS already
  dropped the empty grid column, but `.site-main` stayed a left-aligned 40rem
  (640px) column inside the 72rem shell. The article is now centred at 48rem.
  Weekend Markets (sidebar visible) and AI pages are unchanged. Files:
  `assets/css/nav.css`, `_layouts/default.html` (cache-bust `nav.css` to `?v=8`).

### Changed (2026-11-09)
- Public data feed omits individual shares. `export_feed.py` no longer writes the default
  watchlist, reader-pick stock rows, or `watchlist_data` into `markets.json`; the general
  market update (summary, story cards, index/commodity quotes, rates, calendar, close wrap)
  and `ai.json` stay as they are. Why: the internal consumer only needs the general market
  and AI updates. Files: `scripts/export_feed.py`, `scripts/tests/test_export_feed.py`,
  `ARCHITECTURE.md`. [#72](https://github.com/nick-nguyen-ai/signaletter.si/pull/72).
- Also drop per-share price rows (`tier: watchlist` / `wl_*` ids) from `prices.quotes`
  in the markets export. Files: `scripts/export_feed.py`, `scripts/tests/test_export_feed.py`.
  [#73](https://github.com/nick-nguyen-ai/signaletter.si/pull/73).

### Fixed (2026-11-05)
- Auto-merge now waits for CI. `auto-merge-issues.yml` merged daily `cursor/issue-*` PRs even when CI
  jobs failed (#61, #62 merged with `python` red). It now polls the PR head's check runs and squash-merges
  only once `python`, `jekyll`, `worker` and `changelog` all succeed; a failure or 40-minute timeout
  leaves the PR open with an error naming the failed job. Files: `.github/workflows/auto-merge-issues.yml`.
- Flaky `test_consensus_needs_named_source`. The test builds on the newest live Markets post; the 4 Nov
  post's first calendar row already had a `consensus_source`, so adding a consensus raised no error and
  the test failed on that day's PRs. The test now removes `consensus_source` first and asserts the
  `[consensus]` error; a new test checks a sourced consensus is kept. Files: `scripts/tests/test_qa_markets.py`.
  PR #65.

### Changed (2026-11-05, routines outside the repo)
- The daily publish and close-wrap routines push branches and open PRs with `gh` directly instead of
  using cloud agents (they kept failing with "must be a collaborator"). The morning issue reuses the
  previous close's reader-pick insights unless there is new news; the quality review re-checks flagged
  items plus a sample. Why: cut usage as the reader-pick list grows. Documented in `ARCHITECTURE.md`.

### Added
- Reader-pick insights and an info-tier flag for "My shares" (PR #57). Rows for reader picks can carry a
  short, neutral, sourced `insight` (company news, sector/index, peers, macro) merged from the routine's
  `watchlist-insights.yml` via `build_watchlist_json.py --insights FILE [--merge-only]`; unsourced or
  non-https entries are dropped. Every row gains `price_note` (price + ASX filings only).
  `watchlist_info_tier` in `_config.yml` (`basic` | `full`, default `full`) sets the page tier; a `tier`
  field on the reader's KV record `user:<email>` (returned by `GET /me`) overrides it, ready to map to a
  subscription level. Why: reader-pick rows only said "No new ASX announcement". Files:
  `scripts/build_watchlist_json.py`, `assets/js/my-watchlist.js`, `_layouts/default.html`,
  `worker/src/index.js`, tests `scripts/tests/test_build_watchlist.py`,
  `scripts/tests/test_watchlist_tier.mjs`, `worker/test/worker.spec.mjs`.
- `CHANGELOG.md` (backfilled from PR history), `ARCHITECTURE.md`, `AGENTS.md`, a PR template, and a CI
  `changelog` job (`scripts/check_changelog.py`) that fails a PR touching non-content files without a
  `CHANGELOG.md` change. Why: keep a reviewable record of every feature change for Nick and other coding
  agents. `cursor/issue-*` branches and content-only PRs (`_posts/`, `assets/issues/`) are exempt.

## Daily issues (ongoing)
- 2026-10-17 → present: daily Markets/AI issue and close-wrap PRs from `cursor/issue-*` branches
  (#6 … #55, 26 PRs at the time of writing), auto-merged by `auto-merge-issues.yml`. Content only:
  `_posts/`, `assets/issues/<date>/`, `_data/*.csv`.

## 2026-10-25
### Added
- Data export: each day's Markets and AI posts are written as plain, unbranded JSON to a separate public
  data repo after merges, quick-adds and on a 3-hourly schedule. Why: a reusable public feed. Files:
  `scripts/export_feed.py`, `.github/workflows/data-export.yml`, `scripts/tests/test_export_feed.py`, `ci.yml`.
  [#43](https://github.com/nick-nguyen-ai/signaletter.si/pull/43)

## 2026-10-24
### Added
- Cloudflare Pages prep: `404.html` and `.ruby-version` (move paused). [#41](https://github.com/nick-nguyen-ai/signaletter.si/pull/41)
- Sign-in entry points: header link and landing-page email box. Files: `_includes/top-nav.html`,
  `index.html`, `assets/js/my-watchlist.js`, `assets/css/watchlist.css`. [#39](https://github.com/nick-nguyen-ai/signaletter.si/pull/39)
### Fixed
- Review hardening: auto-merge path gate (`scripts/check_pr_paths.py`, run from base branch, deletions and
  renames counted), QA errors now block merge, session revocation and single-use sign-in links via a
  Durable Object, and a new CI workflow (`.github/workflows/ci.yml`) with Worker, Python and Jekyll jobs.
  [#40](https://github.com/nick-nguyen-ai/signaletter.si/pull/40)

## 2026-10-23
### Added
- My shares instant add: when a reader saves a ticker missing from the day's `watchlist.json`, the Worker
  dispatches `watchlist-add.yml` to add it. Files: `.github/workflows/watchlist-add.yml`, `worker/src/index.js`,
  `scripts/build_watchlist_json.py`. [#37](https://github.com/nick-nguyen-ai/signaletter.si/pull/37)
- Reader picks included in daily `watchlist.json` (union via Worker `GET /admin/tickers`) and the S&P/ASX 300
  ticker universe. Files: `scripts/build_watchlist_json.py`, `scripts/build_asx_list.py`,
  `assets/data/asx-tickers.json`, `docs/my-watchlist.md`. [#36](https://github.com/nick-nguyen-ai/signaletter.si/pull/36)
- My shares: per-reader watchlist on Markets pages, backed by the Cloudflare Worker (off until
  `watchlist_api` is set). Files: `assets/js/my-watchlist.js`, `watchlist.html`, `_includes/markets/edition-body.html`,
  `worker/`. [#35](https://github.com/nick-nguyen-ai/signaletter.si/pull/35)

## 2026-10-19
### Added
- Markets Morning / Close tabs (close wrap edition). Files: `_includes/markets-report.html`,
  `_includes/markets/edition-body.html`, `assets/css/markets.css`. [#26](https://github.com/nick-nguyen-ai/signaletter.si/pull/26)

## 2026-10-18
### Changed
- Site moved to apex domain signaletter.si (`CNAME`, `_config.yml`, meta). [#24](https://github.com/nick-nguyen-ai/signaletter.si/pull/24)
- Cache-busted brand OG images and icons. [#23](https://github.com/nick-nguyen-ai/signaletter.si/pull/23)
- New SignaLetter logo and wordmark (`assets/brand/`). [#22](https://github.com/nick-nguyen-ai/signaletter.si/pull/22)
- AI daily briefing reading experience (`_includes/ai-report.html`, `assets/css/ai-cards.css`, `assets/js/ai-cards.js`). [#21](https://github.com/nick-nguyen-ai/signaletter.si/pull/21)
- Renamed the site to signaletter.si. [#20](https://github.com/nick-nguyen-ai/signaletter.si/pull/20)
- Markets data: Cboe official VIX CSV first (`scripts/fetch_markets.py`). [#19](https://github.com/nick-nguyen-ai/signaletter.si/pull/19)
- Markets v2 redesign: snapshot-driven dashboard, story cards, `fetch_markets.py`, `build_markets_post.py`,
  `qa_markets.py`, schema in `docs/schemas/`. [#17](https://github.com/nick-nguyen-ai/signaletter.si/pull/17)
### Fixed
- Touch scrolling on Markets v2 pages (`assets/js/section-nav.js`). [#18](https://github.com/nick-nguyen-ai/signaletter.si/pull/18)

## 2026-10-17
### Added
- Direction C brand: OG cards and favicons (`scripts/generate_og.py`, `scripts/generate_brand.py`). [#13](https://github.com/nick-nguyen-ai/signaletter.si/pull/13)
- AI card format from front matter. [#12](https://github.com/nick-nguyen-ai/signaletter.si/pull/12)
- AI page prototype (`prototype/`). [#11](https://github.com/nick-nguyen-ai/signaletter.si/pull/11)
### Fixed
- Duplicate Markets section headers. [#15](https://github.com/nick-nguyen-ai/signaletter.si/pull/15)
- Android share preview: share URL only. [#14](https://github.com/nick-nguyen-ai/signaletter.si/pull/14)

## 2026-10-16
### Added
- Share button (Web Share API + fallback) and OG images. [#10](https://github.com/nick-nguyen-ai/signaletter.si/pull/10)
- Auto-merge of daily issue PRs (`cursor/issue-*`) with Pages rebuild (`.github/workflows/auto-merge-issues.yml`). [#7](https://github.com/nick-nguyen-ai/signaletter.si/pull/7)
- Mobile-first layout and PWA manifest. [#5](https://github.com/nick-nguyen-ai/signaletter.si/pull/5)
- Topic tabs, section sidebar, searchable archive. [#4](https://github.com/nick-nguyen-ai/signaletter.si/pull/4)
- Skimmable AI briefings. [#3](https://github.com/nick-nguyen-ai/signaletter.si/pull/3)
- Initial Jekyll site for GitHub Pages: combined Markets + AI newsletter. [#1](https://github.com/nick-nguyen-ai/signaletter.si/pull/1)
### Fixed
- Sydney-dated posts publishing when Pages builds in UTC (`_config.yml`). [#9](https://github.com/nick-nguyen-ai/signaletter.si/pull/9)
- SEO titles; added oil/gold charts. [#2](https://github.com/nick-nguyen-ai/signaletter.si/pull/2)
