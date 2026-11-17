#!/usr/bin/env python3
"""Frozen config keys may not change after their freeze commit.

Schema (config.yaml, top level):

    frozen:
      - key: window.start_tr      # dotted path; freezing a mapping freezes its whole subtree
        frozen_at: <commit sha>   # the gate commit at which the value was frozen

Checks:
  1. every `frozen_at` resolves to a commit that is an ancestor of HEAD and whose config.yaml has the key;
  2. the value at HEAD equals the value at `frozen_at` (missing at HEAD = changed);
  3. no entry present in config.yaml at --base was removed or re-pointed at HEAD (no unfreezing).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402

CONFIG = "config.yaml"
_MISSING = object()


def load(ref: str) -> dict | None:
    text = g.show(ref, CONFIG)
    if text is None:
        return None
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise g.GuardError(f"{CONFIG} at {ref} is not a mapping")
    return data


def lookup(cfg: dict, dotted: str):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def entries(cfg: dict | None) -> list[tuple[str, str]]:
    if not cfg:
        return []
    raw = cfg.get("frozen") or []
    if not isinstance(raw, list):
        raise g.GuardError("`frozen` must be a list of {key, frozen_at}")
    out = []
    for e in raw:
        if not isinstance(e, dict) or not e.get("key") or not e.get("frozen_at"):
            raise g.GuardError(f"bad frozen entry {e!r}: need key and frozen_at")
        out.append((str(e["key"]), str(e["frozen_at"])))
    return out


def main() -> int:
    ap = g.base_parser(__doc__)
    a = ap.parse_args()
    base = g.resolve_base(a.base)
    head_cfg = load("HEAD")
    bad: list[str] = []
    head_entries = entries(head_cfg)
    head_set = set(head_entries)

    if base != g.EMPTY_TREE:
        for key, sha in entries(load(base)):
            if (key, sha) not in head_set:
                bad.append(f"{key}: unfrozen or frozen_at re-pointed (was {sha[:12]} at base)")

    for key, sha in head_entries:
        if not g.ref_exists(sha) or not g.is_ancestor(sha, "HEAD"):
            bad.append(f"{key}: frozen_at {sha[:12]} is not an ancestor commit of HEAD")
            continue
        frozen_cfg = load(sha)
        then = _MISSING if frozen_cfg is None else lookup(frozen_cfg, key)
        if then is _MISSING:
            bad.append(f"{key}: not present in {CONFIG} at frozen_at {sha[:12]}")
            continue
        now = lookup(head_cfg, key)
        if now != then:
            shown = "<missing>" if now is _MISSING else repr(now)
            bad.append(f"{key}: changed after freeze at {sha[:12]}: {then!r} -> {shown}")

    for b in bad:
        print(f"FAIL {b}")
    if not bad:
        print(f"OK {len(head_entries)} frozen config key(s) unchanged")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
