"""ENH-002 latency analysis (yct.tribe_run.enh002) on synthetic predictions with a known response lag."""
from __future__ import annotations

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run.enh002 import analyse, event_courses, latency_ci, standardise

ONS = [15.0, 35.0, 55.0, 75.0, 95.0]


def _synthetic(lag: int, n_t: int = 120, v: int = 40, seed: int = 0):
    rng = np.random.default_rng(seed)
    masks = {"V1_V3": np.zeros(v, bool), "AUD": np.zeros(v, bool), "FFC": np.zeros(v, bool),
             "PH": np.zeros(v, bool), "MT_plus": np.zeros(v, bool)}
    masks["V1_V3"][:10] = True
    masks["AUD"][10:20] = True
    ctrl = rng.normal(0, 0.01, (n_t, v)).astype(np.float32)
    flash, speech = ctrl.copy(), ctrl.copy()
    for t0 in ONS:
        flash[int(t0) + lag, :10] += 1.0
        speech[int(t0) + lag + 1, 10:20] += 1.0
    t = np.arange(n_t, dtype=float)
    preds = {"ref_control": ctrl, "ref_flash": flash, "ref_speech": speech}
    return preds, {k: t for k in preds}, {"ref_flash": ONS, "ref_speech": ONS, "ref_control": []}, masks


@pytest.mark.parametrize("lag", [-2, 0, 3])
def test_recovers_known_lag(lag):
    preds, times, onsets, masks = _synthetic(lag)
    res = analyse(preds, times, onsets, masks, np.zeros(40, bool), load_config())
    for m in ("raw", "spatially_standardised"):
        lat = res["maps"][m]
        assert lat["ref_flash"]["latency"]["peak_lags_tr"] == [lag] * 5
        assert lat["ref_speech"]["latency"]["peak_lags_tr"] == [lag + 1] * 5
        assert lat["ref_flash"]["kernel_peak_lag_tr"] == lag
        assert max(lat["ref_flash"]["kernel_peak_normalised"]) == pytest.approx(1.0)
    assert res["window_tr"] == load_config()["controls"]["kernel"]["window_tr"]


def test_latency_ci_brackets_mean():
    ci = latency_ci(np.array([0, 1, 0, -1, 0]))
    assert ci["boot95_tr"][0] <= ci["mean_lag_tr"] <= ci["boot95_tr"][1]
    assert ci["t95_tr"][0] < 0 < ci["t95_tr"][1] and ci["n_events"] == 5


def test_event_courses_window_and_edges():
    t = np.arange(20, dtype=float)
    ev = event_courses(t * 2, t, [5.0, 18.0], range(-4, 9))
    assert ev[0].tolist() == [2 * x for x in range(1, 14)]
    assert np.isnan(ev[1, -1])  # beyond the clip -> NaN, never wrapped


def test_standardise_zero_mean_unit_sd_off_medial_wall():
    p = np.random.default_rng(1).normal(3, 2, (4, 30))
    med = np.zeros(30, bool)
    med[:5] = True
    z = standardise(p, med)
    assert np.allclose(z[:, 5:].mean(1), 0) and np.allclose(z[:, 5:].std(1), 1)
