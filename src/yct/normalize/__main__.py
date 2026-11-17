"""CLI: python -m yct.normalize --in <file> --out <dir> [--config config.yaml] -> JSON record on stdout."""
from __future__ import annotations

import argparse
import json
import sys

from yct.config import load_config
from yct.normalize.core import normalize_video


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yct.normalize")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    rec = normalize_video(a.src, a.out, load_config(a.config))
    json.dump(rec, sys.stdout, indent=2, default=float)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
