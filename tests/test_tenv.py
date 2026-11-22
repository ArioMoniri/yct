"""T-ENV (D-086 R-ENV, D-085 part 2): the speech_envelope regressor.

op = |hilbert| of the per-clip z-scored 16 kHz sidecar, low-pass 10 Hz, mean per 0.5 s bin, mean onto the
1 s TR grid of yct.confounds. Written before src/yct/confounds/envelope.py."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config

ROOT = Path(__file__).resolve().parents[1]
SR = 16000


def env():
    from yct.confounds import envelope
    return envelope


def am_tone(dur, f_mod, sr=SR, seed=0):
    t = np.arange(int(dur * sr)) / sr
    carrier = np.sin(2 * np.pi * 440 * t)
    return (1 + 0.9 * np.sin(2 * np.pi * f_mod * t)) * carrier


def test_output_is_on_the_confounds_tr_grid():
    from yct.confounds.core import tr_grid
    x = am_tone(7.3, 1.0)
    e = env().speech_envelope_per_tr(x, SR, tr=1.0)
    assert e.shape == (len(tr_grid(len(x) / SR, 1.0)),) and np.all(np.isfinite(e))


def test_per_clip_zscore_makes_it_gain_invariant():
    x = am_tone(6.0, 0.5)
    a = env().speech_envelope_per_tr(x, SR, tr=1.0)
    b = env().speech_envelope_per_tr(37.0 * x + 0.0, SR, tr=1.0)
    assert np.allclose(a, b, atol=1e-9)


def test_lowpass_removes_modulation_above_10hz_and_keeps_slow_modulation():
    mod = env()
    slow = mod.envelope_trace(am_tone(8.0, 1.0), SR)       # 1 Hz AM survives the 10 Hz low-pass
    fast = mod.envelope_trace(am_tone(8.0, 40.0), SR)      # 40 Hz AM is removed
    mid = slice(SR, 7 * SR)                              # away from the filtfilt edges
    assert np.std(slow[mid]) > 10 * np.std(fast[mid])


def test_silent_clip_gives_zeros_not_nan():
    e = env().speech_envelope_per_tr(np.zeros(5 * SR), SR, tr=1.0)
    assert np.array_equal(e, np.zeros(5))


def test_burst_tracks_sound_onset():
    x = np.zeros(10 * SR)
    t = np.arange(2 * SR) / SR
    x[4 * SR:6 * SR] = np.sin(2 * np.pi * 300 * t)       # sound in TRs 4 and 5
    e = env().speech_envelope_per_tr(x, SR, tr=1.0)
    assert np.argmax(e) in (4, 5) and e[4] > 3 * e[0] and e[5] > 3 * e[9]


def test_half_second_bins_then_mean_onto_tr():
    mod = env()
    trace = np.concatenate([np.full(SR // 2, 1.0), np.full(SR // 2, 3.0), np.full(SR // 2, 5.0)])
    bins = mod.bin_means(trace, SR, 0.5)
    assert np.allclose(bins, [1.0, 3.0, 5.0])
    assert np.allclose(mod.bins_to_tr(bins, 0.5, n_tr=2, tr=1.0), [2.0, 5.0])


def test_wrong_sample_rate_refused():
    with pytest.raises(ValueError, match="16000"):
        env().speech_envelope_per_tr(np.zeros(8000), 8000, tr=1.0)


def test_parameters_are_the_frozen_op():
    cfg = load_config()
    op = cfg["controls"]["regressors"]["speech_envelope"]["op"]
    assert op == "abs_hilbert_of_clip_z_lp10hz_bin0p5s_mean_to_tr"
    mod = env()
    assert (mod.SR, mod.LOWPASS_HZ, mod.BIN_S, mod.BUTTER_ORDER) == (16000, 10.0, 0.5, 4)


def test_tenv_config_points_at_this_module_and_its_blob():
    d = load_config()["controls"]["refclips_d085"]["tenv"]
    assert d["module"] == "src/yct/confounds/envelope.py"
    blob = subprocess.run(["git", "hash-object", str(ROOT / d["module"])], capture_output=True, text=True,
                          check=True).stdout.strip()
    assert d["blob_sha1"] == blob, "T-ENV module changed after its blob sha was set"


def test_tenv_is_frozen_before_any_speech_build():
    from yct.tribe_run import speech_corpus
    cfg = load_config()
    assert speech_corpus._frozen(cfg, "controls.refclips_d085.tenv"), "T-ENV must be frozen"


def test_module_blob_is_reproducible_from_the_file():
    d = load_config()["controls"]["refclips_d085"]["tenv"]
    data = (ROOT / d["module"]).read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == d["blob_sha1"]
