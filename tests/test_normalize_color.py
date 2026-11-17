"""P2/T1 colour matrix (G-D032 c3 Neuro G1/N4, P1 c2 Neuro Q3; DECISIONS D-053).

Every P2 output (the T1 stimulus TRIBE decodes, and the 480p round-trip copy) is converted from the source
matrix to BT.709 / limited range and tagged bt709 (matrix, primaries, transfer) / tv, whatever the source
tag: untagged, smpte170m (BT.601) or bt709. The source matrix is the stream tag when present, else the
config rule for untagged streams (`normalize.color.untagged`). Checks read the outputs with ffprobe and an
independent explicit-matrix rawvideo decode written here (not the module's code path).
"""
from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from tests import _synth as syn
from yct.config import load_config
from yct.media import iter_gray_frames
from yct.normalize import normalize_video
from yct.normalize.core import source_color

BT709_TV = {"color_space": "bt709", "color_transfer": "bt709", "color_primaries": "bt709", "color_range": "tv"}
SAT = "eq=saturation=1.8"


def tags(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=color_space,color_transfer,color_primaries,color_range", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def rgb(path, matrix, w, h, n=5):
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", "-vf",
                          f"scale=in_color_matrix={matrix}:in_range=tv,format=rgb24", "-frames:v", str(n),
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, h, w, 3).astype(float)


def y_plane(path, w, h, n=5):
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", "-frames:v", str(n),
                          "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fsz = w * h * 3 // 2
    return np.stack([np.frombuffer(out[i * fsz:i * fsz + w * h], np.uint8).reshape(h, w)
                     for i in range(len(out) // fsz)]).astype(float)


def tagged_clip(out, matrix: str | None, size="640x360", dur=2.0):
    """testsrc2 (saturated) + sine; encoded RGB->YUV with `matrix` and tagged with it (None = untagged)."""
    a = f"sine=f=220:r=48000:d={dur},aformat=channel_layouts=stereo"
    v = f"testsrc2=s={size}:r=30:d={dur},{SAT}"
    extra: list[str] = []
    if matrix is not None:
        sw = {"smpte170m": "bt601", "bt709": "bt709"}[matrix]
        v += f",scale=out_color_matrix={sw}:out_range=tv"
        extra = ["-colorspace", matrix, "-color_primaries", matrix, "-color_trc", matrix, "-color_range", "tv"]
    else:
        v += ",scale=out_color_matrix=bt601:out_range=tv"           # untagged SD: BT.601 bytes, no tag
    syn.ff("-f", "lavfi", "-i", v, "-f", "lavfi", "-i", a, "-shortest", "-c:v", "libx264", "-preset",
           "ultrafast", "-pix_fmt", "yuv420p", *extra, "-c:a", "aac", str(out))
    return out


@pytest.fixture(scope="module")
def cfg():
    return syn.fast_cfg(normalize={"photometric": {"enabled": False}})


@pytest.fixture(scope="module")
def outs(tmp_path_factory, cfg):
    d = tmp_path_factory.mktemp("color")
    res = {}
    for name, m in (("untagged", None), ("smpte170m", "smpte170m"), ("bt709", "bt709")):
        src = tagged_clip(d / f"{name}.mp4", m)
        res[name] = (src, normalize_video(src, d / f"out_{name}", cfg))
    return res


def test_config_color_block():
    c = load_config()["normalize"]["color"]
    assert (c["matrix"], c["primaries"], c["transfer"], c["range"]) == ("bt709", "bt709", "bt709", "tv")
    u = c["untagged"]
    assert u["hd"] == "bt709" and u["sd"] == "smpte170m" and u["range"] == "tv"


@pytest.mark.parametrize("name", ["untagged", "smpte170m", "bt709"])
def test_t1_and_q480_tagged_bt709_tv_under_ffprobe(outs, name):
    src, rec = outs[name]
    if name == "untagged":
        assert "color_space" not in tags(src)                        # the fixture really is untagged
    else:
        assert tags(src)["color_space"] == name
    assert tags(rec["path"]) == BT709_TV
    assert tags(rec["q480_path"]) == BT709_TV


def test_source_colour_logged_per_video(outs):
    exp = {"untagged": ("unknown", "smpte170m", "untagged_sd", True),
           "smpte170m": ("smpte170m", "smpte170m", "tagged", False),
           "bt709": ("bt709", "bt709", "tagged", False)}
    for name, (tag, in_m, rule, flagged) in exp.items():
        c = outs[name][1]["color"]
        assert c["src_color_space"] == tag and c["in_matrix"] == in_m and c["rule"] == rule, name
        assert (c["out_matrix"], c["out_range"]) == ("bt709", "tv")
        assert ("source_color_untagged" in outs[name][1]["flags"]) is flagged


@pytest.mark.parametrize("name", ["untagged", "smpte170m"])
def test_bt601_source_is_converted_not_relabelled(outs, name):
    """RGB is preserved: source decoded with BT.601 == output decoded with BT.709; a mere relabel (no
    matrix conversion) would make the output's BT.709 decode differ by the BT.601/709 matrix error."""
    src, rec = outs[name]
    a = rgb(src, "bt601", 640, 360)
    b = rgb(rec["path"], "bt709", 640, 360)
    c = rgb(rec["path"], "bt601", 640, 360)
    err_ok, err_wrong = np.abs(a - b).mean(), np.abs(a - c).mean()
    assert err_ok < 2.5 and err_wrong > 2 * err_ok


def test_bt709_source_luma_untouched(outs):
    src, rec = outs["bt709"]
    assert np.abs(y_plane(src, 640, 360) - y_plane(rec["path"], 640, 360)).mean() < 1.0


def test_untagged_rule_by_resolution():
    c = load_config()["normalize"]["color"]
    sd = source_color({"width": 640, "height": 360}, c)
    hd = source_color({"width": 1280, "height": 720}, c)
    portrait_hd = source_color({"width": 1080, "height": 1920}, c)
    assert (sd["in_matrix"], sd["rule"]) == ("smpte170m", "untagged_sd")
    assert (hd["in_matrix"], hd["rule"]) == ("bt709", "untagged_hd")
    assert portrait_hd["in_matrix"] == "bt709"
    t = source_color({"width": 640, "height": 360, "color_space": "bt470bg", "color_range": "pc"}, c)
    assert (t["in_matrix"], t["in_range"], t["rule"]) == ("bt470", "pc", "tagged")
    odd = source_color({"width": 640, "height": 360, "color_space": "ycgco"}, c)
    assert odd["rule"] == "unsupported_tag_untagged_sd" and odd["in_matrix"] == "smpte170m"


def test_confounds_gray_decoder_reads_tv_luma_explicitly(outs):
    """yct.media.iter_gray_frames (confounds) decodes the bt709/tv T1 output with an explicit tv range:
    its gray frames equal the raw luma plane expanded from 16-235 to 0-255 (within rounding)."""
    _, rec = outs["smpte170m"]
    g = np.stack([f for _, f in iter_gray_frames(rec["path"], 30, 360)][:5]).astype(float)
    y = y_plane(rec["path"], 640, 360)
    assert g.shape == y.shape
    assert np.abs(g - np.clip((y - 16) * 255 / 219, 0, 255)).mean() < 1.0
