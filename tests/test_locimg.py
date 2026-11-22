"""T-REF58 LOC image processing (D-071 (b) Processing): square crop from the frozen manifest crop_box,
BT.709 luma, INTER_AREA to the 316-px patch, then SHINE specMatch -> lumMatch, 2 iterations, over all 60
images jointly (target mean 128, RMS contrast 32). Synthetic images only."""
from __future__ import annotations

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import locimg as L  # noqa: N812

CFG = load_config()
SH = CFG["controls"]["refclips"]["shine"]


def _rgb(seed, h=500, w=700):
    r = np.random.default_rng(seed)
    base = r.integers(0, 256, (h, w, 3)).astype(np.uint8)
    return base


def test_patch_is_crop_box_bt709_inter_area_316():
    import cv2

    rgb = _rgb(1)
    box = (50, 20, 400)
    p = L.patch(rgb, box)
    assert p.shape == (316, 316) and p.dtype == np.uint8
    x, y, s = box
    c = rgb[y:y + s, x:x + s].astype(np.float64)
    g = (0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]).round().clip(0, 255).astype(np.uint8)
    assert np.array_equal(p, cv2.resize(g, (316, 316), interpolation=cv2.INTER_AREA))


def test_patch_refuses_box_origin_outside_image():
    with pytest.raises(ValueError):
        L.patch(_rgb(2, 300, 300), (300, 0, 100))
    with pytest.raises(ValueError):
        L.patch(_rgb(2, 300, 300), (-1, 0, 100))


def test_patch_clips_an_edge_overrun_exactly_as_the_tlic_crop_did():
    """The frozen crop_box comes from a <=1600-px Haar pass scaled back with rounding, so it can overrun the
    image edge by a few px (face_05: side 3939 on a 3937-px-wide image). T-LIC sliced with numpy (silent
    clip) before the square resize; the stimulus patch must use the same pixels."""
    import cv2

    rgb = _rgb(4, 300, 298)
    p = L.patch(rgb, (0, 2, 300))
    g = L.grey709(rgb[2:302, 0:300])
    assert g.shape == (298, 298)
    assert np.array_equal(p, cv2.resize(g, (316, 316), interpolation=cv2.INTER_AREA))
    assert L.overrun(rgb, (0, 2, 300)) == 4
    with pytest.raises(ValueError):
        L.patch(rgb, (0, 0, 400), max_overrun=8)


def _set(n=6):
    r = np.random.default_rng(7)
    out = []
    for i in range(n):
        f = np.fft.fftfreq(316)
        amp = 1.0 / (np.hypot(*np.meshgrid(f, f)) + 0.01) ** (1 + 0.2 * i)
        ph = r.uniform(-np.pi, np.pi, (316, 316))
        im = np.real(np.fft.ifft2(amp * np.exp(1j * ph)))
        im = (im - im.mean()) / im.std() * (20 + 5 * i) + 90 + 10 * i
        out.append(im.clip(0, 255).round().astype(np.uint8))
    return out


def test_shine_matches_mean_and_rms_jointly():
    out = L.shine(_set(), SH)
    for im in out:
        assert im.dtype == np.uint8 and im.shape == (316, 316)
        assert abs(im.astype(float).mean() - SH["mean_luma"]) < 0.6
        assert abs(im.astype(float).std() - SH["rms_contrast"]) < 0.6


def test_shine_equalises_amplitude_spectra():
    ims = _set()

    def spread(xs):
        a = np.array([np.abs(np.fft.fft2(x.astype(float) - x.mean())) for x in xs])
        return float(np.mean(np.std(a, axis=0)) / np.mean(a))

    assert spread(L.shine(ims, SH)) < 0.25 * spread(ims)


def test_shine_keeps_phase_structure():
    ims = _set()
    out = L.shine(ims, SH)
    for a, b in zip(ims, out, strict=True):
        assert np.corrcoef(a.ravel().astype(float), b.ravel().astype(float))[0, 1] > 0.8


def test_shine_is_deterministic_and_order_equivariant():
    ims = _set()
    a = L.shine(ims, SH)
    b = L.shine(ims, SH)
    assert all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))
    c = L.shine(ims[::-1], SH)[::-1]
    assert all(np.array_equal(x, y) for x, y in zip(a, c, strict=True))


def test_shine_refuses_unknown_steps_and_mixed_shapes():
    with pytest.raises(ValueError):
        L.shine(_set(), {**SH, "steps": ["histMatch"]})
    ims = _set()
    ims[0] = ims[0][:300, :300]
    with pytest.raises(ValueError):
        L.shine(ims, SH)


def test_loc_images_orders_by_manifest_and_shines_all_60_jointly(monkeypatch):
    calls = {}

    def fake_shine(ims, sh):
        calls["n"] = len(ims)
        return [np.full((316, 316), k % 256, np.uint8) for k in range(len(ims))]

    monkeypatch.setattr(L, "shine", fake_shine)
    mans = {c: [{"category": c, "crop_box": [0, 0, 400], "sha256": f"{c}{i}"} for i in range(20)]
            for c in ("face", "body", "place")}
    out = L.loc_images(mans, lambda row: _rgb(3), CFG)
    assert calls["n"] == 60
    assert [len(out[c]) for c in ("face", "body", "place")] == [20, 20, 20]
    assert int(out["body"][0][0, 0]) == 20 and int(out["place"][19][0, 0]) == 59


def test_loc_images_refuses_wrong_count():
    row = {"crop_box": [0, 0, 400], "sha256": "x"}
    mans = {c: [{**row, "category": c}] * 19 for c in ("face", "body", "place")}
    with pytest.raises(ValueError):
        L.loc_images(mans, lambda row: _rgb(3), CFG)
