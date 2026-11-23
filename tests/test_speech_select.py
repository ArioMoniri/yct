"""D-085 part 2 step 2: the selection runner (public record numbers only, private log with texts)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("speech_select", ROOT / "scripts" / "speech_select.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_wilson_interval():
    m = _mod()
    lo, hi = m.wilson(4, 40)
    assert lo == pytest.approx(0.0396, abs=1e-3) and hi == pytest.approx(0.2306, abs=1e-3)
    assert m.wilson(0, 0) == (None, None)


def test_public_record_has_no_text_and_carries_rates():
    m = _mod()
    sel = {"items": {"SPK": [{"slot": 0, "text": "a b c", "n_words": 3, "span_s": 1.2,
                              "source_sha256": ["s" * 64]}]},
           "rejects": [{"slot": 0, "text": "x y z", "family": "SPK", "span_s": 0.8, "reason": "duration",
                        "source_sha256": ["t" * 64], "n_words": 3}],
           "queue_used": 2, "pass_rates": {"SPK": {"tried": 2, "kept": 1}}}
    rec = m.public(sel, {"binary": "b"}, "c" * 64, "deadbeef")
    s = json.dumps(rec)
    assert "a b c" not in s and "x y z" not in s and '"text"' not in s
    r = rec["pass_rates"]["SPK"]
    assert r["tried"] == 2 and r["kept"] == 1 and r["rate"] == 0.5 and len(r["wilson95"]) == 2
    assert rec["engine_verified"] == {"binary": "b"} and rec["corpus_sha256"] == "c" * 64
    assert rec["code_commit"] == "deadbeef" and rec["texts_public"] is False


def test_exhaustion_stop_carries_partial_counts_without_texts():
    from yct.tribe_run import speech_corpus as S  # noqa: N812

    def synth(text):
        return np.r_[np.zeros(100), np.full(4800 * 5, 0.3), np.zeros(100)], 48000   # 0.5 s span: too short

    synth.verified = {"fake": "pin"}
    spec = {"fill_order": ["SPK"], "ranges_s": {"SPK": [1.0, 1.5]}, "counts": {"SPK": 2}, "spk_words": 3,
            "span_dbfs": -40.0, "burst_sentences": 2}
    q = [{"list": 1, "item": i, "sha256": f"{i:064d}", "text": "a b c d"} for i in range(3)]
    with pytest.raises(S.CorpusStopError) as e:
        S.select(q, synth, spec)
    st = e.value.partial
    assert st["pass_rates"] == {"SPK": {"tried": 3, "kept": 0}} and st["queue_used"] == 3
    assert st["family"] == "SPK" and st["slot"] == 0
    s = json.dumps(_mod().stop_record(st, {}, "c" * 64, "x"))
    assert '"text"' not in s and 'a b c' not in s   # the key texts_public is fine


def test_run_refuses_an_unfrozen_corpus(monkeypatch):
    m = _mod()
    from yct.config import load_config

    cfg = load_config()
    key = "controls.refclips_artifacts.speech_corpus_sha256"
    cfg["frozen"] = [f for f in cfg["frozen"] if f["key"] != key]
    with pytest.raises(SystemExit, match="not frozen"):
        m.run(cfg, raw=b"", synth=lambda t: (np.zeros(1), 48000))
