"""Photometric T3 sensitivity copy (owner request). The primary T1 stimulus is never modified.

Per video, ONE global transform (never per frame, so within-video luminance dynamics/flashes survive):
  1. gray-world white balance: channel gains g_c = mean(R,G,B means) / mean_c;
  2. affine luminance map: every channel x -> a * g_c * x + b, chosen so that the mean BT.709 Y equals
     `target_mean_y` and the RMS contrast (mean over frames of the spatial SD of Y) equals
     `target_rms_contrast`. Because Y is linear in R,G,B with weights summing to 1, an identical affine
     map on each channel maps Y -> a*Y + b exactly (before clipping);
  3. clip to [0, 1] (encoded to yuv420p, i.e. legal range); the clipped-sample fraction is reported;
  4. optional per-frame temporal luminance smoothing (ffmpeg deflicker), OFF by default.
Statistics are computed on gamma-encoded RGB in [0, 1] decoded by ffmpeg at `analysis_fps`.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from yct.media import MediaError, ffprobe, run, stream


def iter_rgb_frames(path: str | Path, fps: float):
    v = stream(ffprobe(path), "video")
    if v is None:
        raise MediaError(f"no video stream in {path}")
    w, h = int(v["width"]), int(v["height"])
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", "-vf", f"fps={fps}",
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(h * w, 3).astype(np.float64) / 255.0
    finally:
        proc.stdout.close()
        proc.wait()


def frame_stats(path: str | Path, pcfg: dict[str, Any]) -> dict[str, Any]:
    """Per-frame channel means and 3x3 channel covariances -> video-level photometric covariates."""
    wts = np.asarray(pcfg["luma_weights"], float)
    means, covs = [], []
    for px in iter_rgb_frames(path, pcfg["analysis_fps"]):
        means.append(px.mean(axis=0))
        covs.append(np.cov(px, rowvar=False, bias=True))
    if not means:
        raise MediaError(f"no frames decoded from {path}")
    m, c = np.asarray(means), np.asarray(covs)
    return {"frame_channel_means": m, "frame_channel_covs": c, **summarize(m, c, wts)}


def summarize(m: np.ndarray, c: np.ndarray, wts: np.ndarray, gains: np.ndarray | None = None) -> dict:
    g = np.ones(3) if gains is None else gains
    v = wts * g
    ch = m.mean(axis=0) * g
    frame_y = m @ v
    sd = np.sqrt(np.maximum(np.einsum("i,fij,j->f", v, c, v), 0))
    return {
        "mean_y": float(frame_y.mean()),
        "rms_contrast": float(sd.mean()),
        "channel_means": [float(x) for x in ch],
        "colour_cast": float((ch.max() - ch.min()) / ch.mean()) if ch.mean() > 0 else 0.0,
        "frame_mean_y": frame_y,
    }


def solve_transform(stats: dict[str, Any], pcfg: dict[str, Any]) -> dict[str, Any]:
    wts = np.asarray(pcfg["luma_weights"], float)
    m, c = stats["frame_channel_means"], stats["frame_channel_covs"]
    ch = m.mean(axis=0)
    gains = (ch.mean() / np.maximum(ch, 1e-6)) if pcfg["gray_world"] else np.ones(3)
    wb = summarize(m, c, wts, gains)
    a = pcfg["target_rms_contrast"] / wb["rms_contrast"] if wb["rms_contrast"] > 0 else 1.0
    b = pcfg["target_mean_y"] - a * wb["mean_y"]
    return {"gains": gains, "a": float(a), "b": float(b)}


def clip_fraction(path: str | Path, tf: dict[str, Any], pcfg: dict[str, Any]) -> float:
    scale = tf["a"] * np.asarray(tf["gains"])
    n_clip = n_tot = 0
    for px in iter_rgb_frames(path, pcfg["analysis_fps"]):
        y = px * scale + tf["b"]
        n_clip += int(np.count_nonzero((y < 0) | (y > 1)))
        n_tot += y.size
    return n_clip / n_tot if n_tot else 0.0


def photometric_normalize(mp4: str | Path, out_dir: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    from yct.normalize.core import _BITEXACT, _hash_move, _x264

    n = cfg["normalize"]
    pcfg = n["photometric"]
    mp4, out_dir = Path(mp4), Path(out_dir)
    before = frame_stats(mp4, pcfg)
    tf = solve_transform(before, pcfg)
    clip = clip_fraction(mp4, tf, pcfg)
    flags = ["clipping"] if clip > pcfg["max_clip_frac"] else []

    # lutrgb on 8-bit values: out = clip(val * a * g_c + 255 * b)
    lut = ":".join(
        f"{k}='clip(val*{tf['a'] * g:.8f}+{255.0 * tf['b']:.6f},0,255)'"
        for k, g in zip("rgb", tf["gains"], strict=True)
    )
    vf = f"format=rgb24,lutrgb={lut}"
    ts = pcfg["temporal_smoothing"]
    if ts["enabled"]:
        vf += f",deflicker=size={ts['size_frames']}:mode=am"
    vf += f",format={n['video']['pix_fmt']}"
    with tempfile.TemporaryDirectory(dir=out_dir) as td:
        tmp = Path(td) / "t3.mp4"
        run(["ffmpeg", "-y", "-v", n["ffmpeg_loglevel"], "-nostdin", "-i", str(mp4), "-vf", vf,
             *_x264(n["video"], pcfg["crf"]), "-c:a", "copy", *_BITEXACT, "-movflags", "+faststart", str(tmp)])
        dest, digest = _hash_move(tmp, out_dir / pcfg["subdir"], n["hash_len"])
    after = frame_stats(dest, pcfg)
    fy_in, fy_out = before["frame_mean_y"], after["frame_mean_y"]
    corr = float(np.corrcoef(fy_in, fy_out)[0, 1]) if len(fy_in) > 1 and np.std(fy_in) > 0 else None

    def cov(s: dict) -> dict:
        return {k: s[k] for k in ("mean_y", "rms_contrast", "channel_means", "colour_cast")}

    return {
        "t3_path": str(dest), "t3_sha256": digest,
        "gains": [float(g) for g in tf["gains"]], "gain_a": tf["a"], "offset_b": tf["b"],
        "clip_frac": clip, "before": cov(before), "after": cov(after),
        "frame_luminance_corr": corr, "temporal_smoothing": bool(ts["enabled"]), "flags": flags,
    }
