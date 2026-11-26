#!/usr/bin/env python3
"""Tests for scripts/check_pr_paths.py (the auto-merge path gate). Builds throwaway git repos.
Run: python3 scripts/tests/test_check_pr_paths.py"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import check_pr_paths as cpp  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=repo, check=True, capture_output=True)


def write(repo, path, text="x\n"):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def make_repo():
    repo = tempfile.mkdtemp()
    git(repo, "init", "-q", "-b", "main")
    for p in ("_posts/2026-10-23-markets.md", "_data/markets.csv", "assets/issues/2026-10-23/snapshot.json",
              "worker/src/index.js", ".github/workflows/auto-merge-issues.yml", "scripts/qa_markets.py", "index.html"):
        write(repo, p, f"{p}\n" * 20)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "cursor/issue-test")
    return repo


def commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change", "--allow-empty")


def verdict(repo):
    _, problems = cpp.check("main", "HEAD", cwd=repo)
    return problems


def test_daily_issue_shape_passes():  # mirrors PR #38: new posts, issue assets, csv
    r = make_repo()
    for p in ("_posts/2026-10-24-markets.md", "_posts/2026-10-24-ai.md", "assets/issues/2026-10-24/snapshot.json",
              "assets/issues/2026-10-24/watchlist.json"):
        write(r, p)
    write(r, "_data/markets.csv", "a,b\n")
    commit(r)
    assert verdict(r) == []


def test_chart_csvs_allowed_on_daily_issue_pr():
    """Long-run chart series live in _data/*.csv and must be updatable from issue-* PRs."""
    r = make_repo()
    write(r, "_data/brent.csv", "date,close\n2026-11-24,91.80\n")
    write(r, "_data/gold.csv", "date,close\n2026-11-25,3535.80\n")
    write(r, "_posts/2026-11-27-markets.md")
    commit(r)
    assert verdict(r) == []


def test_allowed_delete_and_rename_pass():
    r = make_repo()
    git(r, "rm", "-q", "assets/issues/2026-10-23/snapshot.json")
    git(r, "mv", "_posts/2026-10-23-markets.md", "_posts/2026-10-23-markets-v2.md")
    commit(r)
    assert verdict(r) == []


def test_deleting_disallowed_file_fails():
    r = make_repo()
    git(r, "rm", "-q", "worker/src/index.js")
    commit(r)
    assert any("deleted" in p and "worker/src/index.js" in p for p in verdict(r)), verdict(r)


def test_deleting_workflow_fails():
    r = make_repo()
    git(r, "rm", "-q", ".github/workflows/auto-merge-issues.yml")
    commit(r)
    assert verdict(r), "deleting the gate itself must fail"


def test_renaming_disallowed_file_into_allowed_path_fails():
    r = make_repo()
    git(r, "mv", "scripts/qa_markets.py", "_posts/qa_markets.py")
    commit(r)
    probs = verdict(r)
    assert any("scripts/qa_markets.py" in p for p in probs), probs


def test_renaming_allowed_file_out_fails():
    r = make_repo()
    git(r, "mv", "_posts/2026-10-23-markets.md", "index2.html")
    commit(r)
    assert any("index2.html" in p for p in verdict(r))


def test_modifying_disallowed_file_fails():
    r = make_repo()
    write(r, "index.html", "changed\n")
    commit(r)
    assert any("index.html" in p for p in verdict(r))


def test_csv_in_data_subdir_or_non_csv_fails():
    r = make_repo()
    write(r, "_data/sub/x.csv")
    write(r, "_data/nav.yml")
    commit(r)
    probs = verdict(r)
    assert any("_data/sub/x.csv" in p for p in probs) and any("_data/nav.yml" in p for p in probs), probs


def test_symlink_in_allowed_path_fails():
    r = make_repo()
    os.symlink("../worker/src/index.js", os.path.join(r, "_posts/evil.md"))
    commit(r)
    assert any("symlink" in p for p in verdict(r))


def test_empty_pr_fails():
    r = make_repo()
    commit(r)
    assert any("no file changes" in p for p in verdict(r))


def test_cli_exit_codes():
    r = make_repo()
    git(r, "rm", "-q", "worker/src/index.js")
    commit(r)
    script = os.path.join(HERE, "..", "check_pr_paths.py")
    res = subprocess.run([sys.executable, script, "main"], cwd=r, capture_output=True, text=True)
    assert res.returncode == 1 and "::error::" in res.stdout, res


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
