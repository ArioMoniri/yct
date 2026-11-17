"""Union medial wall (v2.4 G-D032, D-034): Schaefer 0 | HCP ??? | Destrieux Medial_wall, one mask everywhere."""
from __future__ import annotations

import numpy as np
import pytest

from tests._atlas import NH, NV, load_or_skip, synthetic_atlases
from yct.features import atlas as atl
from yct.features import networks as net


def test_apply_mask_renumbers_and_drops():
    a = atl.Atlas("x", np.array([0, 1, 2, 3, 3, 2]), ("bg", "a", "MW", "b"))
    mask = np.array([False, True, False, False, False, False])
    out = atl.apply_mask(a, mask, drop_names=[2])
    assert out.names == ("bg", "a", "b")
    np.testing.assert_array_equal(out.labels, [0, 0, 0, 2, 2, 0])
    with pytest.raises(ValueError):
        atl.apply_mask(a, mask, drop_names=[0])


def test_medial_wall_mask_rejects_single_atlas():
    at = synthetic_atlases()
    with pytest.raises(TypeError):
        atl.medial_wall_mask(at.schaefer)
    assert atl.medial_wall_mask(at).sum() == 1000


def test_synthetic_union_includes_every_atlas_background():
    at = synthetic_atlases()
    hcp = atl.Atlas("hcp_mmp1", at.hcp.labels.copy(), at.hcp.names)
    hcp.labels[600] = 0                                  # an extra HCP ??? vertex outside Schaefer MW
    raw = atl.AtlasSet(at.schaefer, at.yeo7, hcp, at.destrieux)
    masked = atl.mask_atlas_set(raw)
    assert raw.medial_wall[600] and raw.medial_wall.sum() == 1001
    for a in (masked.schaefer, masked.yeo7, masked.hcp, masked.destrieux):
        assert ((a.labels == a.background) == raw.medial_wall).all()


@pytest.mark.atlas
def test_union_vertex_counts_real():
    at = load_or_skip(atl.load_all)
    mw = atl.medial_wall_mask(at)
    assert mw.dtype == bool and mw.shape == (NV,)
    assert mw[:NH].sum() == 993 and mw[NH:].sum() == 987          # union, checked on cached annots
    raw_s = load_or_skip(atl.load_schaefer400)
    raw_h = load_or_skip(atl.load_hcp_mmp1)
    raw_d = load_or_skip(atl.load_destrieux)
    s0 = atl.schaefer_medial_wall(raw_s)
    h0 = raw_h.labels == 0
    dmw = np.isin(raw_d.labels, [raw_d.names.index("L Medial_wall"), raw_d.names.index("R Medial_wall")])
    assert (s0[:NH].sum(), s0[NH:].sum()) == (870, 873)
    assert (h0[:NH].sum(), h0[NH:].sum()) == (868, 874)
    assert (dmw[:NH].sum(), dmw[NH:].sum()) == (888, 881)
    np.testing.assert_array_equal(mw, s0 | h0 | dmw)
    assert (s0 != h0).sum() == 463                                # Neuro D2: the masks disagree on 463
    # every atlas in the analysis set has exactly this background
    for a in (at.schaefer, at.yeo7, at.hcp, at.destrieux):
        assert ((a.labels == a.background) == mw).all(), a.name
    # Destrieux medial wall is no longer a reportable label
    assert not any(n.endswith("Medial_wall") for n in at.destrieux.names[1:])
    assert at.destrieux.n_labels == raw_d.n_labels - 2
    assert at.schaefer.n_labels == 400 and set(np.unique(at.schaefer.labels)) == set(range(401))


@pytest.mark.atlas
def test_union_mask_used_by_m1_standardisation_real():
    at = load_or_skip(atl.load_all)
    mw = at.medial_wall
    rng = np.random.default_rng(0)
    pred = rng.normal(0, 1, (8, NV))
    z = net.spatial_standardize(pred, mw)
    assert np.isnan(z[:, mw]).all() and np.isfinite(z[:, ~mw]).all()
    assert (~mw).sum() == NV - 1980
