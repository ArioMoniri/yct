"""Shared git helpers for the P0 integrity guards (scripts/check_*.py).

Every guard exits 0 = pass, 1 = violation, 2 = usage/infrastructure error (a bad --base must never
silently pass).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
ZERO_SHA = "0" * 40
PREREG_TAG = "prereg-lock"
PREREG_PATH = "docs/preregistration.md"


class GuardError(Exception):
    """Infrastructure problem (exit 2)."""


def git(*args: str, check: bool = True) -> str:
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise GuardError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True).returncode == 0


def rev(ref: str) -> str:
    return git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()


def ref_exists(ref: str) -> bool:
    return git_ok("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def tag_exists(tag: str = PREREG_TAG) -> bool:
    return git_ok("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")


def show(ref: str, path: str) -> str | None:
    """File content at `ref` (":" = index), or None if absent."""
    spec = f":{path}" if ref == ":" else f"{ref}:{path}"
    res = subprocess.run(["git", "show", spec], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


def resolve_base(base: str | None) -> str:
    """Commit to diff against. Uses the merge-base with HEAD so a moved target branch is harmless.

    None / "" / all-zero sha / "EMPTY" -> the empty tree (whole history is in range).
    """
    if not base or base == ZERO_SHA or base == "EMPTY":
        return EMPTY_TREE
    if not ref_exists(base):
        raise GuardError(f"--base {base!r} is not a commit (fetch-depth 0? fetched the base branch?)")
    if not ref_exists("HEAD"):
        return EMPTY_TREE
    mb = git("merge-base", base, "HEAD", check=False).strip()
    if not mb:
        raise GuardError(f"no merge-base between {base} and HEAD")
    return mb


def commits_in_range(base: str) -> list[str]:
    """Commits reachable from HEAD but not from base, oldest first."""
    if not ref_exists("HEAD"):
        return []
    spec = ["HEAD"] if base == EMPTY_TREE else [f"{base}..HEAD"]
    out = git("rev-list", "--reverse", *spec)
    return out.split()


def parents(commit: str) -> list[str]:
    return git("rev-list", "--parents", "-n", "1", commit).split()[1:]


def changed_paths(commit: str) -> set[str]:
    """Paths a commit changed. For merges, only paths differing from *every* parent (evil merges);
    branch commits are in range and checked individually."""
    ps = parents(commit)
    if not ps:
        out = git("diff-tree", "--root", "-r", "--no-commit-id", "--name-only", commit)
        return set(out.split("\n")) - {""}
    sets = []
    for p in ps:
        out = git("diff-tree", "-r", "--no-commit-id", "--name-only", p, commit)
        sets.append(set(out.split("\n")) - {""})
    return set.intersection(*sets)


def commit_message(commit: str) -> str:
    return git("log", "-1", "--format=%B", commit)


def is_ancestor(a: str, b: str) -> bool:
    return git_ok("merge-base", "--is-ancestor", a, b)


def toplevel() -> Path:
    return Path(git("rev-parse", "--show-toplevel").strip())


def guard_config() -> dict:
    """The `guards:` section of config.yaml in the checked-out tree ({} if absent)."""
    path = toplevel() / "config.yaml"
    if not path.exists():
        return {}
    import yaml

    return (yaml.safe_load(path.read_text()) or {}).get("guards") or {}


def ticket_exists(ticket: str) -> bool:
    """A ticket id is real only if BUGS.md or ENHANCEMENTS.md has an entry line `- <id> ...`."""
    if not re.fullmatch(r"(BUG|ENH)-\d{3,}", str(ticket)):
        return False
    pat = re.compile(rf"^\s*-\s*{re.escape(ticket)}\b", re.M)
    return any(pat.search(f.read_text()) for f in (toplevel() / n for n in ("BUGS.md", "ENHANCEMENTS.md"))
               if f.exists())


def base_parser(desc: str, staged: bool = False) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--base", default=None,
                    help="base ref (e.g. origin/main); range is merge-base(base, HEAD)..HEAD. "
                         "Omit for the whole history.")
    if staged:
        ap.add_argument("--staged", action="store_true", help="compare HEAD with the index (pre-commit)")
    return ap


def run(main) -> None:
    try:
        sys.exit(main())
    except GuardError as e:
        print(f"ERROR: {e}")
        sys.exit(2)
