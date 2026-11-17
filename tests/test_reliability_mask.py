"""Unreliable-vertex mask source (G-D032 c3 Neuro G2; DECISIONS D-053): config `localize.reliability_mask`
fixes source, rule, areas, vertex count and hash; it resolves to a non-empty bilateral vertex set on the
cached atlas, and it is what the peak tables and four-view maps use by default."""
from __future__ import annotations

import hashlib

import matplotlib
import numpy as np
import pytest

from tests._atlas import NV, load_or_skip, synthetic_atlases
from yct.config import load_config, with_overrides
from yct.features import atlas as atl
from yct.interpret import localize as loc

RM = load_config()["localize"]["reliability_mask"]


@pytest.fixture(autouse=True)
def _agg():
    matplotlib.use("Agg")


def _std(at, m):
    return loc.video_map(np.asarray(m, float)[None, :], at.medial_wall, 0, 1)


def test_config_key_is_set_with_source_rule_and_hash():
    assert RM["source"] and RM["rule"] and RM["atlas"] == "hcp_mmp1"
    assert RM["areas"] and set(RM["hemis"]) == {"L", "R"}
    assert RM["n_vertices"] > 0 and len(RM["sha256"]) == 64
    h2 = {"STSva", "STSvp", "STSdp", "PGi", "45", "44", "TE1a"}               # never masks the H2 composite
    ctrl = {a for r in load_config()["controls"]["rois"].values() for a in r["areas"]}
    assert not set(RM["areas"]) & (h2 | ctrl)


@pytest.mark.atlas
def test_mask_resolves_to_non_empty_bilateral_set_matching_count_and_hash():
    at = load_or_skip(atl.load_all)
    m = loc.reliability_mask(at)
    assert m.shape == (NV,) and m.dtype == bool
    assert m.sum() == RM["n_vertices"] > 0
    assert m[:NV // 2].any() and m[NV // 2:].any()
    assert not (m & at.medial_wall).any()
    ids = np.flatnonzero(m).astype("<i4")
    assert hashlib.sha256(ids.tobytes()).hexdigest() == RM["sha256"]
    names = [f"{h}_{a}_ROI" for h in RM["hemis"] for a in RM["areas"]]
    ref = np.isin(at.hcp.labels, [at.hcp.names.index(n) for n in names]) & ~at.medial_wall
    np.testing.assert_array_equal(m, ref)                                      # independent resolution


@pytest.mark.atlas
def test_mask_fails_on_drift():
    at = load_or_skip(atl.load_all)
    drift = with_overrides(load_config(),
                           {"localize": {"reliability_mask": {"n_vertices": RM["n_vertices"] + 1}}})
    with pytest.raises(ValueError, match="n_vertices"):
        loc.reliability_mask(at, drift)
    bad_hash = with_overrides(load_config(), {"localize": {"reliability_mask": {"sha256": "0" * 64}}})
    with pytest.raises(ValueError, match="sha256"):
        loc.reliability_mask(at, bad_hash)
    with pytest.raises(ValueError, match="not in"):
        loc.reliability_mask(synthetic_atlases())                 # areas absent -> no silent empty


@pytest.mark.atlas
def test_peak_table_uses_config_mask_by_default():
    at = load_or_skip(atl.load_all)
    m = _std(at, np.random.default_rng(0).normal(0, 1, NV))
    mask = loc.reliability_mask(at)
    default = loc.peak_table(m, at, k=20)
    explicit = loc.peak_table(m, at, unreliable=mask, k=20)
    none = loc.peak_table(m, at, unreliable=None, k=20)
    assert default.equals(explicit)
    assert default.attrs["n_excluded_unreliable"] == explicit.attrs["n_excluded_unreliable"] > 0
    assert none.attrs["n_excluded_unreliable"] == 0
    assert default.attrs["unreliable_mask"].startswith(RM["source"]) and RM["sha256"][:12] in \
        default.attrs["unreliable_mask"]
    assert none.attrs["unreliable_mask"] == "none (explicit)"
    ofc = at.schaefer.names.index("7Networks_LH_Limbic_OFC_1")
    assert ofc not in set(default.parcel_id)


@pytest.mark.atlas
def test_four_view_map_uses_config_mask_by_default():
    at = load_or_skip(atl.load_all)
    m = _std(at, np.random.default_rng(1).normal(0, 1, NV))
    fa = loc.render_four_views(m, medial_wall=at.medial_wall, views=["ventral"])
    fb = loc.render_four_views(m, medial_wall=at.medial_wall, unreliable=loc.reliability_mask(at),
                               views=["ventral"])
    fc = loc.render_four_views(m, medial_wall=at.medial_wall, unreliable=None, views=["ventral"])
    ca, cb, cc = (np.asarray(f.axes[0].collections[0]._facecolor3d) for f in (fa, fb, fc))
    np.testing.assert_allclose(ca, cb)
    assert np.abs(ca - cc).max() > 0.1                                         # stipple present by default
    assert any("unreliable" in t.get_label() for t in fa.legends[0].get_patches())
    for f in (fa, fb, fc):
        matplotlib.pyplot.close(f)
