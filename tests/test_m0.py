"""M0 assembly (v2.4 G-D032 Biostat D1; D-034): W-averaging, label-free exclusions/imputation, Q(M0) D-037."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from yct.config import load_config, with_overrides
from yct.confounds import FEATURES
from yct.features import m0 as m0m

START, LEN, T = 5, 40, 50
FORCED_Q = ["speech_rate_wps^2", "speech_frac^2", "speech_rate_wps*speech_frac"]


def _video(vid, rng, *, silent=False, faceless=False, unvoiced=False, words_per_s=2.5):
    n = T
    df = pd.DataFrame({"video_id": vid, "tr": np.arange(n), "tr_start_s": np.arange(n) * 1.0,
                       "tr_end_s": np.arange(n) + 1.0, "tr_coverage": 1.0})
    for c in FEATURES:
        df[c] = rng.uniform(0.1, 0.9, n)
    df["rms_db"] = rng.normal(-25, 3, n)
    df["scene_cuts"] = rng.poisson(0.2, n)
    df["text_frac"] = np.nan                                   # not implemented
    df["speech_rate_wps"] = rng.poisson(words_per_s, n).astype(float)
    df["pitch_mean_hz"] = rng.normal(150, 20, n)
    df["pitch_sd_hz"] = rng.uniform(5, 20, n)
    df.loc[0, "motion_energy_crop"] = np.nan                   # first frame has no motion
    df.loc[rng.choice(n, 10, replace=False), "pitch_mean_hz"] = np.nan   # some unvoiced TRs
    if silent:
        df["speech_frac"] = 0.0
        df["speech_rate_wps"] = 0.0
        df["pitch_mean_hz"] = np.nan
        df["pitch_sd_hz"] = np.nan
    if unvoiced:                                               # words present, no voiced frame
        df["pitch_mean_hz"] = np.nan
        df["pitch_sd_hz"] = np.nan
    if faceless:
        for c in ("face_present_frac", "face_area_frac", "face_present_crop", "face_area_crop_frac"):
            df[c] = 0.0
        df["face_area_outside_crop_frac"] = np.nan
    return df


def _dataset(n=100, seed=0):
    rng = np.random.default_rng(seed)
    vids = [_video(f"v{i:03d}", rng, words_per_s=rng.uniform(1.5, 3.5)) for i in range(n)]
    vids.append(_video("silent", rng, silent=True))
    vids.append(_video("noaudio", rng, silent=True))
    vids.append(_video("faceless", rng, faceless=True))
    vids.append(_video("unvoiced", rng, unvoiced=True))
    vids.append(_video("fewwords", rng, words_per_s=0.3))      # ~12 words in 40 s
    per_tr = pd.concat(vids, ignore_index=True)
    has_audio = {v: v != "noaudio" for v in per_tr["video_id"].unique()}
    return per_tr, has_audio


def test_frozen_m0_list_excludes_text_frac():
    feats = m0m.m0_feature_list()
    assert "text_frac" not in feats
    assert {"speech_rate_wps", "speech_frac"} <= set(feats)
    bad = with_overrides(load_config(), {"m0": {"features": [*feats, "text_frac"]}})
    with pytest.raises(ValueError, match="text_frac"):
        m0m.m0_feature_list(bad)
    with pytest.raises(ValueError):
        m0m.impute_m0(pd.DataFrame({"text_frac": [np.nan]}), ["text_frac"])


def test_window_average_is_over_w_only():
    per_tr, _ = _dataset(n=3)
    w = m0m.m0_window_features(per_tr, START, LEN)
    d = per_tr[per_tr.video_id == "v000"]
    inw = d[(d.tr >= START) & (d.tr < START + LEN)]
    assert w.loc["v000", "luminance_crop"] == pytest.approx(inw["luminance_crop"].mean())
    assert w.loc["v000", "pitch_mean_hz"] == pytest.approx(inw["pitch_mean_hz"].mean())   # nan-skipping
    assert w.loc["v000", "n_words_w"] == inw["speech_rate_wps"].sum()
    assert np.isnan(w.loc["silent", "pitch_mean_hz"])
    with pytest.raises(ValueError, match="cover W"):
        m0m.m0_window_features(per_tr, 20, 40)                 # W beyond the series


def test_label_free_exclusions_logged(caplog):
    per_tr, has_audio = _dataset(n=5)
    w = m0m.m0_window_features(per_tr, START, LEN)
    with caplog.at_level(logging.INFO, logger="yct.features.m0"):
        kept, excl = m0m.label_free_exclusions(w, has_audio)
    reasons = dict(zip(excl.video_id, excl.reason, strict=True))
    assert reasons["noaudio"] == "no_audio_track"
    assert reasons["silent"].startswith("fewer_than_20_words")
    assert reasons["fewwords"].startswith("fewer_than_20_words")
    assert {"faceless", "unvoiced", "v000"} <= set(kept)
    assert not set(kept) & set(reasons)
    assert "noaudio" in caplog.text and "silent" in caplog.text


def test_assemble_imputation_rules_and_finite():
    per_tr, has_audio = _dataset(n=100)
    res = m0m.assemble_m0(per_tr, START, LEN, has_audio)
    m0 = res.m0
    assert np.isfinite(m0.to_numpy()).all()
    assert "text_frac" not in m0.columns and m0m.VOICED in m0.columns
    assert m0.loc["faceless", "face_area_crop_frac"] == 0.0
    # no voiced speech -> dataset median over voiced videos + indicator 0
    voiced = m0[m0[m0m.VOICED] == 1]
    assert m0.loc["unvoiced", m0m.VOICED] == 0.0
    assert m0.loc["unvoiced", "pitch_mean_hz"] == pytest.approx(np.median(voiced["pitch_mean_hz"]))
    assert res.imputation["n_imputed"]["pitch_mean_hz"] == 1
    assert set(res.excluded.video_id) == {"silent", "noaudio", "fewwords"}
    assert res.binary == [m0m.VOICED]


def test_missing_transcript_fails_hard():
    per_tr, has_audio = _dataset(n=4)
    per_tr.loc[per_tr.video_id == "v001", "speech_rate_wps"] = np.nan
    with pytest.raises(ValueError, match="transcript"):
        m0m.assemble_m0(per_tr, START, LEN, has_audio)


def test_unhandled_nan_fails_hard():
    per_tr, has_audio = _dataset(n=4)
    per_tr.loc[per_tr.video_id == "v002", "luminance_crop"] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        m0m.assemble_m0(per_tr, START, LEN, has_audio)


def test_kq_always_contains_speech_rate_and_fraction():
    """D-037 (supersedes the D-034 K_Q set): speech rate + fraction and their squares/product always in Q."""
    per_tr, has_audio = _dataset(n=100)
    res = m0m.assemble_m0(per_tr, START, LEN, has_audio)
    # make speech features nearly collinear with others: they must still be kept (listed first)
    m0 = res.m0.copy()
    m0["speech_frac"] = m0["rms_db"] * 0.01 + 1e-6 * np.arange(len(m0))
    plan = m0m.q_m0(m0, binary=res.binary)
    assert plan.columns[1:3] == ["speech_rate_wps", "speech_frac"] and set(FORCED_Q) <= set(plan.columns)
    assert not any(m0m.VOICED in c for c in plan.columns if "^2" in c or "*" in c)
    with pytest.raises(KeyError, match="forced speech"):
        m0m.q_m0(m0.drop(columns="speech_frac"), binary=res.binary)


def test_build_q_rank_and_columns():
    per_tr, has_audio = _dataset(n=100)
    res = m0m.assemble_m0(per_tr, START, LEN, has_audio)
    plan = m0m.q_m0(res.m0, binary=res.binary)
    n = len(res.m0)
    assert plan.q.shape == (n, plan.rank)
    assert np.isfinite(plan.q).all()
    assert plan.rank <= n // 3 and plan.limit == n // 3
    assert f"{m0m.VOICED}^2" not in plan.columns                 # binary not squared
    assert "speech_rate_wps*speech_frac" in plan.columns
    assert plan.aliased == []


def test_build_q_rank_assertion_and_aliasing(caplog):
    per_tr, has_audio = _dataset(n=100)
    res = m0m.assemble_m0(per_tr, START, LEN, has_audio)
    small = res.m0.iloc[:30]                                     # floor(30/3) = 10 < 11 after all merges
    with pytest.raises(ValueError, match="floor"):
        m0m.q_m0(small, binary=res.binary)
    dup = res.m0.copy()
    dup["luminance_crop"] = dup["contrast_crop"] * 2 + 1         # exact alias of another column
    with caplog.at_level(logging.WARNING, logger="yct.features.m0"):
        plan = m0m.q_m0(dup, binary=res.binary)
    assert "contrast_crop" in plan.aliased and "aliased" in caplog.text   # the later duplicate
    with pytest.raises(ValueError, match="non-finite"):
        bad = res.m0.copy()
        bad.iloc[0, 0] = np.nan
        m0m.q_m0(bad, binary=res.binary)


def test_era_dummies_linear_only():
    per_tr, has_audio = _dataset(n=100)
    res = m0m.assemble_m0(per_tr, START, LEN, has_audio)
    era = pd.Series(np.array(["E1", "E2", "E3"])[np.arange(len(res.m0)) % 3], index=res.m0.index)
    plan = m0m.q_m0(res.m0, binary=res.binary, era=era)
    assert [c for c in plan.columns if c.startswith("era")] == ["era=E2", "era=E3"]
    assert not any("era" in c and ("^2" in c or "*" in c) for c in plan.columns)
