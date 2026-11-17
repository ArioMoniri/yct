"""Localisation firewall (v2.4 G-D032): caption, claim lint, company-cluster BCa bootstrap, stability,
BH-FDR q, unreliable handling, best-overlap HCP wording, standardised-map requirement, stippling."""
from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

from tests._atlas import NV, synthetic_atlases
from yct.config import load_config
from yct.interpret import localize as loc


@pytest.fixture(autouse=True)
def _agg():
    matplotlib.use("Agg")


def _std(at, m):
    return loc.video_map(np.asarray(m, float)[None, :], at.medial_wall, 0, 1)


def _videos(at, n=40, seed=0, effect=0.0, pid=5):
    rng = np.random.default_rng(seed)
    group = np.array(["rej", "acc"] * (n // 2))
    maps = []
    for g in group:
        m = rng.normal(0, 1, NV)
        m[at.schaefer.labels == pid] += 2.0 + (effect if g == "acc" else 0.0)
        maps.append(_std(at, m))
    return np.stack(maps), group


# ----------------------------------------------------------------------------- caption + lint

def test_caption_fixed_and_on_every_output(tmp_path):
    at = synthetic_atlases()
    cap = loc.caption()
    for phrase in ("Descriptive only", "not inferential", "not adjusted for parcel selection",
                   "no reverse inference", "spatially standardised", "averaged over W"):
        assert phrase in cap
    assert loc.lint_claims(cap) == []
    t = loc.peak_table(_std(at, np.random.default_rng(0).normal(0, 1, NV)), at, unreliable=None, k=2)
    assert t.attrs["caption"] == cap
    out = loc.write_peak_table(t, tmp_path / "peaks.csv")
    back, header = loc.read_peak_table(out)
    assert header[0] == cap and list(back.columns) == loc.COLUMNS and len(back) == len(t)
    assert any(h.startswith("hcp_label: best-overlap HCP-MMP1 area") for h in header)


def test_claim_lint_flags_banned_language():
    bad = ["Accepted founders drive more engagement.", "the video is more persuasive",
           "viewers trust the founder", "higher brain activity in PFC", "The brain prefers faces",
           "STS activates for accepted videos", "a language area response", "reward circuitry",
           "valuation signal", "theory of mind network"]
    for text in bad:
        assert loc.lint_claims(text), text
        with pytest.raises(loc.ClaimLanguageError):
            loc.assert_no_claims(text)
    ok = "Predicted relative response in the best-overlap HCP-MMP1 area; activation localisation table."
    assert loc.lint_claims(ok) == []
    loc.assert_no_claims(ok)
    assert set(load_config()["localize"]["banned_patterns"])


def test_plot_title_is_linted(tmp_path):
    at = synthetic_atlases()
    with pytest.raises(loc.ClaimLanguageError):
        loc.plot_four_views(_std(at, np.zeros(NV) + np.arange(NV) % 7), tmp_path / "x.png",
                            medial_wall=at.medial_wall, title="FFA activates")


# ----------------------------------------------------------------------------- standardised maps only

def test_peak_table_requires_standardised_map():
    at = synthetic_atlases()
    raw = np.random.default_rng(0).normal(2.0, 1.0, NV)           # not centred, no NaN medial wall
    with pytest.raises(ValueError, match="standardised|medial wall"):
        loc.peak_table(raw, at, k=2)
    shifted = _std(at, raw) + 0.5                                  # NaN wall but not centred
    with pytest.raises(ValueError, match="standardised"):
        loc.peak_table(shifted, at, k=2)


# ----------------------------------------------------------------------------- bootstrap

def test_bootstrap_maps_generator_is_company_cluster_and_stratified():
    at = synthetic_atlases()
    maps, group = _videos(at, n=8)
    company = np.array([0, 0, 1, 1, 2, 2, 3, 3])                  # each company: one rej + one acc video
    gen = loc.bootstrap_maps(maps, group, company, n_boot=5, seed=0, stat="diff", groups=("rej", "acc"))
    draws = list(gen)
    assert len(draws) == 5 and all(d.shape == (NV,) for d in draws)
    # same seed -> identical; parcel-level bootstrap = parcel means of the map bootstrap (linear)
    pv = loc.parcel_values(maps, at.schaefer)
    pb = loc.company_bootstrap(pv, group, company, n_boot=5, seed=0, stat="diff", groups=("rej", "acc"))
    np.testing.assert_allclose(pb.estimate, loc.parcel_values(maps[group == "acc"].mean(0), at.schaefer)[0]
                               - loc.parcel_values(maps[group == "rej"].mean(0), at.schaefer)[0], atol=1e-12)
    assert pb.boots.shape == (5, at.schaefer.n_labels)
    assert pb.jack.shape == (8, at.schaefer.n_labels)              # 4 companies x 2 strata
    with pytest.raises(ValueError):
        next(loc.bootstrap_maps(maps, group, company, n_boot=1, seed=0, stat="mean"))   # two groups
    with pytest.raises(ValueError):
        loc.company_bootstrap(pv, np.array(["a"] * 8), company, n_boot=2, stat="diff")


def test_bootstrap_resamples_whole_companies():
    """A company's videos always enter together: with 2 identical-company videos the bootstrap
    variance equals that of 1 video per company, not of independent videos."""
    rng = np.random.default_rng(1)
    vals = rng.normal(0, 1, (10, 3))
    company = np.arange(10)
    dup_vals = np.repeat(vals, 2, axis=0)
    dup_comp = np.repeat(company, 2)
    a = loc.company_bootstrap(vals, None, company, n_boot=4000, seed=3)
    b = loc.company_bootstrap(dup_vals, None, dup_comp, n_boot=4000, seed=3)
    np.testing.assert_allclose(a.boots, b.boots, atol=1e-12)


def test_bca_matches_reference_on_skewed_data():
    rng = np.random.default_rng(0)
    x = rng.exponential(1.0, 60)
    pb = loc.company_bootstrap(x[:, None], None, np.arange(60), n_boot=8000, seed=5)
    lo, hi = loc.bca_interval(pb.estimate, pb.boots, pb.jack, 0.95)
    from scipy.stats import bootstrap

    ref = bootstrap((x,), np.mean, n_resamples=8000, method="BCa", random_state=5).confidence_interval
    assert lo[0] == pytest.approx(ref.low, abs=0.04) and hi[0] == pytest.approx(ref.high, abs=0.06)
    assert lo[0] < x.mean() < hi[0]
    plo, phi = np.quantile(pb.boots[:, 0], [0.025, 0.975])
    assert hi[0] - phi > -0.02                                     # BCa shifts right for right skew


def test_stability_and_ci_columns():
    at = synthetic_atlases()
    maps, _ = _videos(at, n=30, seed=2)
    pv = loc.parcel_values(maps, at.schaefer)
    boot = loc.company_bootstrap(pv, None, np.arange(30), n_boot=500, seed=0)
    t = loc.peak_table(maps.mean(0), at, boot=boot, unreliable=None, k=2)
    top = t.iloc[0]
    assert top.parcel_id == 5 and top.stability_topk > 0.95
    assert top.ci_lo < top.value < top.ci_hi
    assert ((t.stability_topk >= 0) & (t.stability_topk <= 1)).all()
    assert t.attrs["ci_method"].startswith("BCa, company-cluster")
    allpos = np.random.default_rng(0).normal(0, 1, (50, 10)) + 5
    stab = loc.topk_stability(allpos, 2, "pos")
    assert stab.sum() == pytest.approx(2.0)                        # exactly k parcels in each replicate
    assert loc.topk_stability(allpos, 2, "neg").sum() == 0         # no negative parcels at all


# ----------------------------------------------------------------------------- permutation p + BH-FDR

def test_bh_fdr_known_values():
    p = np.array([0.01, 0.04, 0.03, 0.005, np.nan])
    q = loc.bh_fdr(p)
    np.testing.assert_allclose(q[:4], [0.02, 0.04, 0.04, 0.02])
    assert np.isnan(q[4])
    assert (loc.bh_fdr(np.array([0.9, 0.95])) <= 1).all()


def test_parcel_permutation_p_detects_planted_difference_and_is_uniform_under_null():
    at = synthetic_atlases()
    maps, group = _videos(at, n=40, seed=3, effect=1.5, pid=5)
    pv = loc.parcel_values(maps, at.schaefer)
    era = (np.arange(40) // 2) % 2                                 # both groups in each block
    p = loc.parcel_permutation_p(pv, group, n_perm=499, seed=0, blocks=era, groups=("rej", "acc"))
    assert p.shape == (at.schaefer.n_labels,)
    assert p[4] == pytest.approx(1 / 500)                          # parcel id 5 -> column 4
    assert ((p >= 1 / 500) & (p <= 1)).all()
    rng = np.random.default_rng(9)
    null = rng.normal(0, 1, (40, 200))
    pn = loc.parcel_permutation_p(null, group, n_perm=199, seed=1)
    assert 0.3 < pn.mean() < 0.7 and (pn < 0.05).mean() < 0.12
    confounded = np.arange(40) % 2                                 # block == group: nothing to permute
    assert (loc.parcel_permutation_p(pv, group, n_perm=19, seed=0, blocks=confounded) == 1).all()


def test_difference_table_requires_and_shows_q():
    at = synthetic_atlases()
    maps, group = _videos(at, n=20, seed=4, effect=1.0)
    pv = loc.parcel_values(maps, at.schaefer)
    diff = maps[group == "acc"].mean(0) - maps[group == "rej"].mean(0)
    with pytest.raises(ValueError, match="BH-FDR"):
        loc.peak_table(diff, at, kind="difference", unreliable=None, k=2)
    p = loc.parcel_permutation_p(pv, group, n_perm=99, seed=0, groups=("rej", "acc"))
    boot = loc.company_bootstrap(pv, group, np.arange(20), n_boot=200, stat="diff", groups=("rej", "acc"))
    t = loc.peak_table(diff, at, boot=boot, p_perm=p, kind="difference", unreliable=None, k=2)
    q = loc.bh_fdr(p)
    for _, r in t.iterrows():
        assert r.p_perm == p[r.parcel_id - 1] and r.q_bh == pytest.approx(q[r.parcel_id - 1])
    assert t.attrs["kind"] == "difference" and "BH-FDR" in t.attrs["q_bh"]
    with pytest.raises(ValueError):
        loc.peak_table(maps.mean(0), at, p_perm=p, unreliable=None, k=2)   # p only for the difference map


# ----------------------------------------------------------------------------- unreliable + HCP wording

def test_unreliable_parcels_flagged_and_not_ranked():
    at = synthetic_atlases()
    m = np.random.default_rng(0).normal(0, 0.1, NV)
    m[at.schaefer.labels == 5] += 5.0
    m[at.schaefer.labels == 6] += 3.0
    m = _std(at, m)
    unrel = at.schaefer.labels == 5
    t = loc.peak_table(m, at, unreliable=unrel, k=2)
    assert 5 not in set(t.parcel_id) and t.iloc[0].parcel_id == 6
    assert t.attrs["n_excluded_unreliable"] == 1
    part = np.zeros(NV, bool)
    part[np.flatnonzero(at.schaefer.labels == 5)[:100]] = True     # small share: kept, fraction shown
    t2 = loc.peak_table(m, at, unreliable=part, k=2)
    r = t2[t2.parcel_id == 5].iloc[0]
    assert 0 < r.unreliable_frac < 0.5


def test_best_overlap_hcp_and_second_when_weak():
    at = synthetic_atlases()
    lab = at.hcp.labels.copy()
    vox = np.flatnonzero(at.schaefer.labels == 5)
    lab[vox[: len(vox) * 2 // 5]] = 1                              # 40% X_1, 60% X_3 -> best 0.6
    lab[vox[len(vox) * 2 // 5: len(vox) * 7 // 10]] = 2            # 30% X_2 -> best X_3 at 0.3 < 0.5
    hcp = type(at.hcp)(at.hcp.name, lab, at.hcp.names)
    at2 = type(at)(at.schaefer, at.yeo7, hcp, at.destrieux)
    m = np.random.default_rng(0).normal(0, 0.1, NV)
    m[at.schaefer.labels == 5] += 3
    t = loc.peak_table(_std(at2, m), at2, unreliable=None, k=1)
    r = t.iloc[0]
    assert r.parcel_id == 5 and r.hcp_mmp == "X_1_ROI" and r.hcp_overlap == pytest.approx(0.4, abs=0.01)
    assert r.hcp_mmp_2nd in ("X_2_ROI", "X_3_ROI") and r.hcp_overlap_2nd == pytest.approx(0.3, abs=0.01)
    t1 = loc.peak_table(_std(at, m), at, unreliable=None, k=1)
    assert t1.iloc[0].hcp_mmp_2nd == "" or pd.isna(t1.iloc[0].hcp_mmp_2nd)


# ----------------------------------------------------------------------------- stippling

def test_stipple_colors_not_grey():
    faces = np.array([[0, 1, 2], [1, 2, 3], [3, 4, 5], [4, 5, 6]])
    unrel = np.array([1, 1, 1, 1, 0, 0, 0], bool)
    base = np.tile([0.97, 0.97, 0.97, 1.0], (4, 1))               # near-white "zero" colour
    pattern = load_config()["localize"]["unreliable_pattern"]
    out = loc.stipple_colors(base, faces, unrel, pattern)
    from matplotlib.colors import to_rgba

    assert {tuple(out[0]), tuple(out[1])} == {to_rgba(pattern[0]), to_rgba(pattern[1])}
    np.testing.assert_array_equal(out[2:], base[2:])
    for c in pattern:                                              # pattern colours are not greys
        r, g, b, _ = to_rgba(c)
        assert max(r, g, b) - min(r, g, b) > 0.5 or max(r, g, b) < 0.1


def test_render_four_views_stipples_unreliable_and_carries_caption():
    from matplotlib.colors import to_rgba
    from nilearn import datasets

    at = synthetic_atlases()
    m = _std(at, np.random.default_rng(0).normal(0, 1, NV))
    unrel = np.zeros(NV, bool)
    unrel[at.schaefer.labels == 3] = True                          # LH block
    fig = loc.render_four_views(m, medial_wall=at.medial_wall, unreliable=unrel, views=["lateral"])
    faces = np.asarray(datasets.load_fsaverage("fsaverage5")["inflated"].parts["left"].faces)
    n_unrel_faces = int((unrel[:10242][faces].sum(1) >= 2).sum())
    assert n_unrel_faces > 0
    pattern = [to_rgba(c) for c in load_config()["localize"]["unreliable_pattern"]]
    lh = np.asarray(fig.axes[0].collections[0]._facecolor3d)
    is_pat = np.zeros(len(lh), bool)
    for c in pattern:
        is_pat |= np.all(np.isclose(lh, c), axis=1)
    assert is_pat.sum() == n_unrel_faces
    texts = [t.get_text() for t in fig.texts]
    assert loc.caption() in texts
    assert any("unreliable" in t.get_label() for t in fig.legends[0].get_patches())
    matplotlib.pyplot.close(fig)
