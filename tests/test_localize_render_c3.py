"""v2.5 C3 localisation fixes (G-D032 c2 Neuro N1-N3): raster-legible stipple at the default dpi,
zeros masked not thresholded, medial-wall shrinkage disclosed in peak tables."""
from __future__ import annotations

import matplotlib
import numpy as np
import pytest
from matplotlib.colors import to_rgb

from tests._atlas import NV, load_or_skip, synthetic_atlases
from yct.config import load_config
from yct.features import atlas as atl
from yct.interpret import localize as loc


@pytest.fixture(autouse=True)
def _agg():
    matplotlib.use("Agg")


def _std(at, m):
    return loc.video_map(np.asarray(m, float)[None, :], at.medial_wall, 0, 1)


def _rgb(path):
    import matplotlib.image as mpimg

    return np.asarray(mpimg.imread(path), float)[..., :3]


@pytest.mark.atlas
def test_stipple_is_legible_in_the_raster_at_default_dpi(tmp_path):
    """Render at the DEFAULT dpi; pixels that change when vertices are marked unreliable must be the
    two pattern colours (>= 50%), both present, high contrast, chromatic (not medial-wall grey); the
    same pixels in the reliable render carry no pattern colour."""
    lc = load_config()["localize"]
    assert lc["dpi"] >= 150
    at = load_or_skip(atl.load_all)
    m = _std(at, np.random.default_rng(0).normal(0, 1, NV))
    ids = [at.schaefer.names.index(f"7Networks_LH_Vis_{i}") for i in range(1, 11)]
    unrel = np.isin(at.schaefer.labels, ids)
    a = _rgb(loc.plot_four_views(m, tmp_path / "unrel.png", medial_wall=at.medial_wall, unreliable=unrel))
    b = _rgb(loc.plot_four_views(m, tmp_path / "rel.png", medial_wall=at.medial_wall,
                                    unreliable=None))
    assert a.shape == b.shape
    legend_rows = slice(int(0.06 * a.shape[0]), a.shape[0])           # ignore the legend swatch row
    changed = np.zeros(a.shape[:2], bool)
    changed[legend_rows] = (np.abs(a - b).max(axis=-1) > 0.08)[legend_rows]
    assert changed.sum() >= 3000                                      # the unreliable patch is visible
    pa, pb = a[changed], b[changed]
    cols = [np.array(to_rgb(c)) for c in lc["unreliable_pattern"]]
    near = [np.abs(pa - c).max(axis=1) < 0.15 for c in cols]
    is_pat = near[0] | near[1]
    assert is_pat.mean() >= 0.5
    assert min(near[0].mean(), near[1].mean()) >= 0.15                # a pattern, not a solid fill
    lum = pa @ np.array([0.2126, 0.7152, 0.0722])
    assert lum.std() >= 0.12                                          # contrast survives rasterising
    chroma = pa.max(axis=1) - pa.min(axis=1)
    assert (chroma < 0.15).mean() <= 0.2                              # not a grey (medial wall / zero)
    near_b = [np.abs(pb - c).max(axis=1) < 0.15 for c in cols]
    assert (near_b[0] | near_b[1]).mean() <= 0.02                     # reliable render: no pattern


def test_exact_zero_is_coloured_not_hidden_like_medial_wall():
    at = synthetic_atlases()
    m = _std(at, np.random.default_rng(1).normal(0, 1, NV))
    zero = at.schaefer.labels == 3                                    # LH block set to exactly 0
    m[zero] = 0.0
    from nilearn import datasets

    faces = np.asarray(datasets.load_fsaverage("fsaverage5")["inflated"].parts["left"].faces)
    zf = zero[:10242][faces].all(axis=1)
    assert zf.sum() >= 5
    fa = loc.render_four_views(m, medial_wall=at.medial_wall, views=["lateral"])
    ca = np.asarray(fa.axes[0].collections[0]._facecolor3d)[zf]
    fb = loc.render_four_views(m, medial_wall=at.medial_wall | zero, views=["lateral"])
    cb = np.asarray(fb.axes[0].collections[0]._facecolor3d)[zf]
    centre = np.array(matplotlib.colormaps["RdBu_r"](0.5))
    np.testing.assert_allclose(ca, np.tile(centre, (len(ca), 1)), atol=1e-6)
    assert np.abs(ca - cb).max(axis=1).min() > 0.01                   # every zero face differs from masked
    matplotlib.pyplot.close(fa)
    matplotlib.pyplot.close(fb)


@pytest.mark.atlas
def test_medial_wall_shrinkage_disclosed_in_peak_table():
    at = load_or_skip(atl.load_all)
    lc = load_config()["localize"]
    raw, post, frac = atl.medial_wall_shrinkage(at)
    flagged = [at.schaefer.names[i] for i in np.flatnonzero(frac > lc["mw_shrink_flag_frac"])]
    assert sorted(flagged) == sorted(lc["mw_shrunk_parcels"]) and len(flagged) == 7
    pid = at.schaefer.names.index("7Networks_RH_Default_PFCdPFCm_6")
    assert (raw[pid], post[pid]) == (37, 14)
    m = np.random.default_rng(0).normal(0, 0.1, NV)
    m[at.schaefer.labels == pid] += 3.0
    t = loc.peak_table(_std(at, m), at, k=5)
    top = t.iloc[0]
    assert top.parcel_id == pid and top.n_vertices == 14 and bool(top.mw_shrunk)
    assert top.mw_removed_frac == pytest.approx(23 / 37)
    assert not t[t.parcel_id != pid].mw_shrunk.any() or set(t[t.mw_shrunk].parcel) <= set(flagged)
    assert "mw_removed_frac" in t.attrs and {"n_vertices", "mw_removed_frac", "mw_shrunk"} <= set(t.columns)


def test_synthetic_set_without_raw_reports_zero_shrinkage():
    at = synthetic_atlases()
    t = loc.peak_table(_std(at, np.random.default_rng(0).normal(0, 1, NV)), at, unreliable=None, k=2)
    assert (t.mw_removed_frac == 0).all() and (t.n_vertices > 0).all() and not t.mw_shrunk.any()
