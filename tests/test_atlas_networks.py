"""M1 network features (v2.md §1): spatial standardisation, W-window, 6 Yeo means + spatial SD, G."""
from __future__ import annotations

import numpy as np
import pytest

from tests._atlas import NV, load_or_skip, synthetic_atlases
from yct.features import atlas as A
from yct.features import networks as N

M1_COLS = ["Vis", "SomMot", "DorsAttn", "SalVentAttn", "Cont", "Default", "spatial_sd"]


def _pred(seed=0, t=60, yeo=None):
    rng = np.random.default_rng(seed)
    x = rng.normal(2.0, 1.5, size=(t, NV)).astype(np.float32)
    if yeo is not None:  # network-structured signal so means are not trivially ~0
        x += 1.2 * (yeo.labels == 1)[None, :] - 0.8 * (yeo.labels == 7)[None, :]
    return x


def test_spatial_standardize_masks_and_scales():
    at = synthetic_atlases()
    mw = at.medial_wall
    z = N.spatial_standardize(_pred(), mw)
    assert z.shape == (60, NV)
    assert np.isnan(z[:, mw]).all()
    np.testing.assert_allclose(np.nanmean(z, axis=1), 0, atol=1e-5)
    np.testing.assert_allclose(np.nanstd(z, axis=1), 1, atol=1e-5)


def test_window_average_bounds():
    x = np.arange(10, dtype=float)[:, None] * np.ones((1, 3))
    np.testing.assert_allclose(N.window_average(x, 2, 4), [3.5] * 3)
    with pytest.raises(ValueError):
        N.window_average(x, 8, 4)


def test_m1_synthetic():
    at = synthetic_atlases()
    pred = _pred(yeo=at.yeo7)
    m1 = N.m1_features(pred, at.yeo7, at.medial_wall, start=5, length=40)
    assert list(m1.index) == M1_COLS
    all7 = N.yeo7_means(N.window_average(N.spatial_standardize(pred, at.medial_wall), 5, 40), at.yeo7)
    assert abs(all7["Vis"]) > 0.3
    # limbic is the exact linear combination of the other six (rank 6)
    n = np.array([(at.yeo7.labels == k).sum() for k in range(1, 8)])
    v = all7.to_numpy()
    lim = all7.index.get_loc("Limbic")
    others = np.delete(np.arange(7), lim)
    np.testing.assert_allclose(v[lim], -(n[others] / n[lim]) @ v[others], atol=1e-6)
    sd = np.std(pred[5:45][:, ~at.medial_wall], axis=1).mean()
    assert m1["spatial_sd"] == pytest.approx(sd, rel=1e-5)


def test_global_amplitude_and_parcel_means():
    at = synthetic_atlases()
    pred = _pred()
    g = N.global_amplitude(pred, at.medial_wall, start=5, length=40)
    assert g == pytest.approx(pred[5:45][:, ~at.medial_wall].mean(), rel=1e-5)
    m = np.zeros(NV)
    m[at.schaefer.labels == 3] = 2.0
    pm = N.parcel_means(m, at.schaefer)
    assert pm.shape == (at.schaefer.n_labels,)
    assert pm[2] == 2.0 and np.count_nonzero(pm) == 1


@pytest.mark.atlas
def test_m1_real_yeo_rank():
    s = load_or_skip(A.load_schaefer400)
    yeo = A.yeo7_from_schaefer(s)
    mw = A.medial_wall_mask(s)
    feats = []
    for seed in range(12):
        pred = _pred(seed, t=50, yeo=yeo) + np.random.default_rng(100 + seed).normal(
            0, 1, size=8)[yeo.labels][None, :]
        avg = N.window_average(N.spatial_standardize(pred, mw), 5, 40)
        all7 = N.yeo7_means(avg, yeo)
        # 7 network means of a spatially centred map: size-weighted sum = 0
        n = np.array([(yeo.labels == k).sum() for k in range(1, 8)])
        assert abs(n @ all7.to_numpy()) / n.sum() < 1e-5
        m1 = N.m1_features(pred, yeo, mw, start=5, length=40)
        assert list(m1.index) == M1_COLS
        assert np.abs(m1.iloc[:6].to_numpy()).max() > 0.05     # not degenerate
        feats.append(all7.to_numpy())
    f = np.array(feats)
    assert np.linalg.matrix_rank(f, tol=1e-6 * np.abs(f).max()) == 6       # 7-network set: rank 6
    m1_mat = f[:, [0, 1, 2, 3, 5, 6]]
    assert np.linalg.matrix_rank(m1_mat, tol=1e-6 * np.abs(f).max()) == 6  # 6 kept: full rank
