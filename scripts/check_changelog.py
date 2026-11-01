#!/usr/bin/env python3
"""Changelog gate: a PR that touches any file outside _posts/ or assets/issues/ must modify CHANGELOG.md.

Usage: python3 scripts/check_changelog.py BASE_REF [HEAD_REF] [--branch NAME]
cursor/issue-* branches are exempt. Exit 0 = ok, 1 = CHANGELOG.md missing.
"""
import subprocess
import sys

CONTENT = ("_posts/", "assets/issues/")


def needs_changelog(paths):
    other = [p for p in paths if not p.startswith(CONTENT)]
    return bool(other) and "CHANGELOG.md" not in paths, other


def main(argv):
    branch = ""
    if "--branch" in argv:
        i = argv.index("--branch"); branch = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    if branch.startswith("cursor/issue-"):
        print(f"{branch}: daily issue branch, exempt."); return 0
    base, head = argv[0], (argv[1] if len(argv) > 1 else "HEAD")
    out = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{base}...{head}"],
                         check=True, capture_output=True, text=True).stdout
    paths = [p for p in out.splitlines() if p]
    fail, other = needs_changelog(paths)
    if fail:
        print("::error::This PR changes non-content files but not CHANGELOG.md. Add an [Unreleased] entry (see AGENTS.md).")
        for p in other: print("  " + p)
        return 1
    print("Changelog gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
