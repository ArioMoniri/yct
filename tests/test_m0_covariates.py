"""D-047 metadata covariates in M0 (P1 c2 Biostat #5/N1, Referee D3/B3; G-D032 c3 Referee N1/N2; D-053).

* `platform_nonYT` is a FORCED linear (binary) M0 covariate: always in the primary Q(M0).
* `upload_lag_days` (+ `lag_unknown`) may be outcome-caused (post-decision uploads), so it is a
  SENSITIVITY-only covariate (S-LAG), never forced into the primary Q(M0); UNKNOWN lag -> label-free
  median over the analysis set + `lag_unknown` = 1. A pre-decision-upload-only sensitivity uses lag <= 0.
* The Q dimension table reads the era levels (2 blocks, E12/E3) and the covariates from config and is
  frozen here at N = 46/50/53/56.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.test_m0 import LEN, START, _dataset
from yct.config import load_config
from yct.features import h4_null_sim as sim
from yct.features import m0 as m0m

COV = load_config()["m0"]["covariates"]


def _meta(index, seed=0, frac_unknown=0.3, frac_nonyt=0.15):
    rng = np.random.default_rng(seed)
    n = len(index)
    lag = rng.integers(-400, 900, n).astype(str).astype(object)
    lag[rng.uniform(size=n) < frac_unknown] = ""
    plat = np.where(rng.uniform(size=n) < frac_nonyt, "True", "False")
    plat[0], plat[1] = "True", "False"                                # both levels present
    return pd.DataFrame({"platform_nonYT": plat, "upload_lag_days": lag}, index=index)


def _m0(n, seed, sensitivity=False):
    rng = np.random.default_rng(seed)
    df, era = sim.synthetic_m0(n, rng, n_era=2)
    meta = _meta(df.index, seed)
    cov, _ = m0m.metadata_covariates(meta, sensitivity=sensitivity)
    return pd.concat([df, cov], axis=1), era


def test_config_covariates():
    assert COV["forced"] == ["platform_nonYT"]
    assert COV["sensitivity"] == ["upload_lag_days", "lag_unknown"]
    assert "upload_lag_days" not in COV["forced"]                     # Referee N2: never forced (D-053)
    assert set(COV["binary"]) == {"platform_nonYT", "lag_unknown"}
    assert COV["linear_only"] == ["upload_lag_days"]
    assert COV["lag_impute"] == "median" and COV["predecision_max_lag_days"] == 0


def test_metadata_covariates_rules():
    idx = pd.Index([f"v{i}" for i in range(6)])
    meta = pd.DataFrame({"platform_nonYT": ["True", "False", "False", "True", "False", "False"],
                         "upload_lag_days": ["10", "", "-5", "30", "", "100"]}, index=idx)
    prim, rep = m0m.metadata_covariates(meta)
    assert list(prim.columns) == ["platform_nonYT"]
    assert prim["platform_nonYT"].tolist() == [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    sens, rep = m0m.metadata_covariates(meta, sensitivity=True)
    assert list(sens.columns) == ["platform_nonYT", "upload_lag_days", "lag_unknown"]
    assert sens["lag_unknown"].tolist() == [0.0, 1.0, 0.0, 0.0, 1.0, 0.0]
    med = float(np.median([10, -5, 30, 100]))
    assert sens.loc["v1", "upload_lag_days"] == med == sens.loc["v4", "upload_lag_days"]
    assert sens.loc["v2", "upload_lag_days"] == -5.0
    assert rep["lag_median"] == med and rep["n_lag_unknown"] == 2
    with pytest.raises(ValueError, match="platform_nonYT"):
        m0m.metadata_covariates(meta.assign(platform_nonYT=["True", "x", "False", "True", "False", "False"]))
    with pytest.raises(ValueError, match="no known"):
        m0m.metadata_covariates(meta.assign(upload_lag_days=[""] * 6), sensitivity=True)


def test_predecision_subset_rule():
    meta = pd.DataFrame({"upload_lag_days": ["10", "", "-5", "0", "x"]}, index=list("abcde"))
    with pytest.raises(ValueError):
        m0m.predecision_ids(meta)
    meta.loc["e", "upload_lag_days"] = "-1"
    assert m0m.predecision_ids(meta) == ["c", "d", "e"]               # known lag <= 0 only; unknown excluded


def test_h4_m0_requires_forced_covariates_and_joins_them():
    per_tr, has_audio = _dataset(n=60)
    vids = sorted(per_tr["video_id"].unique())
    meta = _meta(pd.Index(vids), seed=3)
    res = m0m.h4_m0(per_tr, START, LEN, has_audio, meta)
    assert "platform_nonYT" in res.m0.columns and "upload_lag_days" not in res.m0.columns
    assert res.binary == [m0m.VOICED, "platform_nonYT"]
    assert np.isfinite(res.m0.to_numpy()).all()
    sens = m0m.h4_m0(per_tr, START, LEN, has_audio, meta, sensitivity=True)
    assert {"upload_lag_days", "lag_unknown"} <= set(sens.m0.columns)
    assert sens.binary == [m0m.VOICED, "platform_nonYT", "lag_unknown"]
    with pytest.raises(ValueError, match="platform_nonYT"):
        m0m.h4_m0(per_tr, START, LEN, has_audio, meta.drop(columns=["platform_nonYT"]))
    with pytest.raises(KeyError, match="metadata"):
        m0m.h4_m0(per_tr, START, LEN, has_audio, meta.iloc[:10])


def test_covariates_linear_only_in_q():
    m0, era = _m0(80, seed=4, sensitivity=True)
    plan = m0m.q_m0(m0, era=era)
    for c in ("platform_nonYT", "upload_lag_days", "lag_unknown"):
        assert c in plan.columns
        assert not any(c in t for t in plan.candidates), c            # never squared or in a product
    assert "era=E2" in plan.columns and not any(c.startswith("era=") and c != "era=E2" for c in plan.columns)


# N, limit, required, merges, optional, rank  (9 continuous + voiced_any + 2 era blocks + platform_nonYT)
PRIMARY_DIMS = [(46, 15, 16, 1, 0, 15), (50, 16, 16, 0, 0, 16), (53, 17, 16, 0, 1, 17),
                (56, 18, 16, 0, 2, 18)]
# + S-LAG covariates (upload_lag_days, lag_unknown)
LAG_DIMS = [(46, 15, 18, 3, 0, 15), (50, 16, 18, 2, 0, 16), (53, 17, 18, 1, 0, 17), (56, 18, 18, 0, 0, 18)]


@pytest.mark.parametrize("n,limit,required,merges,optional,rank", PRIMARY_DIMS)
def test_primary_q_dimensions_frozen(n, limit, required, merges, optional, rank):
    tab = m0m.q_dimension_table((n,)).iloc[0]
    assert (tab.limit, tab.required, tab.merges, tab.optional, tab["rank"]) == \
        (limit, required, merges, optional, rank)
    m0, era = _m0(n, seed=100 + n)
    plan = m0m.q_m0(m0, era=era)
    assert plan.limit == limit and len(plan.merges) == merges and len(plan.optional) == optional
    assert plan.rank == rank and plan.aliased == [] and "platform_nonYT" in plan.columns


@pytest.mark.parametrize("n,limit,required,merges,optional,rank", LAG_DIMS)
def test_lag_sensitivity_q_dimensions_frozen(n, limit, required, merges, optional, rank):
    tab = m0m.q_dimension_table((n,), sensitivity=True).iloc[0]
    assert (tab.limit, tab.required, tab.merges, tab.optional, tab["rank"]) == \
        (limit, required, merges, optional, rank)
    m0, era = _m0(n, seed=200 + n, sensitivity=True)
    plan = m0m.q_m0(m0, era=era)
    assert plan.limit == limit and len(plan.merges) == merges and plan.rank == rank


def test_dimension_table_reads_era_levels_from_config():
    eb = load_config()["era_blocks"]["merge"]
    assert len(eb) == 2
    a = m0m.q_dimension_table((53,)).iloc[0]
    b = m0m.q_dimension_table((53,), n_era_levels=len(eb), n_covariates=len(COV["forced"])).iloc[0]
    assert a.equals(b)
    legacy = m0m.q_dimension_table((53,), n_era_levels=3, n_covariates=0).iloc[0]
    assert legacy.required == 16 and legacy.optional == 1             # same count, different composition
