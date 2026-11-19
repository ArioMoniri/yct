"""D-071 (f)/(g): per-ROI measured impulse kernels from the P4b reference clips, the K1-K6 acceptance
rules, and the STOP / demotion decision written to kernels_v1.json.

Inputs are per-clip control-subtracted ROI courses d_j(lag), lags = controls.kernel.window_tr (-4..+8),
averaged over clip j's events, on the spatially standardised map (raw enters K5 only). Halves are fixed by
the 0-based clip index i within its family: selection = even i, test = odd i. Thresholds are read only from
the frozen config `controls.kernel.acceptance`.

This module never reads predictions or any analysis-set store: callers pass arrays built from the
reference-clip prefix (p4b_ref/v1). It must not import yct.predict (tested).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

PASS, FAIL, STOP_INVALID = "PASS", "FAIL", "STOP_INVALID"
RULES = ("K1", "K1p", "K2", "K3", "K3p", "K4a", "K4b", "K5")
LIMITATION = ("TRIBE v2's predicted MT+ (MT ∪ MST ∪ FST) did not show a valid impulse response to isolated "
              "coherent motion (rule {rules}); the motion control is descriptive.")
GATING = ("FFC", "AUD", "AUD_audioonly", "MT_plus")


class InvalidInputError(ValueError):
    """Fail-closed input defect: the kernel is STOP_INVALID."""


@dataclass
class KernelInput:
    """Courses of one kernel (one ROI x one reference family x one condition)."""
    name: str                       # FFC, AUD, AUD_audioonly, MT_plus, PH, V1_V3, ...
    d_std: np.ndarray               # (n_clips, n_lags) standardised, control-subtracted
    clip_index: np.ndarray          # (n_clips,) 0-based index i within the family
    d_raw: np.ndarray | None = None  # (n_clips, n_lags) raw map, for K5
    span_means: np.ndarray | None = None   # (n_clips,) per-clip K3' span means (standardised)
    sigma_nat: float | None = None  # median ROI temporal SD over W in NAT (standardised)
    events_per_clip: int = 3
    complete: bool = True           # every family job of this kernel synced and passed
    extra: dict[str, Any] = field(default_factory=dict)


def lags_from(cfg: dict) -> np.ndarray:
    w0, w1 = cfg["controls"]["kernel"]["window_tr"]
    return np.arange(int(w0), int(w1) + 1)


def _finite(name: str, a: np.ndarray, shape: tuple | None = None) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    if shape is not None and a.shape != shape:
        raise InvalidInputError(f"{name}: shape {a.shape} != {shape} (truncated window or missing clips)")
    if not np.all(np.isfinite(a)):
        raise InvalidInputError(f"{name}: NaN/inf")
    return a


def _check(inp: KernelInput, lags: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not inp.complete:
        raise InvalidInputError(f"{inp.name}: incomplete family job")
    d = _finite("d_std", inp.d_std)
    if d.ndim != 2 or d.shape[1] != lags.size or d.shape[0] < 4:
        raise InvalidInputError(f"{inp.name}: d_std shape {d.shape} (need (n>=4, {lags.size}))")
    idx = np.asarray(inp.clip_index)
    if idx.shape != (d.shape[0],) or len(set(idx.tolist())) != idx.size:
        raise InvalidInputError(f"{inp.name}: clip_index must be unique, one per clip")
    if np.all(d == 0) or np.any(np.all(d == 0, axis=1)):
        raise InvalidInputError(f"{inp.name}: all-zero course (zero-filled clip)")
    sel, test = idx % 2 == 0, idx % 2 == 1
    if sel.sum() < 2 or test.sum() < 2:
        raise InvalidInputError(f"{inp.name}: each half needs >= 2 clips")
    return d, sel, test


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) == 0 or np.std(b) == 0:
        raise InvalidInputError("zero SD in a correlation")
    return float(np.corrcoef(a, b)[0, 1])


def derive(d: np.ndarray, sel: np.ndarray, lags: np.ndarray) -> dict[str, Any]:
    m_sel, m_test, m_full = d[sel].mean(0), d[~sel].mean(0), d.mean(0)
    j = int(np.argmax(m_sel))            # signed argmax of m_sel
    peak = float(m_full[j])
    return {"m_sel": m_sel, "m_test": m_test, "m_full": m_full, "p_star": int(lags[j]), "j_star": j,
            "peak": peak, "kernel": (m_full / peak) if peak > 0 else None}


def evaluate(inp: KernelInput, cfg: dict) -> dict[str, Any]:
    """K1-K5 (+K6 via evaluate_mt_plus) for one kernel. Returns {status, rules, peak, p_star, kernel, ...}."""
    acc = cfg["controls"]["kernel"]["acceptance"]
    lags = lags_from(cfg)
    try:
        d, sel, test = _check(inp, lags)
        k = derive(d, sel, lags)
        rules: dict[str, dict[str, Any]] = {}
        peak, j = k["peak"], k["j_star"]
        if peak <= 0:
            return _out(inp, k, {"peak": {"result": FAIL, "peak": peak}}, FAIL, lags)
        n = d.shape[0]
        # K1: one-sided one-sample t over test-half d_j(p*), plus the sign check
        x = d[test, j]
        if np.std(x, ddof=1) == 0:
            raise InvalidInputError("K1: zero SD")
        t, p2 = stats.ttest_1samp(x, 0.0)
        p1 = float(p2 / 2 if t > 0 else 1 - p2 / 2)
        if inp.name == "FFC":
            sign_ok = float(np.mean(x > 0)) >= acc["K1"]["ffc_min_positive_frac"]
        else:
            sign_ok = bool(np.all(x > 0)) if acc["K1"]["sign_all_positive"] else True
        rules["K1"] = {"result": PASS if (p1 < acc["K1"]["alpha"] and sign_ok) else FAIL, "t": float(t),
                       "p_one_sided": p1, "sign_ok": bool(sign_ok), "n_test": int(x.size)}
        # K1': absolute floor against NAT temporal SD
        if inp.sigma_nat is None:
            raise InvalidInputError("K1': sigma_nat missing (NAT job)")
        sn = _finite("sigma_nat", np.asarray(inp.sigma_nat))
        if sn <= 0:
            raise InvalidInputError("K1': sigma_nat <= 0")
        k1p = acc["K1p"]
        rules["K1p"] = {"result": PASS if (peak >= k1p["min_frac_sigma_nat"] * float(sn)
                                           and peak >= k1p["min_abs"]) else FAIL,
                        "peak": peak, "sigma_nat": float(sn)}
        # K2: timing (late plateau tolerated)
        mf = k["m_full"]
        k2 = acc["K2"]
        mx = float(mf.max())
        in_w = (lags >= k2["window"][0]) & (lags <= k2["window"][1])
        c1 = float(mf[in_w].max()) >= k2["plateau_frac"] * mx
        jmax = int(np.argmax(mf))
        cross = None
        for jj in range(0, jmax + 1):
            if mf[jj] >= k2["crossing_frac"] * mx:
                cross = int(lags[jj])
                break
        c2 = cross is not None and k2["crossing_window"][0] <= cross <= k2["crossing_window"][1]
        tail = (lags >= k2["tail_lags"][0]) & (lags <= k2["tail_lags"][1])
        c3 = float(mf[tail].mean()) >= k2["tail_frac"] * peak
        rules["K2"] = {"result": PASS if (c1 and c2 and c3) else FAIL, "plateau_ok": bool(c1),
                       "crossing_lag": cross, "crossing_ok": bool(c2), "tail_ok": bool(c3)}
        # K3: peak over the SE of the pre-onset baseline
        b = (lags >= acc["K3"]["baseline_lags"][0]) & (lags <= acc["K3"]["baseline_lags"][1])
        v = float(d[:, b].var(axis=0, ddof=1).mean())
        if v <= 0:
            raise InvalidInputError("K3: zero baseline variance")
        snr = peak / np.sqrt(v / n)
        rules["K3"] = {"result": PASS if snr >= acc["K3"]["min"] else FAIL, "snr": float(snr)}
        # K3': inter-event span offset (FAIL only if both large and significant)
        if inp.span_means is None:
            raise InvalidInputError("K3': span means missing")
        s = _finite("span_means", inp.span_means, (n,))
        if np.std(s, ddof=1) == 0:
            raise InvalidInputError("K3': zero SD")
        ts, ps = stats.ttest_1samp(s, 0.0)
        big = abs(float(s.mean())) > acc["K3p"]["max_frac_peak"] * peak
        sig = float(ps) < acc["K3p"]["alpha_two_sided"]
        rules["K3p"] = {"result": FAIL if (big and sig) else PASS, "offset": float(s.mean()),
                        "p_two_sided": float(ps)}
        # K4a: median leave-one-clip-out r(training kernel, held-out d_j)
        rs = [_corr(np.delete(d, i, axis=0).mean(0), d[i]) for i in range(n)]
        rules["K4a"] = {"result": PASS if float(np.median(rs)) >= acc["K4a"]["min_median_r"] else FAIL,
                        "median_r": float(np.median(rs))}
        # K4b: split-half r(m_sel, m_test)
        r_sh = _corr(k["m_sel"], k["m_test"])
        rules["K4b"] = {"result": PASS if r_sh >= acc["K4b"]["min_r"] else FAIL, "r": r_sh}
        # K5: standardised vs raw sign/peak-lag agreement
        if inp.d_raw is None:
            raise InvalidInputError("K5: raw map missing")
        dr = _finite("d_raw", inp.d_raw, d.shape)
        mr = dr.mean(0)
        k5 = acc["K5"]
        lw = ((lags >= k5["lags"][0]) & (lags <= k5["lags"][1])
              & (np.abs(mf) >= k5["min_abs_frac_peak"] * peak))
        sign_agree = bool(np.all(np.sign(mf[lw]) == np.sign(mr[lw])))
        p_raw = int(lags[int(np.argmax(dr[sel].mean(0)))])
        lag_ok = abs(k["p_star"] - p_raw) <= k5["max_lag_diff"]
        rules["K5"] = {"result": PASS if (sign_agree and lag_ok) else FAIL, "p_star_raw": p_raw,
                       "sign_agree": sign_agree}
        status = PASS if all(r["result"] == PASS for r in rules.values()) else FAIL
        return _out(inp, k, rules, status, lags)
    except InvalidInputError as exc:
        return {"name": inp.name, "status": STOP_INVALID, "reason": str(exc), "rules": {}}


def evaluate_mt_plus(mot: KernelInput, flash: KernelInput | None, cfg: dict, seed: int,
                     n_boot: int = 10000) -> dict[str, Any]:
    """MT_plus kernel from MOT (moving - static twin) only, plus K6 against FLASH - GREY-CTRL.
    The motion kernel is never taken from FLASH: a missing or invalid MOT set is STOP_INVALID."""
    if mot is None or mot.name != "MT_plus" or mot.extra.get("family") != "MOT":
        return {"name": "MT_plus", "status": STOP_INVALID, "reason": "MOT courses required", "rules": {}}
    res = evaluate(mot, cfg)
    if res["status"] == STOP_INVALID:
        return res
    if flash is None or not flash.complete:
        return {"name": "MT_plus", "status": STOP_INVALID, "reason": "FLASH incomplete (K6)", "rules": {}}
    lags = lags_from(cfg)
    try:
        f = _finite("flash d_std", flash.d_std)
        if f.ndim != 2 or f.shape[1] != lags.size or np.all(f == 0):
            raise InvalidInputError("FLASH: bad shape or all-zero")
    except InvalidInputError as exc:
        return {"name": "MT_plus", "status": STOP_INVALID, "reason": f"FLASH STOP_INVALID: {exc}",
                "rules": {}}
    k6 = cfg["controls"]["kernel"]["acceptance"]["K6"]
    w = (lags >= k6["lags"][0]) & (lags <= k6["lags"][1])
    dm = np.asarray(mot.d_std, float)[:, w].mean(1)
    dfl = f[:, w].mean(1)
    diff = float(dm.mean() - dfl.mean())
    rng = np.random.default_rng(seed)
    boot = np.array([dm[rng.integers(0, dm.size, dm.size)].mean()
                     - dfl[rng.integers(0, dfl.size, dfl.size)].mean() for _ in range(n_boot)])
    res["rules"]["K6"] = {"result": PASS if diff > 0 else FAIL, "diff": diff,
                          "boot95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]}
    res["status"] = PASS if all(r["result"] == PASS for r in res["rules"].values()) else FAIL
    return res


def _out(inp, k, rules, status, lags) -> dict[str, Any]:
    return {"name": inp.name, "status": status, "rules": rules, "peak": k["peak"], "p_star": k["p_star"],
            "lags": lags.tolist(), "m_full": np.round(k["m_full"], 8).tolist(),
            "kernel": None if k["kernel"] is None else np.round(k["kernel"], 8).tolist(),
            "n_clips": int(np.asarray(inp.d_std).shape[0])}


# ---------------------------------------------------------------- (g) STOP versus descriptive
def decide(results: dict[str, dict], cfg: dict, motion_complete: bool, qc_pass: bool) -> dict[str, Any]:
    """Per gating kernel: gating | stop | demoted. MT_plus is demoted only on a valid K-rule FAIL with a
    complete MOT / MOT-STAT / FLASH set whose stimulus QC passed; every STOP_INVALID is a stop."""
    acc = cfg["controls"]["kernel"]["acceptance"]
    out: dict[str, Any] = {}
    for name in GATING:
        r = results.get(name)
        st = STOP_INVALID if r is None else r["status"]
        if st == PASS:
            out[name] = {"status": "gating"}
        elif st == STOP_INVALID:
            out[name] = {"status": "stop", "why": "STOP_INVALID", "action": acc["on_stop_invalid"]}
        else:
            action = acc["on_fail"][name]
            failed = sorted(k for k, v in r["rules"].items() if v["result"] == FAIL) or ["peak"]
            if action == "descriptive" and name == "MT_plus" and motion_complete and qc_pass:
                out[name] = {"status": "demoted", "failed_rules": failed,
                             "limitation": LIMITATION.format(rules=", ".join(failed))}
            else:
                out[name] = {"status": "stop", "why": "FAIL", "failed_rules": failed}
    out["p4b"] = "stop" if any(v["status"] == "stop" for v in out.values() if isinstance(v, dict)) else "go"
    return out


def write_kernels(path: Path, results: dict[str, dict], decision: dict, manifest_shas: dict[str, str],
                  version: str = "v1") -> str:
    doc = {"version": version, "decision": decision, "results": results, "manifest_shas": manifest_shas}
    text = json.dumps(doc, indent=1, sort_keys=True, default=float)
    Path(path).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def mt_plus_status(kernels_path: Path) -> str:
    """The MT_plus gating status, read from the K table in kernels_v1.json and nothing else."""
    doc = json.loads(Path(kernels_path).read_text())
    if doc.get("version") != "v1":
        raise ValueError("kernels file is not v1")
    return doc["decision"]["MT_plus"]["status"]


def check_redesign(v1_path: Path, v2_decision: dict, v2_manifest_shas: dict[str, str], cfg: dict) -> None:
    """D-071 (g) finality: a demoted MT_plus stays demoted in p4b_ref/v2, and v2 carries MOT / MOT-STAT
    over unchanged by manifest sha."""
    if not cfg["controls"]["kernel"]["acceptance"]["demotion_final"]:
        return
    v1 = json.loads(Path(v1_path).read_text())
    if v1["decision"]["MT_plus"]["status"] != "demoted":
        return
    if v2_decision["MT_plus"]["status"] != "demoted":
        raise ValueError("demotion_final: a v2 kernels file cannot set MT_plus back to gating")
    for fam in ("MOT", "MOT_STAT"):
        if v2_manifest_shas.get(fam) != v1["manifest_shas"].get(fam):
            raise ValueError(f"demotion_final: v2 {fam} manifest sha differs from v1 "
                             "(MOT must not be re-run)")
