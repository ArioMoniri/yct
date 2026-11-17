"""Run TRIBE v2 (average subject, as shipped) on one clip and record P0 metrics.

Determinism by design (BUG-006): features are extracted exactly once per input sha256 into a
content-addressed cache (``--feature-cache``, see yct.tribe_run.feature_cache); the reported
prediction always reads only cached features, so reruns are bit-identical. ``--fresh-drift`` also
re-extracts into a throw-away dir and REPORTS the drift (not gated).

The clip is copied into the cache entry together with its hand-made transcript (<stem>.tsv), so the
sidecar .wav is re-extracted and WhisperX (`uvx whisperx`) is never needed. `uvx` is removed from
PATH, the ASR entry point is monkeypatched to raise, and every TRIBE call runs inside
yct.transcribe.asr_guard(), so any ASR attempt fails loudly. Copy this repo's src/ next to the
script's package layout (src/yct/...) on the GPU box; remote_setup.sh pins the environment.

Offline (BUG-003): HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 are set before any HF import, the HF cache
must resolve the three backbones to the pinned revisions (yct.tribe_run.offline.BACKBONE_REVISIONS;
remote_setup.sh pre-populates it) and every extraction/prediction runs with non-loopback network
blocked. The pinned revisions are part of the cache revisions.

Usage: python run_clip.py --video clip.mp4 --feature-cache DIR --out OUT_PREFIX --weights WEIGHTS_DIR
       [--fresh-drift]
Writes OUT_PREFIX.npy (T, 20484) float32, OUT_PREFIX.segments.csv, OUT_PREFIX.events.csv (every TRIBE
event with start/duration: chunk/context boundaries, BUG-002 word-time check), OUT_PREFIX.json.
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/ (for yct.*)


def _strip_uv_from_path() -> None:
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep)
             if not (Path(p) / "uvx").exists()]
    os.environ["PATH"] = os.pathsep.join(parts)


def _version(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def _revisions(weights: Path, tribev2_mod, torch, backbones: dict | None = None) -> dict:
    """Everything that determines the extracted features; a mismatch refuses to reuse the cache."""
    from yct.tribe_run.feature_cache import sha256_file

    repo = Path(tribev2_mod.__file__).resolve().parents[1]
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip() or None
    return {
        "tribe_commit": commit,
        "ckpt_sha256": sha256_file(weights / "best.ckpt"),
        "backbones": backbones,
        "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
        **{p: _version(p) for p in ("transformers", "exca", "neuralset", "neuraltrain", "numpy",
                                    "x-transformers", "moviepy")},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--feature-cache", required=True, help="persistent content-addressed feature cache")
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--fresh-drift", action="store_true", help="also report fresh-extraction drift")
    a = ap.parse_args()

    _strip_uv_from_path()
    assert shutil.which("uvx") is None, "uvx still on PATH"
    from yct.tribe_run.offline import check_hf_cache_pins, enforce_offline

    offline_env = enforce_offline()  # before huggingface_hub / transformers are imported
    backbones = check_hf_cache_pins()

    import numpy as np
    import torch
    import tribev2
    import tribev2.eventstransforms as et
    from tribev2 import TribeModel

    from yct.tribe_run.feature_cache import FeatureStore, run_cached

    def _no_asr(*_a, **_k):
        raise RuntimeError("ASR attempted: transcript .tsv missing/not used")

    et.ExtractWordsFromAudio._get_transcript_from_audio = staticmethod(_no_asr)

    src = Path(a.video)
    if not src.with_suffix(".tsv").exists():
        raise SystemExit(f"missing transcript {src.with_suffix('.tsv')}")
    weights = Path(a.weights)
    timing: dict[str, float] = {}

    def _model(feat_dir: Path):
        t0 = time.time()
        m = TribeModel.from_pretrained(str(weights), cache_folder=str(feat_dir), device="cuda")
        timing["wall_load_s"] = round(time.time() - t0, 1)
        return m

    def extract(video: Path, feat_dir: Path) -> None:
        # Populates TRIBE's (exca) feature cache in feat_dir; these predictions are discarded.
        t0 = time.time()
        m = _model(feat_dir)
        m.predict(events=m.get_events_dataframe(video_path=str(video)), verbose=False)
        torch.cuda.synchronize()
        timing["wall_extract_s"] = round(time.time() - t0, 1)

    def predict(video: Path, feat_dir: Path):
        m = _model(feat_dir)
        t1 = time.time()
        df = m.get_events_dataframe(video_path=str(video))
        preds, segments = m.predict(events=df, verbose=False)
        torch.cuda.synchronize()
        timing["wall_events_predict_s"] = round(time.time() - t1, 1)
        return np.asarray(preds), {"segments": segments, "df": df, "TR": float(m.data.TR), "video": video}

    smi_log = Path(a.out + ".vram.txt")
    smi = subprocess.Popen(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                            "-lms", "1000"], stdout=smi_log.open("w"))
    torch.cuda.reset_peak_memory_stats()
    try:
        res = run_cached(src, FeatureStore(a.feature_cache), extract, predict,
                         _revisions(weights, tribev2, torch, backbones), a.out, fresh_drift=a.fresh_drift,
                         offline=True)
    finally:
        smi.terminate()
        smi.wait()
    aux = res.pop("aux")
    preds = np.load(a.out + ".npy")
    segments, df, tr = aux["segments"], aux["df"], aux["TR"]

    vram = [int(x) for x in smi_log.read_text().split() if x.strip().isdigit()]
    starts = [float(s.start) for s in segments]
    with open(a.out + ".segments.csv", "w") as f:
        f.write("tr_index,segment_start_s,segment_duration_s\n")
        for i, s in enumerate(segments):
            f.write(f"{i},{float(s.start):.3f},{float(s.duration):.3f}\n")
    ev = df.copy()
    keep = [c for c in ("type", "start", "duration", "stop", "text", "sequence_id") if c in ev.columns]
    ev[keep].to_csv(a.out + ".events.csv", index=False)
    chunks = {t: [[round(float(r.start), 3), round(float(r.duration), 3)]
                  for r in ev[ev.type == t].itertuples()]
              for t in ("Audio", "Video") if (ev.type == t).any()}
    words = ev[ev.type == "Word"]
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(aux["video"])]).decode())
    n_words = int((df.type == "Word").sum())
    m = {
        **res,
        "clip": src.name, "duration_s": dur, "shape": list(preds.shape), "dtype": str(preds.dtype),
        "finite": bool(np.isfinite(preds).all()), "TR_s": tr, "expected_T": dur / tr,
        "T_within_1": abs(preds.shape[0] - dur / tr) <= 1,
        "first_segment_start_s": starts[0] if starts else None,
        "last_segment_start_s": starts[-1] if starts else None,
        "event_types": df.type.value_counts().to_dict(), "n_words": n_words,
        "chunks": chunks, "n_segments": len(starts),
        "word_start_min_s": float(words.start.min()) if len(words) else None,
        "word_start_max_s": float(words.start.max()) if len(words) else None,
        "words_after_duration": int((words.start > dur).sum()) if len(words) else 0,
        "offline_env": offline_env, "backbone_revisions": backbones,
        **timing,
        "peak_vram_smi_mib": max(vram) if vram else None, "vram_samples": len(vram),
        "torch_max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20),
        "torch_max_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20),
        "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
        "cuda": torch.version.cuda, "python": sys.version.split()[0],
        "pred_mean": float(preds.mean()), "pred_std": float(preds.std()),
        "uvx_on_path": shutil.which("uvx") is not None, "asr_called": False,
    }
    Path(a.out + ".json").write_text(json.dumps(m, indent=1, default=str))
    print(json.dumps(m, default=str))


if __name__ == "__main__":
    main()
