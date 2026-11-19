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

BUG-018 (chunked clips > ~70 s get shifted + duplicated words upstream): clips longer than 60 s are
REFUSED unless --bug018-word-fix is given, which monkeypatches ExtractWordsFromAudio with absolute-time,
non-duplicated Word events (yct.tribe_run.word_events) and fails the run if the post-run word check
(n_words == .tsv rows, none after the clip, no duplicates) or the T check fails. GPU verification of the
fix is pending (BUGS.md BUG-018 status).

Usage: python run_clip.py --video clip.mp4 --feature-cache DIR --out OUT_PREFIX --weights WEIGHTS_DIR
       [--fresh-drift] [--bug018-word-fix]
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


def _revisions(weights: Path, tribev2_mod, torch, backbones: dict | None = None,
               bug018_fix: bool = False) -> dict:
    """Everything that determines the extracted features: part of the cache key (FIX-P4E, D-063) and
    checked against the sidecar. Includes the backbone revisions, the GPU model (device class) and the
    BUG-018 word-fix setting (QA P4-entry D11; P4 always runs with the fix on)."""
    from yct.tribe_run.feature_cache import sha256_file

    repo = Path(tribev2_mod.__file__).resolve().parents[1]
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip() or None
    return {
        "tribe_commit": commit,
        "ckpt_sha256": sha256_file(weights / "best.ckpt"),
        "backbones": backbones,
        "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
        "bug018_word_fix": bool(bug018_fix),
        **{p: _version(p) for p in ("transformers", "exca", "neuralset", "neuraltrain", "numpy",
                                    "x-transformers", "moviepy")},
    }


def ffprobe_duration(video: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(video)]).decode())


def preflight(video: Path, bug018_fix: bool, probe=ffprobe_duration) -> float:
    """BUG-018 hard guard before any GPU work: > 60 s needs --bug018-word-fix."""
    from yct.tribe_run.word_events import guard_duration

    dur = float(probe(video))
    guard_duration(dur, bug018_fix)
    return dur


def apply_word_fix(et, enabled: bool) -> None:
    if enabled:
        from yct.tribe_run.word_events import install

        install(et)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--feature-cache", required=True, help="persistent content-addressed feature cache")
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--fresh-drift", action="store_true", help="also report fresh-extraction drift")
    ap.add_argument("--keep-fresh", action="store_true",
                    help="keep the throw-away fresh extraction in OUT.fresh_feat/ and its predictions in "
                         "OUT.fresh_pred.npy (D-038 gate audit; D-063: Gate 2 re-scored on M1 after P4)")
    ap.add_argument("--qc-gate", choices=("t1", "t3"),
                    help="fail the run unless the per-clip P4 gate passes (yct.tribe_run.qc.clip_gate: one "
                         "Audio + one Video chunk, shape, T, finite, words; D-063)")
    ap.add_argument("--bug018-word-fix", action="store_true",
                    help="absolute-time Word events (BUG-018); required for clips > 60 s")
    ap.add_argument("--condition", choices=tuple(CONDITION_FEATURES), default="full",
                    help="T-ABL (D-071 Q1): predict from the cached features with only these modalities "
                         "(audioonly = [audio], textonly = [text]; the dropped ones are zero-filled). The "
                         "extraction (and so the cache key) is always the full model")
    return ap


# T-ABL (D-071 Q1; tribe_requirements.md: config_update={"data.features_to_use": [...]})
CONDITION_FEATURES: dict[str, list[str] | None] = {"full": None, "audioonly": ["audio"], "textonly": ["text"]}


def condition_config_update(condition: str) -> dict:
    feats = CONDITION_FEATURES[condition]
    return {} if feats is None else {"data.features_to_use": list(feats)}


def main() -> None:
    a = build_parser().parse_args()
    preflight(Path(a.video), a.bug018_word_fix)

    _strip_uv_from_path()
    assert shutil.which("uvx") is None, "uvx still on PATH"
    from yct.tribe_run.offline import check_hf_cache_pins, check_spacy_model, enforce_offline

    offline_env = enforce_offline()  # before huggingface_hub / transformers are imported
    backbones = {**check_hf_cache_pins(), **check_spacy_model()}

    import numpy as np
    import pandas as pd
    import torch
    import tribev2
    import tribev2.eventstransforms as et
    from tribev2 import TribeModel

    from yct.tribe_run.feature_cache import FeatureStore, run_cached

    def _no_asr(*_a, **_k):
        raise RuntimeError("ASR attempted: transcript .tsv missing/not used")

    et.ExtractWordsFromAudio._get_transcript_from_audio = staticmethod(_no_asr)
    apply_word_fix(et, a.bug018_word_fix)

    src = Path(a.video)
    if not src.with_suffix(".tsv").exists():
        raise SystemExit(f"missing transcript {src.with_suffix('.tsv')}")
    weights = Path(a.weights)
    timing: dict[str, float] = {}

    def _model(feat_dir: Path, condition: str = "full"):
        t0 = time.time()
        upd = condition_config_update(condition)
        m = TribeModel.from_pretrained(str(weights), cache_folder=str(feat_dir), device="cuda",
                                       **({"config_update": upd} if upd else {}))
        timing["wall_load_s"] = round(time.time() - t0, 1)
        return m

    def extract(video: Path, feat_dir: Path) -> None:
        # Populates TRIBE's (exca) feature cache in feat_dir; these predictions are discarded.
        if a.condition != "full":   # T-ABL: a condition run predicts from the full model's cache entry only
            raise RuntimeError(f"--condition {a.condition}: no cache entry for {video.name}; run full first")
        t0 = time.time()
        m = _model(feat_dir)
        m.predict(events=m.get_events_dataframe(video_path=str(video)), verbose=False)
        torch.cuda.synchronize()
        timing["wall_extract_s"] = round(time.time() - t0, 1)

    def predict(video: Path, feat_dir: Path):
        m = _model(feat_dir, a.condition)
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
    revisions = _revisions(weights, tribev2, torch, backbones)
    revisions["bug018_word_fix"] = bool(a.bug018_word_fix)   # part of the cache key (QA P4-entry D11)
    if a.bug018_word_fix:                                    # BUG-029 word-end clamp version (cache key)
        from yct.tribe_run.word_events import WORD_END_CLAMP
        revisions["bug018_word_end_clamp"] = WORD_END_CLAMP
    try:
        res = run_cached(src, FeatureStore(a.feature_cache), extract, predict,
                         revisions, a.out,
                         fresh_drift=a.fresh_drift, offline=True,
                         keep_fresh=(a.out + ".fresh_feat") if a.keep_fresh else None,
                         fresh_preds_out=(a.out + ".fresh_pred.npy") if a.keep_fresh else None)
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
    dur = ffprobe_duration(aux["video"])
    n_words = int((df.type == "Word").sum())
    from yct.tribe_run.word_events import check_word_events, is_installed, n_words_past_end

    tsv_df = pd.read_csv(src.with_suffix(".tsv"), sep="\t")
    n_tsv = len(tsv_df)
    word_check = {**check_word_events(df, n_tsv, dur), "bug018_fix": is_installed(et),
                  "n_tsv_words_past_end": n_words_past_end(tsv_df, dur)}   # BUG-029: clamped, not dropped
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
        "bug018_word_check": word_check,
        "condition": a.condition,
    }
    Path(a.out + ".json").write_text(json.dumps(m, indent=1, default=str))
    print(json.dumps(m, default=str))
    if a.bug018_word_fix and not (word_check["ok"] and m["T_within_1"]):
        raise SystemExit(f"BUG-018 word/T check FAILED: {word_check}, T_within_1={m['T_within_1']}")
    if a.qc_gate:
        from yct.tribe_run.qc import clip_gate

        g = clip_gate(m, a.qc_gate)
        if not g["pass"]:
            raise SystemExit(f"P4 clip gate ({a.qc_gate}) FAILED: {g['failures']}")


if __name__ == "__main__":
    main()
