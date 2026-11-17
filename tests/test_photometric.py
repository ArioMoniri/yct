"""Photometric T3 copy (owner request): global gain/offset to target mean Y and RMS contrast."""

from __future__ import annotations

import numpy as np
import pytest

from tests import _synth as syn
from yct.normalize.photometric import iter_rgb_frames, photometric_normalize

W709 = np.array([0.2126, 0.7152, 0.0722])


# V-JEPA2 view of a 640x360 frame, derived independently: short edge 360 -> 292, centre 256^2 crop
# = a 256 * 360 / 292 = 315.6 -> 316 px square centred in the source: y 22..338, x 162..478.
CROP_640x360 = (22, 338, 162, 478)


def _measure(path, fps=5, region=CROP_640x360):
    """Independent of the module's covariance shortcut: direct per-frame Y statistics (in the crop)."""
    ys = [px @ W709 for px in iter_rgb_frames(path, fps, region)]
    return np.array([y.mean() for y in ys]), np.array([y.std() for y in ys])


@pytest.fixture(scope="module")
def cfg():
    return syn.fast_cfg()


# dark+low-contrast and bright+tinted; both with within-video brightness dynamics (a flash + a slow drift)
DYN = "eq=brightness='0.06*sin(2*PI*t/3)+0.12*between(t\\,1.5\\,1.8)':eval=frame"


@pytest.mark.parametrize(
    "vf",
    [
        f"eq=contrast=0.5:brightness=-0.2,{DYN}",
        f"eq=contrast=0.8:brightness=0.15,colorbalance=rm=0.25:bm=-0.2,{DYN}",
    ],
    ids=["dark_lowcontrast", "bright_tinted"],
)
def test_targets_hit_and_dynamics_preserved(tmp_path, cfg, vf):
    src = syn.clip(tmp_path / "src.mp4", dur=4.0, vf=vf)
    p = cfg["normalize"]["photometric"]
    rec = photometric_normalize(src, tmp_path / "out", cfg)
    m_out, sd_out = _measure(rec["t3_path"])
    assert m_out.mean() == pytest.approx(p["target_mean_y"], abs=0.02)
    assert sd_out.mean() == pytest.approx(p["target_rms_contrast"], abs=0.02)
    assert rec["after"]["mean_y"] == pytest.approx(p["target_mean_y"], abs=0.02)
    assert rec["after"]["rms_contrast"] == pytest.approx(p["target_rms_contrast"], abs=0.02)
    m_in, _ = _measure(src)
    assert np.corrcoef(m_in, m_out)[0, 1] > 0.99
    assert rec["frame_luminance_corr"] > 0.99
    assert 0.0 <= rec["clip_frac"] <= 1.0
    assert rec["after"]["colour_cast"] <= rec["before"]["colour_cast"] + 1e-3
    for k in ("mean_y", "rms_contrast", "channel_means", "colour_cast"):
        assert k in rec["before"] and k in rec["after"]


def test_gray_world_removes_cast(tmp_path, cfg):
    src = syn.clip(tmp_path / "tint.mp4", dur=2.0, vf="colorchannelmixer=rr=1:gg=0.8:bb=0.55")
    rec = photometric_normalize(src, tmp_path / "out", cfg)
    assert rec["before"]["colour_cast"] > 0.1
    assert rec["after"]["colour_cast"] < 0.3 * rec["before"]["colour_cast"]


def test_clipping_reported_and_flagged(tmp_path, cfg):
    # very high contrast target on a full-range pattern forces clipping
    hard = syn.fast_cfg(normalize={"photometric": {"target_rms_contrast": 0.45}})
    src = syn.clip(tmp_path / "c.mp4", dur=2.0)
    rec = photometric_normalize(src, tmp_path / "out", hard)
    assert rec["clip_frac"] > 0.01 and "clipping" in rec["flags"]
    soft = photometric_normalize(src, tmp_path / "out2", cfg)
    assert soft["clip_frac"] < 0.01 and soft["flags"] == []


def test_global_transform_is_one_gain_offset(tmp_path, cfg):
    src = syn.clip(tmp_path / "g.mp4", dur=2.0, vf=DYN)
    rec = photometric_normalize(src, tmp_path / "out", cfg)
    assert isinstance(rec["gain_a"], float) and isinstance(rec["offset_b"], float)
    assert len(rec["gains"]) == 3 and rec["temporal_smoothing"] is False
    assert rec["t3_path"].endswith(".mp4") and "/t3/" in rec["t3_path"]


def test_temporal_smoothing_optional(tmp_path):
    on = syn.fast_cfg(normalize={"photometric": {"temporal_smoothing": {"enabled": True}}})
    src = syn.clip(tmp_path / "s.mp4", dur=2.0, vf=DYN)
    rec = photometric_normalize(src, tmp_path / "out", on)
    assert rec["temporal_smoothing"] is True and rec["t3_path"].endswith(".mp4")
    assert syn.fast_cfg()["normalize"]["photometric"]["temporal_smoothing"]["enabled"] is False
