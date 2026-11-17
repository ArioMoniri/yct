#!/usr/bin/env python3
"""Fail if an append-only log had an existing line modified or deleted between --base and HEAD.

Only appends are allowed: the new content must start with the old content byte-for-byte.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402

APPEND_ONLY = [
    "DECISIONS.md",
    "BUGS.md",
    "CHANGELOG.md",
    "ENHANCEMENTS.md",
    "reviews/watchdog/audit_log.jsonl",
]


def violations(old_ref: str, new_ref: str) -> list[str]:
    out = []
    for path in APPEND_ONLY:
        old = None if old_ref == g.EMPTY_TREE else g.show(old_ref, path)
        if old is None:
            continue
        new = g.show(new_ref, path)
        if new is None:
            out.append(f"{path}: deleted (append-only log)")
        elif not new.startswith(old):
            old_lines, new_lines = old.splitlines(), new.splitlines()
            n = next((i for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=False)) if a != b),
                     min(len(old_lines), len(new_lines)))
            out.append(f"{path}:{n + 1}: existing line modified or deleted (append-only log)")
    return out


def main() -> int:
    ap = g.base_parser(__doc__, staged=True)
    a = ap.parse_args()
    if a.staged:
        old_ref = "HEAD" if g.ref_exists("HEAD") else g.EMPTY_TREE
        new_ref = ":"
    else:
        old_ref, new_ref = g.resolve_base(a.base), "HEAD"
    bad = violations(old_ref, new_ref)
    for v in bad:
        print(f"FAIL {v}")
    if not bad:
        print(f"OK append-only logs unchanged except appends ({len(APPEND_ONLY)} files)")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
