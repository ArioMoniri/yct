#!/usr/bin/env python3
"""Recompute the D-038 per-feature reliability of kept fresh extractions (`run_clip.py --keep-fresh`)
against their cached features, CPU only (runs on the pod; no exca/neuralset/torch needed).

Usage: python scripts/recompute_reliability.py POD_RUN_DIR [NAME ...]
  POD_RUN_DIR holds res/<NAME>.json (with cache_key), res/<NAME>.fresh_feat/ and fc/<cache_key>/feat/.
Writes res/<NAME>.reliability.json and prints a one-line summary per NAME.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yct.tribe_run.feature_cache import feature_reliability  # noqa: E402


def main(argv: list[str]) -> int:
    run = Path(argv[0])
    names = argv[1:] or sorted(p.name[: -len(".fresh_feat")] for p in (run / "res").glob("*.fresh_feat"))
    ok = True
    for n in names:
        m = json.loads((run / "res" / f"{n}.json").read_text())
        fr = feature_reliability(run / "fc" / m["cache_key"] / "feat", run / "res" / f"{n}.fresh_feat")
        fr["cache_key"], fr["clip"] = m["cache_key"], m.get("clip")
        (run / "res" / f"{n}.reliability.json").write_text(json.dumps(fr, indent=1))
        per = {k.split(".")[2] if k.count(".") >= 2 else k: round(v["reliability"], 6)
               for k, v in fr["per_extractor"].items()}
        print(json.dumps({"name": n, "n_arrays": fr["n_arrays"], "unreadable": len(fr["unreadable"]),
                          "reliability_min": fr["reliability_min"], "gate_pass": fr["reliability_gate_pass"],
                          "per_extractor": per}))
        ok &= fr["reliability_gate_pass"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
