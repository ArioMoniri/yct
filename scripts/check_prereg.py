#!/usr/bin/env python3
"""If tag `prereg-lock` exists, fail if docs/preregistration.md at HEAD differs from its content at the tag.

Post-lock prereg changes are a human-only action made outside git (DECISIONS D-030); there is no
in-git exception. --base is accepted for uniformity but the comparison is always tag vs HEAD.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402


def main() -> int:
    ap = g.base_parser(__doc__)
    ap.parse_args()
    if not g.tag_exists():
        print(f"OK no {g.PREREG_TAG} tag yet; {g.PREREG_PATH} not frozen")
        return 0
    locked = g.show(f"refs/tags/{g.PREREG_TAG}", g.PREREG_PATH)
    if locked is None:
        print(f"FAIL {g.PREREG_TAG} tag exists but {g.PREREG_PATH} is absent at the tag")
        return 1
    now = g.show("HEAD", g.PREREG_PATH)
    if now is None:
        print(f"FAIL {g.PREREG_PATH} deleted after {g.PREREG_TAG}")
        return 1
    if now != locked:
        print(f"FAIL {g.PREREG_PATH} differs from its content at {g.PREREG_TAG} "
              "(post-lock edits are human-only, via SSM per D-030)")
        return 1
    print(f"OK {g.PREREG_PATH} identical to {g.PREREG_TAG}")
    return 0


if __name__ == "__main__":
    g.run(main)
