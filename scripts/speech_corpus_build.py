#!/usr/bin/env python3
"""D-085 draft: build data/refstim/speech/speech_corpus_v1.json from the recorded IEEE/Harvard source page.

  python scripts/speech_corpus_build.py [SOURCE_HTML] --fetched-utc YYYY-MM-DD

Offline and deterministic: parse 72 x 10 sentences, apply the frozen exclusion lexicon, order the kept
sentences by sha256(text). The written file holds (list, item, sha256) only, never sentence text (owner
2026-11-22). Without SOURCE_HTML the raw page is fetched from the private bucket (speech.private_raw_s3).
No synthesis happens here (that waits for the speech_corpus_sha256 freeze). Prints the corpus sha256 for
controls.refclips_artifacts.speech_corpus_sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.tribe_run import speech_corpus as S  # noqa: E402,N812


def fetch_private_raw(spec: dict) -> bytes:
    """The raw source page from the private yct bucket (D-059: yct resources only)."""
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "raw.html"
        subprocess.run(["aws", "s3", "cp", "--only-show-errors", spec["private_raw_s3"], str(dst)],
                       check=True, env={**os.environ, "AWS_DEFAULT_REGION": "eu-central-1"})
        return dst.read_bytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_html", type=Path, nargs="?")
    ap.add_argument("--fetched-utc", required=True)
    a = ap.parse_args()
    cfg = load_config()
    spec = cfg["controls"]["refclips_d085"]["speech"]
    raw = a.source_html.read_bytes() if a.source_html else fetch_private_raw(spec)
    rows = S.parse_harvard_html(raw.decode("utf-8"))
    if len(rows) != 720 or sorted({r["list"] for r in rows}) != list(range(1, 73)):
        raise SystemExit(f"source does not parse to 72 x 10 sentences ({len(rows)} rows)")
    lex_path = ROOT / spec["lexicon_file"]
    lex = json.loads(lex_path.read_text())
    lex["_sha256"] = hashlib.sha256(lex_path.read_bytes()).hexdigest()
    source = {"url": spec["source_url"], "fetched_utc": a.fetched_utc,
              "raw_sha256": hashlib.sha256(raw).hexdigest(),
              "citation": "IEEE Recommended Practice for Speech Quality Measurements, IEEE Trans. Audio "
                          "Electroacoust. 17(3):225-246, 1969, Appendix C (IEEE Std 297-1969, "
                          "doi:10.1109/IEEESTD.1969.7405210)"}
    doc = S.build_corpus(rows, lex, spec, source)
    sha = S.write_corpus(doc, ROOT / spec["corpus_file"])
    print(json.dumps({"kept": len(doc["queue"]), "excluded": len(doc["excluded"]), "sha256": sha}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
