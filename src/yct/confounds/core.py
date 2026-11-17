"""P3 per-TR stimulus confounds (M0) on the 1.0 s TR grid (v2.md §5 P3; ROADMAP P3).

Input: a normalized T1 mp4 (+ its 16 kHz mono sidecar WAV, + optional TRIBE-format tsv).
TR k covers [k*TR, (k+1)*TR); n_tr = ceil(duration / TR); the last TR may be partial (`tr_coverage`).

Choices (documented):
  * speech fraction: energy VAD (yct.media.energy_vad) - not speech-specific.
  * pitch: normalized-autocorrelation F0 on VAD-active frames (no librosa dependency).
  * motion energy: mean absolute luma difference between consecutive sampled frames (0..1), full frame
    and inside the V-JEPA2 central crop (short edge -> 292, centre 256x256).
  * faces: OpenCV Haar frontal-face cascade (ships with opencv-python-headless; mediapipe needs model
    downloads). Frontal faces only; profile faces are missed. Detection runs on the 292-short-edge frame;
    the crop-aware columns (v2.4 G-D032 N-D5) use only what V-JEPA2 sees, the central 256x256 crop:
      - `face_area_crop_frac` = summed box area inside the crop / crop area (capped at 1). This is the
        P4b FFC regressor (`confounds.ffc_regressor`) and the M0 face-area feature;
      - `face_present_crop` = 1 if any box has >= `face.crop_min_inside_frac` of its area inside the crop.
    The full-frame columns (`face_present_frac`, `face_area_frac`) are kept for QC only.
  * luminance / contrast: full frame and inside the crop (`luminance_crop`, `contrast_crop`).
  * per-video summary carries `has_audio_track`, `n_words`, `speech_rate_wps` (words / s over the clip) and
    `speech_frac`; the W-level values used by M0 are computed in yct.features.m0.
  * scene cuts: PySceneDetect ContentDetector.
  * on-screen text: NOT implemented (needs a downloaded EAST/OCR model); column is NaN and the summary
    carries `text_detection: "not_implemented"`.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yct.config import load_config
from yct.media import decode_audio, duration, energy_vad, ffprobe, iter_gray_frames, stream

FEATURES = [
    "rms_db",
    "speech_frac",
    "speech_rate_wps",
    "pitch_mean_hz",
    "pitch_sd_hz",
    "luminance",
    "contrast",
    "luminance_crop",
    "contrast_crop",
    "motion_energy",
    "motion_energy_crop",
    "scene_cuts",
    "face_present_frac",
    "face_count_mean",
    "face_area_frac",
    "face_area_outside_crop_frac",
    "face_present_crop",
    "face_area_crop_frac",
    "text_frac",
]


def tr_grid(dur: float, tr: float) -> pd.DataFrame:
    n = max(1, math.ceil(dur / tr - 1e-6))
    start = np.arange(n) * tr
    end = np.minimum(start + tr, dur)
    return pd.DataFrame(
        {"tr": np.arange(n), "tr_start_s": start, "tr_end_s": end, "tr_coverage": (end - start) / tr}
    )


def _bin(t: np.ndarray, tr: float, n: int) -> np.ndarray:
    return np.minimum((np.asarray(t) // tr).astype(int), n - 1)


def _per_tr(t: np.ndarray, v: np.ndarray, tr: float, n: int, how: str = "mean") -> np.ndarray:
    out = np.full(n, np.nan)
    if len(t) == 0:
        return out
    b = _bin(t, tr, n)
    for k in range(n):
        sel = v[b == k]
        sel = sel[np.isfinite(sel)]
        if sel.size:
            out[k] = {"mean": np.mean, "std": np.std, "sum": np.sum}[how](sel)
    return out


# ---------------------------------------------------------------- audio
def pitch_track(x: np.ndarray, sr: int, pc: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """(frame centre times, F0 Hz or NaN when unvoiced) via normalized autocorrelation."""
    flen, hop = int(round(pc["frame_s"] * sr)), int(round(pc["hop_s"] * sr))
    if len(x) < flen:
        return np.zeros(0), np.zeros(0)
    n = 1 + (len(x) - flen) // hop
    idx = np.arange(flen)[None, :] + hop * np.arange(n)[:, None]
    fr = x[idx] - x[idx].mean(axis=1, keepdims=True)
    fr *= np.hanning(flen)[None, :]
    nfft = 1 << (2 * flen - 1).bit_length()
    spec = np.fft.rfft(fr, nfft, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, nfft, axis=1)[:, :flen]
    e0 = ac[:, :1]
    win_ac = np.correlate(np.hanning(flen), np.hanning(flen), "full")[flen - 1 :]
    acn = np.where(e0 > 0, ac / np.maximum(e0, 1e-12), 0) / np.maximum(win_ac / win_ac[0], 1e-3)
    lo, hi = int(sr / pc["fmax_hz"]), min(int(sr / pc["fmin_hz"]), flen - 2)
    seg = acn[:, lo : hi + 1]
    # first local maximum within octave_ratio of the best one (avoids sub-octave errors)
    locmax = np.zeros_like(seg, dtype=bool)
    locmax[:, 1:-1] = (seg[:, 1:-1] >= seg[:, :-2]) & (seg[:, 1:-1] >= seg[:, 2:])
    best = np.max(np.where(locmax, seg, -np.inf), axis=1, keepdims=True)
    cand = locmax & (seg >= pc["octave_ratio"] * best)
    k = np.where(cand.any(axis=1), np.argmax(cand, axis=1), np.argmax(seg, axis=1))
    peak = seg[np.arange(n), k]
    lag = (k + lo).astype(float)
    # parabolic interpolation around the peak
    kk = np.clip(k + lo, 1, flen - 2)
    a, b, c = acn[np.arange(n), kk - 1], acn[np.arange(n), kk], acn[np.arange(n), kk + 1]
    den = a - 2 * b + c
    lag = lag + np.where(np.abs(den) > 1e-12, 0.5 * (a - c) / np.where(den == 0, 1, den), 0)
    f0 = np.where(peak >= pc["voicing_threshold"], sr / lag, np.nan)
    t = (np.arange(n) * hop + flen / 2) / sr
    return t, f0


def audio_features(
    wav: str | Path, grid: pd.DataFrame, cfg: dict[str, Any], words: pd.DataFrame | None
) -> dict:
    c, vc, tr = cfg["confounds"], cfg["vad"], cfg["tribe"]["tr_s"]
    sr = vc["sample_rate"]
    x = decode_audio(wav, sr, 1)[:, 0]
    n = len(grid)
    t = np.arange(len(x)) / sr
    ms = _per_tr(t, x**2, tr, n)
    rms_db = np.maximum(10 * np.log10(np.maximum(ms, 1e-30)), c["rms_floor_db"])
    rms_db = np.where(np.isfinite(ms), rms_db, c["rms_floor_db"])
    mask, segs = energy_vad(x, sr, vc)
    tv = np.arange(mask.size) * vc["hop_s"] + vc["frame_s"] / 2
    speech = np.nan_to_num(_per_tr(tv, mask.astype(float), tr, n), nan=0.0)
    tp, f0 = pitch_track(x, sr, c["pitch"])
    if tp.size and mask.size:

        def vad_at(tt: np.ndarray) -> np.ndarray:
            k = np.round((tt - vc["frame_s"] / 2) / vc["hop_s"]).astype(int)
            return mask[np.clip(k, 0, mask.size - 1)]

        half = c["pitch"]["frame_s"] / 2  # the whole pitch frame must lie in VAD-active audio
        active = vad_at(tp - half) & vad_at(tp + half)
        f0 = np.where(active, f0, np.nan)
    rate = word_rate_per_tr(words, grid, tr)
    return {
        "rms_db": rms_db,
        "speech_frac": speech,
        "speech_rate_wps": rate,
        "pitch_mean_hz": _per_tr(tp, f0, tr, n),
        "pitch_sd_hz": _per_tr(tp, f0, tr, n, "std"),
        "_f0": f0,
        "_speech_s": sum(e - s for s, e in segs),
    }


def word_rate_per_tr(words: pd.DataFrame | None, grid: pd.DataFrame, tr: float) -> np.ndarray:
    """Per-TR speech rate (words / s): words binned by midpoint, divided by the TR's coverage.
    NaN everywhere without a transcript; 0 for a transcript with no words."""
    n = len(grid)
    if words is None:
        return np.full(n, np.nan)
    if not len(words):
        return np.zeros(n)
    mid = (words["start"] + words["duration"] / 2).to_numpy(dtype=float)
    cnt = np.bincount(_bin(mid, tr, n), minlength=n)[:n].astype(float)
    return cnt / (grid["tr_coverage"].to_numpy() * tr)


def speech_rate_summary(words: pd.DataFrame | None, dur: float) -> dict[str, Any]:
    """Per-video transcript-derived summary fields (None without a transcript)."""
    n_words = int(len(words)) if words is not None else None
    return {
        "n_words": n_words,
        "speech_rate_wps": float(n_words / dur) if n_words is not None and dur > 0 else None,
        "words_per_min": float(n_words / dur * 60) if n_words is not None and dur > 0 else None,
    }


def apply_transcript(
    df: pd.DataFrame, summary: dict[str, Any], tsv: str | Path, cfg: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fill the transcript-derived confounds of an existing per-TR frame + summary (P2b after P3).

    Recomputes exactly what `extract_confounds(..., tsv=tsv)` would put in `speech_rate_wps` (per TR),
    `n_words`, `speech_rate_wps`, `words_per_min` and `speech_rate_wps_mean`, without re-running the
    audio/video extractors. The frame's TR grid and the summary's `duration_s` are reused."""
    cfg = cfg or load_config()
    tr = cfg["tribe"]["tr_s"]
    words = pd.read_csv(tsv, sep="\t", keep_default_na=False)
    grid = df[["tr", "tr_start_s", "tr_end_s", "tr_coverage"]]
    out = df.copy()
    out["speech_rate_wps"] = word_rate_per_tr(words, grid, tr)
    s = {**summary, **speech_rate_summary(words, float(summary["duration_s"]))}
    col = out["speech_rate_wps"].to_numpy(dtype=float)
    s["speech_rate_wps_mean"] = float(np.nanmean(col)) if np.isfinite(col).any() else None
    return out, s


# ---------------------------------------------------------------- video
def _crop_box(h: int, w: int, crop: int) -> tuple[int, int, int, int]:
    y0, x0 = max(0, (h - crop) // 2), max(0, (w - crop) // 2)
    return y0, min(h, y0 + crop), x0, min(w, x0 + crop)


def _face_detector(fc: dict[str, Any]):
    import cv2

    det = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / fc["detector"]))
    if det.empty():
        raise RuntimeError(f"could not load Haar cascade {fc['detector']}")
    return det


def video_features(mp4: str | Path, grid: pd.DataFrame, cfg: dict[str, Any]) -> dict:
    c, st, tr = cfg["confounds"], cfg["stimulus"], cfg["tribe"]["tr_s"]
    n = len(grid)
    fps, short = c["video_fps"], c["analysis_short_side_px"]
    face_every = max(1, int(round(fps / c["face_fps"])))
    fc = c["face"]
    det = _face_detector(fc)
    ts, lum, con, lumc, conc, mot, motc = [], [], [], [], [], [], []
    ft, fpres, fcount, farea, fout, fpc, fac = [], [], [], [], [], [], []
    min_inside = float(fc["crop_min_inside_frac"])
    prev = None
    for i, (t, g) in enumerate(iter_gray_frames(mp4, fps, short)):
        h, w = g.shape
        y0, y1, x0, x1 = _crop_box(h, w, st["center_crop_px"])
        f = g.astype(np.float64) / 255.0
        ts.append(t)
        lum.append(f.mean())
        con.append(f.std())
        fcrop = f[y0:y1, x0:x1]
        lumc.append(fcrop.mean())
        conc.append(fcrop.std())
        if prev is None:
            mot.append(np.nan)
            motc.append(np.nan)
        else:
            d = np.abs(f - prev)
            mot.append(d.mean())
            motc.append(d[y0:y1, x0:x1].mean())
        prev = f
        if i % face_every == 0:
            mins = int(round(fc["min_size_frac"] * min(h, w)))
            boxes = det.detectMultiScale(
                g, scaleFactor=fc["scale_factor"], minNeighbors=fc["min_neighbors"], minSize=(mins, mins)
            )
            boxes = np.asarray(boxes).reshape(-1, 4)
            area = inside = 0.0
            present_crop = False
            for bx, by, bw, bh in boxes:
                area += bw * bh
                iw = max(0, min(bx + bw, x1) - max(bx, x0))
                ih = max(0, min(by + bh, y1) - max(by, y0))
                inside += iw * ih
                present_crop |= bw * bh > 0 and iw * ih >= min_inside * bw * bh
            ft.append(t)
            fpc.append(float(present_crop))
            fac.append(min(1.0, inside / ((y1 - y0) * (x1 - x0))))
            fpres.append(float(len(boxes) > 0))
            fcount.append(float(len(boxes)))
            farea.append(min(1.0, area / (h * w)))
            fout.append(1 - inside / area if area > 0 else np.nan)
    ts, ft = np.asarray(ts), np.asarray(ft)
    return {
        "luminance": _per_tr(ts, np.asarray(lum), tr, n),
        "contrast": _per_tr(ts, np.asarray(con), tr, n),
        "luminance_crop": _per_tr(ts, np.asarray(lumc), tr, n),
        "contrast_crop": _per_tr(ts, np.asarray(conc), tr, n),
        "motion_energy": _per_tr(ts, np.asarray(mot), tr, n),
        "motion_energy_crop": _per_tr(ts, np.asarray(motc), tr, n),
        "face_present_frac": _per_tr(ft, np.asarray(fpres), tr, n),
        "face_count_mean": _per_tr(ft, np.asarray(fcount), tr, n),
        "face_area_frac": _per_tr(ft, np.asarray(farea), tr, n),
        "face_area_outside_crop_frac": _per_tr(ft, np.asarray(fout), tr, n),
        "face_present_crop": _per_tr(ft, np.asarray(fpc), tr, n),
        "face_area_crop_frac": _per_tr(ft, np.asarray(fac), tr, n),
    }


def scene_cut_times(mp4: str | Path, cfg: dict[str, Any]) -> list[float]:
    from scenedetect import ContentDetector, detect

    sc = cfg["confounds"]["scene"]
    scenes = detect(
        str(mp4), ContentDetector(threshold=sc["threshold"], min_scene_len=sc["min_scene_len_frames"])
    )
    return [s[0].get_seconds() for s in scenes[1:]]


# ---------------------------------------------------------------- entry
def extract_confounds(
    mp4: str | Path,
    wav: str | Path,
    tsv: str | Path | None = None,
    video_id: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Tidy per-TR frame (video_id, tr, tr_start_s, tr_end_s, tr_coverage, *FEATURES) + per-video summary."""
    cfg = cfg or load_config()
    if cfg["confounds"]["text_detection"]:
        raise NotImplementedError(
            "on-screen text detection is not implemented (needs a downloaded OCR model)"
        )
    tr = cfg["tribe"]["tr_s"]
    mp4 = Path(mp4)
    vid = video_id or mp4.stem
    dur = duration(mp4)
    grid = tr_grid(dur, tr)
    n = len(grid)
    words = pd.read_csv(tsv, sep="\t", keep_default_na=False) if tsv is not None else None
    a = audio_features(wav, grid, cfg, words)
    v = video_features(mp4, grid, cfg)
    cuts = scene_cut_times(mp4, cfg)
    cut_counts = np.bincount(_bin(np.asarray(cuts), tr, n), minlength=n)[:n] if cuts else np.zeros(n, int)
    df = grid.copy()
    df.insert(0, "video_id", vid)
    for k in FEATURES:
        if k == "scene_cuts":
            df[k] = cut_counts
        elif k == "text_frac":
            df[k] = np.nan  # not implemented, see module docstring
        else:
            df[k] = a[k] if k in a else v[k]
    f0 = a["_f0"][np.isfinite(a["_f0"])]
    sr = speech_rate_summary(words, dur)
    summary = {
        "video_id": vid,
        "duration_s": dur,
        "n_tr": n,
        "has_audio_track": stream(ffprobe(mp4), "audio") is not None,
        "n_words": sr["n_words"],
        "speech_rate_wps": sr["speech_rate_wps"],
        "speech_s": a["_speech_s"],
        "speech_frac": float(df["speech_frac"].mean()),
        "words_per_min": sr["words_per_min"],
        "pitch_mean_hz": float(f0.mean()) if f0.size else None,
        "pitch_sd_hz": float(f0.std()) if f0.size else None,
        "n_scene_cuts": len(cuts),
        "cuts_per_min": len(cuts) / dur * 60,
        "scene_cut_times_s": cuts,
        "text_detection": "not_implemented",
    }
    for k in FEATURES:
        if k not in ("scene_cuts", "speech_frac", "pitch_mean_hz", "pitch_sd_hz"):
            col = df[k].to_numpy(dtype=float)
            summary[f"{k}_mean"] = float(np.nanmean(col)) if np.isfinite(col).any() else None
    return df, summary
