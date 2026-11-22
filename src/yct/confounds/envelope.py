"""T-ENV: the speech_envelope regressor (D-086 R-ENV; config controls.regressors.speech_envelope.op =
abs_hilbert_of_clip_z_lp10hz_bin0p5s_mean_to_tr).

Steps, on the 16 kHz mono sidecar of one clip (one chunk = one clip, TRIBE's audio input space):
  1. z-score over the whole clip (a silent clip, SD 0, is all zeros: no sound, no envelope);
  2. |hilbert| (analytic amplitude);
  3. low-pass 10 Hz: Butterworth order 4, zero-phase (sosfiltfilt);
  4. mean per 0.5 s bin, bins [j*0.5, (j+1)*0.5) s (a partial last bin uses its samples);
  5. mean onto the 1 s TR grid of yct.confounds (tr_grid): bin j goes to TR floor(j*0.5 / TR).
Pinned choices not named in R-ENV (filter family and order) are stated here and frozen with this file's
blob sha (controls.refclips_d085.tenv). Never gates on reference clips (D-085)."""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

SR = 16000
LOWPASS_HZ = 10.0
BUTTER_ORDER = 4
BIN_S = 0.5


def envelope_trace(x: np.ndarray, sr: int) -> np.ndarray:
    """Steps 1-3: low-passed analytic amplitude of the per-clip z-scored signal, one value per sample."""
    if sr != SR:
        raise ValueError(f"T-ENV needs the {SR} Hz sidecar, got {sr} Hz")
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("T-ENV needs a mono signal")
    sd = float(np.std(x))
    if sd == 0.0 or x.size == 0:
        return np.zeros(x.size)
    z = (x - float(np.mean(x))) / sd
    amp = np.abs(hilbert(z))
    sos = butter(BUTTER_ORDER, LOWPASS_HZ, btype="low", fs=sr, output="sos")
    return sosfiltfilt(sos, amp)


def bin_means(trace: np.ndarray, sr: int, bin_s: float = BIN_S) -> np.ndarray:
    """Step 4: mean per bin of bin_s seconds; a partial last bin uses the samples it has."""
    n = int(round(bin_s * sr))
    k = math.ceil(len(trace) / n)
    return np.array([float(np.mean(trace[j * n:(j + 1) * n])) for j in range(k)])


def bins_to_tr(bins: np.ndarray, bin_s: float, n_tr: int, tr: float) -> np.ndarray:
    """Step 5: mean of the bins whose start falls in each TR [k*tr, (k+1)*tr)."""
    idx = np.minimum((np.arange(len(bins)) * bin_s // tr).astype(int), n_tr - 1)
    out = np.zeros(n_tr)
    for k in range(n_tr):
        sel = bins[idx == k]
        out[k] = float(np.mean(sel)) if sel.size else 0.0
    return out


def speech_envelope_per_tr(x: np.ndarray, sr: int, tr: float) -> np.ndarray:
    """The speech_envelope regressor on the yct.confounds TR grid of a clip of len(x)/sr seconds."""
    from yct.confounds.core import tr_grid

    trace = envelope_trace(x, sr)
    n_tr = len(tr_grid(len(x) / sr, tr))
    return bins_to_tr(bin_means(trace, sr), BIN_S, n_tr, tr)
