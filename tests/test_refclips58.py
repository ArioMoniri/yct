"""T-REF58 / T-STIM (D-071 (a)-(d)): schedule balance, Latin square, MOT direction/pattern balance,
scramble-switch timing, audio level/RMS matching, determinism, and the §1.5 stimulus QC with the real
yct.confounds code. Synthetic image and speech fixtures only (real LOC images / NAT clips: T-LIC / T-NAT)."""
from __future__ import annotations

import shutil
from collections import Counter

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import refclips58 as R  # noqa: N812

CFG = load_config()
PLAN = R.plan(CFG)
FFMPEG = shutil.which("ffmpeg") is not None


def fam(name):
    return [c for c in PLAN if c.family == name]


def halves(clips):
    return [c for c in clips if c.i % 2 == 0], [c for c in clips if c.i % 2 == 1]


# ---------------------------------------------------------------- schedule
def test_family_counts_match_config():
    n = Counter(c.family for c in PLAN)
    assert dict(n) == CFG["controls"]["refclips"]["families"]
    assert sum(n.values()) == 120
    assert len({c.name for c in PLAN}) == len(PLAN)


def test_seed_formula_is_d071_b():
    import hashlib
    s = f"{CFG['seeds']['refclips']}:MOT:3:0"
    assert R.item_seed(CFG, "MOT", 3, 0) == int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)
    assert R.item_seed(CFG, "MOT", 3, 0) != R.item_seed(CFG, "MOT", 4, 0)


@pytest.mark.parametrize("family,n_per_shift", [("LOC", 5), ("SPK", 5), ("MOT", 4)])
def test_each_half_holds_both_shifts(family, n_per_shift):
    for half in halves(fam(family)):
        assert Counter(c.shift for c in half) == {0: n_per_shift, -1: n_per_shift}


def test_onsets_and_windows_fit_58s():
    for c in PLAN:
        assert c.onsets == [o + c.shift for o in (9.0, 29.0, 49.0)]
        for a, b in R.windows(c, CFG):
            assert a >= 0 and b < R.DUR


def test_loc_latin_rows_per_half_and_categories():
    for half in halves(fam("LOC")):
        assert sorted(Counter(c.extra["latin_row"] for c in half).values()) == [3, 3, 4]
    for c in fam("LOC"):
        assert sorted(e["category"] for e in c.events) == ["body", "face", "place"]
    per_cat = Counter((e["category"], e["image"]) for c in fam("LOC") for e in c.events)
    assert len(per_cat) == 60 and set(per_cat.values()) == {1}   # 20 distinct images per category


def test_loc_scramble_switch_outside_every_window_and_equal_in_twins():
    by = {c.name: c for c in PLAN}
    for c in fam("LOC"):
        tw = by[c.control]
        assert tw.extra["switch_s"] == c.extra["switch_s"] and len(c.extra["switch_s"]) == 2
        assert [e["scramble_seed"] for e in tw.events] == [e["scramble_seed"] for e in c.events]
        for s in c.extra["switch_s"]:
            assert float(s).is_integer()
            assert all(not (a <= s <= b) for a, b in R.windows(c, CFG)), (c.name, s)


def test_mot_direction_and_pattern_balance():
    for half in halves(fam("MOT")):
        d = Counter(e["direction_deg"] for c in half for e in c.events)
        assert d == {deg: 3 for deg in CFG["controls"]["refclips"]["mot_directions_deg"]}
        assert Counter((c.extra["pattern"], c.shift) for c in half) == {
            ("dot", 0): 2, ("dot", -1): 2, ("grating", 0): 2, ("grating", -1): 2}
    for c in fam("MOT"):
        assert len({e["direction_deg"] for e in c.events}) == 3
    ex = {(c.extra["pattern_seed"], e["direction_deg"]) for c in fam("MOT") for e in c.events}
    assert len(ex) == 48 and len({c.extra["pattern_seed"] for c in fam("MOT")}) == 16


def test_twins_and_controls():
    by = {c.name: c for c in PLAN}
    for c in fam("MOT"):
        st = by[c.control]
        assert st.family == "MOT_STAT" and st.extra["pattern_seed"] == c.extra["pattern_seed"]
    for f in ("SPK", "BURST", "FLASH", "TALKFACE"):
        assert {c.control for c in fam(f)} == {"grey_ctrl_00"}
    utt = [e["utterance"] for c in fam("SPK") for e in c.events]
    assert sorted(utt) == list(range(60))


# ---------------------------------------------------------------- images / motion (no encode)
def test_phase_scramble_keeps_amplitude_spectrum():
    img = np.random.default_rng(0).random((64, 64)) * 255
    s = R.phase_scramble(img, 7)
    a0 = np.abs(np.fft.fft2(img - img.mean()))
    a1 = np.abs(np.fft.fft2(s - s.mean())) * img.std() / s.std()
    assert np.allclose(a0, a1, rtol=1e-6, atol=1e-6)
    assert np.allclose(R.phase_scramble(img, 7), s) and not np.allclose(R.phase_scramble(img, 8), s)


def _patch_stats(frames):
    y0, x0 = (R.H - R.PATCH) // 2, (R.W - R.PATCH) // 2
    p = np.array([f[y0:y0 + R.PATCH, x0:x0 + R.PATCH].astype(float) for f in frames])
    return p.mean(axis=(1, 2)), p.std(axis=(1, 2))


@pytest.mark.parametrize("i", [0, 4])     # dot field, grating
def test_mot_luminance_contrast_constant_and_static_twin(i, monkeypatch):
    monkeypatch.setattr(R, "DUR", 12.0)
    c = next(x for x in PLAN if x.family == "MOT" and x.i == i)
    st = next(x for x in PLAN if x.name == c.control)
    fm, fs = R.mot_frames(c), R.mot_frames(st)
    m, s = _patch_stats(fm)
    assert np.all(np.abs(m - m.mean()) <= 0.01 * m.mean()) and np.all(np.abs(s - s.mean()) <= 0.01 * s.mean())
    assert all(np.array_equal(fs[0], f) for f in fs)            # MOT_STAT never moves
    ev = int(c.onsets[0] * R.FPS)
    assert np.array_equal(fm[0], fs[0]) and np.array_equal(fm[ev - 1], fs[0])   # static before the event
    assert not np.array_equal(fm[ev + 5], fm[ev + 4])            # drifts during the event


def test_flash_frames():
    c = fam("FLASH")[0]
    f = R.flash_frames(c)
    ev = int(c.onsets[0] * R.FPS)
    assert f[ev].min() == 255 and f[ev - 1].max() == R.GREY and f[ev + R.FPS].max() == R.GREY


# ---------------------------------------------------------------- audio
def test_k_weighting_matches_bs1770_48k_table():
    from scipy.signal import lfilter
    x = np.random.default_rng(1).standard_normal(48000)
    b1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    a1 = [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    ref = lfilter(b2, a2, lfilter(b1, a1, x))
    assert np.allclose(R.k_weight(x, 48000), ref, atol=1e-6)


def test_bed_is_minus_23_lufs_and_deterministic():
    b = R.bed()
    assert abs(R.integrated_lufs(b) - R.TARGET_LUFS) < 0.05
    assert np.array_equal(b, R.bed())


def _tone(dur, f=220.0):
    t = np.arange(int(dur * R.SR)) / R.SR
    return np.sin(2 * np.pi * f * t) * (1 + 0.5 * np.sin(2 * np.pi * 4 * t)), ["alpha", "beta"]


def _speech(family, u):
    lo, hi = R.UTTER_RANGE[family]
    return _tone(lo + (hi - lo) * ((u % 5 + 0.5) / 5))   # strictly inside the range: the R-11 span trim
    # (D-086 S-24) drops the zero-valued first sample of a sine, so a tone of exactly `lo` falls just below it


def test_speech_replaces_bed_at_matched_rms_and_chunk_sd_within_1pct():
    c = fam("SPK")[0]
    a, rows = R.clip_audio(c, _speech)
    b = R.bed()
    assert abs(a.std() / b.std() - 1) < 0.01
    for e in c.events:
        s0, n = int(e["onset"] * R.SR), int(e["utterance_s"] * R.SR)
        assert abs(np.sqrt(np.mean(a[s0:s0 + n] ** 2)) / np.sqrt(np.mean(b[s0:s0 + n] ** 2)) - 1) < 0.02
    assert len(rows) == 6 and rows[0][1] == c.events[0]["onset"]


def test_utterance_duration_out_of_range_is_refused():
    with pytest.raises(ValueError, match="outside"):
        R.clip_audio(fam("SPK")[0], lambda f, u: _tone(2.0))


def test_visual_clips_carry_the_control_audio_bit_for_bit():
    ctrl, _ = R.clip_audio(fam("GREY_CTRL")[0], None)
    for f in ("FLASH", "MOT", "MOT_STAT", "LOC", "LOC_SCR"):
        a, rows = R.clip_audio(fam(f)[0], None)
        assert np.array_equal(a, ctrl) and rows == []


def test_nat_and_loc_need_their_manifests():
    with pytest.raises(ValueError, match="T-NAT"):
        R.clip_frames(fam("NAT")[0], None)
    with pytest.raises(ValueError, match="T-LIC"):
        R.clip_frames(fam("LOC")[0], None)


# ---------------------------------------------------------------- encode + §1.5 QC (real confounds code)
def _pink(seed):
    """1/f noise (natural-image-like spectrum; a blocky fixture makes the Haar cascade fire on scrambles)."""
    f = np.fft.fftfreq(R.PATCH) * R.PATCH
    amp = np.maximum(1, np.hypot(*np.meshgrid(f, f)))
    noise = np.random.default_rng(seed).standard_normal((R.PATCH, R.PATCH))
    return np.real(np.fft.ifft2(np.fft.fft2(noise) / amp))


def _fixture_images():
    return {cat: [_pink(100 * j + n) for n in range(20)] for j, cat in enumerate(("face", "body", "place"))}


def test_encode_is_deterministic_and_mot_qc_passes(tmp_path, monkeypatch):
    import dataclasses
    monkeypatch.setattr(R, "DUR", 14.0)
    cfg = CFG
    c0 = next(x for x in PLAN if x.family == "MOT" and x.i == 0)
    st0 = next(x for x in PLAN if x.name == c0.control)
    c = dataclasses.replace(c0, events=c0.events[:1])           # 14 s fixture: first event only
    st = dataclasses.replace(st0, events=st0.events[:1])
    r1 = R.build_clip(c, tmp_path / "a", cfg)
    r2 = R.build_clip(c, tmp_path / "b", cfg)
    assert r1["sha256"] == r2["sha256"]
    rs = R.build_clip(st, tmp_path / "a", cfg)
    q = R.stimulus_qc(c, tmp_path / "a" / f"{c.name}.mp4", cfg, (st, tmp_path / "a" / f"{st.name}.mp4"))
    assert q["pass"] and q["checks"]["ratio"] >= 10, q
    assert rs["sha256"]["wav"] == R.build_clip(fam("GREY_CTRL")[0], tmp_path / "c", cfg)["sha256"]["wav"]
    m = R.manifest([r1, rs], {"ffmpeg": "x"}, {"images": "y"}, tmp_path / "m.json")
    assert len(m) == 64 and m == R.manifest([rs, r1], {"ffmpeg": "x"}, {"images": "y"}, tmp_path / "m2.json")


def test_loc_qc_no_face_on_non_face_tr(tmp_path, monkeypatch):
    import dataclasses
    monkeypatch.setattr(R, "DUR", 12.0)
    c0 = next(x for x in PLAN if x.family == "LOC_SCR" and x.i == 0)
    c = dataclasses.replace(c0, events=c0.events[:1])
    R.build_clip(c, tmp_path, CFG, images=_fixture_images())
    q = R.stimulus_qc(c, tmp_path / f"{c.name}.mp4", CFG)
    assert q["checks"]["no_face_elsewhere"] is True and q["pass"]


def test_loc_qc_logic_requires_90pct_face_hits(monkeypatch):
    import yct.confounds.core as cc
    c = next(x for x in PLAN if x.family == "LOC" and x.i == 0)
    face_tr = int(next(e["onset"] for e in c.events if e["category"] == "face"))
    n = int(R.DUR)

    def fake(mp4, grid, cfg, hit=True):
        fa = np.zeros(n)
        if hit:
            fa[face_tr] = 0.2
        return {"face_area_crop_frac": fa, "motion_energy_crop": np.zeros(n)}

    monkeypatch.setattr(cc, "video_features", fake)
    assert R.stimulus_qc(c, "x.mp4", CFG)["pass"]
    with pytest.raises(ValueError, match="past the clip end"):
        monkeypatch.setattr(R, "DUR", 20.0)
        R.stimulus_qc(c, "x.mp4", CFG)
    monkeypatch.setattr(R, "DUR", 58.0)
    monkeypatch.setattr(cc, "video_features", lambda *a: fake(*a, hit=False))
    assert not R.stimulus_qc(c, "x.mp4", CFG)["pass"]

    def leak(mp4, grid, cfg):
        d = fake(mp4, grid, cfg)
        d["face_area_crop_frac"][face_tr + 5] = 0.1
        return d

    monkeypatch.setattr(cc, "video_features", leak)
    assert not R.stimulus_qc(c, "x.mp4", CFG)["pass"]


def test_manifest_records_builder_blob_sha(tmp_path):
    import json
    p = tmp_path / "x.txt"
    p.write_bytes(b"hello\n")
    assert R.git_blob_sha(p) == "ce013625030ba8dba906f756967f9e9ca394464a"   # hash-object of b"hello\n"
    R.manifest([], {}, {}, tmp_path / "m.json")
    got = json.loads((tmp_path / "m.json").read_text())["builder_blob_sha1"]
    assert got == {"refclips58.py": R.git_blob_sha(R.__file__)}
