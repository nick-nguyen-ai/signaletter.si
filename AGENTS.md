# Notes for coding agents

- **Update `CHANGELOG.md` in every PR that changes code, workflows, layouts, scripts, the Worker or docs.**
  Add an entry under `[Unreleased]` (Added/Changed/Removed/Fixed): what and why, key files, PR link.
  CI (`changelog` job) fails otherwise. Exempt: `cursor/issue-*` daily PRs and changes only under `_posts/` or `assets/issues/`.
- **Update `ARCHITECTURE.md`** when the structure changes (new script, workflow, endpoint, data file, routine step).
- Read `ARCHITECTURE.md` first for how the system fits together.
- Never commit secrets. Daily issue PRs may only touch `_posts/`, `assets/issues/`, `_data/*.csv`.
