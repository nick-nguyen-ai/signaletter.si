# Changelog

All notable changes to SignaLetter (code, workflows, layout, scripts, Worker, docs).
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), newest first, dates in Sydney time.
Daily content PRs (`cursor/issue-*`) are not listed one by one.

**Every PR that changes non-content files must add an entry under `[Unreleased]`** (CI enforces this; see AGENTS.md).
Entry shape: what changed and why, key files, PR link.

## [Unreleased]

### Added
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
