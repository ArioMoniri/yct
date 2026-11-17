"""P4b controls config (v2.5 C3; D-039; G-D032 c2 Neuro N5, Phase-0 Referee/Neuro): exact HCP-MMP ROI
lists resolve to the expected non-empty vertex sets on the cached, union-masked atlas."""
from __future__ import annotations

import numpy as np
import pytest

from tests._atlas import load_or_skip
from yct.config import load_config
from yct.confounds import FEATURES
from yct.features import atlas as atl

CTRL = load_config()["controls"]


def roi_mask(at, spec):
    names = [f"{h}_{a}_ROI" for h in spec["hemis"] for a in spec["areas"]]
    missing = [n for n in names if n not in at.hcp.names]
    assert not missing, missing
    return np.isin(at.hcp.labels, [at.hcp.names.index(n) for n in names])


def test_controls_config_shape():
    assert set(CTRL["rois"]) == {"FFC", "PH", "AUD", "V1_V3", "MT_plus"}
    assert CTRL["rois"]["AUD"]["areas"] == ["A4", "A5"]
    assert CTRL["rois"]["V1_V3"]["areas"] == ["V1", "V2", "V3"]
    assert CTRL["readout_lag_tr"] == [0, 3]
    assert CTRL["kernel"]["shift_by_L"] is False and CTRL["kernel"]["min_reference_clips"] >= 5
    assert CTRL["aud_selectivity_run"] == "audio_only"
    assert CTRL["dry_run"]["talking_face_clip"] is True
    assert "luminance_change" in CTRL["partial_out"] and set(CTRL["partial_out"]) == set(CTRL["regressors"])
    for name, r in CTRL["regressors"].items():
        assert r["roi"] in CTRL["rois"], name
        if r["source"] == "confounds":
            assert r["column"] in FEATURES, name
        else:
            assert r["source"] == "derived" and r["from"] and r["op"], name
    assert CTRL["regressors"]["face"]["column"] == load_config()["confounds"]["ffc_regressor"]


@pytest.mark.atlas
@pytest.mark.parametrize("roi", sorted(CTRL["rois"]))
def test_control_rois_resolve_on_cached_atlas(roi):
    at = load_or_skip(atl.load_all)
    spec = CTRL["rois"][roi]
    m = roi_mask(at, spec)
    assert m.sum() == spec["n_vertices"] > 0
    assert not (m & at.medial_wall).any()
    nh = len(m) // 2
    assert m[:nh].any() and m[nh:].any()                              # bilateral


@pytest.mark.atlas
def test_control_rois_disjoint():
    at = load_or_skip(atl.load_all)
    masks = {r: roi_mask(at, s) for r, s in CTRL["rois"].items()}
    names = sorted(masks)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not (masks[a] & masks[b]).any(), (a, b)


def test_t1_tail_margin_is_5s_d039():
    assert load_config()["window"]["min_tail_s"] == 5
