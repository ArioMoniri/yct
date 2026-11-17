"""GPU-box CLI for P2b: one pinned WhisperX batch over many 16 kHz wavs -> raw <stem>.json + a run record.

  python -m yct.transcribe --out-dir DIR --record RUN.json WAV [WAV ...]

The JSON files hold speech text: they stay on the box / pod (never in the public repo). The record holds no
text: whisperx / faster-whisper / ctranslate2 / torch versions, the resolved model snapshot revisions in the
HF cache, the argv (paths only), wall time, and which stems produced no JSON. Conversion to TRIBE .tsv
(`store_transcript`, validation against the media duration) happens pod-side (scripts/wave1_p2b_pod.py).
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import os
import sys
import time
from pathlib import Path

from yct.config import load_config
from yct.transcribe.core import transcribe_whisperx_batch


def _v(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def hf_snapshot_revisions(hub: Path | None = None) -> dict[str, str]:
    """{repo: refs/main sha} for every model in the HF hub cache (records what faster-whisper resolved)."""
    hub = hub or Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    out = {}
    for d in sorted(hub.glob("models--*")):
        ref = d / "refs" / "main"
        if ref.exists():
            out[d.name[len("models--"):].replace("--", "/")] = ref.read_text().strip()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yct.transcribe")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--record", required=True)
    ap.add_argument("wavs", nargs="+")
    a = ap.parse_args(argv)
    cfg = load_config()
    t0 = time.time()
    res = transcribe_whisperx_batch(a.wavs, a.out_dir, cfg)
    rec = {
        "whisperx": res["version"], "pinned": cfg["transcribe"]["whisperx"],
        **{p: _v(p) for p in ("faster-whisper", "ctranslate2", "torch", "torchaudio", "pyannote.audio",
                              "transformers", "nltk")},
        "hf_snapshot_revisions": hf_snapshot_revisions(),
        "command": res["command"], "n_wavs": len(a.wavs), "n_json": len(res["segments"]),
        "missing": res["missing"], "wall_s": round(time.time() - t0, 1), "python": sys.version.split()[0],
    }
    Path(a.record).write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec[k] for k in ("whisperx", "n_wavs", "n_json", "missing", "wall_s")}))
    return 0 if not res["missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
