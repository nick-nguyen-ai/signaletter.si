# SignaLetter architecture

How https://signaletter.si works end to end. Read this, then `CHANGELOG.md`, then the code.

## 1. Site (Jekyll on GitHub Pages)
- Jekyll site built with the `github-pages` gem, served from `main` ("Deploy from a branch"), domain in `CNAME`.
- Posts: `_posts/YYYY-MM-DD-markets.md` and `_posts/YYYY-MM-DD-ai.md`. Markets posts carry structured front
  matter (schema `docs/schemas/markets-post.schema.json`, format `docs/markets-post-format.md`); AI posts use
  the card format in `docs/ai-post-format.md`.
- Layouts/includes: `_layouts/default.html`, `_layouts/day.html`, `_includes/markets-report.html`,
  `_includes/markets/*` (tiles, cards, Morning/Close `edition-body.html`), `_includes/ai-report.html`.
- Data: `_data/watchlist.csv` (default watchlist), `_data/brent.csv`, `_data/gold.csv`, `_data/charts.yml`, `_data/topics.yml`.
- Assets: `assets/css`, `assets/js` (`my-watchlist.js`, `ai-cards.js`, `section-nav.js`, `share.js`), `assets/brand`,
  `assets/og`, `assets/data/asx-tickers.json`, `assets/data/watchlist-default-tickers.txt`.
- Per-day machine files: `assets/issues/YYYY-MM-DD/` (`snapshot.json`, `close-snapshot.json`, `watchlist.json`, content YAML).
- Pages: `index.html`, `markets.md`, `ai.md`, `archive.html`, `watchlist.html`, `404.html`.

## 2. Daily routines (scheduled agents, outside this repo)
Working files for each day live in `/workspace/newsletter/YYYY-MM-DD/` on the agent box.
| Routine | Output |
| --- | --- |
| AI report | `ai.yml`, `newsletter.md` → `_posts/<date>-ai.md` |
| ASX morning (weekdays) / weekend macro (Sat-Sun) | `markets-content.yml`, `markets-draft.md`, snapshot via `fetch_markets.py` |
| Quality review | `markets.md`, `review-log.md` (fact/source checks before publish) |
| Publish | builds the post, runs `qa_markets.py --fix`, `build_watchlist_json.py`, opens a `cursor/issue-<date>` PR |
| Close wrap (~16:15) | `close-content.yml`, `close-snapshot.json`, `close-chat.md`, `close-review-log.md` → `cursor/issue-<date>-close` PR |

## 3. Scripts (`scripts/`, see `scripts/README.md`)
- `fetch_markets.py`: deterministic market snapshot (official sources first, Yahoo labelled delayed/unofficial; never guesses). `--close` for the close.
- `build_markets_post.py`: merges editorial YAML with the snapshot into a Markets post; `--close` merges the close edition.
- `qa_markets.py`: QA gate. `--fix` drops failing claims/modules; report-only mode exits 1/2 on unresolved errors (blocks merge).
- `build_watchlist_json.py`: builds `assets/issues/<date>/watchlist.json` for defaults + every reader pick.
- `build_asx_list.py`: allowed ticker universe (S&P/ASX 300 via VAS holdings) → `assets/data/asx-tickers.json`.
- `check_pr_paths.py`: auto-merge path gate. `check_changelog.py`: changelog CI gate.
- `export_feed.py`: unbranded JSON export for the public data feed.
- `generate_og.py`, `generate_brand.py`: brand/OG images. Tests in `scripts/tests/`.

## 4. snapshot.json and watchlist.json
- `snapshot.json` / `close-snapshot.json`: dashboard and `wl_<ticker>` quotes with provenance (provider, URL, session date, status). Tiles render only from it.
- `watchlist.json` (`signaletter.watchlist/v1`): `editions.{morning,close}.items.<TICKER>` with price, note, sources, `reviewed`. Reviewed notes come from the post; other tickers get price + ASX announcement headlines. Details: `docs/my-watchlist.md`.

## 5. Reader watchlist ("My shares")
- Cloudflare Worker `signaletter-watchlist` (`worker/`, docs `worker/README.md`): magic-link email sign-in (`/auth/request`, `/auth/verify`), `GET /me`, `PUT /me/tickers`, `DELETE /me`, stub subscribe endpoints.
- Picks stored in KV binding `WATCHLIST` at `user:<email>`, tickers mirrored in key metadata; auth state (single-use links, session versions) in the `AuthState` Durable Object.
- `GET /admin/tickers` (bearer admin token) returns the union of codes, never emails; used by `build_watchlist_json.py`.
- Browser side: `assets/js/my-watchlist.js` swaps the watchlist section for the reader's picks from the day's `watchlist.json`; enabled by `watchlist_api` in `_config.yml`.

## 6. GitHub dispatch for new picks
When a reader saves a ticker missing from today's `watchlist.json`, the Worker calls the GitHub API to dispatch
`.github/workflows/watchlist-add.yml` (inputs `date`, `tickers`). The workflow validates input, adds only the new
tickers to the file (never changes existing entries), pushes to `main` with rebase-retry and requests a Pages build.

## 7. Workflows (`.github/workflows/`)
- `auto-merge-issues.yml`: for same-repo, non-draft `cursor/issue-*` PRs: path gate (checker taken from base branch), Markets QA report-only, Jekyll build, squash-merge, then explicit Pages build request.
- `ci.yml`: on PRs/pushes: Worker vitest + wrangler dry run, Python tests + QA of all Markets posts, Jekyll strict build, changelog gate.
- `watchlist-add.yml`: see §6.
- `data-export.yml`: see §9.

## 8. QA checks
Editorial review by the quality routine; `qa_markets.py` (schema, sources, numbers vs snapshot, summary rules; warnings non-blocking); path gate; Jekyll build; Worker tests; changelog gate.

## 9. Public data feed
`export_feed.py` writes `days/<date>/markets.json`, `days/<date>/ai.json`, `latest/*` and `index.json` with all branding and site links stripped (the export fails if any remain). `data-export.yml` pushes it to a separate public repository using a deploy key secret, after merges, quick-adds and on a schedule. Keep that feed free of anything identifying this site.
