"""Run TRIBE v2 (average subject, as shipped) on one clip and record P0 metrics.

The clip is copied into a fresh work dir together with its hand-made transcript (<stem>.tsv), so
the sidecar .wav is re-extracted and WhisperX (`uvx whisperx`) is never needed. `uvx` is removed
from PATH and the ASR entry point is monkeypatched to raise, so any ASR attempt fails loudly.

Usage: python run_clip.py --video clip.mp4 --cache EMPTY_DIR --out OUT_PREFIX --weights WEIGHTS_DIR
Writes OUT_PREFIX.npy (T, 20484) float32, OUT_PREFIX.segments.csv, OUT_PREFIX.json.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _strip_uv_from_path() -> None:
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep)
             if not (Path(p) / "uvx").exists()]
    os.environ["PATH"] = os.pathsep.join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", required=True)
    a = ap.parse_args()

    _strip_uv_from_path()
    assert shutil.which("uvx") is None, "uvx still on PATH"

    import numpy as np
    import torch
    import tribev2.eventstransforms as et
    from tribev2 import TribeModel

    def _no_asr(*_a, **_k):
        raise RuntimeError("ASR attempted: transcript .tsv missing/not used")
    et.ExtractWordsFromAudio._get_transcript_from_audio = staticmethod(_no_asr)

    cache = Path(a.cache)
    if cache.exists() and any(cache.iterdir()):
        raise SystemExit(f"cache folder not empty: {cache}")
    cache.mkdir(parents=True, exist_ok=True)
    src = Path(a.video)
    work = cache / "clip"
    work.mkdir()
    vid = work / src.name
    shutil.copy2(src, vid)
    shutil.copy2(src.with_suffix(".tsv"), vid.with_suffix(".tsv"))

    smi_log = Path(a.out + ".vram.txt")
    smi = subprocess.Popen(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                            "-lms", "1000"], stdout=smi_log.open("w"))
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    model = TribeModel.from_pretrained(a.weights, cache_folder=str(cache / "feat"), device="cuda")
    t_load = time.time() - t0
    t1 = time.time()
    df = model.get_events_dataframe(video_path=str(vid))
    preds, segments = model.predict(events=df, verbose=False)
    torch.cuda.synchronize()
    t_pred = time.time() - t1
    smi.terminate(); smi.wait()

    vram = [int(x) for x in smi_log.read_text().split() if x.strip().isdigit()]
    starts = [float(s.start) for s in segments]
    np.save(a.out + ".npy", preds)
    with open(a.out + ".segments.csv", "w") as f:
        f.write("tr_index,segment_start_s,segment_duration_s\n")
        for i, s in enumerate(segments):
            f.write(f"{i},{float(s.start):.3f},{float(s.duration):.3f}\n")
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(vid)]).decode())
    tr = float(model.data.TR)
    n_words = int((df.type == "Word").sum())
    m = {
        "clip": src.name, "duration_s": dur, "shape": list(preds.shape), "dtype": str(preds.dtype),
        "finite": bool(np.isfinite(preds).all()), "TR_s": tr, "expected_T": dur / tr,
        "T_within_1": abs(preds.shape[0] - dur / tr) <= 1,
        "first_segment_start_s": starts[0] if starts else None,
        "last_segment_start_s": starts[-1] if starts else None,
        "event_types": df.type.value_counts().to_dict(), "n_words": n_words,
        "wall_load_s": round(t_load, 1), "wall_events_predict_s": round(t_pred, 1),
        "wall_total_s": round(t_load + t_pred, 1),
        "peak_vram_smi_mib": max(vram) if vram else None, "vram_samples": len(vram),
        "torch_max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20),
        "torch_max_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20),
        "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
        "cuda": torch.version.cuda, "python": sys.version.split()[0],
        "pred_mean": float(preds.mean()), "pred_std": float(preds.std()),
        "uvx_on_path": shutil.which("uvx") is not None, "asr_called": False,
    }
    Path(a.out + ".json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m))


if __name__ == "__main__":
    main()
