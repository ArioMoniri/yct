#!/usr/bin/env python3
"""Refuse an empty guard range (QA G-D032 D4): `make guards` must never print OK having checked nothing.

--base EMPTY (the Makefile default) = whole history, never empty. Any other base must leave at least one
commit in merge-base(base, HEAD)..HEAD. Exit 0 = range OK (prints its size), 2 = empty / bad base.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402


def main() -> int:
    a = g.base_parser(__doc__).parse_args()
    base = g.resolve_base(a.base)
    n = len(g.commits_in_range(base))
    label = "whole history" if base == g.EMPTY_TREE else f"{base[:12]}..HEAD"
    if n == 0:
        raise g.GuardError(f"guard range {label} (--base {a.base}) is empty; nothing would be checked")
    print(f"guard range: {label}, {n} commit(s)")
    return 0


if __name__ == "__main__":
    g.run(main)
