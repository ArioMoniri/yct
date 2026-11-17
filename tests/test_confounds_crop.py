"""Crop-aware face regressor (v2.4 G-D032 N-D5): face columns computed inside the V-JEPA2 view.

The V-JEPA2 view = resize short edge -> 292, centre 256x256 crop. The Haar detector is mocked by a
blob detector (bounding box of bright pixels) so the test checks the geometry, not the cascade.
"""
from __future__ import annotations

import numpy as np
import pytest

from tests import _synth as syn
from yct.config import load_config
from yct.confounds import core


class BlobDetector:
    def detectMultiScale(self, g, **_kw):  # noqa: N802 (OpenCV API name)
        ys, xs = np.nonzero(g > 128)
        if ys.size == 0:
            return ()
        return np.array([[xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1]])


def _blob_video(path, x, y, size=80, dur=2.0):
    vf = ["-vf", f"drawbox=x={x}:y={y}:w={size}:h={size}:color=white:t=fill"] if size else []
    syn.ff("-f", "lavfi", "-i", f"color=black:s=640x360:r=30:d={dur}", *vf,
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path))
    return path


@pytest.fixture
def blob(monkeypatch):
    monkeypatch.setattr(core, "_face_detector", lambda fc: BlobDetector())


def _run(mp4):
    cfg = load_config()
    grid = core.tr_grid(core.duration(mp4), cfg["tribe"]["tr_s"])
    return core.video_features(mp4, grid, cfg)


def test_face_outside_crop_is_not_counted(tmp_path, blob):
    # 640x360 -> 519x292; crop x in [131, 387). Blob at x 10..90 (source) -> 8..73: fully outside.
    v = _run(_blob_video(tmp_path / "out.mp4", x=10, y=140))
    assert np.nanmin(v["face_present_frac"]) == 1.0            # full-frame detector sees it
    assert np.nanmax(v["face_present_crop"]) == 0.0            # V-JEPA2 does not
    assert np.nanmax(v["face_area_crop_frac"]) == 0.0
    assert np.nanmin(v["face_area_outside_crop_frac"]) == pytest.approx(1.0)


def test_face_inside_crop_is_counted(tmp_path, blob):
    v = _run(_blob_video(tmp_path / "in.mp4", x=280, y=140))   # centred
    assert np.nanmin(v["face_present_crop"]) == 1.0
    # 80 px source box -> ~65 px at short edge 292; area / 256^2 ~ 0.064
    area = v["face_area_crop_frac"]
    assert np.nanmin(area) == pytest.approx((80 * 292 / 360) ** 2 / 256**2, rel=0.15)
    assert np.nanmax(v["face_area_outside_crop_frac"]) == pytest.approx(0.0, abs=1e-9)


def test_face_straddling_crop_edge(tmp_path, blob):
    # source x 120..200 -> 97..162 at 292; inside part 131..162 ~ 48% of the box
    v = _run(_blob_video(tmp_path / "edge.mp4", x=120, y=140))
    a = np.nanmean(v["face_area_crop_frac"])
    full = (80 * 292 / 360) ** 2 / 256**2
    assert 0.25 * full < a < 0.75 * full
    assert np.nanmax(v["face_present_crop"]) == 0.0            # < crop_min_inside_frac (0.5) inside


def test_no_face_gives_zero_not_nan(tmp_path, blob):
    v = _run(_blob_video(tmp_path / "none.mp4", x=0, y=0, size=0))
    assert np.nanmax(v["face_present_crop"]) == 0.0
    assert np.isfinite(v["face_area_crop_frac"]).all() and np.nanmax(v["face_area_crop_frac"]) == 0.0


def test_ffc_regressor_is_crop_column():
    cfg = load_config()["confounds"]
    assert cfg["ffc_regressor"] == "face_area_crop_frac"
    assert cfg["ffc_regressor"] in core.FEATURES
    for col in ("face_present_crop", "luminance_crop", "contrast_crop", "speech_rate_wps", "speech_frac"):
        assert col in core.FEATURES
