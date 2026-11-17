"""Activation localisation outputs (v2.md §1 v2.3, D-032): peak table + four-view surface maps."""
from __future__ import annotations

import matplotlib
import numpy as np
import pytest

from tests._atlas import NV, load_or_skip, synthetic_atlases
from yct.features import atlas as atl
from yct.interpret import localize as loc


@pytest.fixture(autouse=True)
def _agg():
    matplotlib.use("Agg")

COLS = ["sign", "rank", "parcel_id", "parcel", "hemi", "yeo7", "hcp_mmp", "hcp_overlap", "hcp_mmp_2nd",
        "hcp_overlap_2nd", "destrieux", "value", "ci_lo", "ci_hi", "stability_topk", "p_perm", "q_bh",
        "unreliable_frac"]


def _planted(at, pid, neg_pid=None, seed=0, amp=3.0, noise=0.1):
    """A spatially standardised map (union medial wall NaN, cortex centred) with planted parcels."""
    rng = np.random.default_rng(seed)
    m = rng.normal(0, noise, NV)
    m[at.schaefer.labels == pid] += amp
    if neg_pid is not None:
        m[at.schaefer.labels == neg_pid] -= amp
    return loc.video_map(m[None, :], at.medial_wall, 0, 1)


def test_peak_table_synthetic():
    at = synthetic_atlases()
    maps = np.stack([_planted(at, 5, 20, seed=s) for s in range(1, 41)])
    m = maps.mean(axis=0)
    pv = loc.parcel_values(maps, at.schaefer)
    boot = loc.company_bootstrap(pv, None, np.arange(40), n_boot=400, seed=1)
    t = loc.peak_table(m, at, boot=boot, k=3)
    assert list(t.columns) == COLS
    assert len(t) == 6
    top = t[(t.sign == "pos") & (t["rank"] == 1)].iloc[0]
    assert top.parcel_id == 5 and top.parcel == at.schaefer.names[5]
    assert top.hemi == "LH" and top.yeo7 == "DorsAttn"
    assert top.hcp_mmp == "X_3_ROI" and top.hcp_overlap == pytest.approx(1.0)
    assert top.destrieux == "G_b"
    assert top.ci_lo < top.value < top.ci_hi
    bot = t[(t.sign == "neg") & (t["rank"] == 1)].iloc[0]
    assert bot.parcel_id == 20 and bot.hemi == "RH" and bot.value < 0
    assert t[t.sign == "neg"].value.is_monotonic_increasing


def test_peak_table_without_bootstrap_and_shape_check():
    at = synthetic_atlases()
    t = loc.peak_table(_planted(at, 2), at, k=2)
    assert t.ci_lo.isna().all() and t.stability_topk.isna().all()
    with pytest.raises(ValueError):
        loc.peak_table(np.zeros(100), at)


def test_plot_four_views_synthetic(tmp_path):
    at = synthetic_atlases()
    m = _planted(at, 5, 20)
    rel = np.zeros(NV, bool)
    rel[at.schaefer.labels == 7] = True
    out = loc.plot_four_views(m, tmp_path / "map.png", medial_wall=at.medial_wall,
                            unreliable=rel, title="synthetic")
    assert out.exists() and out.stat().st_size > 10_000


@pytest.mark.atlas
def test_peak_table_real_atlases_planted():
    at = load_or_skip(atl.load_all)
    pid = at.schaefer.names.index("7Networks_LH_Vis_3")
    neg = at.schaefer.names.index("7Networks_RH_Default_Par_1")
    m = _planted(at, pid, neg)
    t = loc.peak_table(m, at, k=20)
    assert len(t) == 40
    top = t.iloc[0]
    assert top.sign == "pos" and top.parcel_id == pid and top.yeo7 == "Vis" and top.hemi == "LH"
    vox = at.schaefer.labels == pid
    hcp_ids, cnt = np.unique(at.hcp.labels[vox & (at.hcp.labels > 0)], return_counts=True)
    assert top.hcp_mmp == at.hcp.names[hcp_ids[cnt.argmax()]] and top.hcp_mmp.startswith("L_")
    assert top.destrieux.startswith("L ")
    b = t[t.sign == "neg"].iloc[0]
    assert b.parcel_id == neg and b.yeo7 == "Default" and b.hcp_mmp.startswith("R_")
    assert b.destrieux.startswith("R ")


@pytest.mark.atlas
def test_plot_four_views_real(tmp_path):
    at = load_or_skip(atl.load_all)
    m = _planted(at, 3, 250)
    out = loc.plot_four_views(m, tmp_path / "real.png", medial_wall=at.medial_wall)
    assert out.stat().st_size > 10_000
