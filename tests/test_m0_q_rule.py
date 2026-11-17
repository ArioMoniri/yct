"""Q(M0) rule D-037 (v2.5 C3): all linear M0, forced speech quadratics, fixed-order quadratics to
numerical rank floor(N/3) (SVD, rcond 1e-8), pre-registered label-free merge list, never PCA; P5b
"dropped term drives M1 and y" FPR simulation."""
from __future__ import annotations

import inspect
import logging

import numpy as np
import pandas as pd
import pytest

from yct.config import load_config, with_overrides
from yct.features import h4_null_sim as sim
from yct.features import m0 as m0m

FORCED_Q = ["speech_rate_wps^2", "speech_frac^2", "speech_rate_wps*speech_frac"]


def _m0(n, seed=0, voiced_varies=True, n_era=3):
    rng = np.random.default_rng(seed)
    df, era = sim.synthetic_m0(n, rng, n_era=n_era)
    if not voiced_varies:
        df[m0m.VOICED] = 1.0
    return df, era


def _in_span(q, v, tol=1e-8):
    beta, *_ = np.linalg.lstsq(q, v, rcond=None)
    return np.linalg.norm(v - q @ beta) <= tol * max(1.0, np.linalg.norm(v))


def test_config_rule_and_merge_list_valid():
    mc = load_config()["m0"]
    assert mc["q_rule"] == "D-037"
    assert "k_q" not in mc and "forced_kq" not in mc                  # D-034 1/VIF K_Q withdrawn
    assert mc["rank_rcond"] == pytest.approx(1e-8) and mc["max_cond"] == pytest.approx(1e8)
    steps = m0m.merge_list()
    assert [s["name"] for s in steps] == ["photometric_crop", "visual_change", "voice_acoustics"]
    members = [m for s in steps for m in s["members"]]
    assert len(members) == len(set(members))
    assert not set(members) & {"speech_rate_wps", "speech_frac", "face_area_crop_frac", m0m.VOICED}
    assert all(s["why"] for s in steps)
    bad = with_overrides(load_config(), {"m0": {"merge_list": [
        {"name": "x", "members": ["speech_frac", "rms_db"], "why": "no"}]}})
    with pytest.raises(ValueError, match="forced speech"):
        m0m.merge_list(bad)
    bad2 = with_overrides(load_config(), {"m0": {"merge_list": [
        {"name": "x", "members": ["pitch_sd_hz", "pitch_mean_hz"], "why": "not in M0"}]}})
    with pytest.raises(ValueError, match="not in m0.features"):
        m0m.merge_list(bad2)


def test_q_m0_is_label_free_and_has_no_pca():
    params = set(inspect.signature(m0m.q_m0).parameters)
    assert params == {"m0", "binary", "era", "cfg"}                  # no outcome / label argument
    src = inspect.getsource(m0m.q_m0) + inspect.getsource(m0m.optional_term_order)
    assert "pca" not in src.lower().replace("no pca", "").replace("never pca", "")


DIMS = [  # N, limit, merges, optional, rank   (9 continuous M0 + voiced_any + 3 eras; generic data)
    (40, 13, 3, 0, 13),
    (60, 20, 0, 4, 20),
    (80, 26, 0, 10, 26),
]


@pytest.mark.parametrize("n,limit,merges,optional,rank", DIMS)
def test_q_dimensions_n40_60_80(n, limit, merges, optional, rank):
    m0, era = _m0(n, seed=n)
    plan = m0m.q_m0(m0, era=era)
    assert plan.limit == limit == n // 3
    assert len(plan.merges) == merges and len(plan.optional) == optional and plan.rank == rank
    assert plan.q.shape == (n, rank) and plan.aliased == []
    tab = m0m.q_dimension_table((n,)).iloc[0]
    assert (tab.limit, tab.merges, tab.optional, tab["rank"]) == (limit, merges, optional, rank)


def test_q_dimensions_voiced_constant_is_aliased_not_counted(caplog):
    m0, era = _m0(40, seed=3, voiced_varies=False)
    with caplog.at_level(logging.WARNING, logger="yct.features.m0"):
        plan = m0m.q_m0(m0, era=era)
    assert m0m.VOICED in plan.aliased and "aliased" in caplog.text
    assert plan.merges == ["photometric_crop", "visual_change"] and plan.rank == 13
    tab = m0m.q_dimension_table((40, 60, 80), voiced_varies=False)
    assert tab.merges.tolist() == [2, 0, 0] and tab.optional.tolist() == [0, 5, 11]


@pytest.mark.parametrize("n", [40, 60, 80])
def test_all_linear_and_forced_terms_always_in_q(n):
    m0, era = _m0(n, seed=10 + n)
    plan = m0m.q_m0(m0, era=era)
    for t in FORCED_Q:
        assert t in plan.columns
    for c in ["1", "speech_rate_wps", "speech_frac", m0m.VOICED, "era=E2", "era=E3", "face_area_crop_frac"]:
        assert c in plan.columns
    merged = {m for s in m0m.merge_list() if s["name"] in plan.merges for m in s["members"]}
    for c in m0m.m0_feature_list():                                   # every linear M0 term is in span(Q)
        if c not in merged:
            assert _in_span(plan.q, m0m.zscore(m0[[c]].to_numpy())[:, 0]), c
    for s in m0m.merge_list():
        if s["name"] in plan.merges:
            comp = m0m.zscore(m0[s["members"]].to_numpy()).mean(axis=1)
            assert _in_span(plan.q, comp)
    sr, sf = (m0m.zscore(m0[[c]].to_numpy())[:, 0] for c in ("speech_rate_wps", "speech_frac"))
    for v in (sr ** 2, sf ** 2, sr * sf):
        assert _in_span(plan.q, v)


def test_optional_terms_follow_fixed_label_free_order():
    m0, era = _m0(80, seed=5)
    plan = m0m.q_m0(m0, era=era)
    z = pd.DataFrame(m0m.zscore(m0[m0m.m0_feature_list()].to_numpy()), columns=m0m.m0_feature_list())
    sq = [c for c in plan.candidates if c.endswith("^2")]
    v = [np.var(z[c.removesuffix("^2")] ** 2) for c in sq]
    assert v == sorted(v, reverse=True) and len(sq) == 7
    first_prod = plan.candidates.index(next(c for c in plan.candidates if "*" in c))
    assert all(c.endswith("^2") for c in plan.candidates[:first_prod])
    assert "speech_rate_wps*speech_frac" not in plan.candidates      # forced, not optional
    assert plan.optional == plan.candidates[: len(plan.optional)]
    assert plan.excluded_terms == plan.candidates[len(plan.optional):]
    perm = np.random.default_rng(0).permutation(len(m0))              # row order does not matter
    plan2 = m0m.q_m0(m0.iloc[perm].reset_index(drop=True), era=era.iloc[perm].reset_index(drop=True))
    assert plan2.columns == plan.columns
    np.testing.assert_allclose(plan2.q, plan.q[perm], atol=1e-10)


def test_rank_is_numerical_svd_with_rcond_and_cond_checked(caplog):
    m0, era = _m0(60, seed=7)
    plan = m0m.q_m0(m0, era=era)
    s = np.linalg.svd(plan.q, compute_uv=False)
    assert plan.rank == int((s > 1e-8 * s[0]).sum()) == plan.q.shape[1]
    assert plan.cond == pytest.approx(s[0] / s[-1]) and plan.cond <= 1e8
    # Biostat c2 B4: rms_db = speech_frac + 1e-9 noise passed numpy's default tolerance; now aliased
    near = m0.copy()
    near["rms_db"] = near["speech_frac"] + 1e-9 * np.random.default_rng(1).normal(size=len(near))
    with caplog.at_level(logging.WARNING, logger="yct.features.m0"):
        p2 = m0m.q_m0(near, era=era)
    assert "rms_db" in p2.aliased and "speech_frac" in p2.columns and "speech_rate_wps" in p2.columns
    assert np.linalg.cond(p2.q) <= 1e8
    assert m0m.numerical_rank(np.column_stack([near["rms_db"], near["speech_frac"]]) - 0.5) == 1
    tight = with_overrides(load_config(), {"m0": {"max_cond": 10.0}})
    with pytest.raises(ValueError, match="cond"):
        m0m.q_m0(m0, era=era, cfg=tight)


def test_merge_list_exhausted_and_nonfinite_fail_hard():
    m0, era = _m0(36, seed=2)                                          # floor(36/3) = 12 < 13 after merges
    with pytest.raises(ValueError, match="merge list"):
        m0m.q_m0(m0, era=era)
    with pytest.raises(ValueError, match="merge list"):
        m0m.q_dimension_table((36,))
    bad = _m0(60)[0]
    bad.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        m0m.q_m0(bad, era=_m0(60)[1])


def test_merges_are_composites_of_z_scores_in_order():
    m0, era = _m0(40, seed=40)
    plan = m0m.q_m0(m0, era=era)
    used = plan.m0_used
    assert list(used.columns[:4]) == ["voice_acoustics", "speech_frac", "speech_rate_wps", "photometric_crop"]
    np.testing.assert_allclose(used["photometric_crop"],
                               m0m.zscore(m0[["luminance_crop", "contrast_crop"]].to_numpy()).mean(1))
    assert "luminance_crop" not in used and "scene_cuts" not in used


def test_residualize_removes_q_span():
    m0, era = _m0(60, seed=8)
    plan = m0m.q_m0(m0, era=era)
    m1 = np.random.default_rng(0).normal(size=(60, 7)) + plan.q[:, :7]
    r = m0m.residualize(m1, plan.q)
    np.testing.assert_allclose(plan.q.T @ r, 0.0, atol=1e-8)


# ----------------------------------------------------------------------------- P5b FPR simulation

def test_p5b_dropped_term_inflates_size_and_included_term_is_nominal():
    """Fast version (small B): a term outside Q that drives M1 and y inflates the H4 size; inside Q it
    does not (Biostat G-D032 c2 B3). The P5b run uses 500 replicates x B = 500 at the final N and Q."""
    out = sim.simulate_h4_null(60, "dropped_term", n_reps=30, n_perm=19, seed=1)
    inc = sim.simulate_h4_null(60, "included_term", n_reps=30, n_perm=19, seed=1)
    assert not out.term_in_q and out.term not in out.q_columns and out.term.endswith("^2")
    assert inc.term_in_q and inc.term in inc.q_columns
    assert len(out.p_values) == 30 and out.p_values.min() >= 1 / 20
    assert out.fpr >= 0.3                                             # size outside the span: inflated
    assert inc.fpr <= 0.15                                            # inside the span: nominal-ish
    assert out.fpr > inc.fpr + 0.2


def test_p5b_sim_at_n40_uses_merged_q():
    out = sim.simulate_h4_null(40, "dropped_term", n_reps=2, n_perm=4, seed=3)
    assert out.term == "photometric_crop^2" and not out.term_in_q
    inc = sim.simulate_h4_null(40, "included_term", n_reps=2, n_perm=4, seed=3)
    assert inc.term == "speech_rate_wps^2" and inc.term_in_q
