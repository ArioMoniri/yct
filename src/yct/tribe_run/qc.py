"""Per-clip P4 QC gate and record sanitiser (FIX-P4E; D-063; Neuro P4-entry C2/D2, QA D1e/D5).

PER-CLIP ONLY. Output firewall (D-063 B2): until the P4b design entry is committed nothing may compute a
W-average, ROI/network readout, OOD or any cross-video statistic on analysis-set predictions. This module
therefore never loads a prediction array; it checks the metrics run_clip.py records (shape, finite, T,
chunks, words, offline/ASR guards, GPU model) and drops per-clip prediction statistics (pred_mean/std) and
feature names (they contain transcript text) from the record that leaves the box.

    clip_gate(metrics, track, expected=None) -> {"pass": bool, "failures": [str, ...]}

track "t1": the T1 trim (first <= 58.0 s; duration <= 58.5 s and >= window.end_tr + window.min_tail_s = 50 s,
D-039; T within 1 of duration / TR. BUG-030: was |T - 58| <= 1, which wrongly failed source videos
shorter than 58 s that D-039 keeps); "t3": the photometric copy of the same
clip, gated on its own duration (T within 1 of duration / TR). Both: exactly one Audio and one Video chunk
(v2.md:52), shape (T, 20484), all finite, n_words == .tsv rows, no word after the clip, no ASR, no uvx,
offline, GPU == GPU_NAME, BUG-018 word fix on (one setting for all of P4, QA D11).
"""
from __future__ import annotations

import re
from typing import Any

from yct.tribe_run.feature_cache import revisions_sha256

GPU_NAME = "NVIDIA A100-SXM4-40GB"   # D-062 / v2.md §3: one GPU type for all of P4 (gpu_1x_a100_sxm4)
N_VERTICES = 20484
T1_TRIM_S = 58.0
T1_MAX_PROBE_S = 58.5
T1_MIN_S = 45 + 5          # window.end_tr + window.min_tail_s (D-039; frozen, D-063); test pins == config
WORD_END_CLAMP = "v1"      # BUG-029: one word-end clamp version for all of P4 (== word_events.WORD_END_CLAMP)
TRACKS = ("t1", "t3")

_KEEP = ("duration_s", "shape", "finite", "TR_s", "expected_T", "T_within_1", "n_words", "n_segments",
         "words_after_duration", "wall_load_s", "wall_extract_s", "wall_events_predict_s",
         "peak_vram_smi_mib", "torch_max_allocated_mib", "gpu", "torch", "cuda", "uvx_on_path", "asr_called",
         "input_sha256", "transcript_sha256", "cache_key", "cache_reused", "pred_sha256", "pred_shape",
         "pred_dtype", "offline", "revisions", "event_types")


def _n_chunks(v: Any) -> int | None:
    if isinstance(v, int):
        return v
    if isinstance(v, list | tuple):
        return len(v)
    return None


def short_extractor(name: str) -> str:
    m = re.search(r"extractors\.(\w+)\.(\w+)", name)
    return f"{m.group(1)}.{m.group(2)}" if m else re.sub(r"[^\w.=-]", "_", name)[:60]


def sanitize_metrics(j: dict[str, Any]) -> dict[str, Any]:
    """Numbers and hashes only (see module docstring); idempotent."""
    out = {k: j[k] for k in _KEEP if k in j}
    out["chunks"] = {k: _n_chunks(v) for k, v in (j.get("chunks") or {}).items()} if "chunks" in j else None
    if out["chunks"] is None:
        out.pop("chunks")
    wc = j.get("bug018_word_check") or {}
    out["bug018_word_check"] = {k: wc.get(k) for k in ("ok", "n_words", "n_tsv_rows", "bug018_fix",
                                                       "n_duplicate_text_start", "words_after_duration")
                                if k in wc}
    if "n_feature_files" in j:
        out["n_feature_files"] = j["n_feature_files"]
    else:
        out["n_feature_files"] = len(j.get("feature_sha256") or {})
    if j.get("revisions") is not None:
        out["revisions_sha256"] = revisions_sha256(j["revisions"])
    d = j.get("fresh_extraction_drift") or j.get("drift")
    if d:
        fr = d.get("feature_reliability") or {}
        per: dict[str, Any] = {}
        for k, v in (fr.get("per_extractor") or d.get("per_extractor") or {}).items():
            s = short_extractor(k)
            per[s if s not in per else f"{s}#{len(per)}"] = {x: v.get(x) for x in
                                                             ("n_arrays", "reliability", "max_abs_diff",
                                                              "bit_identical") if x in v}
        out["drift"] = {
            "pred_reliability": d.get("pred_reliability"), "pred_max_abs_diff": d.get("pred_max_abs_diff"),
            "pred_bit_identical": d.get("pred_bit_identical"),
            "n_arrays": fr.get("n_arrays", d.get("n_arrays")),
            "n_unreadable": len(fr.get("unreadable") or []) if fr else d.get("n_unreadable"),
            "reliability_min": fr.get("reliability_min", d.get("reliability_min")),
            "reliability_gate": fr.get("reliability_gate", d.get("reliability_gate")),
            "reliability_gate_pass": fr.get("reliability_gate_pass", d.get("reliability_gate_pass")),
            "fresh_pred_sha256": d.get("fresh_pred_sha256"), "per_extractor": per}
    return out


def clip_gate(m: dict[str, Any], track: str, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed per-clip gate; a missing field is a failure."""
    if track not in TRACKS:
        raise ValueError(f"track must be one of {TRACKS}, got {track!r}")
    f: list[str] = []
    chunks = m.get("chunks")
    if not isinstance(chunks, dict):
        f.append("chunks missing")
    else:
        for t in ("Audio", "Video"):
            n = _n_chunks(chunks.get(t))
            if n != 1:
                f.append(f"{t} chunks = {n}, need exactly 1")
    shape = m.get("shape") or m.get("pred_shape")
    n_t = None
    if not (isinstance(shape, list | tuple) and len(shape) == 2 and shape[1] == N_VERTICES):
        f.append(f"shape {shape} is not (T, {N_VERTICES})")
    else:
        n_t = int(shape[0])
    if m.get("finite") is not True:
        f.append("predictions not all finite")
    if m.get("T_within_1") is not True:
        f.append("T not within 1 of duration / TR")
    dur = m.get("duration_s")
    if not isinstance(dur, int | float):
        f.append("duration missing")
    elif track == "t1":
        if dur > T1_MAX_PROBE_S:
            f.append(f"T1 duration {dur} s > {T1_MAX_PROBE_S} s")
        if dur < T1_MIN_S:
            f.append(f"T1 duration {dur} s < {T1_MIN_S} s (window end + min tail, D-039)")
        if n_t is not None and (n_t > T1_TRIM_S + 1 or abs(n_t - dur) > 1):
            f.append(f"T1 T = {n_t}, need within 1 of duration {dur} s and <= 59")
    wc = m.get("bug018_word_check") or {}
    if wc.get("ok") is not True:
        f.append("word check not ok")
    if wc.get("n_words") is None or wc.get("n_words") != wc.get("n_tsv_rows"):
        f.append(f"word count {wc.get('n_words')} != .tsv rows {wc.get('n_tsv_rows')}")
    if m.get("words_after_duration", 1) != 0:
        f.append("word events after the clip end")
    for k, want in (("asr_called", False), ("uvx_on_path", False), ("offline", True)):
        if m.get(k) is not want:
            f.append(f"{k} is {m.get(k)!r}, need {want}")
    rev = m.get("revisions") or {}
    if rev.get("gpu") != GPU_NAME:
        f.append(f"gpu {rev.get('gpu')!r} != {GPU_NAME!r} (one GPU type for all of P4)")
    if rev.get("bug018_word_fix") is not True:
        f.append("bug018 word fix not on (one setting for all of P4)")
    if rev.get("bug018_word_end_clamp") != WORD_END_CLAMP:
        f.append(f"word-end clamp {rev.get('bug018_word_end_clamp')!r} != {WORD_END_CLAMP!r} (BUG-029)")
    for k in ("pred_sha256", "cache_key", "input_sha256", "transcript_sha256"):
        if not m.get(k):
            f.append(f"{k} missing")
    for k, want in (expected or {}).items():
        got = revisions_sha256(rev) if k == "revisions_sha256" and rev else m.get(k)
        if got != want:
            f.append(f"{k} {str(got)[:16]} != expected {str(want)[:16]}"
                     + (" (revisions differ from the rest of P4)" if k == "revisions_sha256" else ""))
    return {"pass": not f, "failures": f}
