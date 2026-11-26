#!/usr/bin/env python3
"""Auto-merge gate: a daily issue PR may only add, modify or delete files under
  _posts/**   assets/issues/**   _data/<name>.csv   (top level of _data only)

Top-level chart series (_data/brent.csv, _data/gold.csv) and other _data/*.csv
files are allowed so the daily publish routine can commit chart backfills.

Every touched path counts, including deletions and both sides of a rename (renames are
split into delete + add with --no-renames, so renaming a disallowed file out of place fails).
Symlinks and submodules are rejected anywhere. Exit 0 = allowed, 1 = rejected.

Usage: python3 scripts/check_pr_paths.py BASE_REF [HEAD_REF]   (compares BASE...HEAD)
"""
from __future__ import annotations

import re
import subprocess
import sys

ALLOWED = [re.compile(r"^_posts/[^\0]+$"), re.compile(r"^assets/issues/[^\0]+$"), re.compile(r"^_data/[^/]+\.csv$")]
BAD_MODES = {"120000": "symlink", "160000": "submodule"}
STATUS = {"A": "added", "M": "modified", "D": "deleted", "T": "type changed", "U": "unmerged", "X": "unknown", "B": "broken"}


def changes(base: str, head: str = "HEAD", cwd: str | None = None):
    """Yield (status, old_mode, new_mode, path) for every path touched by base...head."""
    out = subprocess.run(["git", "diff", "--raw", "-z", "--no-renames", "--no-ext-diff", f"{base}...{head}"],
                         cwd=cwd, check=True, capture_output=True).stdout.decode("utf-8", "surrogateescape")
    parts = out.split("\0")
    i = 0
    while i < len(parts) - 1:
        meta, path = parts[i], parts[i + 1]
        i += 2
        f = meta.lstrip(":").split()
        yield f[4][0], f[0], f[1], path


def check(base: str, head: str = "HEAD", cwd: str | None = None):
    rows = list(changes(base, head, cwd))
    problems = []
    if not rows:
        problems.append("PR has no file changes")
    for st, old_mode, new_mode, path in rows:
        what = STATUS.get(st, st)
        if not any(rx.match(path) for rx in ALLOWED):
            problems.append(f"Disallowed path ({what}): {path}")
        for m in (old_mode, new_mode):
            if m in BAD_MODES:
                problems.append(f"Disallowed {BAD_MODES[m]} ({what}): {path}")
                break
    return rows, problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not 1 <= len(argv) <= 2:
        print(__doc__)
        return 2
    rows, problems = check(*argv)
    print("Changed files:")
    for st, _, _, path in rows:
        print(f"  {st} {path}")
    for p in problems:
        print(f"::error::{p} (only _posts/**, assets/issues/**, _data/*.csv)")
    if problems:
        return 1
    print("All paths allowed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
