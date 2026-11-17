"""T3 photometric: independent decoding (QA G-D032 c2 D6) and a temporal-smoothing test with teeth (D7).

The checks below never go through the module's own decoder (``iter_rgb_frames``): the T3 output is read
(a) as the raw Y plane of yuv420p (no colour conversion at all), (b) with ffmpeg ``signalstats`` YAVG, and
(c) with an explicit BT.709/tv rawvideo decode written here. BT.709 is used everywhere and the output is
tagged bt709 / tv.
"""
from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from tests import _synth as syn
from yct.normalize.photometric import iter_rgb_frames, photometric_normalize, video_size

W709 = np.array([0.2126, 0.7152, 0.0722])
W601 = np.array([0.299, 0.587, 0.114])
CROP_640x360 = (22, 338, 162, 478)  # V-JEPA2 view of 640x360, derived independently (see test_photometric)


def y_plane_frames(path, fps=None):
    """Raw luma plane (8-bit code values) of every frame: yuv420p rawvideo, NO matrix conversion."""
    h, w = video_size(path)
    vf = ["-vf", f"fps={fps}"] if fps else []
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", *vf,
                          "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    fsz = w * h * 3 // 2
    n = len(out) // fsz
    return np.stack([np.frombuffer(out[i * fsz:i * fsz + w * h], np.uint8).reshape(h, w) for i in range(n)])


def tv_to_unit(y):
    return (np.asarray(y, float) - 16.0) / 219.0


def rgb_decode(path, matrix, fps=5):
    """Independent explicit-matrix decode (not the module's code path). Uses the ENH-005 swscale flags
    (accurate_rnd + full_chroma_int) written out literally here, as the specified decoder does."""
    h, w = video_size(path)
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", "-vf",
                          f"fps={fps},scale=flags=accurate_rnd+full_chroma_int:in_color_matrix={matrix}"
                          ":in_range=tv,format=rgb24",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, h, w, 3).astype(float) / 255.0


def signalstats_yavg(path, region):
    y0, y1, x0, x1 = region
    out = subprocess.run(["ffprobe", "-v", "error", "-f", "lavfi", "-i",
                          f"movie={path},crop={x1 - x0}:{y1 - y0}:{x0}:{y0},signalstats",
                          "-show_entries", "frame_tags=lavfi.signalstats.YAVG", "-of", "csv=p=0"],
                         capture_output=True, text=True, check=True).stdout
    return np.array([float(v.strip(",")) for v in out.split() if v.strip(",")])


@pytest.fixture(scope="module")
def t3(tmp_path_factory):
    d = tmp_path_factory.mktemp("bt709")
    cfg = syn.fast_cfg()
    # saturated colours make BT.601 vs BT.709 decoding differ measurably
    src = syn.clip(d / "src.mp4", dur=3.0, vf="eq=contrast=0.6:brightness=-0.15:saturation=1.8")
    rec = photometric_normalize(src, d / "out", cfg)
    return src, rec, cfg["normalize"]["photometric"]


def test_output_is_tagged_bt709_tv(t3):
    _, rec, _ = t3
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=color_space,color_transfer,color_primaries,color_range", "-of", "json",
                            rec["t3_path"]], capture_output=True, text=True, check=True).stdout
    s = json.loads(probe)["streams"][0]
    assert s == {"color_space": "bt709", "color_transfer": "bt709", "color_primaries": "bt709",
                 "color_range": "tv"}
    assert rec["color_matrix"] == "bt709" and rec["color_range"] == "tv"


def test_raw_y_plane_hits_targets_in_crop(t3):
    """Independent of every RGB decoder: the encoded luma plane itself has the target mean and contrast."""
    _, rec, p = t3
    y0, y1, x0, x1 = CROP_640x360
    y = tv_to_unit(y_plane_frames(rec["t3_path"], fps=5)[:, y0:y1, x0:x1])
    assert y.mean(axis=(1, 2)).mean() == pytest.approx(p["target_mean_y"], abs=0.01)
    assert y.std(axis=(1, 2)).mean() == pytest.approx(p["target_rms_contrast"], abs=0.01)


def test_signalstats_yavg_hits_target_in_crop(t3):
    _, rec, p = t3
    yavg = signalstats_yavg(rec["t3_path"], CROP_640x360)
    assert len(yavg) >= 60
    assert tv_to_unit(yavg.mean()) == pytest.approx(p["target_mean_y"], abs=0.01)


def test_module_decoder_matches_independent_bt709_decode(t3):
    src, rec, _ = t3
    for path in (src, rec["t3_path"]):
        ours = np.stack(list(iter_rgb_frames(path, 5)))
        ref = rgb_decode(path, "bt709").reshape(ours.shape)
        assert np.max(np.abs(ours - ref)) <= 1 / 255 + 1e-9
    # the module's statistics agree with the raw luma plane (encoder and decoder use the same matrix; the
    # residual is RGB gamut clipping of 4:2:0 chroma on saturated content)
    y0, y1, x0, x1 = CROP_640x360
    y = tv_to_unit(y_plane_frames(rec["t3_path"], fps=5)[:, y0:y1, x0:x1])
    assert rec["after"]["mean_y"] == pytest.approx(y.mean(), abs=0.01)


def test_bt601_decode_would_disagree(t3):
    """Guard against silently falling back to ffmpeg's untagged default: on saturated content the BT.601
    decode gives a measurably different Y' than the luma plane; BT.709 gives the same."""
    _, rec, _ = t3
    y0, y1, x0, x1 = CROP_640x360
    plane = tv_to_unit(y_plane_frames(rec["t3_path"], fps=5)[:, y0:y1, x0:x1])
    y709 = (rgb_decode(rec["t3_path"], "bt709")[:, y0:y1, x0:x1] @ W709)
    y601 = (rgb_decode(rec["t3_path"], "bt601")[:, y0:y1, x0:x1] @ W709)
    err709 = np.abs(y709 - plane).mean()
    err601 = np.abs(y601 - plane).mean()
    assert err709 < 0.006 and err601 > 2 * err709


# ---------------------------------------------------------------- D7: temporal smoothing has teeth
FLICKER = "eq=brightness='0.10*(2*mod(n\\,2)-1)':eval=frame"  # +/-0.10 every other frame (30 fps)


@pytest.fixture(scope="module")
def flicker(tmp_path_factory):
    d = tmp_path_factory.mktemp("flicker")
    src = syn.clip(d / "flicker.mp4", dur=2.0, vf=f"eq=contrast=0.7,{FLICKER}")
    off = photometric_normalize(src, d / "off", syn.fast_cfg())
    on = photometric_normalize(src, d / "on", syn.fast_cfg(
        normalize={"photometric": {"temporal_smoothing": {"enabled": True}}}))
    series = {k: tv_to_unit(y_plane_frames(p).mean(axis=(1, 2)))
              for k, p in (("src", src), ("off", off["t3_path"]), ("on", on["t3_path"]))}
    return series, off, on


def test_smoothing_on_strictly_reduces_frame_to_frame_luminance_variance(flicker):
    s, _, on = flicker
    assert on["temporal_smoothing"] is True
    v_on, v_off = np.var(np.diff(s["on"])), np.var(np.diff(s["off"]))
    assert v_on < 0.5 * v_off, (v_on, v_off)  # a measurable effect, not just a flag


def test_smoothing_off_is_identity_up_to_the_global_affine_map(flicker):
    s, off, _ = flicker
    assert off["temporal_smoothing"] is False
    assert len(s["src"]) == len(s["off"]) >= 55
    slope, icpt = np.polyfit(s["src"], s["off"], 1)
    resid = s["off"] - (slope * s["src"] + icpt)
    assert np.corrcoef(s["src"], s["off"])[0, 1] > 0.999
    assert np.abs(resid).max() < 0.01
    # per-frame flicker amplitude is carried over (scaled by the global gain), not damped
    ratio = np.var(np.diff(s["off"])) / (slope ** 2 * np.var(np.diff(s["src"])))
    assert ratio == pytest.approx(1.0, abs=0.1)


def test_smoothing_keeps_the_mean_level(flicker):
    s, _, _ = flicker
    assert s["on"].mean() == pytest.approx(s["off"].mean(), abs=0.01)
