"""D-089 v2 (council REVISE wf_f75444e5-978; owner 2026-11-23 "120 wpm by rule" and "Final stop, report it").

- The SPK rate is chosen by a rule stated before any synthesis and computed only from the committed v1 STOP
  spans: the slowest 5-wpm step (below 175) whose linear projection puts <= 5% of spans above 1.5 s -> 120.
- A queue exhaustion in ANY family (SPK, BURST, TALKFACE) is a final STOP: the speech control is reported as
  failed and every analysis that needs it is dropped and named (stated before the re-run).
- The build condition is code: EspeakSynth refuses a missing rate when the spec is per-family; the build takes
  its rates from the frozen selection record and asserts they equal effective_spec; the clip manifest records
  the rate per clip; QC re-measures every SPK span (in [1.0, 1.5] s and equal to the selection span +/- 1 sample).
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.config_schema import validate_config
from yct.tribe_run import speech_corpus as S  # noqa: N812
from yct.tribe_run.espeak_engine import EspeakSynth

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
D089 = CFG["controls"]["refclips_d089"]
STOP_REC = ROOT / "outputs/runs/d085p2_selection/speech_selection_v1_STOP.json"
SR = 48000


def _v1_spans() -> list[float]:
    d = json.loads(STOP_REC.read_text())
    return [x["span_s"] for x in d["items"]["SPK"]] + [r["span_s"] for r in d["rejects"] if r["family"] == "SPK"]


# ------------------------------------------------------------------ the rate rule
def test_rule_is_stated_in_config_and_points_at_the_committed_stop_record():
    r = D089["spk_rate_rule"]
    assert r["source"] == "outputs/runs/d085p2_selection/speech_selection_v1_STOP.json"
    assert r["source_sha256"] == hashlib.sha256(STOP_REC.read_bytes()).hexdigest()
    assert r["step_wpm"] == 5 and r["max_too_long_frac"] == 0.05 and r["range_s"] == [1.0, 1.5]
    assert r["projection"] == "linear" and r["from_wpm"] == 175


def test_rule_recomputed_from_the_stop_record_gives_120():
    r = D089["spk_rate_rule"]
    got = S.spk_rate_by_rule(_v1_spans(), from_wpm=r["from_wpm"], step=r["step_wpm"],
                             max_too_long=r["max_too_long_frac"], rng=tuple(r["range_s"]))
    assert got == 120
    assert D089["rate_wpm_by_family"] == {"SPK": got, "BURST": 175, "TALKFACE": 175}


def test_rule_boundary_115_is_over_and_120_is_within():
    sp = _v1_spans()
    assert S.expected_spk_at_rate(sp, 175, 120, (1.0, 1.5))["too_long"] / len(sp) <= 0.05
    assert S.expected_spk_at_rate(sp, 175, 115, (1.0, 1.5))["too_long"] / len(sp) > 0.05


def test_sensitivity_projection_at_three_slowdown_exponents():
    """Disclosed in d089_v2: pass counts at 120 wpm if espeak slows down by (175/120)^e, e in {1, 0.8, 0.6}."""
    sens = S.spk_sensitivity(_v1_spans(), 175, 120, (1.0, 1.5), (1.0, 0.8, 0.6))
    assert [s["exponent"] for s in sens] == [1.0, 0.8, 0.6]
    assert sens[0]["pass"] == 298
    assert all(0 < s["pass"] < 410 for s in sens)


def test_schema_pins_spk_at_the_rule_rate():
    for bad in (140, 125, 115):
        c = copy.deepcopy(CFG)
        c["controls"]["refclips_d089"]["rate_wpm_by_family"]["SPK"] = bad
        with pytest.raises(ValueError):
            validate_config(c)


# ------------------------------------------------------------------ final STOP in every family
def test_final_stop_covers_every_family_and_states_the_downstream_meaning():
    assert D089["on_exhausted"] == "final_stop_owner"
    assert D089["final_stop_families"] == ["SPK", "BURST", "TALKFACE"]
    fs = D089["on_final_stop"]
    assert fs["control_status"] == "failed"
    assert fs["dependent_analyses"] == "dropped_and_named_in_report"
    assert fs["amendment"] is False


def _fake(dur_by_family_rate):
    calls = []

    def synth(text, rate_wpm=None):
        calls.append((text, rate_wpm))
        d = dur_by_family_rate(text, rate_wpm)
        x = np.zeros(int(SR * (d + 0.4)))
        x[int(0.2 * SR):int(0.2 * SR) + int(round(d * SR))] = 0.3
        return x, SR
    synth.verified = {"fake": "pin"}
    synth.calls = calls
    return synth


def _queue(n):
    return [{"text": f"w{j}a w{j}b w{j}c w{j}d w{j}e.", "sha256": f"{j:064x}"} for j in range(n)]


def test_exhaustion_in_burst_is_a_stop_with_a_per_family_record():
    spec = dict(S.effective_spec(CFG), counts={"SPK": 2, "BURST": 2, "TALKFACE": 1})
    synth = _fake(lambda t, r: 1.2 if r == 120 else 3.0)          # BURST never reaches 4.0 s
    with pytest.raises(S.CorpusStopError) as e:
        S.select(_queue(10), synth, spec)
    p = e.value.partial
    assert p["family"] == "BURST"
    assert p["queue_used_by_family"]["SPK"] == 2 and p["queue_used_by_family"]["BURST"] == 8
    assert p["queue_used_by_family"]["TALKFACE"] == 0
    assert p["pass_rates"]["BURST"] == {"tried": 4, "kept": 0}


def test_stop_record_is_numbers_only_with_wilson_and_stop_position():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import speech_select as SS  # noqa: N812
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    spec = dict(S.effective_spec(CFG), counts={"SPK": 1, "BURST": 1, "TALKFACE": 1})
    synth = _fake(lambda t, r: 1.2 if r == 120 else 3.0)
    with pytest.raises(S.CorpusStopError) as e:
        S.select(_queue(5), synth, spec)
    rec = SS.stop_record(e.value.partial, synth.verified, "c" * 64, "0" * 40)
    assert rec["stop"] == "queue_exhausted" and rec["final_stop"] is True
    assert rec["stopped_at"]["family"] == "BURST" and rec["stopped_at"]["queue_position"] == 5
    assert set(rec["queue_used_by_family"]) == {"SPK", "BURST", "TALKFACE"}
    for f in ("SPK", "BURST", "TALKFACE"):
        assert set(rec["pass_rates"][f]) >= {"tried", "kept", "rate", "wilson95"}
    assert '"text"' not in json.dumps(rec)                         # numbers and ids only


# ------------------------------------------------------------------ selection record carries the rate
def test_selection_records_rate_per_item_and_queue_used_by_family():
    spec = dict(S.effective_spec(CFG), counts={"SPK": 2, "BURST": 1, "TALKFACE": 1})
    synth = _fake(lambda t, r: 1.2 if r == 120 else (5.0 if t.count(".") == 2 else 3.0))
    sel = S.select(_queue(20), synth, spec)
    assert all(it["rate_wpm"] == 120 for it in sel["items"]["SPK"])
    assert all(it["rate_wpm"] == 175 for f in ("BURST", "TALKFACE") for it in sel["items"][f])
    assert sum(sel["queue_used_by_family"].values()) == sel["queue_used"]


def test_no_v1_keep_enters_without_remeasurement():
    """Every D-089 item was synthesised at the D-089 rate in this run; v1 keeps are never copied in."""
    v1 = json.loads(STOP_REC.read_text())
    v1_ids = {x["source_sha256"][0] for x in v1["items"]["SPK"]}
    q = [{"text": f"a{j} b{j} c{j} d{j}.", "sha256": sha} for j, sha in enumerate(sorted(v1_ids))]
    spec = dict(S.effective_spec(CFG), counts={"SPK": 3, "BURST": 0, "TALKFACE": 0})
    synth = _fake(lambda t, r: 1.2)
    sel = S.select(q, synth, spec)
    measured = {t for t, _ in synth.calls}
    for it in sel["items"]["SPK"]:
        assert it["text"] in measured and it["rate_wpm"] == 120
    S.check_no_carry_over(sel, v1)                                 # passes: all re-measured
    bad = copy.deepcopy(sel)
    bad["items"]["SPK"].append({**v1["items"]["SPK"][0]})       # a copied v1 keep (no rate_wpm)
    with pytest.raises(SystemExit, match="carry-over"):
        S.check_no_carry_over(bad, v1)


# ------------------------------------------------------------------ the build path
def _synth_obj(spec):
    s = EspeakSynth.__new__(EspeakSynth)
    s.spec = spec
    s.paths = {"binary": Path("/usr/bin/espeak-ng")}
    return s


def test_espeak_refuses_missing_rate_when_spec_is_per_family():
    s = _synth_obj(S.effective_spec(CFG))
    with pytest.raises(SystemExit, match="rate_wpm"):
        s.args("x y z")
    a = s.args("x y z", rate_wpm=120)
    assert a[a.index("-s") + 1] == "120"
    base = _synth_obj(dict(CFG["controls"]["refclips_d085"]["speech"]))
    a = base.args("x y z")                                         # frozen pre-D-089 path unchanged
    assert a[a.index("-s") + 1] == "175"


def _sel_record(rates=None):
    return {"rate_wpm_by_family": dict(rates or D089["rate_wpm_by_family"]),
            "items": {"SPK": [{"slot": 0, "text": "a b c", "span_s": 1.2, "rate_wpm": 120}],
                      "BURST": [{"slot": 0, "text": "a. b.", "span_s": 5.0, "rate_wpm": 175}],
                      "TALKFACE": [{"slot": 0, "text": "a.", "span_s": 2.0, "rate_wpm": 175}]}}


def test_build_rates_come_from_the_selection_record_and_must_equal_effective_spec():
    assert S.build_rates(CFG, _sel_record()) == {"SPK": 120, "BURST": 175, "TALKFACE": 175}
    with pytest.raises(SystemExit, match="effective_spec"):
        S.build_rates(CFG, _sel_record({"SPK": 140, "BURST": 175, "TALKFACE": 175}))
    rec = _sel_record()
    rec["items"]["SPK"][0]["rate_wpm"] = 175
    with pytest.raises(SystemExit, match="rate_wpm"):
        S.build_rates(CFG, rec)


def test_build_raw_speech_sends_the_spk_rate_never_175():
    sent = []

    def synth(text, rate_wpm=None):
        sent.append(rate_wpm)
        x = np.zeros(SR)
        x[100:100 + int(1.2 * SR) if rate_wpm == 120 else 100 + SR // 2] = 0.3
        return x, SR
    synth.verified = {"fake": "pin"}
    raw = S.build_raw_speech(CFG, _sel_record(), synth)
    x, sr, words = raw("SPK", 0)
    assert sent == [120] and sr == SR and words == ["a", "b", "c"]
    raw("BURST", 0)
    assert sent[-1] == 175


def test_manifest_records_rate_per_clip():
    m = S.clip_speech_meta("spk_03", "SPK", CFG, _sel_record())
    assert m == {"clip": "spk_03", "family": "SPK", "rate_wpm": 120, "rule": "D-089"}
    assert S.clip_speech_meta("burst_00", "BURST", CFG, _sel_record())["rate_wpm"] == 175


def test_spk_span_qc_remeasures_and_matches_selection_within_one_sample():
    from yct.tribe_run import refclips_qc85 as Q

    def utter(d):
        return np.full(int(round(d * SR)), 0.3)
    ok = Q.spk_span_qc([(1.2, utter(1.2)), (1.05, utter(1.05))], sr=SR, rng=(1.0, 1.5), tol_samples=1)
    assert ok["pass"] is True and ok["tol_samples"] == 1
    off = Q.spk_span_qc([(1.2, utter(1.21))], sr=SR, rng=(1.0, 1.5), tol_samples=1)
    assert off["pass"] is False and off["mismatch"] == [0]
    out = Q.spk_span_qc([(1.6, utter(1.6))], sr=SR, rng=(1.0, 1.5), tol_samples=1)
    assert out["pass"] is False and out["out_of_range"] == [0]


def test_qc_tolerance_is_stated_in_config():
    assert D089["build_qc"] == {"spk_span_tol_samples": 1, "span_dbfs": -40, "sr": 48000, "gating": True}


# ------------------------------------------------------------------ descriptive envelope-rate check (neuro Q1)
def test_modulation_peak_is_descriptive_only():
    from yct.confounds import modspec

    sr = 1000
    t = np.arange(0, 4, 1 / sr)
    env = 1 + np.sin(2 * np.pi * 4.0 * t)
    r = modspec.peak_modulation_hz(env, sr)
    assert abs(r["peak_hz"] - 4.0) < 0.3 and r["gating"] is False
