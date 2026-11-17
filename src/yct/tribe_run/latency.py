"""Impulse-response latency from TRIBE predictions on the P0 impulse clip.

ROIs (Destrieux a2009s on fsaverage5, both hemispheres; TRIBE layout = 10242 L then 10242 R):
  visual   = Pole_occipital + S_calcarine          (event: white flash at t=15 s)
  auditory = G_temp_sup-G_T_transv + S_temporal_transverse  (event: speech burst at t=25 s)
Output time = segment start (s) of each kept TR; TRIBE's 5 s hemodynamic offset is already inside.
Usage: python latency.py PRED.npy SEGMENTS.csv OUTDIR [flash_onset speech_onset]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROIS = {"visual": (["Pole_occipital", "S_calcarine"], 15.0),
        "auditory": (["G_temp_sup-G_T_transv", "S_temporal_transverse"], 25.0)}


def roi_masks() -> dict[str, np.ndarray]:
    from nilearn.datasets import fetch_atlas_surf_destrieux
    d = fetch_atlas_surf_destrieux()
    labels = [x.decode() if isinstance(x, bytes) else str(x) for x in d["labels"]]
    lab = np.concatenate([np.asarray(d["map_left"]), np.asarray(d["map_right"])])
    assert lab.shape == (20484,), lab.shape
    out = {}
    for roi, (names, _) in ROIS.items():
        idx = [labels.index(n) for n in names]
        out[roi] = np.isin(lab, idx)
    return out


def main(pred: str, seg: str, outdir: str, flash: float = 15.0, speech: float = 25.0) -> dict:
    ROIS["visual"] = (ROIS["visual"][0], flash)
    ROIS["auditory"] = (ROIS["auditory"][0], speech)
    p = np.load(pred)
    t = np.loadtxt(seg, delimiter=",", skiprows=1, usecols=1)
    assert len(t) == p.shape[0]
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    res = {}
    for roi, mask in roi_masks().items():
        onset = ROIS[roi][1]
        tc = p[:, mask].mean(axis=1)
        np.savetxt(out / f"latency_{roi}.csv", np.c_[t, t - onset, tc], delimiter=",",
                   header="output_time_s,time_rel_onset_s,mean_pred", comments="", fmt="%.6f")
        win = (t >= onset) & (t <= onset + 15)
        base = (t >= onset - 6) & (t < onset)
        i = np.flatnonzero(win)[np.argmax(tc[win])]
        res[roi] = {"n_vertices": int(mask.sum()), "onset_s": onset,
                    "peak_output_time_s": float(t[i]), "peak_rel_onset_s": float(t[i] - onset),
                    "peak_value": float(tc[i]), "baseline_mean": float(tc[base].mean()),
                    "peak_minus_baseline": float(tc[i] - tc[base].mean())}
    (out / "latency.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))
    return res


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], *map(float, sys.argv[4:6]))
