"""ENH-002 dry run, latency part (v2.md §5 P4b; config controls): impulse kernels + latency CI per ROI.

Inputs: TRIBE predictions (T, 20484) + segments.csv for the reference clips of make_reference_clips.py
(ref_flash, ref_speech, ref_control, optionally ref_face). Per event (5 flashes -> V1_V3, 5 speech bursts ->
AUD; config `controls.rois`, HCP-MMP on the union-medial-wall atlas) the control-subtracted ROI course is read
at output lags `controls.kernel.window_tr` (-4..+8 TR) relative to the onset (segment start times = stimulus
clock; TRIBE's 5 s offset is already inside the model). Latency of an event = lag of its peak; the CI is a
seeded percentile bootstrap over events plus a t interval. Done on raw and on spatially standardised maps
(each TR z-scored over non-medial-wall vertices). The peak-normalised mean course is the per-ROI kernel
candidate (fixed only by a DECISIONS entry before the P4b lock; this module only reports it).

Usage: python -m yct.tribe_run.enh002 PRED_DIR OUT_DIR   (PRED_DIR holds <clip>.npy + <clip>.segments.csv
and enh002.json from make_reference_clips.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from yct.config import load_config

EVENTS = {"ref_flash": "V1_V3", "ref_speech": "AUD"}
N_BOOT = 10000
BOOT_SEED = 20261117


def roi_masks(cfg: dict | None = None) -> tuple[dict[str, np.ndarray], np.ndarray]:
    from yct.features import atlas as atl

    cfg = cfg or load_config()
    at = atl.load_all(cfg)
    out = {}
    for roi, spec in cfg["controls"]["rois"].items():
        names = [f"{h}_{a}_ROI" for h in spec["hemis"] for a in spec["areas"]]
        out[roi] = np.isin(at.hcp.labels, [at.hcp.names.index(n) for n in names])
    return out, at.medial_wall


def standardise(pred: np.ndarray, medial: np.ndarray) -> np.ndarray:
    """Spatially standardised map: each TR z-scored over the non-medial-wall vertices.

    R-11 M-12b: delegates to the single M-12 implementation (yct.features.networks.spatial_standardize),
    which sets the medial wall to NaN and raises on non-finite or spatially constant TRs. Bit-identical on
    cortex to the former local copy (ENH-002 read only cortical ROI vertices)."""
    from yct.features.networks import spatial_standardize

    return spatial_standardize(pred, medial)


def event_courses(course: np.ndarray, times: np.ndarray, onsets: list[float], lags: range) -> np.ndarray:
    """(n_events, n_lags) values of a 1-D course at output time onset + lag (nearest TR, must exist)."""
    out = np.full((len(onsets), len(lags)), np.nan)
    for i, t0 in enumerate(onsets):
        for j, lag in enumerate(lags):
            k = int(np.argmin(np.abs(times - (t0 + lag))))
            if abs(times[k] - (t0 + lag)) < 0.51:
                out[i, j] = course[k]
    return out


def latency_ci(peaks: np.ndarray, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> dict[str, Any]:
    peaks = np.asarray(peaks, float)
    rng = np.random.default_rng(seed)
    boot = rng.choice(peaks, size=(n_boot, peaks.size), replace=True).mean(axis=1)
    from scipy import stats

    n = peaks.size
    sem = peaks.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    tcrit = stats.t.ppf(0.975, n - 1) if n > 1 else np.nan
    return {"n_events": int(n), "peak_lags_tr": peaks.tolist(), "mean_lag_tr": float(peaks.mean()),
            "median_lag_tr": float(np.median(peaks)),
            "sd_lag_tr": float(peaks.std(ddof=1)) if n > 1 else None,
            "boot95_tr": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "t95_tr": ([float(peaks.mean() - tcrit * sem), float(peaks.mean() + tcrit * sem)]
                       if n > 1 else None),
            "n_boot": n_boot, "boot_seed": seed}


def analyse(preds: dict[str, np.ndarray], times: dict[str, np.ndarray], onsets: dict[str, list[float]],
            masks: dict[str, np.ndarray], medial: np.ndarray, cfg: dict | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    w0, w1 = cfg["controls"]["kernel"]["window_tr"]
    lags = range(int(w0), int(w1) + 1)
    res: dict[str, Any] = {"window_tr": [w0, w1], "maps": {}}
    for mapname in cfg["controls"]["maps"]:
        f = (lambda p: standardise(p, medial)) if mapname == "spatially_standardised" else (lambda p: p)
        ctrl = f(preds["ref_control"])
        out = {}
        for clip, roi in EVENTS.items():
            if clip not in preds:
                continue
            p = f(preds[clip])
            assert p.shape == ctrl.shape, (clip, p.shape, ctrl.shape)
            course = (p - ctrl)[:, masks[roi]].mean(axis=1)
            ev = event_courses(course, times[clip], onsets[clip], lags)
            peaks = np.array([list(lags)[int(np.nanargmax(r))] for r in ev])
            mean_course = np.nanmean(ev, axis=0)
            kernel = mean_course / np.nanmax(np.abs(mean_course))
            # off-target ROI response to the same events (e.g. AUD to flashes, P0 finding)
            other = {r: float(np.nanmean(event_courses((p - ctrl)[:, m].mean(axis=1), times[clip],
                                                       onsets[clip], range(0, 4))))
                     for r, m in masks.items()}
            out[clip] = {"roi": roi, "lags_tr": list(lags), "event_courses": ev.round(6).tolist(),
                         "mean_course": mean_course.round(6).tolist(),
                         "kernel_peak_normalised": kernel.round(6).tolist(),
                         "kernel_peak_lag_tr": int(list(lags)[int(np.nanargmax(mean_course))]),
                         "latency": latency_ci(peaks), "mean_response_lag0_3_by_roi": other}
        res["maps"][mapname] = out
    if "ref_face" in preds:
        n = preds["ref_face"].shape[0]
        d = preds["ref_face"] - preds["ref_control"][:n]
        res["ref_face_minus_control_mean"] = {r: float(d[:, m].mean()) for r, m in masks.items()}
        res["ref_face_note"] = ("synthetic cartoon face (no real face footage); FFC response is descriptive "
                                "only, "
                                "not a test of control (a)")
    return res


def main(pred_dir: str, out_dir: str) -> dict[str, Any]:
    pd_ = Path(pred_dir)
    rec = json.loads((pd_ / "enh002.json").read_text())
    preds, times, onsets = {}, {}, {}
    for clip in ("ref_control", "ref_flash", "ref_speech", "ref_face"):
        if (pd_ / f"{clip}.npy").exists():
            preds[clip] = np.load(pd_ / f"{clip}.npy")
            times[clip] = np.loadtxt(pd_ / f"{clip}.segments.csv", delimiter=",", skiprows=1, usecols=1,
                                     ndmin=1)
            onsets[clip] = rec["clips"][clip].get("event_onsets_s", [])
    masks, medial = roi_masks()
    res = analyse(preds, times, onsets, masks, medial)
    res["clips"] = rec["clips"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "enh002_latency.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2])
    print(json.dumps({m: {c: v["latency"] for c, v in d.items()} for m, d in r["maps"].items()}, indent=1))
