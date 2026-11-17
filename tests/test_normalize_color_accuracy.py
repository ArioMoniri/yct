"""ENH-005 (Neuro G-D032 A1): swscale accurate_rnd + full_chroma_int on every P2 colour conversion.

Without these flags swscale's fast rounding / chroma interpolation biases a BT.601 -> BT.709 conversion by
about -1.2..-1.5 code values; with them the bias is ~0. A synthetic BT.601 (smpte170m-tagged), losslessly
encoded chart is normalised (T1) and decoded back to RGB with an accurate explicit-matrix decoder written
here (not the module's code path): |mean signed bias| per channel must be < 1 code value.
"""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from tests import _synth as syn
from yct.config import load_config
from yct.normalize import normalize_video
from yct.normalize.core import color_scale_opts, sws_flags
from yct.normalize.photometric import decode_filter, encode_filter

W, H = 640, 360
ACC = "accurate_rnd+full_chroma_int"


def rgb(path, matrix, n=5):
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", "-vf",
                          f"scale=flags=bicubic+{ACC}:in_color_matrix={matrix}:in_range=tv,format=rgb24",
                          "-frames:v", str(n), "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, H, W, 3).astype(float)


def bt601_chart(out, dur=2.0):
    """Saturated testsrc2 chart: RGB -> BT.601 YUV (accurate swscale), lossless x264, tagged smpte170m."""
    v = (f"testsrc2=s={W}x{H}:r=30:d={dur},eq=saturation=1.8,"
         f"scale=flags={ACC}:out_color_matrix=bt601:out_range=tv,format=yuv420p")
    a = f"sine=f=220:r=48000:d={dur},aformat=channel_layouts=stereo"
    syn.ff("-f", "lavfi", "-i", v, "-f", "lavfi", "-i", a, "-shortest", "-c:v", "libx264", "-qp", "0",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-colorspace", "smpte170m", "-color_primaries",
           "smpte170m", "-color_trc", "smpte170m", "-color_range", "tv", "-c:a", "aac", str(out))
    return out


def test_config_sws_flags():
    c = load_config()["normalize"]["color"]
    assert c["sws_flags"] == ["accurate_rnd", "full_chroma_int"]
    assert sws_flags("lanczos", c) == "lanczos+accurate_rnd+full_chroma_int"


def test_every_normalize_colour_conversion_carries_the_flags():
    c = load_config()["normalize"]["color"]
    assert "flags=" in color_scale_opts("smpte170m", "tv", c) and ACC in color_scale_opts("bt709", "tv", c)
    p = load_config()["normalize"]["photometric"]
    assert ACC in decode_filter(sws=p["sws_flags"]) and ACC in encode_filter("yuv420p", sws=p["sws_flags"])


@pytest.mark.parametrize("q480", [False, True])
def test_bt601_chart_to_bt709_mean_bias_below_one_code_value(tmp_path, q480):
    src = bt601_chart(tmp_path / "chart601.mp4")
    cfg = syn.fast_cfg(normalize={"photometric": {"enabled": False}, "video": {"crf": 0}})
    rec = normalize_video(src, tmp_path / "out", cfg)
    assert rec["color"]["in_matrix"] == "smpte170m"
    a = rgb(src, "bt601")
    b = rgb(rec["q480_path"] if q480 else rec["path"], "bt709")
    bias = (b - a).mean(axis=(0, 1, 2))
    assert np.all(np.abs(bias) < 1.0), bias          # without the flags: about -1.0 / -0.5 / -1.15
    if not q480:                  # the 480p round trip is lossy by design: bias bound only
        assert np.abs(b - a).mean() < 2.5
