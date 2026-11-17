#!/usr/bin/env python3
"""Fail if any commit in --base..HEAD performs a human-only action through git (DECISIONS D-030).

Human-only actions now live in AWS SSM under /yct/owner/* (owner-only write; see
src/yct/owner_actions.py). Therefore no commit may:
  * touch UNBLIND_TOKEN (add, modify or delete);
  * add, modify or delete infra/BUDGET_USD;
  * change docs/preregistration.md after the prereg-lock tag.
Every commit in the range is checked individually (a later revert does not excuse it).

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
}


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
    for c in commits:
        paths = g.changed_paths(c)
        for p, why in ALWAYS_FORBIDDEN.items():
            if p in paths:
                bad.append(f"{c[:12]}: {p} changed via git ({why})")
        if lock and g.PREREG_PATH in paths and not g.is_ancestor(c, lock):
            bad.append(f"{c[:12]}: {g.PREREG_PATH} changed after {g.PREREG_TAG} (human-only, via SSM)")
    for b in bad:
        print(f"FAIL {b}")
    if not bad:
        print(f"OK no human-only action committed via git ({len(commits)} commits checked)")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
