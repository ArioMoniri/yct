"""D-089 draft (owner 2026-11-23 "Slower rate for SPK", post hoc after the D-085 part-2 selection STOP):
SPK speaks its 3-word leads at 120 wpm (D-089 v2: the rule-derived rate, replacing the draft 140); BURST and
TALKFACE stay at the frozen 175 wpm. Everything else in the frozen D-085 part-2 speech key is unchanged and
the frozen key itself is never edited: the rates live in a new
`controls.refclips_d089` block layered over it by `speech_corpus.effective_spec`. Selection re-runs from queue
position 0 (no carry-over of the 31 v1 keeps) and refuses to run until D-089 is frozen."""
from __future__ import annotations

import copy
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
BASE = CFG["controls"]["refclips_d085"]["speech"]
STOP_REC = ROOT / "outputs/runs/d085p2_selection/speech_selection_v1_STOP.json"


def _with_frozen(cfg, *keys):
    c = copy.deepcopy(cfg)
    c["frozen"] = list(c.get("frozen", [])) + [{"key": k, "frozen_at": "0" * 40} for k in keys]
    return c


def test_d089_block_rates_and_policy():
    assert D089["decision"] == "D-089" and D089["post_hoc"] is True
    assert D089["amends"] == ["D-085"]
    assert D089["rate_wpm_by_family"] == {"SPK": 120, "BURST": 175, "TALKFACE": 175}
    assert D089["carry_over_v1_keeps"] is False and D089["restart_queue_at"] == 0
    assert D089["on_exhausted"] == "final_stop_owner"     # no third amendment
    assert D089["trigger"] == "outputs/runs/d085p2_selection/STOP_NOTE.md"


def test_frozen_d085_speech_key_is_not_edited():
    assert BASE["rate_wpm"] == 175                         # frozen key unchanged; D-089 layers over it
    assert "rate_wpm_by_family" not in BASE


def test_effective_spec_layers_rates_and_keeps_everything_else():
    eff = S.effective_spec(CFG)
    assert eff["rate_wpm_by_family"] == {"SPK": 120, "BURST": 175, "TALKFACE": 175}
    for k, v in BASE.items():
        assert eff[k] == v                                 # corpus, order, lexicon, span gate, ranges, pin
    assert eff["rate_wpm"] == 175


def test_effective_spec_without_d089_is_the_frozen_key():   # pre-D-089 config copies
    c = copy.deepcopy(CFG)
    del c["controls"]["refclips_d089"]
    assert S.effective_spec(c) == BASE


def test_schema_refuses_a_changed_burst_or_talkface_rate_or_missing_family():
    for bad in ({"SPK": 120, "BURST": 160, "TALKFACE": 175}, {"SPK": 120, "BURST": 175}):
        c = copy.deepcopy(CFG)
        c["controls"]["refclips_d089"]["rate_wpm_by_family"] = bad
        with pytest.raises(ValueError):           # pydantic ValidationError is a ValueError
            validate_config(c)


def _fake(durs_by_rate):
    """synth(text, rate_wpm) -> wav whose -40 dBFS span is durs_by_rate[rate](text)."""
    sr = 16000
    calls = []

    def synth(text, rate_wpm=None):
        calls.append((text, rate_wpm))
        d = durs_by_rate[rate_wpm](text)
        x = np.zeros(int(sr * (d + 0.4)))
        x[int(0.2 * sr):int(0.2 * sr) + int(round(d * sr))] = 0.3
        return x, sr
    synth.verified = {"fake": "pin"}
    synth.calls = calls
    return synth


def _queue(n):
    return [{"text": f"w{j}a w{j}b w{j}c w{j}d w{j}e.", "sha256": f"{j:064x}"} for j in range(n)]


def test_select_passes_the_family_rate_to_the_synth():
    spec = dict(S.effective_spec(CFG), counts={"SPK": 2, "BURST": 1, "TALKFACE": 1})
    durs = {120: lambda t: 1.2, 175: lambda t: 5.0 if t.count(".") == 2 else 3.0}
    synth = _fake(durs)
    sel = S.select(_queue(50), synth, spec)
    fam_rate = [r for _, r in synth.calls]
    assert fam_rate[:2] == [120, 120] and set(fam_rate[2:]) == {175}
    assert len(sel["items"]["SPK"]) == 2 and sel["rate_wpm_by_family"] == spec["rate_wpm_by_family"]


def test_select_without_by_family_rates_calls_the_synth_with_text_only():
    spec = dict(BASE, counts={"SPK": 1, "BURST": 0, "TALKFACE": 0})
    seen = []

    def synth(text):
        seen.append(text)
        x = np.zeros(16000 * 2)
        x[3200:3200 + 19200] = 0.3
        return x, 16000
    synth.verified = {"fake": "pin"}
    S.select(_queue(3), synth, spec)
    assert len(seen) == 1


def test_selection_restarts_at_queue_zero_with_no_carry_over():
    spec = dict(S.effective_spec(CFG), counts={"SPK": 1, "BURST": 0, "TALKFACE": 0})
    synth = _fake({120: lambda t: 1.2, 175: lambda t: 3.0})
    sel = S.select(_queue(5), synth, spec)
    assert synth.calls[0][0] == "w0a w0b w0c"              # position 0, not after the v1 keeps
    assert sel["queue_used"] == 1


def test_espeak_args_use_the_given_rate():
    s = EspeakSynth.__new__(EspeakSynth)
    s.spec = dict(BASE)
    s.paths = {"binary": Path("/usr/bin/espeak-ng")}
    a = s.args("x y z", rate_wpm=140)
    assert a[a.index("-s") + 1] == "140"
    a = s.args("x y z")
    assert a[a.index("-s") + 1] == "175"


def test_speech_select_refuses_until_d089_frozen():
    sys_path = str(ROOT / "scripts")
    import sys
    sys.path.insert(0, sys_path)
    try:
        import speech_select as SS  # noqa: N812
    finally:
        sys.path.remove(sys_path)
    with pytest.raises(SystemExit, match="D-089"):
        SS.require_d089(CFG if not any(f["key"] == "controls.refclips_d089" for f in CFG["frozen"]) else
                        {**CFG, "frozen": [f for f in CFG["frozen"] if f["key"] != "controls.refclips_d089"]})
    SS.require_d089(_with_frozen(CFG, "controls.refclips_d089"))


def test_expected_pass_rate_from_the_v1_stop_record():
    """Numbers only: v1 spans (175 wpm) scaled linearly by 175/140; the v1 draft quoted these values (the
    superseded 140 wpm option, kept as the disclosed history)."""
    d = json.loads(STOP_REC.read_text())
    spans = [x["span_s"] for x in d["items"]["SPK"]]
    spans += [r["span_s"] for r in d["rejects"] if r["family"] == "SPK"]
    assert len(spans) == 410
    est = S.expected_spk_at_rate(spans, 175, 140, (1.0, 1.5))
    assert est["n"] == 410 and est["pass"] == 184 and est["too_short"] == 224 and est["too_long"] == 2
    assert abs(est["rate"] - 184 / 410) < 1e-9
