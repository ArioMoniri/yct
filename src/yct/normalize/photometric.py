"""Photometric T3 sensitivity copy (owner request). The primary T1 stimulus is never modified.

Per video, ONE global transform (never per frame, so within-video luminance dynamics/flashes survive):
  1. gray-world white balance: channel gains g_c = mean(R,G,B means) / mean_c;
  2. affine luminance map: every channel x -> a * g_c * x + b, chosen so that the mean BT.709 Y equals
     `target_mean_y` and the RMS contrast (mean over frames of the spatial SD of Y) equals
     `target_rms_contrast`. Because Y is linear in R,G,B with weights summing to 1, an identical affine
     map on each channel maps Y -> a*Y + b exactly (before clipping);
  3. clip to [0, 1] (encoded to yuv420p, i.e. legal range); the clipped-sample fraction is reported;
  4. optional per-frame temporal luminance smoothing (ffmpeg deflicker), OFF by default.
Statistics are computed on gamma-encoded RGB in [0, 1] decoded by ffmpeg at `analysis_fps`; "luminance"
here means gamma-encoded luma Y' (not linear-light luminance).

Colour (FIX-C3-ENG, QA G-D032 c2 D6): BT.709 everywhere. YUV -> RGB decoding (statistics, and the input of
the T3 lut) uses an explicit BT.709 matrix + limited ("tv") range (`normalize.photometric.color_matrix` /
`color_range`), never ffmpeg's untagged default (BT.601), so the luma weights, the decoder and the encoder
agree. The T3 output is encoded RGB -> YUV with the BT.709 matrix and tagged bt709 (matrix, primaries,
transfer) / tv range, so any downstream decoder (TRIBE/V-JEPA2) reads it with the same matrix.

v2.4 G-D032 (N-D6, Referee D3, Biostat D5):
  * statistics are estimated on the V-JEPA2 view only (`stats_region: vjepa_crop`): the source region that
    maps to the central `center_crop_px`^2 crop after resizing the short edge to `min_short_side_px`
    (:func:`vjepa_crop_region`). The transform is still ONE global map applied to the whole frame;
    before/after statistics are reported both in the crop and over the full frame;
  * the contrast gain is capped to [`min_gain`, `max_gain`]; when the cap binds, b is re-solved so the
    mean-Y target is still met, `gain_capped` is recorded and the flag `gain_capped` raised;
  * the clipped-sample fraction is reported in the crop (`clip_frac`, used for the `clipping` flag) and
    over the full frame (`clip_frac_full`). Flagged clips are KEPT in T3 (`kept_in_t3` is always True) and
    reported;
    :func:`t3_report` gives the descriptive gain / clipping / colour-cast distributions (by group only
    after unblinding).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from yct.media import MediaError, ffprobe, run, stream


def video_size(path: str | Path) -> tuple[int, int]:
    """(height, width) of the first video stream."""
    v = stream(ffprobe(path), "video")
    if v is None:
        raise MediaError(f"no video stream in {path}")
    return int(v["height"]), int(v["width"])


def vjepa_crop_region(h: int, w: int, short_px: int = 292, crop_px: int = 256) -> tuple[int, int, int, int]:
    """(y0, y1, x0, x1) in source pixels of what V-JEPA2 sees: resize short edge -> short_px, centre crop."""
    side = crop_px * min(h, w) / short_px
    ch, cw = min(h, int(round(side))), min(w, int(round(side)))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return y0, y0 + ch, x0, x0 + cw


COLOR_MATRIX = "bt709"
COLOR_RANGE = "tv"
# ENH-005 (Neuro G-D032 A1): accurate rounding + full chroma interpolation on every swscale colour
# conversion (config `normalize.photometric.sws_flags`; this default mirrors config.yaml).
SWS_FLAGS: tuple[str, ...] = ("accurate_rnd", "full_chroma_int")


def _sws(sws) -> str:
    return "+".join(sws) if not isinstance(sws, str) else sws


def decode_filter(matrix: str = COLOR_MATRIX, rng: str = COLOR_RANGE, sws=SWS_FLAGS) -> str:
    """YUV -> rgb24 with an explicit matrix/range (never ffmpeg's untagged BT.601 default)."""
    fl = f"flags={_sws(sws)}:" if sws else ""
    return f"scale={fl}in_color_matrix={matrix}:in_range={rng},format=rgb24"


def encode_filter(pix_fmt: str, matrix: str = COLOR_MATRIX, rng: str = COLOR_RANGE, sws=SWS_FLAGS) -> str:
    """rgb24 -> YUV with an explicit matrix/range."""
    fl = f"flags={_sws(sws)}:" if sws else ""
    return f"scale={fl}out_color_matrix={matrix}:out_range={rng},format={pix_fmt}"


def color_tags(matrix: str = COLOR_MATRIX, rng: str = COLOR_RANGE) -> list[str]:
    """Container/bitstream colour tags for the output."""
    return ["-colorspace", matrix, "-color_primaries", matrix, "-color_trc", matrix, "-color_range", rng]


def iter_rgb_frames(path: str | Path, fps: float, region: tuple[int, int, int, int] | None = None,
                    matrix: str = COLOR_MATRIX, rng: str = COLOR_RANGE, sws=SWS_FLAGS):
    """(n_pixels, 3) RGB frames in [0, 1] decoded with an explicit BT.709 / tv matrix; ``region`` =
    (y0, y1, x0, x1) restricts to a source-pixel box."""
    h, w = video_size(path)
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-an",
        "-vf",
        f"fps={fps},{decode_filter(matrix, rng, sws)}",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            fr = np.frombuffer(buf, dtype=np.uint8)
            if region is not None:
                y0, y1, x0, x1 = region
                fr = fr.reshape(h, w, 3)[y0:y1, x0:x1]
            yield fr.reshape(-1, 3).astype(np.float64) / 255.0
    finally:
        proc.stdout.close()
        proc.wait()


def frame_stats(path: str | Path, pcfg: dict[str, Any],
                region: tuple[int, int, int, int] | None = None) -> dict[str, Any]:
    """Per-frame channel means and 3x3 channel covariances -> video-level photometric covariates."""
    wts = np.asarray(pcfg["luma_weights"], float)
    means, covs = [], []
    for px in iter_rgb_frames(path, pcfg["analysis_fps"], region, *_colour(pcfg)):
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
    a_raw = pcfg["target_rms_contrast"] / wb["rms_contrast"] if wb["rms_contrast"] > 0 else float("inf")
    lo, hi = float(pcfg["min_gain"]), float(pcfg["max_gain"])
    a = float(min(max(a_raw, lo), hi))
    b = pcfg["target_mean_y"] - a * wb["mean_y"]      # re-solved after the cap: the mean target still holds
    return {"gains": gains, "a": a, "b": float(b), "a_uncapped": float(a_raw), "gain_capped": a != a_raw}


def clip_fraction(path: str | Path, tf: dict[str, Any], pcfg: dict[str, Any],
                  region: tuple[int, int, int, int] | None = None) -> float:
    scale = tf["a"] * np.asarray(tf["gains"])
    n_clip = n_tot = 0
    for px in iter_rgb_frames(path, pcfg["analysis_fps"], region, *_colour(pcfg)):
        y = px * scale + tf["b"]
        n_clip += int(np.count_nonzero((y < 0) | (y > 1)))
        n_tot += y.size
    return n_clip / n_tot if n_tot else 0.0


def _colour(pcfg: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    m, r = pcfg.get("color_matrix", COLOR_MATRIX), pcfg.get("color_range", COLOR_RANGE)
    if (m, r) != (COLOR_MATRIX, COLOR_RANGE):
        raise ValueError("normalize.photometric colour must be bt709 / tv (FIX-C3-ENG: BT.709 everywhere)")
    return m, r, tuple(pcfg.get("sws_flags", SWS_FLAGS))


def photometric_normalize(mp4: str | Path, out_dir: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    from yct.normalize.core import _BITEXACT, _hash_move, _x264

    n = cfg["normalize"]
    pcfg = n["photometric"]
    st = cfg["stimulus"]
    mp4, out_dir = Path(mp4), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if pcfg["stats_region"] != "vjepa_crop":
        raise ValueError("normalize.photometric.stats_region must be 'vjepa_crop' (v2.4 G-D032 N-D6)")
    crop_in = vjepa_crop_region(*video_size(mp4), st["min_short_side_px"], st["center_crop_px"])
    before = frame_stats(mp4, pcfg, crop_in)
    before_full = frame_stats(mp4, pcfg)
    tf = solve_transform(before, pcfg)
    clip = clip_fraction(mp4, tf, pcfg, crop_in)
    clip_full = clip_fraction(mp4, tf, pcfg)
    flags = ["clipping"] if clip > pcfg["max_clip_frac"] else []
    if tf["gain_capped"]:
        flags.append("gain_capped")

    # lutrgb on 8-bit values: out = clip(val * a * g_c + 255 * b)
    lut = ":".join(
        f"{k}='clip(val*{tf['a'] * g:.8f}+{255.0 * tf['b']:.6f},0,255)'"
        for k, g in zip("rgb", tf["gains"], strict=True)
    )
    matrix, rng, sws = _colour(pcfg)
    vf = f"{decode_filter(matrix, rng, sws)},lutrgb={lut}"
    ts = pcfg["temporal_smoothing"]
    if ts["enabled"]:
        vf += f",deflicker=size={ts['size_frames']}:mode=am"
    vf += f",{encode_filter(n['video']['pix_fmt'], matrix, rng, sws)}"
    with tempfile.TemporaryDirectory(dir=out_dir) as td:
        tmp = Path(td) / "t3.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                n["ffmpeg_loglevel"],
                "-nostdin",
                "-i",
                str(mp4),
                "-vf",
                vf,
                *_x264(n["video"], pcfg["crf"]),
                *color_tags(matrix, rng),
                "-c:a",
                "copy",
                *_BITEXACT,
                "-movflags",
                "+faststart",
                str(tmp),
            ]
        )
        dest, digest = _hash_move(tmp, out_dir / pcfg["subdir"], n["hash_len"])
    crop_out = vjepa_crop_region(*video_size(dest), st["min_short_side_px"], st["center_crop_px"])
    after = frame_stats(dest, pcfg, crop_out)
    after_full = frame_stats(dest, pcfg)
    fy_in, fy_out = before["frame_mean_y"], after["frame_mean_y"]
    corr = float(np.corrcoef(fy_in, fy_out)[0, 1]) if len(fy_in) > 1 and np.std(fy_in) > 0 else None

    def cov(s: dict) -> dict:
        return {k: s[k] for k in ("mean_y", "rms_contrast", "channel_means", "colour_cast")}

    return {
        "t3_path": str(dest),
        "t3_sha256": digest,
        "gains": [float(g) for g in tf["gains"]],
        "max_channel_gain": float(np.max(tf["gains"])),
        "gain_a": tf["a"],
        "gain_a_uncapped": tf["a_uncapped"],
        "gain_capped": bool(tf["gain_capped"]),
        "offset_b": tf["b"],
        "stats_region": "vjepa_crop",
        "crop_region_yx": [int(v) for v in crop_in],
        "clip_frac": clip,
        "clip_frac_full": clip_full,
        "before": cov(before),
        "after": cov(after),
        "before_full": cov(before_full),
        "after_full": cov(after_full),
        "frame_luminance_corr": corr,
        "temporal_smoothing": bool(ts["enabled"]),
        "color_matrix": matrix,
        "color_range": rng,
        "flags": flags,
        "kept_in_t3": True,                      # flagged clips are never excluded (v2.4 G-D032)
    }


REPORT_KEYS = ("gain_a", "gain_a_uncapped", "max_channel_gain", "clip_frac", "clip_frac_full")


def t3_report(records: list[dict[str, Any]], groups: list[Any] | None = None, *, unblinded: bool = False,
              channel_gain_threshold: float = 1.3) -> dict[str, Any]:
    """Descriptive T3 report: distributions of gain, clipping and colour cast; flagged counts.

    Pooled distributions are label-free. ``groups`` (one label per record) may be given only after
    unblinding (``unblinded=True``); before that a by-group report would leak outcome information.
    """
    import pandas as pd

    if groups is not None and not unblinded:
        raise PermissionError("T3 gain/clipping by group is reported only after unblinding")
    df = pd.DataFrame([{**{k: r[k] for k in REPORT_KEYS}, "gain_capped": bool(r["gain_capped"]),
                        "clipping": "clipping" in r["flags"],
                        "colour_cast_before": r["before"]["colour_cast"],
                        "kept_in_t3": bool(r.get("kept_in_t3", True))} for r in records])
    if not df["kept_in_t3"].all():
        raise ValueError("flagged T3 clips must be kept, not excluded")

    def summ(d: pd.DataFrame) -> dict[str, Any]:
        q = d[[*REPORT_KEYS, "colour_cast_before"]].quantile([0.0, 0.25, 0.5, 0.75, 1.0])
        return {"n": int(len(d)), "quantiles": q.to_dict(), "n_gain_capped": int(d["gain_capped"].sum()),
                "n_clipping": int(d["clipping"].sum()),
                "share_channel_gain_gt": float((d["max_channel_gain"] > channel_gain_threshold).mean())}

    out: dict[str, Any] = {"pooled": summ(df), "channel_gain_threshold": channel_gain_threshold}
    if groups is not None:
        if len(groups) != len(df):
            raise ValueError("one group label per record")
        df["group"] = list(groups)
        out["by_group"] = {str(g): summ(d) for g, d in df.groupby("group")}
    return out
