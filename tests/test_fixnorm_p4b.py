"""R-11 / D-086 FIX-NORM-P4B (normalisation audit): blocking fixes before the P4b reference campaign.

S-23/S-24 speech span trim + band-limited resampling + span-based RMS/length/word timing; BS.1770 reference
value; M-12b one spatial-standardisation path; A-18 (owner Q1) Legendre-1 drift in the P4b(a) partial-out;
S-22 bt709/tv colour tags on the reference clips; X-02 toolchain record.
"""
import ast
from pathlib import Path

import numpy as np
import pytest
import yaml

from yct.tribe_run import refclips58 as R

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())


# ---------------------------------------------------------------- S-23 / S-24 speech
def _tone(sec: float, sr: int, amp: float = 0.5, f: float = 220.0) -> np.ndarray:
    t = np.arange(int(sec * sr)) / sr
    return amp * np.sin(2 * np.pi * f * t)


def _padded(sec: float, pad: float, sr: int = R.SR) -> np.ndarray:
    z = np.zeros(int(pad * sr))
    return np.concatenate([z, _tone(sec, sr), z])


def test_trim_to_span_drops_silence_padding():
    x = _padded(1.2, 0.3)
    y = R.trim_to_span(x, R.SR)
    assert abs(len(y) / R.SR - 1.2) < 2e-3
    assert np.abs(y[0]) >= 10 ** (-40 / 20) and np.abs(y[-1]) >= 10 ** (-40 / 20)


def test_trim_uses_the_corpus_span_threshold():
    assert R.SPAN_DBFS == CFG["controls"]["refclips_d085"]["speech"]["span_dbfs"]


def test_bandlimited_resample_is_polyphase_not_nearest():
    from scipy.signal import resample_poly

    x = _tone(0.5, 22050, f=3000.0)
    y = R.resample_bandlimited(x, 22050, R.SR)
    assert np.allclose(y, resample_poly(x, 320, 147))
    assert abs(len(y) - round(len(x) * R.SR / 22050)) <= 1


def test_speech_provider_wrapper_resamples_then_trims():
    def raw(family, idx):
        z = np.zeros(int(0.2 * 22050))
        return np.concatenate([z, _tone(1.25, 22050), z]), 22050, ["one", "two", "three"]
    prov = R.make_speech_provider(raw)
    wav, words = prov("SPK", 0)
    assert abs(len(wav) / R.SR - 1.25) < 3e-3
    assert words == ["one", "two", "three"]


def test_clip_audio_length_gate_and_word_times_on_the_span():
    plan = [c for c in R.plan(CFG) if c.family == "SPK"]
    clip = plan[0]

    def speech(family, idx):           # a provider that forgot to trim: 0.5 s padding each side
        return _padded(1.2, 0.5), ["alpha", "beta", "gamma"]
    audio, rows = R.clip_audio(clip, speech)
    e = clip.events[0]
    assert abs(e["utterance_s"] - 1.2) < 2e-3          # span length, not 2.2 s padded length
    w0 = [r for r in rows if r[3] == e["k"]]
    assert abs(w0[0][1] - e["onset"]) < 1e-9
    assert abs(w0[-1][1] + w0[-1][2] - (e["onset"] + 1.2)) < 2e-3


def test_rms_match_uses_the_span():
    base = R.bed()
    u = _tone(1.2, R.SR)
    t0 = 10.0
    y = R.place_speech(base, R.trim_to_span(_padded(1.2, 0.5), R.SR), t0)
    s0 = int(round(t0 * R.SR))
    f = int(R.XFADE_S * R.SR)
    seg = base[s0 + f:s0 + len(u) - f]
    got = y[s0 + f:s0 + len(u) - f]
    assert abs(np.sqrt(np.mean(got ** 2)) / np.sqrt(np.mean(seg ** 2)) - 1) < 0.02


def test_bs1770_reference_value():
    """997 Hz full-scale sine, mono: integrated loudness = -3.01 LUFS (ITU-R BS.1770-4 reference)."""
    x = _tone(5.0, R.SR, amp=1.0, f=997.0)
    assert abs(R.integrated_lufs(x) - (-3.01)) < 0.05


# ---------------------------------------------------------------- M-12b
def test_enh002_standardise_delegates_to_networks():
    from yct.features.networks import spatial_standardize
    from yct.tribe_run.enh002 import standardise

    rng = np.random.default_rng(0)
    pred = rng.standard_normal((6, 50))
    med = np.zeros(50, bool)
    med[:5] = True
    a, b = standardise(pred, med), spatial_standardize(pred, med)
    assert np.allclose(a[:, ~med], b[:, ~med])
    with pytest.raises(ValueError):
        standardise(np.where(np.arange(50) == 7, np.nan, pred), med)


def _defs_and_imports(path: Path):
    tree = ast.parse(path.read_text())
    defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    imports = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            imports |= {f"{n.module}.{a.name}" for a in n.names}
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    kw_dstd = any(isinstance(n, ast.keyword) and n.arg == "d_std" for n in ast.walk(tree))
    return defs, imports, calls, kw_dstd


def test_only_networks_defines_spatial_standardisation():
    for p in (ROOT / "src" / "yct").rglob("*.py"):
        defs, *_ = _defs_and_imports(p)
        rel = p.relative_to(ROOT).as_posix()
        own = {d for d in defs if d in ("spatial_standardize", "spatial_standardise")}
        assert not own or rel == "src/yct/features/networks.py", rel


def test_enh002_standardise_calls_spatial_standardize():
    tree = ast.parse((ROOT / "src/yct/tribe_run/enh002.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "standardise")
    names = {getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "spatial_standardize" in names
    assert not any(isinstance(c, ast.Attribute) and c.attr == "std" for c in ast.walk(fn))


def test_every_d_std_producer_uses_m12():
    """Any module that builds KernelInputs(d_std=...) must import networks.spatial_standardize (M-12b)."""
    for p in list((ROOT / "src" / "yct").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        defs, imports, calls, kw = _defs_and_imports(p)
        if kw and p.name != "kernels.py":
            assert "yct.features.networks.spatial_standardize" in imports, p


# ---------------------------------------------------------------- A-18 drift (owner Q1)
def test_partial_out_nuisance_config():
    assert CFG["controls"]["partial_out_nuisance"] == ["intercept", "legendre_1"]


def test_legendre_design():
    from yct.controls.partial import nuisance_design

    X = nuisance_design(41, ["intercept", "legendre_1"])
    assert X.shape == (41, 2)
    assert np.allclose(X[:, 0], 1)
    assert np.isclose(X[0, 1], -1) and np.isclose(X[-1, 1], 1) and np.isclose(X[:, 1].mean(), 0)
    with pytest.raises(ValueError):
        nuisance_design(41, ["intercept", "cubic"])


def test_drift_is_partialled_out():
    from yct.controls.partial import partial_r

    n = 40
    t = np.linspace(-1, 1, n)
    rng = np.random.default_rng(1)
    target = t + 0.01 * rng.standard_normal(n)
    y = 3 * t + rng.standard_normal(n) * 0.01
    other = rng.standard_normal((n, 1))
    r_drift = partial_r(y, target, other, ["intercept", "legendre_1"])
    r_int = partial_r(y, target, other, ["intercept"])
    assert r_int > 0.9 and abs(r_drift) < 0.5


def test_partial_r_matches_residual_correlation():
    from yct.controls.partial import nuisance_design, partial_r

    rng = np.random.default_rng(2)
    n = 40
    y, x, o = rng.standard_normal(n), rng.standard_normal(n), rng.standard_normal((n, 2))
    N = np.column_stack([nuisance_design(n, ["intercept", "legendre_1"]), o])
    res = lambda v: v - N @ np.linalg.lstsq(N, v, rcond=None)[0]   # noqa: E731
    want = np.corrcoef(res(y), res(x))[0, 1]
    assert np.isclose(partial_r(y, x, o, ["intercept", "legendre_1"]), want)


def test_partial_r_refuses_nonfinite_and_rank_deficiency():
    from yct.controls.partial import partial_r

    n = 20
    t = np.linspace(-1, 1, n)
    with pytest.raises(ValueError):
        partial_r(np.full(n, np.nan), t, np.zeros((n, 0)), ["intercept"])
    with pytest.raises(ValueError):
        partial_r(t ** 2, t, t[:, None], ["intercept", "legendre_1"])


# ---------------------------------------------------------------- S-22 colour tags
def test_reference_encode_carries_bt709_tv_tags(monkeypatch, tmp_path):
    seen = []

    def fake_run(cmd, *a, **k):
        seen.append(cmd)
        out = Path(cmd[-1])
        out.write_bytes(b"x")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    frames = [np.full((R.H, R.W), R.GREY, np.uint8)]
    R.encode(frames, np.zeros(R.SR), [], tmp_path, "c", CFG)
    enc = seen[0]
    c = CFG["normalize"]["color"]
    for flag, val in (("-colorspace", c["matrix"]), ("-color_primaries", c["primaries"]),
                      ("-color_trc", c["transfer"]), ("-color_range", c["range"])):
        assert enc[enc.index(flag) + 1] == val


def test_rebuild_compares_mp4_by_decoded_stream():
    import importlib.util

    spec = importlib.util.spec_from_file_location("rb", ROOT / "scripts" / "refclips_build.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    recs = {"c": {"sha256": {"mp4": "NEW", "wav": "w", "tsv": "t"}, "decoded_sha256": "D"}}
    assert rb.rebuild_mismatches(recs, {"c.mp4": "OLD", "c.wav": "w", "c.tsv": "t"}, {"c.mp4": "D"}) == []
    assert rb.rebuild_mismatches(recs, {"c.mp4": "OLD", "c.wav": "w", "c.tsv": "t"}, {"c.mp4": "X"}) == ["c.mp4"]
    assert rb.rebuild_mismatches(recs, {"c.mp4": "OLD", "c.wav": "w", "c.tsv": "t"}, {}) == ["c.mp4"]


# ---------------------------------------------------------------- X-02 toolchain record
def test_toolchain_record_shape(monkeypatch):
    from yct.provenance import toolchain_record

    rec = toolchain_record(run=lambda cmd: "ffmpeg version 6.1.1 Copyright\nlibavcodec 60.31.102\n",
                           which=lambda n: None)
    assert rec["ffmpeg_version"].startswith("ffmpeg version 6.1.1")
    assert "libavcodec" in rec["libs"]
    assert rec["ffmpeg_sha256"] is None
