"""P2 normalisation (v2.md §5 P2; tribe_requirements §2.3-2.4).

One source video -> one T1 stimulus `<sha256[:16]>.mp4` (+ sidecar 16 kHz mono WAV, 480p round-trip copy,
optional photometric T3 copy) and a JSON record of every measurement and flag. All tunables: config.yaml
`normalize:`, `stimulus:`, `vad:`.

Speech gating (documented approximation): integrated loudness (ffmpeg loudnorm, BS.1770) is measured on
the concatenation of energy-VAD-active segments (yct.media.energy_vad), not on a speech-specific VAD.
The gain that brings that speech-gated loudness to the target is applied by a two-pass loudnorm in linear
mode (pure gain) whose integrated target is shifted by (I_full - I_speech); if the true-peak ceiling would
be exceeded loudnorm falls back to its dynamic mode, which is recorded (`loudnorm_mode`).

Colour (G-D032 c3 Neuro G1/N4, P1 c2 Neuro Q3; DECISIONS D-053): every P2 output (T1 mp4, q480 copy) is
converted from the SOURCE matrix to BT.709 / limited range (swscale `in_color_matrix`/`out_color_matrix`,
`in_range`/`out_range`) and tagged bt709 matrix/primaries/transfer + tv range (config `normalize.color`).
The source matrix is the stream's `color_space` tag; an untagged (or unsupported) stream gets the
resolution rule `normalize.color.untagged` (HD -> bt709, SD -> smpte170m) and the flag
`source_color_untagged`. :func:`source_color` is logged per video as `rec["color"]` (src_color_space ...).
"""

from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yct.config import load_config
from yct.media import (
    MediaError,
    decode_audio,
    energy_vad,
    ffprobe,
    fnum,
    ratio,
    run,
    sha256_file,
    stream,
)

_BLACK_RE = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)")
_SIL_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")
_BITEXACT = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]


# ---------------------------------------------------------------- probing
def _rotation(v: dict[str, Any]) -> int:
    rot = v.get("tags", {}).get("rotate")
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = sd["rotation"]
    try:
        return int(round(float(rot))) % 360 if rot is not None else 0
    except ValueError:
        return 0


def probe_source(path: str | Path) -> dict[str, Any]:
    p = ffprobe(path)
    v, a = stream(p, "video"), stream(p, "audio")
    if v is None:
        raise MediaError(f"no video stream in {path}")
    w, h = int(v["width"]), int(v["height"])
    sar = ratio(v.get("sample_aspect_ratio")) or 1.0
    if sar > 0 and abs(sar - 1.0) > 1e-6:
        w = int(round(w * sar))
    rot = _rotation(v)
    if rot in (90, 270):
        w, h = h, w
    r_fps, avg_fps = ratio(v.get("r_frame_rate")), ratio(v.get("avg_frame_rate"))
    v_start, a_start = fnum(v.get("start_time")) or 0.0, (fnum(a.get("start_time")) or 0.0) if a else None
    return {
        "width": w,
        "height": h,
        "rotation": rot,
        "fps_r": r_fps,
        "fps_avg": avg_fps,
        "vfr": bool(r_fps and avg_fps and abs(r_fps - avg_fps) > 0.01 * r_fps),
        "duration_s": fnum(p["format"].get("duration")),
        "bitrate_bps": fnum(p["format"].get("bit_rate")),
        "video_bitrate_bps": fnum(v.get("bit_rate")),
        "video_codec": v.get("codec_name"),
        "has_audio": a is not None,
        "audio_channels": int(a["channels"]) if a else 0,
        "audio_sample_rate": int(a["sample_rate"]) if a else None,
        "video_start_s": v_start,
        "audio_start_s": a_start,
        "color_stream": {k: v.get(k) for k in ("width", "height", "color_space", "color_range",
                                               "color_primaries", "color_transfer")},
    }


# ---------------------------------------------------------------- colour (D-053)
# ffprobe `color_space` tag -> swscale matrix name (scale filter in_color_matrix)
_SWS_MATRIX = {"bt709": "bt709", "smpte170m": "smpte170m", "bt470bg": "bt470", "fcc": "fcc",
               "smpte240m": "smpte240m", "bt2020nc": "bt2020", "bt2020c": "bt2020"}
_SWS_RANGE = {"tv": "tv", "mpeg": "tv", "pc": "pc", "jpeg": "pc"}
_NO_TAG = {"", "unknown", "reserved", "unspecified"}


def source_color(v: dict[str, Any], ccfg: dict[str, Any]) -> dict[str, Any]:
    """Source colour tags of a video stream (ffprobe dict) and the input matrix/range P2 converts FROM.

    Tagged matrix -> that matrix (rule ``tagged``). Untagged or unsupported tag -> config rule
    ``normalize.color.untagged`` on the coded size: long side >= ``hd_min_long_px`` or short side >
    ``sd_max_short_px`` -> ``hd`` (bt709), else ``sd`` (smpte170m); rule ``untagged_hd|sd``, prefixed
    ``unsupported_tag_`` when a tag was present but unknown. Untagged range -> ``untagged.range`` (tv).
    """
    tag = str(v.get("color_space") or "unknown")
    rng_tag = str(v.get("color_range") or "unknown")
    u = ccfg["untagged"]
    if tag in _SWS_MATRIX:
        in_m, rule = _SWS_MATRIX[tag], "tagged"
    else:
        w, h = int(v["width"]), int(v["height"])
        hd = max(w, h) >= int(u["hd_min_long_px"]) or min(w, h) > int(u["sd_max_short_px"])
        in_m = _SWS_MATRIX[u["hd"] if hd else u["sd"]]
        rule = ("untagged_hd" if hd else "untagged_sd")
        if tag not in _NO_TAG:
            rule = f"unsupported_tag_{rule}"
    in_r = _SWS_RANGE.get(rng_tag, u["range"])
    return {
        "src_color_space": tag,
        "src_color_range": rng_tag,
        "src_color_primaries": str(v.get("color_primaries") or "unknown"),
        "src_color_transfer": str(v.get("color_transfer") or "unknown"),
        "in_matrix": in_m,
        "in_range": in_r,
        "rule": rule,
        "out_matrix": ccfg["matrix"],
        "out_range": ccfg["range"],
    }


def sws_flags(kernel: str | None, ccfg: dict[str, Any]) -> str:
    """swscale ``flags`` value: the scaling kernel plus ``normalize.color.sws_flags`` (ENH-005, Neuro
    G-D032 A1: accurate_rnd + full_chroma_int remove the ~-1.5 code-value BT.601 -> BT.709 bias)."""
    return "+".join([*([kernel] if kernel else []), *ccfg.get("sws_flags", [])])


def color_scale_opts(in_matrix: str, in_range: str, ccfg: dict[str, Any],
                     kernel: str | None = "bicubic") -> str:
    """swscale options converting in_matrix/in_range -> the configured output matrix/range (incl. flags)."""
    fl = sws_flags(kernel, ccfg)
    return ((f"flags={fl}:" if fl else "") + f"in_color_matrix={in_matrix}:in_range={in_range}"
            f":out_color_matrix={ccfg['matrix']}:out_range={ccfg['range']}")


def color_tags(ccfg: dict[str, Any]) -> list[str]:
    """Output bitstream/container colour tags (bt709 matrix/primaries/transfer, tv range)."""
    return ["-colorspace", ccfg["matrix"], "-color_primaries", ccfg["primaries"],
            "-color_trc", ccfg["transfer"], "-color_range", ccfg["range"]]


# ---------------------------------------------------------------- HDR (ENH-006)
_ZS_RANGE = {"tv": "limited", "mpeg": "limited", "pc": "full", "jpeg": "full"}


def hdr_info(v: dict[str, Any], hcfg: dict[str, Any]) -> dict[str, Any]:
    """HDR iff the stream's ffprobe ``color_transfer`` is one of ``normalize.color.hdr.transfers``."""
    trc = str(v.get("color_transfer") or "unknown")
    return {"hdr_source": trc in set(hcfg["transfers"]), "hdr_transfer": trc}


def ffmpeg_filters() -> frozenset[str]:
    """Names of the filters the local ffmpeg provides (``ffmpeg -filters``)."""
    out = run(["ffmpeg", "-hide_banner", "-nostdin", "-filters"]).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and "->" in parts[2]:
            names.add(parts[1])
    return frozenset(names)


def tonemap_filter(v: dict[str, Any], hcfg: dict[str, Any]) -> str:
    """zscale + tonemap chain: HDR (PQ/HLG, BT.2020) -> SDR BT.709 transfer/matrix/primaries, tv range,
    yuv420p. The source transfer/matrix/primaries/range are passed explicitly from the ffprobe tags."""
    trc = str(v.get("color_transfer"))
    m = str(v.get("color_space") or "")
    m = m if m and m not in _NO_TAG else hcfg["untagged_matrix"]
    p = str(v.get("color_primaries") or "")
    p = p if p and p not in _NO_TAG else hcfg["untagged_primaries"]
    r = _ZS_RANGE.get(str(v.get("color_range") or ""), "limited")
    return (f"zscale=tin={trc}:min={m}:pin={p}:rin={r}:t=linear:npl={hcfg['npl']},format=gbrpf32le,"
            f"zscale=p=bt709,tonemap=tonemap={hcfg['tonemap']}:desat={hcfg['desat']},"
            f"zscale=t=bt709:m=bt709:p=bt709:r=tv,format=yuv420p")


def hdr_prefilter(v: dict[str, Any], hcfg: dict[str, Any], src: str | Path) -> str:
    """Filter prefix for an HDR source (fails loudly if it cannot be tone-mapped)."""
    trc = v.get("color_transfer")
    if hcfg["action"] == "fail":
        raise MediaError(f"HDR source ({trc}) refused by normalize.color.hdr.action=fail: {src}")
    missing = sorted({"zscale", "tonemap"} - ffmpeg_filters())
    if missing:
        raise MediaError(
            f"HDR source ({trc}) needs ffmpeg filters zscale + tonemap to tone-map to SDR BT.709, but the "
            f"local ffmpeg lacks {missing} (build with libzimg); refusing to relabel HDR as SDR: {src}")
    return tonemap_filter(v, hcfg) + ","


def normalisation_covariates(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Binary covariates from normalisation records (index = video_id): ``hdr_source`` (ENH-006)."""
    return pd.DataFrame({"hdr_source": [float(bool(r.get("hdr_source"))) for r in records]},
                        index=pd.Index([r["video_id"] for r in records], name="video_id"))


# ---------------------------------------------------------------- detection
def _null_run(path: str | Path, flt: str, kind: str) -> str:
    sel = ["-an", "-vf", flt] if kind == "v" else ["-vn", "-af", flt]
    res = run(["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-i", str(path), *sel, "-f", "null", "-"])
    return res.stderr


def detect_black(path: str | Path, ncfg: dict[str, Any]) -> list[tuple[float, float]]:
    b = ncfg["blackdetect"]
    err = _null_run(
        path, f"blackdetect=d={b['min_duration_s']}:pix_th={b['pix_th']}:pic_th={b['pic_th']}", "v"
    )
    return [(float(s), float(e)) for s, e in _BLACK_RE.findall(err)]


def detect_silence(path: str | Path, ncfg: dict[str, Any], total: float) -> list[tuple[float, float]]:
    s = ncfg["silencedetect"]
    err = _null_run(path, f"silencedetect=noise={s['noise_db']}dB:d={s['min_duration_s']}", "a")
    starts = [float(x) for x in _SIL_START_RE.findall(err)]
    ends = [float(x) for x in _SIL_END_RE.findall(err)]
    ends += [total] * (len(starts) - len(ends))  # silence running to EOF may be unterminated
    return [(max(0.0, a), b) for a, b in zip(starts, ends, strict=False)]


def _edges(intervals: list[tuple[float, float]], total: float, tol: float) -> tuple[float, float]:
    """Length of the leading interval (end time) and the trailing interval start (default 0 / total)."""
    lead = max((e for s, e in intervals if s <= tol), default=0.0)
    trail = min((s for s, e in intervals if e >= total - tol), default=total)
    return lead, trail


def compute_trim(
    black: list[tuple[float, float]],
    silence: list[tuple[float, float]] | None,
    total: float,
    ncfg: dict[str, Any],
) -> dict[str, Any]:
    tol = ncfg["edge_tolerance_s"]
    bl, bt = _edges(black, total, tol)
    if silence is None:  # no audio: silence everywhere
        sl, st = total, 0.0
    else:
        sl, st = _edges(silence, total, tol)
    if ncfg["trim_mode"] == "both":
        start, end = min(bl, sl), max(bt, st)
    elif ncfg["trim_mode"] == "either":
        start, end = max(bl, sl), min(bt, st)
    else:
        raise ValueError(f"unknown trim_mode {ncfg['trim_mode']!r}")
    if end <= start:  # whole file dead: keep it all and let QC flag it
        start, end = 0.0, total
    return {
        "lead_black_s": bl,
        "trail_black_start_s": bt,
        "lead_silence_s": sl,
        "trail_silence_start_s": st,
        "trim_start_s": round(start, 4),
        "trim_end_s": round(end, 4),
        "trimmed_lead_s": round(start, 4),
        "trimmed_tail_s": round(total - end, 4),
        "black_intervals": black,
        "silence_intervals": silence,
    }


# ---------------------------------------------------------------- geometry
def target_dims(w: int, h: int, min_short: int) -> tuple[int, int, bool]:
    """Native aspect, short side >= min_short (upscale only as far as needed), even dims, no padding."""
    short = min(w, h)
    upscaled = short < min_short
    s = min_short / short if upscaled else 1.0
    # upscaling: round UP to even (stays >= min_short); native: round DOWN to even (only drops <= 1 px)
    step = math.ceil if upscaled else math.floor
    tw, th = (2 * int(step(round(d * s, 6) / 2)) for d in (w, h))
    return tw, th, upscaled


def crop_coverage(w: int, h: int, short_edge: int, crop: int) -> dict[str, float]:
    """V-JEPA2 view: resize short edge -> short_edge, center-crop crop x crop. Fractions NOT seen."""
    s = short_edge / min(w, h)
    rw, rh = w * s, h * s
    fw, fh = max(0.0, 1 - crop / rw), max(0.0, 1 - crop / rh)
    return {
        "crop_frac_width_outside": fw,
        "crop_frac_height_outside": fh,
        "crop_frac_area_outside": 1 - (min(crop, rw) * min(crop, rh)) / (rw * rh),
    }


def aspect_info(w: int, h: int, ncfg: dict[str, Any]) -> dict[str, Any]:
    r = w / h
    label = "portrait" if r < 1 else ("square" if r == 1 else "landscape")
    return {
        "aspect_ratio": r,
        "aspect_label": label,
        "stratum_9x16": r <= ncfg["aspect"]["portrait_max_ratio"],
    }


# ---------------------------------------------------------------- audio checks
def mono_phase(path: str | Path, start: float, dur: float, cfg: dict[str, Any]) -> dict[str, Any]:
    mp = cfg["normalize"]["mono_phase"]
    x = decode_audio(path, cfg["vad"]["sample_rate"], channels=None, start=start, dur=dur)
    if x.shape[1] < 2:
        return {"mono_phase_drop_db": 0.0, "mono_phase_flag": False, "channels_checked": int(x.shape[1])}
    ch_rms = math.sqrt(float(np.mean(x**2)))
    mono_rms = math.sqrt(float(np.mean(x.mean(axis=1) ** 2)))
    if ch_rms == 0:
        drop = 0.0
    elif mono_rms == 0:
        drop = mp["drop_cap_db"]
    else:
        drop = min(20 * math.log10(ch_rms / mono_rms), mp["drop_cap_db"])
    return {
        "mono_phase_drop_db": drop,
        "mono_phase_flag": drop > mp["max_drop_db"],
        "channels_checked": int(x.shape[1]),
    }


def _loudnorm_json(stderr: str) -> dict[str, Any]:
    tail = stderr[stderr.rfind("[Parsed_loudnorm") :]
    m = re.search(r"\{[^{}]*\}", tail, re.S)
    if not m:
        raise MediaError("loudnorm produced no JSON")
    return {k: (fnum(v) if fnum(v) is not None else v) for k, v in json.loads(m.group(0)).items()}


def _select_expr(segs: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t\\,{s:.3f}\\,{e:.3f})" for s, e in segs)


def measure_loudness(
    path: str | Path,
    lcfg: dict[str, Any],
    segs: list[tuple[float, float]] | None = None,
    start: float | None = None,
    dur: float | None = None,
) -> dict[str, Any]:
    """Pass-1 loudnorm measurement, optionally restricted to `segs` (times relative to `start`)."""
    pre = f"aselect={_select_expr(segs)},asetpts=N/SR/TB," if segs else ""
    flt = (
        f"{pre}loudnorm=I={lcfg['target_lufs']}:TP={lcfg['true_peak_dbtp']}:LRA={lcfg['target_lra']}"
        ":print_format=json"
    )
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{start:.6f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.6f}"]
    cmd += ["-i", str(path), "-vn", "-af", flt, "-f", "null", "-"]
    return _loudnorm_json(run(cmd).stderr)


# ---------------------------------------------------------------- encoding helpers
def _x264(vcfg: dict[str, Any], crf: int | None = None) -> list[str]:
    return [
        "-c:v",
        vcfg["codec"],
        "-crf",
        str(crf if crf is not None else vcfg["crf"]),
        "-preset",
        vcfg["preset"],
        "-pix_fmt",
        vcfg["pix_fmt"],
        "-threads",
        str(vcfg["threads"]),
    ]


def _aac(acfg: dict[str, Any]) -> list[str]:
    return ["-c:a", acfg["codec"], "-ar", str(acfg["sample_rate"]), "-b:a", str(acfg["bitrate"])]


def _hash_move(tmp: Path, dest_dir: Path, hash_len: int, suffix: str = ".mp4") -> tuple[Path, str]:
    digest = sha256_file(tmp)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest[:hash_len]}{suffix}"
    shutil.move(str(tmp), dest)
    return dest, digest


def quality_floor_copy(mp4: Path, out_dir: Path, w: int, h: int, cfg: dict[str, Any], tmpd: Path) -> dict:
    """480p round trip: downscale (never up) to short side 480 at a lower CRF, then back to (w, h)."""
    n = cfg["normalize"]
    q = n["quality_floor"]
    s = min(1.0, q["short_side_px"] / min(w, h))
    lw, lh = int(round(w * s / 2) * 2), int(round(h * s / 2) * 2)
    low = tmpd / "q_low.mp4"
    lvl = n["ffmpeg_loglevel"]
    cc = n["color"]
    keep = color_scale_opts(cc["matrix"], cc["range"], cc)    # T1 is already bt709/tv: keep it explicit
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            lvl,
            "-nostdin",
            "-i",
            str(mp4),
            "-vf",
            f"scale={lw}:{lh}:{keep},setsar=1",
            *_x264(n["video"], q["crf"]),
            *color_tags(cc),
            "-c:a",
            "copy",
            *_BITEXACT,
            str(low),
        ]
    )
    back = tmpd / "q_back.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            lvl,
            "-nostdin",
            "-i",
            str(low),
            "-vf",
            f"scale={w}:{h}:{keep},setsar=1",
            *_x264(n["video"]),
            *color_tags(cc),
            "-c:a",
            "copy",
            *_BITEXACT,
            "-movflags",
            "+faststart",
            str(back),
        ]
    )
    dest, digest = _hash_move(back, out_dir / q["subdir"], n["hash_len"])
    return {"q480_path": str(dest), "q480_sha256": digest, "q480_low_dims": [lw, lh]}


# ---------------------------------------------------------------- main entry
def normalize_video(
    src: str | Path, out_dir: str | Path, cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    n, st, vad_cfg = cfg["normalize"], cfg["stimulus"], cfg["vad"]
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    flags: list[str] = []
    info = probe_source(src)
    total = info["duration_s"]
    rec: dict[str, Any] = {"source_path": str(src), "source_sha256": sha256_file(src), "source": info}
    col = source_color(info["color_stream"], n["color"])
    hdr = hdr_info(info["color_stream"], n["color"]["hdr"])
    pre = hdr_prefilter(info["color_stream"], n["color"]["hdr"], src) if hdr["hdr_source"] else ""
    if hdr["hdr_source"]:            # after tone-mapping the frames are BT.709 / tv
        col.update(in_matrix="bt709", in_range="tv")
        flags.append("hdr_source")
    col.update(hdr, hdr_tonemapped=bool(pre))
    rec["color"] = col
    rec["hdr_source"] = hdr["hdr_source"]
    if col["rule"] != "tagged":
        flags.append("source_color_untagged")

    if (info["fps_avg"] or info["fps_r"] or 0) < st["min_source_fps"]:
        flags.append("source_fps_below_min")
    if info["vfr"]:
        flags.append("source_vfr")

    # A/V sync (stream start offset)
    if info["has_audio"]:
        off_ms = (info["audio_start_s"] - info["video_start_s"]) * 1000.0
        rec["av_offset_ms"] = off_ms
        if abs(off_ms) > n["av_sync"]["max_offset_ms"]:
            flags.append("av_sync_offset")
    else:
        rec["av_offset_ms"] = None
        flags.append("no_audio")

    # trims
    black = detect_black(src, n)
    silence = detect_silence(src, n, total) if info["has_audio"] else None
    trims = compute_trim(black, silence, total, n)
    rec["trims"] = trims
    t0 = trims["trim_start_s"]
    kept = trims["trim_end_s"] - t0
    t1 = min(kept, st["t1_trim_s"])
    rec["trimmed_duration_s"] = kept
    rec["t1_duration_target_s"] = t1

    # geometry
    tw, th, upscaled = target_dims(info["width"], info["height"], st["min_short_side_px"])
    rec.update({"out_width": tw, "out_height": th, "upscaled": upscaled})
    if upscaled:
        flags.append("upscaled_to_min_short_side")
    rec.update(crop_coverage(tw, th, st["min_short_side_px"], st["center_crop_px"]))
    rec.update(aspect_info(tw, th, n))

    lc = n["loudness"]
    with tempfile.TemporaryDirectory(dir=out_dir) as td:
        tmpd = Path(td)
        tmp_mp4 = tmpd / "t1.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-nostats",
            "-nostdin",
            "-v",
            "info",
            "-ss",
            f"{t0:.6f}",
            "-t",
            f"{t1:.6f}",
            "-i",
            str(src),
        ]
        vf = (f"fps={st['fps']},{pre}scale={tw}:{th}:"
              f"{color_scale_opts(col['in_matrix'], col['in_range'], n['color'], 'lanczos')},"
              f"setsar=1,format={n['video']['pix_fmt']}")
        if info["has_audio"]:
            rec.update(mono_phase(src, t0, t1, cfg))
            if rec["mono_phase_flag"]:
                flags.append("mono_phase")
            x = decode_audio(src, vad_cfg["sample_rate"], 1, start=t0, dur=t1)[:, 0]
            _, segs = energy_vad(x, vad_cfg["sample_rate"], vad_cfg)
            speech_s = sum(e - s for s, e in segs)
            full = measure_loudness(src, lc, start=t0, dur=t1)
            gated = speech_s >= lc["min_speech_s"]
            if not gated:
                flags.append("no_speech_detected_ungated_loudness")
            sp = measure_loudness(src, lc, segs, start=t0, dur=t1) if gated else full
            i_full, i_sp = full["input_i"], sp["input_i"]
            rec.update(
                {
                    "speech_s": speech_s,
                    "loudness_in_full_lufs": i_full,
                    "loudness_in_speech_lufs": i_sp,
                    "true_peak_in_dbtp": full["input_tp"],
                }
            )
            silent = not (math.isfinite(i_full) and math.isfinite(i_sp)) or i_full <= -70 or i_sp <= -70
            if silent:
                flags.append("silent_audio_no_loudnorm")
                af = f"aresample={n['audio']['sample_rate']}:async=1:first_pts=0"
            else:
                tgt = lc["target_lufs"] + (i_full - i_sp)
                af = (
                    f"aresample=async=1:first_pts=0,loudnorm=I={tgt:.2f}:TP={lc['true_peak_dbtp']}"
                    f":LRA={lc['target_lra']}:measured_I={i_full}:measured_TP={full['input_tp']}"
                    f":measured_LRA={full['input_lra']}:measured_thresh={full['input_thresh']}"
                    f":offset={full['target_offset']}:linear=true:print_format=json,"
                    f"aresample={n['audio']['sample_rate']}"
                )
            cmd += ["-map", "0:v:0", "-map", "0:a:0", "-vf", vf, "-af", af]
        else:
            segs = []
            cmd += [
                "-f",
                "lavfi",
                "-t",
                f"{t1:.6f}",
                "-i",
                f"anullsrc=r={n['audio']['sample_rate']}:cl=mono",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                vf,
            ]
        cmd += [
            *_x264(n["video"]),
            *color_tags(n["color"]),
            *_aac(n["audio"]),
            "-t",
            f"{t1:.6f}",
            *_BITEXACT,
            "-movflags",
            "+faststart",
            str(tmp_mp4),
        ]
        res = run(cmd)
        if info["has_audio"] and "silent_audio_no_loudnorm" not in flags:
            rec["loudnorm_mode"] = str(_loudnorm_json(res.stderr).get("normalization_type"))

        mp4, digest = _hash_move(tmp_mp4, out_dir, n["hash_len"])
        vid = mp4.stem
        rec.update({"video_id": vid, "path": str(mp4), "sha256": digest})

        # output QC
        outp = ffprobe(mp4)
        ov, oa = stream(outp, "video"), stream(outp, "audio")
        dur = float(outp["format"]["duration"])
        rec.update(
            {
                "out_duration_s": dur,
                "out_fps_r": ratio(ov.get("r_frame_rate")),
                "out_fps_avg": ratio(ov.get("avg_frame_rate")),
                "out_pix_fmt": ov.get("pix_fmt"),
                "out_vcodec": ov.get("codec_name"),
                "out_acodec": oa.get("codec_name") if oa else None,
                "out_audio_sample_rate": int(oa["sample_rate"]) if oa else None,
                "out_av_offset_ms": (
                    (fnum(oa.get("start_time")) or 0.0) - (fnum(ov.get("start_time")) or 0.0)
                )
                * 1000.0
                if oa
                else None,
            }
        )
        if dur > st["t1_max_probe_s"]:
            raise MediaError(f"T1 duration {dur:.3f}s > {st['t1_max_probe_s']}s for {mp4}")
        if info["has_audio"] and "silent_audio_no_loudnorm" not in flags:
            o_full = measure_loudness(mp4, lc)
            o_sp = measure_loudness(mp4, lc, segs) if gated else o_full
            rec.update(
                {
                    "loudness_out_speech_lufs": o_sp["input_i"],
                    "loudness_out_full_lufs": o_full["input_i"],
                    "true_peak_out_dbtp": o_full["input_tp"],
                }
            )
            if abs(o_sp["input_i"] - lc["target_lufs"]) > lc["tolerance_lu"]:
                flags.append("loudness_off_target")
            if o_full["input_tp"] > lc["true_peak_dbtp"] + lc["tp_tolerance_db"]:
                flags.append("true_peak_over")

        # sidecar 16 kHz mono WAV (in a subdir: TRIBE would silently reuse <stem>.wav next to the mp4)
        sw = n["sidecar_wav"]
        wav = out_dir / sw["subdir"] / f"{vid}.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                n["ffmpeg_loglevel"],
                "-nostdin",
                "-i",
                str(mp4),
                "-vn",
                "-ac",
                str(sw["channels"]),
                "-ar",
                str(sw["sample_rate"]),
                "-c:a",
                "pcm_s16le",
                *_BITEXACT,
                str(wav),
            ]
        )
        rec["wav_path"] = str(wav)

        rec.update(quality_floor_copy(mp4, out_dir, tw, th, cfg, tmpd))

        if n["photometric"]["enabled"]:
            from yct.normalize.photometric import photometric_normalize

            rec["t3"] = photometric_normalize(mp4, out_dir, cfg)
            flags += [f"t3_{f}" for f in rec["t3"]["flags"]]

    rec["flags"] = flags
    rec["speech_segments"] = segs
    (out_dir / f"{vid}.json").write_text(json.dumps(rec, indent=2, default=float))
    return rec
