"""T-KERNEL (D-071 (f)/(g)): K1-K6 acceptance rules, operating characteristics under two null models,
fail-closed inputs, the on_fail / on_stop_invalid matrix, MT_plus demotion (T2 runtime tests a-e) and the
kernels_v1.json read path. Synthetic courses only (no predictions, no store)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config, with_overrides
from yct.controls import kernels as K  # noqa: N812
from yct.controls.kernels import FAIL, PASS, STOP_INVALID, KernelInput

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
LAGS = np.arange(-4, 9)
R_NULL = 600


def tmpl(lat=1.0, width=1.5):
    return np.exp(-0.5 * ((LAGS - lat) / width) ** 2)


def ar_noise(rng, n, phi=0.5):
    e = rng.normal(size=(n, LAGS.size))
    x = np.zeros_like(e)
    x[:, 0] = e[:, 0] / np.sqrt(1 - phi ** 2)
    for t in range(1, LAGS.size):
        x[:, t] = phi * x[:, t - 1] + e[:, t]
    return x * np.sqrt(1 - phi ** 2)


def jitter_null(rng, n):
    """Zero-mean jitter null: each clip has a bump of random sign (mean amplitude 0) and latency +-2 TR."""
    a = rng.normal(size=n)
    a -= a.mean()
    bumps = np.array([a[i] * tmpl(1 + rng.integers(-2, 3)) for i in range(n)])
    return bumps + 0.5 * rng.normal(size=(n, LAGS.size))


def inp(d, name="AUD", rng=None, **kw):
    rng = rng or np.random.default_rng(0)
    base = {"d_raw": d.copy(), "span_means": 0.3 * rng.normal(size=d.shape[0]), "sigma_nat": 1.0}
    base.update(kw)
    return KernelInput(name, d, np.arange(d.shape[0]), **base)


def signal(rng, n, amp=3.0):
    return amp * tmpl() + 0.5 * rng.normal(size=(n, LAGS.size))


# ---------------------------------------------------------------- operating characteristics
def _null_rates(gen, n):
    rng = np.random.default_rng(20261119)
    cnt, conj = {}, 0
    for _ in range(R_NULL):
        r = K.evaluate(inp(gen(rng, n), rng=rng), CFG)
        assert r["status"] != STOP_INVALID, r
        for k, v in r["rules"].items():
            cnt[k] = cnt.get(k, 0) + (v["result"] == PASS)
        conj += r["status"] == PASS
    return {k: v / R_NULL for k, v in cnt.items()}, conj / R_NULL


@pytest.mark.parametrize("n", [16, 20])
def test_null_ar_per_rule_and_conjunction(n):
    rates, conj = _null_rates(ar_noise, n)
    for rule in ("K1", "K3", "K4a", "K4b"):
        assert rates.get(rule, 0.0) < 0.05, (rule, rates)
    assert conj < 0.01


@pytest.mark.parametrize("n", [16, 20])
def test_null_jitter_conjunction(n):
    _, conj = _null_rates(jitter_null, n)
    assert conj < 0.01


def test_strong_response_passes_every_rule():
    rng = np.random.default_rng(3)
    r = K.evaluate(inp(signal(rng, 20), rng=rng), CFG)
    assert r["status"] == PASS, r["rules"]
    assert r["p_star"] in (0, 1, 2) and abs(max(r["kernel"]) - 1.0) < 0.2


# ---------------------------------------------------------------- single rules
def test_peak_not_positive_is_fail():
    rng = np.random.default_rng(4)
    r = K.evaluate(inp(-signal(rng, 20) - 5, rng=rng), CFG)
    assert r["status"] == FAIL and r["rules"]["peak"]["result"] == FAIL


def test_ffc_sign_rule_uses_80_percent():
    rng = np.random.default_rng(5)
    d = signal(rng, 20, amp=4.0)
    odd = np.arange(20)[1::2]
    d[odd[:2]] = -0.5 * tmpl() + 0.05 * rng.normal(size=(2, LAGS.size))   # 2/10 test clips negative
    assert K.evaluate(inp(d, "FFC", rng=rng), CFG)["rules"]["K1"]["sign_ok"]
    assert not K.evaluate(inp(d, "AUD", rng=rng), CFG)["rules"]["K1"]["sign_ok"]


def test_k2_tolerates_late_plateau_but_not_late_onset():
    rng = np.random.default_rng(6)
    plateau = np.where(LAGS >= 0, 3.0, 0.0) * 1.0
    r = K.evaluate(inp(plateau + 0.3 * rng.normal(size=(20, LAGS.size)), rng=rng), CFG)
    assert r["rules"]["K2"]["result"] == PASS
    late = 3.0 * tmpl(lat=7.0, width=0.8)
    r = K.evaluate(inp(late + 0.3 * rng.normal(size=(20, LAGS.size)), rng=rng), CFG)
    assert r["rules"]["K2"]["result"] == FAIL


def test_k3p_fails_only_if_large_and_significant():
    rng = np.random.default_rng(7)
    d = signal(rng, 20)
    big_noisy = rng.normal(loc=0.5, scale=10.0, size=20)
    big_sig = rng.normal(loc=1.5, scale=0.1, size=20)
    small_sig = rng.normal(loc=0.01, scale=0.001, size=20)
    assert K.evaluate(inp(d, rng=rng, span_means=big_noisy), CFG)["rules"]["K3p"]["result"] == PASS
    assert K.evaluate(inp(d, rng=rng, span_means=small_sig), CFG)["rules"]["K3p"]["result"] == PASS
    assert K.evaluate(inp(d, rng=rng, span_means=big_sig), CFG)["rules"]["K3p"]["result"] == FAIL


def test_k5_raw_sign_disagreement_fails():
    rng = np.random.default_rng(8)
    d = signal(rng, 20)
    assert K.evaluate(inp(d, rng=rng, d_raw=-d), CFG)["rules"]["K5"]["result"] == FAIL


def test_thresholds_come_from_frozen_config():
    rng = np.random.default_rng(9)
    d = signal(rng, 20, amp=1.0)
    r = K.evaluate(inp(d, rng=rng), CFG)
    strict = with_overrides(CFG, {"controls": {"kernel": {"acceptance": {"K3": {"min": 1e6}}}}})
    assert K.evaluate(inp(d, rng=rng), strict)["rules"]["K3"]["result"] == FAIL
    assert r["rules"]["K3"]["snr"] < 1e6


@pytest.mark.parametrize("defect", ["nan", "inf", "truncated", "zero_clip", "incomplete", "no_sigma",
                                    "no_raw", "no_spans", "zero_sd_spans", "dup_index", "sigma_zero"])
def test_fail_closed_inputs_are_stop_invalid(defect):
    rng = np.random.default_rng(10)
    d = signal(rng, 20)
    kw = {}
    if defect == "nan":
        d[3, 4] = np.nan
    elif defect == "inf":
        d[3, 4] = np.inf
    elif defect == "truncated":
        d = d[:, :-1]
    elif defect == "zero_clip":
        d[5] = 0.0
    elif defect == "incomplete":
        kw["complete"] = False
    elif defect == "no_sigma":
        kw["sigma_nat"] = None
    elif defect == "no_raw":
        kw["d_raw"] = None
    elif defect == "no_spans":
        kw["span_means"] = None
    elif defect == "zero_sd_spans":
        kw["span_means"] = np.zeros(20)
    elif defect == "sigma_zero":
        kw["sigma_nat"] = 0.0
    x = inp(d, rng=rng, **kw)
    if defect == "dup_index":
        x.clip_index = np.zeros(20, int)
    if defect == "truncated":
        x.d_raw = d.copy()
    r = K.evaluate(x, CFG)
    assert r["status"] == STOP_INVALID, (defect, r)


# ---------------------------------------------------------------- MT_plus + K6
def _mot(rng, amp=3.0, **kw):
    x = inp(signal(rng, 16, amp), "MT_plus", rng=rng, **kw)
    x.extra["family"] = "MOT"
    return x


def _flash(rng, amp=0.5, complete=True):
    return KernelInput("V1_V3", signal(rng, 5, amp), np.arange(5), complete=complete)


def test_mt_plus_k6_pass_and_fail():
    rng = np.random.default_rng(11)
    assert K.evaluate_mt_plus(_mot(rng), _flash(rng, 0.2), CFG, seed=1, n_boot=200)["status"] == PASS
    r = K.evaluate_mt_plus(_mot(rng), _flash(rng, 20.0), CFG, seed=1, n_boot=200)
    assert r["status"] == FAIL and r["rules"]["K6"]["result"] == FAIL


def test_c_flash_stop_invalid_makes_mt_plus_stop_invalid():
    rng = np.random.default_rng(12)
    fl = _flash(rng)
    fl.d_std[0, 0] = np.nan
    assert K.evaluate_mt_plus(_mot(rng), fl, CFG, seed=1, n_boot=50)["status"] == STOP_INVALID
    assert K.evaluate_mt_plus(_mot(rng), _flash(rng, complete=False), CFG, 1, 50)["status"] == STOP_INVALID


def test_d_motion_kernel_never_taken_from_flash():
    rng = np.random.default_rng(13)
    fl = _flash(rng, 3.0)
    as_mot = KernelInput("MT_plus", fl.d_std, fl.clip_index, d_raw=fl.d_std, span_means=np.ones(5),
                         sigma_nat=1.0, extra={"family": "FLASH"})
    assert K.evaluate_mt_plus(None, fl, CFG, 1, 50)["status"] == STOP_INVALID
    assert K.evaluate_mt_plus(as_mot, fl, CFG, 1, 50)["status"] == STOP_INVALID


# ---------------------------------------------------------------- (g) decision matrix
def _res(status, rules=("K3",)):
    return {"status": status, "rules": {r: {"result": FAIL if status == FAIL else PASS} for r in rules}}


ALL_PASS = {k: _res(PASS) for k in K.GATING}


def test_all_pass_is_go():
    d = K.decide(ALL_PASS, CFG, motion_complete=True, qc_pass=True)
    assert d["p4b"] == "go" and all(d[k]["status"] == "gating" for k in K.GATING)


@pytest.mark.parametrize("name", ["FFC", "AUD", "AUD_audioonly"])
def test_hard_stop_kernels_fail_to_stop(name):
    d = K.decide({**ALL_PASS, name: _res(FAIL)}, CFG, True, True)
    assert d[name]["status"] == "stop" and d["p4b"] == "stop"


@pytest.mark.parametrize("name", list(K.GATING))
def test_stop_invalid_is_always_stop(name):
    d = K.decide({**ALL_PASS, name: _res(STOP_INVALID)}, CFG, True, True)
    assert d[name]["status"] == "stop" and d["p4b"] == "stop"


def test_missing_kernel_is_stop():
    d = K.decide({k: v for k, v in ALL_PASS.items() if k != "AUD_audioonly"}, CFG, True, True)
    assert d["AUD_audioonly"]["status"] == "stop"


def test_mt_plus_valid_fail_is_demoted_with_frozen_sentence():
    d = K.decide({**ALL_PASS, "MT_plus": _res(FAIL, ("K2", "K6"))}, CFG, True, True)
    assert d["MT_plus"]["status"] == "demoted" and d["p4b"] == "go"
    assert d["MT_plus"]["limitation"] == ("TRIBE v2's predicted MT+ (MT ∪ MST ∪ FST) did not show a valid "
                                          "impulse response to isolated coherent motion (rule K2, K6); the "
                                          "motion control is descriptive.")


def test_a_incomplete_motion_run_is_stop_not_demotion():
    d = K.decide({**ALL_PASS, "MT_plus": _res(FAIL)}, CFG, motion_complete=False, qc_pass=True)
    assert d["MT_plus"]["status"] == "stop"


def test_b_failed_stimulus_qc_is_no_demotion():
    d = K.decide({**ALL_PASS, "MT_plus": _res(FAIL)}, CFG, motion_complete=True, qc_pass=False)
    assert d["MT_plus"]["status"] == "stop"


def test_on_fail_is_read_from_config():
    cfg = with_overrides(CFG, {"controls": {"kernel": {"acceptance": {"on_fail": {"MT_plus": "stop"}}}}})
    assert K.decide({**ALL_PASS, "MT_plus": _res(FAIL)}, cfg, True, True)["MT_plus"]["status"] == "stop"


# ---------------------------------------------------------------- kernels_v1.json, finality, firewall
def test_demotion_decided_only_from_kernels_v1_json(tmp_path):
    dec = K.decide({**ALL_PASS, "MT_plus": _res(FAIL)}, CFG, True, True)
    p = tmp_path / "kernels_v1.json"
    sha = K.write_kernels(p, {"MT_plus": _res(FAIL)}, dec, {"MOT": "a" * 64, "MOT_STAT": "b" * 64})
    assert len(sha) == 64 and K.mt_plus_status(p) == "demoted"
    doc = json.loads(p.read_text())
    doc["version"] = "v2"
    p.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        K.mt_plus_status(p)


def test_e_demotion_final_through_v2(tmp_path):
    dec = K.decide({**ALL_PASS, "MT_plus": _res(FAIL)}, CFG, True, True)
    p = tmp_path / "kernels_v1.json"
    shas = {"MOT": "a" * 64, "MOT_STAT": "b" * 64}
    K.write_kernels(p, {}, dec, shas)
    regated = {**dec, "MT_plus": {"status": "gating"}}
    with pytest.raises(ValueError, match="back to gating"):
        K.check_redesign(p, regated, shas, CFG)
    with pytest.raises(ValueError, match="MOT"):
        K.check_redesign(p, dec, {**shas, "MOT": "c" * 64}, CFG)
    K.check_redesign(p, dec, shas, CFG)


def test_kernel_code_cannot_reach_the_analysis_store():
    src = (ROOT / "src" / "yct" / "controls" / "kernels.py").read_text()
    tree = ast.parse(src)
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and (m.startswith("yct.predict") or m.startswith("boto")) for m in mods), mods
    assert "pred_clampv1" not in src and "np.load" not in src
