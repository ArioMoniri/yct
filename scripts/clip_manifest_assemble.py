"""Write data/refstim/refclips_manifest.json (D-071 (d)) from the committed parts and the TALKFACE finish
record; prints its sha256 (to go to controls.refclips_artifacts.manifest_sha256). Local, no network.

Usage: clip_manifest_assemble.py [--talkface data/refstim/talkface_finish_record.json]
                                 [--out data/refstim/refclips_manifest.json] [--check]
--check: refuse (exit 1) unless the written file's sha256 equals the configured manifest_sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yct.config import load_config  # noqa: E402
from yct.tribe_run import clip_manifest as cm  # noqa: E402

TALK = ROOT / "data" / "refstim" / "talkface_finish_record.json"
OUT = ROOT / "data" / "refstim" / "refclips_manifest.json"


def build(cfg: dict, talk_path: Path = TALK) -> str:
    return cm.manifest_text(cm.assemble(cm.load_parts(ROOT, cfg), json.loads(talk_path.read_text()), cfg))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--talkface", default=str(TALK))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    text = build(cfg, Path(a.talkface))
    sha = hashlib.sha256(text.encode()).hexdigest()
    if a.check:
        want = cfg["controls"]["refclips_artifacts"]["manifest_sha256"]
        if sha != want or Path(a.out).read_text() != text:
            print(f"manifest sha {sha} != configured {want} (or the committed file differs)")
            return 1
    else:
        Path(a.out).write_text(text)
    print(sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
