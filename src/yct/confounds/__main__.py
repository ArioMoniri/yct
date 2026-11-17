"""CLI: python -m yct.confounds --mp4 X.mp4 --wav X.wav [--tsv X.tsv] --out confounds.parquet"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yct.config import load_config
from yct.confounds.core import extract_confounds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yct.confounds")
    ap.add_argument("--mp4", required=True)
    ap.add_argument("--wav", required=True)
    ap.add_argument("--tsv", default=None)
    ap.add_argument("--out", required=True, help=".parquet or .csv for the per-TR table")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    df, summary = extract_confounds(a.mp4, a.wav, a.tsv, cfg=load_config(a.config))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False) if out.suffix == ".parquet" else df.to_csv(out, index=False)
    json.dump(summary, sys.stdout, indent=2, default=float)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
