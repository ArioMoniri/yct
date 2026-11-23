#!/usr/bin/env python3
"""D-091 NAT word tsvs, POD side (run with /work/yct/venv python from a repo checkout on the pod).

Builds the 15 NAT <CLIP_ID>.tsv with the frozen P2b core (src/yct/tribe_run/nat_tsv.py) into
controls.refclips_d091.nat_tsv.out_dir, twice (run 2 into a temp dir; every tsv sha must be identical), and
writes the sidecar (shas + counts only; no text) to --out. Prints counts only. Exit 1 on any STOP
(tsv_invalid, zero words, provenance mismatch, non-deterministic build): a human decides; no substitution.

    python scripts/nat_tsv_build.py --clip-manifest data/refstim/refclips_manifest.json \
        --out data/refstim/nat_tsv_manifest.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yct.config import load_config  # noqa: E402
from yct.tribe_run import nat_tsv as nt  # noqa: E402


def ffprobe_duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(p)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip-manifest", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cfg = load_config()
    d = cfg["controls"]["refclips_d091"]["nat_tsv"]
    text = Path(a.clip_manifest).read_text()
    want = cfg["controls"]["refclips_artifacts"]["manifest_sha256"]
    if nt.hashlib.sha256(text.encode()).hexdigest() != want:
        raise SystemExit("clip manifest sha256 != the frozen manifest_sha256")
    rows = nt.nat_rows(json.loads(text))
    sc1 = nt.build(rows, Path(d["json_dir"]), Path(d["t1_dir"]), Path(d["out_dir"]), ffprobe_duration, cfg)
    with tempfile.TemporaryDirectory() as tmp:
        sc2 = nt.build(rows, Path(d["json_dir"]), Path(d["t1_dir"]), Path(tmp) / "run2", ffprobe_duration,
                       cfg)
    same = nt.sidecar_text(sc1) == nt.sidecar_text(sc2)
    sc1["runs"] = 2
    sc1["runs_bit_identical"] = same
    Path(a.out).write_text(nt.sidecar_text(sc1))
    summary = {"n": sc1["n"], "stop": sc1["stop"], "runs_bit_identical": same,
               "n_words": [r["n_words"] for r in sc1["rows"]],
               "all_valid": all(r["tsv_valid"] for r in sc1["rows"])}
    print(json.dumps(summary))
    return 0 if (same and not sc1["stop"] and summary["all_valid"]) else 1


if __name__ == "__main__":
    sys.exit(main())
