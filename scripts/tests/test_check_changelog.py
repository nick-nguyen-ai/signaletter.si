import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from check_changelog import needs_changelog, main

assert needs_changelog(["_posts/a.md", "assets/issues/2026-11-02/x.json"])[0] is False
assert needs_changelog(["scripts/x.py"])[0] is True
assert needs_changelog(["scripts/x.py", "CHANGELOG.md"])[0] is False
assert needs_changelog([])[0] is False
assert main(["origin/main", "--branch", "cursor/issue-2026-11-02"]) == 0
print("check_changelog tests passed")
