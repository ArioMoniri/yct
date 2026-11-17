#!/usr/bin/env python3
"""Pre-fetch and sha256-verify every atlas in config.yaml `atlases:` into the atlas cache (CI, BUG-008).

  python scripts/fetch_atlases.py          # download missing files, verify all; exit 1 on any failure
  python scripts/fetch_atlases.py --key    # print a cache key = sha256 of the atlas sha256s in config.yaml

CI restores ~/.cache/yct/atlases with actions/cache keyed by --key, then runs this (a no-op when the
cache hit), so atlas tests always RUN in CI; YCT_OFFLINE is never set there.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def atlas_entries(cfg: dict) -> list[tuple[str, str, str]]:
    out = []
    for key, val in sorted(cfg["atlases"].items()):
        if not isinstance(val, dict):
            continue
        for hemi in ("lh", "rh"):
            if isinstance(val.get(hemi), dict) and "sha256" in val[hemi]:
                out.append((key, hemi, val[hemi]["sha256"]))
    return out


def cache_key(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(atlas_entries(cfg)).encode()).hexdigest()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", action="store_true")
    a = ap.parse_args(argv)
    from yct.config import load_config

    cfg = load_config()
    entries = atlas_entries(cfg)
    if a.key:
        print(cache_key(cfg))
        return 0
    if not entries:
        print("ERROR no atlas entries with sha256 in config.yaml")
        return 1
    from yct.features.atlas import atlas_file

    for key, hemi, _ in entries:
        print(f"OK {key}/{hemi}: {atlas_file(key, hemi, cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
