#!/usr/bin/env python3
"""The guard exceptions themselves are frozen (Watchdog/QA G-D032 cycle 2, FIX-C3-ENG).

Protected config.yaml sections: `guards:` (history exceptions read by the other guards) and `owner:`
(the pinned owner ARN, owner_actions). For every commit in --base..HEAD that changes either section
(compared with its parent; for merges, with every parent):

  1. the commit message must contain `[QA-approved guard change: <TICKET>]` with TICKET an existing
     BUGS.md/ENHANCEMENTS.md entry;
  2. regardless of approval, every exception entry ADDED by the commit must name a commit that is a
     strict ancestor of it (an exception can only excuse the past, never itself or the future);
  3. regardless of approval, guards.human_signed_since may never be introduced or moved later (it can
     only be removed or moved earlier: moving it later exempts more commits from check_human_signed);
  4. the owner ARN pin (owner.arn_pin) may never change once set.
Commits up to and including GUARDS_BASELINE (the state reviewed at gate G-D032 cycle 2) are exempt from
1-4, and only if the protected sections at GUARDS_BASELINE hash to GUARDS_BASELINE_SHA256 (history cannot
be rewritten underneath the baseline). Fixture repos without that commit get no exemption.

Exit 0 = OK, 1 = violation, 2 = usage/infrastructure error.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402

CONFIG = "config.yaml"
PROTECTED = ("guards", "owner")
TOKEN_RE = re.compile(r"\[QA-approved guard change: ((?:BUG|ENH)-\d{3,})\]")
ENTRY_LISTS = ("test_weakening_allowlist", "human_only_exempt")
# Reviewed state at gate G-D032 cycle 2 (HEAD when FIX-C3-ENG started).
GUARDS_BASELINE = "18b39c279222308b316d34ba42157c6c4c9c3cda"
GUARDS_BASELINE_SHA256 = "07dd709dc043603bffef8e081a240ee6dc908503d49715f05d5d68ebc9251d0b"


def sections(ref: str) -> dict:
    text = g.show(ref, CONFIG)
    data = (yaml.safe_load(text) or {}) if text else {}
    if not isinstance(data, dict):
        raise g.GuardError(f"{CONFIG} at {ref[:12]} is not a mapping")
    return {k: data.get(k) for k in PROTECTED}


def canonical_sha256(sec: dict) -> str:
    return hashlib.sha256(json.dumps(sec, sort_keys=True, default=str).encode()).hexdigest()


def _entries(sec: dict) -> set[str]:
    gd = sec.get("guards") or {}
    out = set()
    for lst in ENTRY_LISTS:
        for e in gd.get(lst) or []:
            out.add(json.dumps({"list": lst, **(e if isinstance(e, dict) else {"raw": e})}, sort_keys=True,
                               default=str))
    return out


def _since(sec: dict) -> str | None:
    v = (sec.get("guards") or {}).get("human_signed_since")
    return str(v) if v else None


def _pin(sec: dict) -> str | None:
    v = (sec.get("owner") or {}).get("arn_pin")
    return str(v) if v else None


def baseline_ok() -> bool:
    """True if GUARDS_BASELINE exists in HEAD's history and its protected sections match the pinned hash."""
    if not g.ref_exists(GUARDS_BASELINE) or not g.is_ancestor(GUARDS_BASELINE, "HEAD"):
        return False
    got = canonical_sha256(sections(GUARDS_BASELINE))
    if got != GUARDS_BASELINE_SHA256:
        raise g.GuardError(f"protected config at GUARDS_BASELINE hashes to {got}, expected "
                           f"{GUARDS_BASELINE_SHA256} (history rewritten?)")
    return True


def check_commit(c: str, parent_secs: list[dict], new: dict, exempt: bool) -> list[str]:
    bad = []
    changed = all(new != p for p in parent_secs)
    if not changed:
        return bad
    old = parent_secs[0]
    if exempt:  # reviewed history up to GUARDS_BASELINE (its state is pinned by GUARDS_BASELINE_SHA256)
        return bad
    m = TOKEN_RE.search(g.commit_message(c))
    if not m:
        bad.append(f"{c[:12]}: changes config `guards:`/`owner:` without "
                   "'[QA-approved guard change: <TICKET>]' in the commit message")
    elif not g.ticket_exists(m.group(1)):
        bad.append(f"{c[:12]}: guard-change ticket {m.group(1)} not in BUGS.md/ENHANCEMENTS.md")
    for e in sorted(_entries(new) - set().union(*(_entries(p) for p in parent_secs))):
        sha = str(json.loads(e).get("commit", ""))
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or not g.ref_exists(sha) or sha == c \
                or not g.is_ancestor(sha, c):
            bad.append(f"{c[:12]}: added exception {e} does not name a strict ancestor commit")
    s_old, s_new = _since(old), _since(new)
    if s_new and s_new != s_old:
        if s_old is None or not g.ref_exists(s_new) or not g.ref_exists(s_old) \
                or not g.is_ancestor(s_new, s_old):
            bad.append(f"{c[:12]}: guards.human_signed_since introduced or moved later "
                       f"({(s_old or 'none')[:12]} -> {s_new[:12]}); it may only be removed or moved earlier")
    p_old, p_new = _pin(old), _pin(new)
    if p_old and p_new != p_old:
        bad.append(f"{c[:12]}: owner.arn_pin changed or removed ({p_old} -> {p_new}); never allowed")
    return bad


def main() -> int:
    a = g.base_parser(__doc__).parse_args()
    base = g.resolve_base(a.base)
    commits = g.commits_in_range(base)
    use_baseline = baseline_ok()
    bad: list[str] = []
    for c in commits:
        ps = g.parents(c)
        parent_secs = [sections(p) for p in ps] if ps else [{k: None for k in PROTECTED}]
        exempt = use_baseline and g.is_ancestor(c, GUARDS_BASELINE)
        bad += check_commit(c, parent_secs, sections(c), exempt)
    for b in bad:
        print(f"FAIL {b}")
    if not bad:
        tag = f"baseline {GUARDS_BASELINE[:12]}" if use_baseline else "no baseline in this history"
        print(f"OK guard exceptions unchanged or QA-approved ({len(commits)} commits checked; {tag})")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
