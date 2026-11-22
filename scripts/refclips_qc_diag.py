#!/usr/bin/env python3
"""Diagnostic only (no rule, no decision): for each failed LOC / LOC_SCR clip, list the TRs where the frozen
stimulus QC (yct.confounds face_area_crop_frac) sees a face, and what the clip shows then: an event
(category, image) or a scramble segment (category and image of the scrambled exemplar).

  python scripts/refclips_qc_diag.py BUILD_DIR > diag.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.confounds.core import tr_grid, video_features  # noqa: E402
from yct.tribe_run import refclips58 as R  # noqa: E402,N812


def main() -> int:
    out = Path(sys.argv[1])
    cfg = load_config()
    tr = cfg["tribe"]["tr_s"]
    grid = tr_grid(R.DUR, tr)
    qc = {q["name"]: q for q in json.loads((out / "qc.json").read_text())}
    res = []
    for c in R.plan(cfg):
        if c.family not in ("LOC", "LOC_SCR") or qc[c.name]["pass"]:
            continue
        fa = np.nan_to_num(video_features(out / f"{c.name}.mp4", grid, cfg)["face_area_crop_frac"])
        hits = []
        for t in np.flatnonzero(fa > 0):
            k = R._in_event(t * tr + tr / 2, c)
            if k is not None:
                e = c.events[k]
                what = f"{'intact' if c.family == 'LOC' else 'swap-scramble'} {e['category']}_{e['image']:02d}"
            else:
                e = c.events[min(R._segment(t * tr + tr / 2, c), len(c.events) - 1)]
                what = f"scramble of {e['category']}_{e['image']:02d}"
            hits.append({"tr": int(t), "face_area": round(float(fa[t]), 4), "shows": what})
        res.append({"name": c.name, "n_hit_trs": len(hits), "hits": hits})
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
