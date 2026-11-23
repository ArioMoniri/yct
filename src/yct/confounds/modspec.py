"""D-089 v2 (neuro / referee Q1): descriptive-only envelope modulation peak per speech family.

SPK is spoken at 120 wpm and BURST / TALKFACE at 175 wpm, so the speech-family readouts are not rate-matched.
This reports the peak of the envelope modulation spectrum (about the syllable rate) for each family, so the
mismatch is visible in the v1 report. It never gates and is never used inferentially. The envelope itself is
the frozen T-ENV trace (yct.confounds.envelope); this module does not change it.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def peak_modulation_hz(env: np.ndarray, sr: int, band: tuple[float, float] = (0.5, 20.0)) -> dict[str, Any]:
    x = np.asarray(env, np.float64)
    x = x - x.mean()
    if not np.any(x):
        return {"peak_hz": None, "band_hz": list(band), "gating": False}
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    m = (f >= band[0]) & (f <= band[1])
    return {"peak_hz": float(f[m][int(np.argmax(spec[m]))]), "band_hz": list(band), "gating": False}
