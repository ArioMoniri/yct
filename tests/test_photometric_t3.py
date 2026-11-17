"""T3 v2.4 G-D032: crop-region statistics, max_gain cap with re-solved offset, clipping report, kept clips."""

from __future__ import annotations

import numpy as np
import pytest

from tests import _synth as syn
from yct.normalize.photometric import (
    iter_rgb_frames,
    photometric_normalize,
    solve_transform,
    t3_report,
    vjepa_crop_region,
)

W709 = np.array([0.2126, 0.7152, 0.0722])


def _y_stats(path, region=None, fps=5):
    ys = [px @ W709 for px in iter_rgb_frames(path, fps, region)]
    return float(np.mean([y.mean() for y in ys])), float(np.mean([y.std() for y in ys]))


def test_vjepa_crop_region_geometry():
    assert vjepa_crop_region(360, 640) == (22, 338, 162, 478)
    assert vjepa_crop_region(292, 520) == (18, 274, 132, 388)          # already at 292: exact 256 crop
    y0, y1, x0, x1 = vjepa_crop_region(1920, 1080)                     # portrait
    assert (x1 - x0) == (y1 - y0) == round(256 * 1080 / 292) and x0 == 0 or x0 >= 0
    assert y0 == (1920 - (y1 - y0)) // 2


def test_stats_estimated_in_crop_not_full_frame(tmp_path):
    """Bright borders outside the crop must not drive the transform: the target is hit inside the crop."""
    cfg = syn.fast_cfg()
    p = cfg["normalize"]["photometric"]
    src = tmp_path / "border.mp4"
    # dark textured centre, white side bars that V-JEPA2 never sees (x < 162 or x >= 478)
    syn.ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=2",
           "-vf", "eq=brightness=-0.25:contrast=0.6,drawbox=x=0:y=0:w=150:h=360:color=white:t=fill,"
                  "drawbox=x=490:y=0:w=150:h=360:color=white:t=fill",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(src))
    rec = photometric_normalize(src, tmp_path / "out", cfg)
    assert rec["stats_region"] == "vjepa_crop" and rec["crop_region_yx"] == [22, 338, 162, 478]
    m_crop, sd_crop = _y_stats(rec["t3_path"], (22, 338, 162, 478))
    m_full, _ = _y_stats(rec["t3_path"])
    assert m_crop == pytest.approx(p["target_mean_y"], abs=0.02)
    assert sd_crop == pytest.approx(p["target_rms_contrast"], abs=0.02)
    assert abs(m_full - p["target_mean_y"]) > 0.05                     # full frame is NOT the target region
    assert rec["after"]["mean_y"] == pytest.approx(m_crop, abs=0.01)
    assert rec["after_full"]["mean_y"] == pytest.approx(m_full, abs=0.01)
    for k in ("before", "after", "before_full", "after_full"):
        assert {"mean_y", "rms_contrast", "channel_means", "colour_cast"} <= set(rec[k])
    assert 0 <= rec["clip_frac"] <= 1 and 0 <= rec["clip_frac_full"] <= 1


def _stats(mean_y, sd):
    """Synthetic frame_stats input: grey frames with given mean and spatial SD (all channels equal)."""
    m = np.full((4, 3), mean_y)
    c = np.full((4, 3, 3), sd**2)
    return {"frame_channel_means": m, "frame_channel_covs": c}


def test_gain_cap_binds_and_offset_resolved():
    p = syn.fast_cfg()["normalize"]["photometric"]
    assert p["max_gain"] == 3.0 and p["min_gain"] == 0.25
    tf = solve_transform(_stats(0.3, 0.02), p)                         # needs a = 10
    assert tf["a_uncapped"] == pytest.approx(10.0)
    assert tf["a"] == p["max_gain"] and tf["gain_capped"] is True
    assert tf["a"] * 0.3 + tf["b"] == pytest.approx(p["target_mean_y"])  # mean target still met
    tf2 = solve_transform(_stats(0.5, 0.1), p)                         # a = 2: no cap
    assert tf2["gain_capped"] is False and tf2["a"] == pytest.approx(2.0)
    tf3 = solve_transform(_stats(0.5, 2.0), p)                         # a = 0.1 -> floor 0.25
    assert tf3["a"] == p["min_gain"] and tf3["gain_capped"] is True
    tf4 = solve_transform(_stats(0.5, 0.0), p)                         # flat video: capped, not inf
    assert tf4["a"] == p["max_gain"] and np.isfinite(tf4["b"])


def test_capped_clip_flagged_and_kept(tmp_path):
    cfg = syn.fast_cfg()
    src = syn.clip(tmp_path / "flat.mp4", dur=2.0, vf="lutyuv=y=128+(val-128)*0.1:u=128:v=128")   # a ~ 6
    rec = photometric_normalize(src, tmp_path / "out", cfg)
    assert rec["gain_capped"] is True and "gain_capped" in rec["flags"]
    assert rec["gain_a"] == 3.0 and rec["gain_a_uncapped"] > 3.0
    assert rec["kept_in_t3"] is True and rec["t3_path"].endswith(".mp4")
    assert rec["after"]["mean_y"] == pytest.approx(cfg["normalize"]["photometric"]["target_mean_y"], abs=0.03)


def _rec(a, clip, flags, cast=0.1, gmax=1.1):
    return {"gain_a": a, "gain_a_uncapped": a, "max_channel_gain": gmax, "clip_frac": clip,
            "clip_frac_full": clip, "gain_capped": "gain_capped" in flags, "flags": flags,
            "before": {"colour_cast": cast}, "kept_in_t3": True}


def test_t3_report_pooled_and_by_group_after_unblinding_only():
    recs = [_rec(1.0, 0.0, []), _rec(3.0, 0.02, ["clipping", "gain_capped"], gmax=1.5),
            _rec(1.5, 0.001, []), _rec(0.8, 0.0, [], gmax=1.4)]
    r = t3_report(recs)
    assert r["pooled"]["n"] == 4 and r["pooled"]["n_clipping"] == 1 and r["pooled"]["n_gain_capped"] == 1
    assert r["pooled"]["share_channel_gain_gt"] == pytest.approx(0.5)
    assert r["pooled"]["quantiles"]["gain_a"][0.5] == pytest.approx(1.25)
    assert "by_group" not in r
    with pytest.raises(PermissionError):
        t3_report(recs, groups=["acc", "rej", "acc", "rej"])
    rg = t3_report(recs, groups=["acc", "rej", "acc", "rej"], unblinded=True)
    assert rg["by_group"]["rej"]["n_clipping"] == 1 and rg["by_group"]["acc"]["n"] == 2
    bad = [*recs[:1], {**recs[1], "kept_in_t3": False}]
    with pytest.raises(ValueError):
        t3_report(bad)
