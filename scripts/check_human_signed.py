#!/usr/bin/env python3
"""Fail if any commit in --base..HEAD performs a human-only action through git (DECISIONS D-030).

Human-only actions now live in AWS SSM under /yct/owner/* (owner-only write; see
src/yct/owner_actions.py). Therefore no commit may:
  * touch UNBLIND_TOKEN (add, modify or delete);
  * add, modify or delete infra/BUDGET_USD;
  * add, modify or delete docs/owner_age.pub (the blinding root; the owner's key lives in SSM
    /yct/owner/age_pub and src/yct/owner_actions.verify_age_pub checks the repo copy against it at
    runtime) or DATA_DECISION.md (owner sign-off lives in SSM /yct/owner/data_decision) (QA G-D032 c2 #1);
  * change docs/preregistration.md after the prereg-lock tag.
Every commit in the range is checked individually (a later revert does not excuse it).

Exact history exceptions: config.yaml `guards.human_only_exempt` entries {commit: <full sha>, path,
ticket} excuse exactly that (commit, path) pair (reported as EXEMPT); the ticket must exist; an entry
whose commit is in range but matches nothing FAILS (dead entry). check_guard_config.py freezes the list.

History exception (FIX-D032-1): config.yaml `guards.human_signed_since` names the D-030 adoption
commit. Commits that are strict ancestors of it predate SSM owner actions (e.g. 6c16d89 committed the
budget file under the earlier signed-commit rule, D-021) and are skipped; that commit and everything
after it are checked. The SHA must be a full commit SHA reachable from HEAD, else exit 2.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402

ALWAYS_FORBIDDEN = {
    "UNBLIND_TOKEN": "the unblind token is issued by the owner in SSM /yct/owner/unblind_token",
    "infra/BUDGET_USD": "the GPU budget is set by the owner in SSM /yct/owner/budget_usd",
    "docs/owner_age.pub": "the owner's age key is set by the owner in SSM /yct/owner/age_pub",
    "DATA_DECISION.md": "the data decision is signed by the owner in SSM /yct/owner/data_decision",
}


def exemptions() -> list[dict]:
    out = []
    for e in g.guard_config().get("human_only_exempt") or []:
        ok = isinstance(e, dict) and re.fullmatch(r"[0-9a-f]{40}", str(e.get("commit", ""))) \
            and e.get("path") in ALWAYS_FORBIDDEN and g.ticket_exists(e.get("ticket", ""))
        if not ok:
            raise g.GuardError(f"bad guards.human_only_exempt entry {e!r}: need full commit sha, a "
                               "protected path and an existing ticket")
        out.append(e)
    return out


def main() -> int:
    ap = g.base_parser(__doc__)
    a = ap.parse_args()
    base = g.resolve_base(a.base)
    lock = g.rev(f"refs/tags/{g.PREREG_TAG}") if g.tag_exists() else None
    bad = []
    commits = g.commits_in_range(base)
    since = g.guard_config().get("human_signed_since")
    skipped = 0
    if since:
        since = str(since)
        if not re.fullmatch(r"[0-9a-f]{40}", since) or not g.ref_exists(since):
            raise g.GuardError(f"guards.human_signed_since {since!r} is not a full commit SHA")
        if not g.is_ancestor(since, "HEAD"):
            raise g.GuardError(f"guards.human_signed_since {since[:12]} is not in HEAD's history")
        kept = [c for c in commits if c == since or not g.is_ancestor(c, since)]
        skipped = len(commits) - len(kept)
        commits = kept
        print(f"note: {skipped} commit(s) before guards.human_signed_since {since[:12]} (D-030) not checked")
    ex = exemptions()
    used: set[int] = set()
    for c in commits:
        paths = g.changed_paths(c)
        for p, why in ALWAYS_FORBIDDEN.items():
            if p in paths:
                hit = [i for i, e in enumerate(ex) if e["commit"] == c and e["path"] == p]
                if hit:
                    used.update(hit)
                    print(f"EXEMPT ({ex[hit[0]]['ticket']}) {c[:12]}: {p}")
                else:
                    bad.append(f"{c[:12]}: {p} changed via git ({why})")
        if lock and g.PREREG_PATH in paths and not g.is_ancestor(c, lock):
            bad.append(f"{c[:12]}: {g.PREREG_PATH} changed after {g.PREREG_TAG} (human-only, via SSM)")
    in_range = set(commits)
    bad += [f"unused guards.human_only_exempt entry {e['commit'][:12]} {e['path']} ({e['ticket']})"
            for i, e in enumerate(ex) if i not in used and e["commit"] in in_range]
    for b in bad:
        print(f"FAIL {b}")
    if not bad:
        print(f"OK no human-only action committed via git ({len(commits)} commits checked)")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
