"""ENH-006 (Neuro G-D032 A2): HDR (PQ / HLG transfer) sources are detected from the ffprobe
``color_transfer`` tag, flagged ``hdr_source`` in the normalisation record (and as a covariate), and
tone-mapped to SDR BT.709 / tv with zscale + tonemap. If the local ffmpeg lacks those filters the run fails
loudly (never a silent relabel of PQ code values as BT.709).
"""
from __future__ import annotations

import json
import subprocess

import numpy as np
import pandas as pd
import pytest

from tests import _synth as syn
from yct.config import load_config
from yct.media import MediaError
from yct.normalize import core, normalize_video
from yct.normalize.core import hdr_info, normalisation_covariates, tonemap_filter

BT709_TV = {"color_space": "bt709", "color_transfer": "bt709", "color_primaries": "bt709",
            "color_range": "tv"}


def tags(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=color_space,color_transfer,color_primaries,color_range", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def y_mean(path, n=5) -> float:
    st = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height", "-of", "json", str(path)],
                                   capture_output=True, text=True, check=True).stdout)["streams"][0]
    w, h = st["width"], st["height"]
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-an", "-frames:v", str(n),
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return float(np.frombuffer(out, np.uint8).reshape(-1, h, w).mean())


def hdr_clip(out, trc="smpte2084", dur=2.0):
    """testsrc2 + sine, 10-bit, tagged BT.2020 / <trc> (synthetic PQ/HLG-tagged clip)."""
    syn.ff("-f", "lavfi", "-i", f"testsrc2=s=640x360:r=30:d={dur}", "-f", "lavfi", "-i",
           f"sine=f=220:r=48000:d={dur},aformat=channel_layouts=stereo", "-shortest",
           "-vf", "format=yuv420p10le",
           "-c:v", "libx264", "-preset", "ultrafast", "-colorspace", "bt2020nc", "-color_primaries", "bt2020",
           "-color_trc", trc, "-color_range", "tv", "-c:a", "aac", str(out))
    return out


@pytest.fixture(scope="module")
def cfg():
    return syn.fast_cfg(normalize={"photometric": {"enabled": False}})


def test_config_hdr_block():
    h = load_config()["normalize"]["color"]["hdr"]
    assert set(h["transfers"]) == {"smpte2084", "arib-std-b67"}
    assert h["action"] == "tonemap" and h["covariate"] == "hdr_source"


def test_hdr_detection_from_color_transfer():
    h = load_config()["normalize"]["color"]["hdr"]
    assert hdr_info({"color_transfer": "smpte2084"}, h)["hdr_source"] is True
    assert hdr_info({"color_transfer": "arib-std-b67"}, h)["hdr_source"] is True
    for t in ("bt709", "smpte170m", None, "unknown"):
        assert hdr_info({"color_transfer": t}, h)["hdr_source"] is False


def test_tonemap_filter_is_zscale_tonemap_to_bt709_tv():
    h = load_config()["normalize"]["color"]["hdr"]
    f = tonemap_filter({"color_transfer": "smpte2084", "color_space": "bt2020nc",
                        "color_primaries": "bt2020", "color_range": "tv"}, h)
    assert f.startswith("zscale=tin=smpte2084:min=bt2020nc:pin=bt2020") and "tonemap=tonemap=hable" in f
    assert "zscale=t=bt709:m=bt709:p=bt709:r=tv" in f


@pytest.mark.parametrize("trc", ["smpte2084", "arib-std-b67"])
def test_hdr_clip_flagged_and_tonemapped_to_sdr_bt709(tmp_path, cfg, trc):
    src = hdr_clip(tmp_path / f"{trc}.mp4", trc)
    assert tags(src)["color_transfer"] == trc                     # the fixture really is HDR-tagged
    rec = normalize_video(src, tmp_path / "out", cfg)
    assert rec["hdr_source"] is True and "hdr_source" in rec["flags"]
    assert rec["color"]["hdr_source"] is True and rec["color"]["hdr_tonemapped"] is True
    assert rec["color"]["src_color_transfer"] == trc
    assert tags(rec["path"]) == BT709_TV and tags(rec["q480_path"]) == BT709_TV
    assert rec["out_pix_fmt"] == "yuv420p"
    # tone-mapped content is a real picture in legal range (not black, not clipped white)
    assert 30 < y_mean(rec["path"]) < 220
    assert normalisation_covariates([rec]).loc[rec["video_id"], "hdr_source"] == 1.0


def test_sdr_clip_not_flagged(tmp_path, cfg):
    src = syn.clip(tmp_path / "sdr.mp4", dur=2.0)
    rec = normalize_video(src, tmp_path / "out", cfg)
    assert rec["hdr_source"] is False and "hdr_source" not in rec["flags"]
    assert rec["color"]["hdr_tonemapped"] is False
    cov = normalisation_covariates([rec])
    assert isinstance(cov, pd.DataFrame) and cov.loc[rec["video_id"], "hdr_source"] == 0.0


def test_hdr_without_zscale_tonemap_fails_loudly(tmp_path, cfg, monkeypatch):
    src = hdr_clip(tmp_path / "pq.mp4")
    monkeypatch.setattr(core, "ffmpeg_filters", lambda: frozenset({"scale", "fps"}))
    with pytest.raises(MediaError, match=r"HDR source .*zscale.*tonemap"):
        normalize_video(src, tmp_path / "out", cfg)


def test_hdr_action_fail_refuses(tmp_path):
    c = syn.fast_cfg(normalize={"photometric": {"enabled": False}, "color": {"hdr": {"action": "fail"}}})
    src = hdr_clip(tmp_path / "pq.mp4")
    with pytest.raises(MediaError, match="HDR source"):
        normalize_video(src, tmp_path / "out", c)
