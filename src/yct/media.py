"""Shared ffmpeg/ffprobe helpers and the energy VAD used by P2 (loudness gating) and P3 (confounds).

All decoding goes through ffmpeg pipes, so no audio/video I/O library is needed beyond numpy.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

_CHUNK = 1 << 20


class MediaError(RuntimeError):
    pass


def run(cmd: list[str], *, binary: bool = False) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=not binary)
    if res.returncode != 0:
        err = res.stderr if not binary else res.stderr.decode(errors="replace")
        raise MediaError(f"{cmd[0]} failed ({res.returncode}): {' '.join(cmd)}\n{err[-4000:]}")
    return res


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def ffprobe(path: str | Path) -> dict[str, Any]:
    res = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(res.stdout)


def stream(probe: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for s in probe.get("streams", []):
        if s.get("codec_type") == kind:
            return s
    return None


def ratio(text: str | None) -> float | None:
    """'30000/1001' -> 29.97; '0/0' or None -> None."""
    if not text:
        return None
    num, _, den = str(text).partition("/")
    try:
        n, d = float(num), float(den or 1)
    except ValueError:
        return None
    return n / d if d else None


def fnum(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def duration(path: str | Path) -> float:
    return float(ffprobe(path)["format"]["duration"])


def decode_audio(
    path: str | Path,
    sample_rate: int,
    channels: int | None = 1,
    start: float | None = None,
    dur: float | None = None,
) -> np.ndarray:
    """Decode audio to float32 of shape (n_samples, n_channels). channels=None keeps the source layout."""
    if channels is None:
        a = stream(ffprobe(path), "audio")
        if a is None:
            raise MediaError(f"no audio stream in {path}")
        channels = int(a["channels"])
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{start:.6f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.6f}"]
    cmd += ["-i", str(path), "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-f", "f32le", "-"]
    raw = run(cmd, binary=True).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, channels).astype(np.float64)


def iter_gray_frames(path: str | Path, fps: float, short_side: int):
    """Yield (t_seconds, HxW uint8 luma frame) sampled at `fps`, resized so the short edge is `short_side`."""
    v = stream(ffprobe(path), "video")
    if v is None:
        raise MediaError(f"no video stream in {path}")
    w, h = int(v["width"]), int(v["height"])
    s = short_side / min(w, h)
    ow, oh = int(round(w * s / 2) * 2), int(round(h * s / 2) * 2)
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-an",
        "-vf",
        f"fps={fps},scale={ow}:{oh}:flags=area",
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = ow * oh
    i = 0
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield (i / fps, np.frombuffer(buf, dtype=np.uint8).reshape(oh, ow))
            i += 1
    finally:
        proc.stdout.close()
        proc.wait()


def frame_levels_db(x: np.ndarray, sr: int, frame_s: float, hop_s: float, floor_db: float) -> np.ndarray:
    """Per-frame RMS level in dBFS for a mono signal; frame k starts at k*hop_s."""
    flen, hop = max(1, int(round(frame_s * sr))), max(1, int(round(hop_s * sr)))
    if len(x) < flen:
        return np.full(0, floor_db)
    n = 1 + (len(x) - flen) // hop
    idx = np.arange(flen)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt(np.mean(x[idx] ** 2, axis=1))
    return np.maximum(20 * np.log10(np.maximum(rms, 1e-300)), floor_db)


def energy_vad(x: np.ndarray, sr: int, vcfg: dict[str, Any]) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Energy VAD (approximates speech gating; it is not speech-specific: music/tones also pass).

    A frame is active if its level is above abs_floor_dbfs and within rel_db of the ref_percentile frame
    level. Active runs separated by < min_gap_s are merged; runs < min_seg_s are dropped.
    Returns (per-frame bool mask on the hop grid, list of (start_s, end_s) segments).
    """
    hop_s, frame_s = vcfg["hop_s"], vcfg["frame_s"]
    lv = frame_levels_db(x, sr, frame_s, hop_s, vcfg["abs_floor_dbfs"] - 1.0)
    if lv.size == 0:
        return np.zeros(0, bool), []
    ref = np.percentile(lv, vcfg["ref_percentile"])
    active = (lv > vcfg["abs_floor_dbfs"]) & (lv > ref - vcfg["rel_db"])
    segs: list[list[float]] = []
    for k in np.flatnonzero(active):
        c = k * hop_s + frame_s / 2  # each active frame claims the hop-wide span around its centre
        s, e = c - hop_s / 2, c + hop_s / 2
        if segs and s - segs[-1][1] < vcfg["min_gap_s"]:
            segs[-1][1] = max(segs[-1][1], e)
        else:
            segs.append([s, e])
    segs = [(round(s, 4), round(e, 4)) for s, e in segs if e - s >= vcfg["min_seg_s"]]
    mask = np.zeros_like(active)
    t = np.arange(lv.size) * hop_s + frame_s / 2
    for s, e in segs:
        mask |= (t >= s) & (t < e)
    return mask, segs
