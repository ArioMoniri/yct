"""D-085 part 2 step 4 (D-089 rates): the SPK / BURST speech build and its frozen QC.

- The build needs the frozen selection record (sha frozen and equal to the committed file) and D-089 frozen.
- Texts never come from git: they are reconstructed from the resolved private queue by the frozen selection
  rules (SPK: leading 3 tokens of one source; BURST: two sources joined; TALKFACE: one source), keyed by the
  public record's source_sha256, and every reconstruction must match its slot exactly (fail closed).
- QC per SPK / BURST clip: the constructive speech gate (outside the windows identical to the GREY_CTRL
  rendering; whole clip = place_speech of the re-synthesised utterances) and, for SPK, the integer span QC
  (+/- 1 sample of the selection span_samples). The T-ENV envelope is descriptive only.
- Nothing written for the public repo carries a sentence text.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run import speech_build as B  # noqa: N812
from yct.tribe_run import speech_corpus as S  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()


def _queue(n: int = 12) -> list[dict]:
    words = ["red", "blue", "green", "small", "round", "cold", "tall", "soft", "dark", "loud", "slow", "wide"]
    out = []
    for j in range(n):
        t = f"The {words[j % 12]} cup sat near item {chr(97 + j)} today."
        out.append({"list": 1, "item": j + 1, "sha256": S.sha_text(t), "text": t})
    return out


def _sel(q: list[dict]) -> dict:
    """A public-shaped record: SPK 2 slots, BURST 1 slot (2 sources), TALKFACE 1 slot."""
    return {"rate_wpm_by_family": {"SPK": 120, "BURST": 175, "TALKFACE": 175},
            "items": {"SPK": [{"slot": 0, "n_words": 3, "source_sha256": [q[0]["sha256"]], "span_samples": 1,
                               "sr": 48000, "rate_wpm": 120},
                              {"slot": 1, "n_words": 3, "source_sha256": [q[2]["sha256"]], "span_samples": 1,
                               "sr": 48000, "rate_wpm": 120}],
                      "BURST": [{"slot": 0, "n_words": None, "source_sha256": [q[3]["sha256"], q[4]["sha256"]],
                                 "span_samples": 1, "sr": 48000, "rate_wpm": 175}],
                      "TALKFACE": [{"slot": 0, "n_words": None, "source_sha256": [q[5]["sha256"]],
                                    "span_samples": 1, "sr": 48000, "rate_wpm": 175}]}}


# ------------------------------------------------------------------ texts from the private queue only
def test_texts_are_reconstructed_by_the_frozen_rules():
    q = _queue()
    t = B.reconstruct_texts(_sel(q), q, spk_words=3)
    assert t["items"]["SPK"][0]["text"] == " ".join(S.tokens(q[0]["text"])[:3])
    assert t["items"]["BURST"][0]["text"] == q[3]["text"] + " " + q[4]["text"]
    assert t["items"]["TALKFACE"][0]["text"] == q[5]["text"]
    assert t["items"]["SPK"][1]["span_samples"] == 1          # numbers carried unchanged


def test_unknown_source_sha_is_a_stop():
    q = _queue()
    s = _sel(q)
    s["items"]["SPK"][0]["source_sha256"] = ["0" * 64]
    with pytest.raises(SystemExit, match="not in the resolved queue"):
        B.reconstruct_texts(s, q, spk_words=3)


def test_wrong_source_count_or_word_count_is_a_stop():
    q = _queue()
    s = _sel(q)
    s["items"]["BURST"][0]["source_sha256"] = [q[3]["sha256"]]
    with pytest.raises(SystemExit, match="sources"):
        B.reconstruct_texts(s, q, spk_words=3, burst_sentences=2)
    s = _sel(q)
    s["items"]["SPK"][0]["n_words"] = 2
    with pytest.raises(SystemExit, match="n_words"):
        B.reconstruct_texts(s, q, spk_words=3)


def test_slots_must_be_contiguous_in_order():
    q = _queue()
    s = _sel(q)
    s["items"]["SPK"][1]["slot"] = 5
    with pytest.raises(SystemExit, match="slot"):
        B.reconstruct_texts(s, q, spk_words=3)


def test_every_planned_event_maps_to_a_selection_slot():
    sel = json.loads((ROOT / B.SEL_PATH).read_text())
    clips = [c for c in R.plan(CFG) if c.family in ("SPK", "BURST", "TALKFACE")]
    m = B.utterance_map(clips, sel)
    assert len(m) == 60 + 15 + 3
    assert m[("spk_19", 2)] == ("SPK", 59) and m[("burst_04", 2)] == ("BURST", 14)
    assert m[("talkface_00", 1)] == ("TALKFACE", 1)


def test_utterance_map_refuses_a_short_selection():
    sel = json.loads((ROOT / B.SEL_PATH).read_text())
    sel["items"]["SPK"] = sel["items"]["SPK"][:59]
    clips = [c for c in R.plan(CFG) if c.family == "SPK"]
    with pytest.raises(SystemExit, match="no selection slot"):
        B.utterance_map(clips, sel)


# ------------------------------------------------------------------ preconditions
def test_the_committed_selection_record_is_accepted():
    sel = B.check_selection_record(CFG, ROOT)
    assert sel["rate_wpm_by_family"] == {"SPK": 120, "BURST": 175, "TALKFACE": 175}


def test_selection_record_refused_unless_frozen_and_equal(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["frozen"] = [f for f in cfg["frozen"] if f["key"] != B.SEL_KEY]
    with pytest.raises(SystemExit, match="not frozen"):
        B.check_selection_record(cfg, ROOT)
    p = tmp_path / B.SEL_PATH
    p.parent.mkdir(parents=True)
    p.write_text((ROOT / B.SEL_PATH).read_text() + " ")
    with pytest.raises(SystemExit, match="sha256"):
        B.check_selection_record(CFG, tmp_path)


def test_d089_must_be_frozen():
    cfg = copy.deepcopy(CFG)
    cfg["frozen"] = [f for f in cfg["frozen"] if f["key"] != "controls.refclips_d089"]
    with pytest.raises(SystemExit, match="refclips_d089"):
        B.require_d089(cfg)
    B.require_d089(CFG)


def test_build_families_are_grey_ctrl_spk_burst_only():
    assert B.BUILD_FAMILIES == ("GREY_CTRL", "SPK", "BURST")


# ------------------------------------------------------------------ QC
class FakeSynth:
    """Deterministic, 'verified' tone bursts whose length depends on the word count."""

    verified = {"fake": True}

    def __call__(self, text: str, rate_wpm: int | None = None):
        if rate_wpm is None:
            raise SystemExit("rate required")
        n = len(S.tokens(text))
        dur = n * 60.0 / rate_wpm * (0.8 if n <= 3 else 0.5)
        t = np.arange(int(dur * 48000)) / 48000
        x = 0.3 * np.sin(2 * np.pi * 220 * t)
        pad = np.zeros(2400)
        return np.concatenate([pad, x, pad]), 48000


def _spk_setup():
    cfg = copy.deepcopy(CFG)
    q = _queue(12)
    clip = R.Clip("SPK", 0, 0, [10.0, 26.0, 42.0], [{"k": k, "onset": o, "utterance": k}
                                                     for k, o in enumerate([10.0, 26.0, 42.0])], "grey_ctrl_00")
    synth = FakeSynth()
    items = []
    for k in range(3):
        text = " ".join(S.tokens(q[k]["text"])[:3])
        x, sr = synth(text, rate_wpm=120)
        s0, s1 = S.speech_span(x, sr, -40.0)
        items.append({"slot": k, "n_words": 3, "source_sha256": [q[k]["sha256"]], "span_samples": s1 - s0,
                      "sr": sr, "rate_wpm": 120, "text": text})
    sel = {"rate_wpm_by_family": {"SPK": 120, "BURST": 175, "TALKFACE": 175},
           "items": {"SPK": items, "BURST": [], "TALKFACE": []}}
    prov = R.make_speech_provider(S.build_raw_speech(cfg, sel, synth))
    audio, _rows = R.clip_audio(clip, prov)
    from yct.tribe_run.refclips_qc85 import pcm16

    rendered = {"spk_00": pcm16(audio), "grey_ctrl_00": pcm16(R.bed())}
    return cfg, clip, sel, prov, rendered


def test_speech_rows_pass_on_a_correct_build():
    cfg, clip, sel, prov, rendered = _spk_setup()
    rows = B.speech_rows([clip], rendered, prov, sel, cfg)
    r = rows[0]
    assert r["pass"], r
    assert r["checks"]["speech_gate"]["pass"] and r["checks"]["spk_span"]["pass"]


def test_speech_rows_fail_on_a_sample_changed_outside_the_windows():
    cfg, clip, sel, prov, rendered = _spk_setup()
    rendered["spk_00"] = rendered["spk_00"].copy()
    rendered["spk_00"][100] += 1
    r = B.speech_rows([clip], rendered, prov, sel, cfg)[0]
    assert not r["pass"] and not r["checks"]["speech_gate"]["outside_identical"]


def test_speech_rows_fail_on_a_span_mismatch():
    cfg, clip, sel, prov, rendered = _spk_setup()
    sel["items"]["SPK"][1]["span_samples"] += 5
    r = B.speech_rows([clip], rendered, prov, sel, cfg)[0]
    assert not r["pass"] and r["checks"]["spk_span"]["mismatch"] == [1]


def test_envelope_is_descriptive_only():
    cfg, clip, sel, prov, rendered = _spk_setup()
    env = B.envelope_descriptive(clip, np.asarray(rendered["spk_00"], np.float64) / 32768.0, 48000, cfg)
    assert env["gating"] is False and "event_nonevent_ratio" in env and "point_biserial_r" in env


def test_public_outputs_carry_no_text():
    cfg, clip, sel, prov, rendered = _spk_setup()
    rows = B.speech_rows([clip], rendered, prov, sel, cfg)
    blob = json.dumps(rows, default=float)
    for it in sel["items"]["SPK"]:
        assert it["text"] not in blob
    B.assert_no_text(rows, sel)
    with pytest.raises(SystemExit, match="text"):
        B.assert_no_text({"x": sel["items"]["SPK"][0]["text"]}, sel)


def test_selection_sha_helper_matches_config():
    want = CFG["controls"]["refclips_artifacts"]["speech_selection_sha256"]
    assert hashlib.sha256((ROOT / B.SEL_PATH).read_bytes()).hexdigest() == want
