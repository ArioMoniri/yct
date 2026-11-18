"""Per-clip P4 gate (D-063 engineering blockers; Neuro P4-entry C2/D2, QA D1e, v2.md:52 "exactly one Audio
and one Video chunk per T1 clip"): synthetic run_clip metrics dicts, CPU only."""
from __future__ import annotations

import copy

import pytest

from yct.tribe_run.qc import GPU_NAME, clip_gate, sanitize_metrics

GOOD = {
    "duration_s": 58.0, "shape": [58, 20484], "finite": True, "TR_s": 1.0, "expected_T": 58.0,
    "T_within_1": True, "chunks": {"Audio": [[0.0, 58.0]], "Video": [[0.0, 58.0]]},
    "bug018_word_check": {"ok": True, "n_words": 181, "n_tsv_rows": 181, "bug018_fix": True},
    "words_after_duration": 0, "asr_called": False, "uvx_on_path": False, "offline": True,
    "revisions": {"gpu": GPU_NAME, "bug018_word_fix": True, "backbones": {"x": "y"}},
    "pred_shape": [58, 20484], "pred_sha256": "a" * 64, "cache_key": "b" * 64, "input_sha256": "c" * 64,
    "transcript_sha256": "d" * 64, "n_words": 181, "pred_mean": 0.01, "pred_std": 0.15,
    "feature_sha256": {"text/llama::some transcript words": "e" * 64},
    "event_types": {"Word": 181, "Audio": 1, "Video": 1}, "cache_reused": False,
}


def _bad(**kw):
    m = copy.deepcopy(GOOD)
    for k, v in kw.items():
        if v is None:
            m.pop(k)
        else:
            m[k] = v
    return m


def test_good_t1_clip_passes():
    g = clip_gate(GOOD, "t1")
    assert g["pass"] is True and g["failures"] == []


@pytest.mark.parametrize("change,why", [
    ({"chunks": {"Audio": [[0, 60], [60, 60]], "Video": [[0, 58]]}}, "Audio"),
    ({"chunks": {"Audio": [[0, 58]]}}, "Video"),
    ({"chunks": {"Audio": 1, "Video": 2}}, "Video"),
    ({"finite": False}, "finite"),
    ({"shape": [58, 20000]}, "shape"),
    ({"shape": [58]}, "shape"),
    ({"T_within_1": False}, "T"),
    ({"shape": [55, 20484], "pred_shape": [55, 20484]}, "T"),
    ({"bug018_word_check": {"ok": False, "n_words": 180, "n_tsv_rows": 181}}, "word"),
    ({"bug018_word_check": {"ok": True, "n_words": 180, "n_tsv_rows": 181}}, "word"),
    ({"words_after_duration": 2}, "word"),
    ({"asr_called": True}, "asr"),
    ({"uvx_on_path": True}, "uvx"),
    ({"offline": False}, "offline"),
    ({"revisions": {"gpu": "NVIDIA A100-SXM4-80GB", "bug018_word_fix": True}}, "gpu"),
    ({"revisions": {"gpu": GPU_NAME, "bug018_word_fix": False}}, "bug018"),
    ({"pred_sha256": None}, "pred_sha256"),
    ({"chunks": None}, "chunks"),
    ({"duration_s": 59.2}, "duration"),
])
def test_each_violation_fails_the_gate(change, why):
    g = clip_gate(_bad(**change), "t1")
    assert g["pass"] is False and any(why.lower() in f.lower() for f in g["failures"]), g


def test_t3_short_clip_gated_on_its_own_duration_not_58():
    short = _bad(duration_s=42.8, shape=[43, 20484], pred_shape=[43, 20484], expected_T=42.8)
    assert clip_gate(short, "t3")["pass"] is True
    assert clip_gate(short, "t1")["pass"] is False      # T1 clips are the 58 s trim


def test_expectations_from_the_driver_are_enforced():
    assert clip_gate(GOOD, "t1", expected={"transcript_sha256": "d" * 64, "input_sha256": "c" * 64})["pass"]
    g = clip_gate(GOOD, "t1", expected={"transcript_sha256": "f" * 64})
    assert not g["pass"] and any("transcript_sha256" in f for f in g["failures"])
    g = clip_gate(GOOD, "t1", expected={"revisions_sha256": "0" * 64})
    assert not g["pass"] and any("revisions" in f for f in g["failures"])


def test_unknown_track_refused():
    with pytest.raises(ValueError):
        clip_gate(GOOD, "t2")


def test_sanitized_record_is_numbers_and_hashes_only_no_prediction_statistics():
    """Firewall (D-063 B2) + privacy: no per-clip prediction statistic (mean/std/W-average) and no feature
    names (they hold transcript text) leave the box for analysis-set clips."""
    r = sanitize_metrics(GOOD)
    assert "pred_mean" not in r and "pred_std" not in r and "feature_sha256" not in r
    assert r["chunks"] == {"Audio": 1, "Video": 1} and r["n_feature_files"] == 1
    flat = repr(r)
    assert "transcript words" not in flat and "llama" not in flat
    assert clip_gate(r, "t1")["pass"] is True     # the gate works on the sanitized record too
    assert not any(k.endswith(("_mean", "_std", "_sd")) or k.startswith("w_") for k in r)


def test_gate_on_real_d062_records():
    """Real-shape check on the archived, sanitised D-062 records (run wave1p2b_20261118T002855Z): the real
    58 s clips pass every content check (1 Audio + 1 Video chunk, shape, T, words) and fail only on what P4
    adds (GPU model in the revisions, word fix on); the 160 s synthetic clip fails the chunk/T1 rules."""
    import json
    from pathlib import Path

    runs = json.loads((Path(__file__).resolve().parents[1] / "outputs/runs/wave1p2b_20261118T002855Z"
                       / "child_metrics.json").read_text())["runs"]
    p4_only = {"gpu None != 'NVIDIA A100-SXM4-40GB' (one GPU type for all of P4)",
               "bug018 word fix not on (one setting for all of P4)"}
    for vid in ("yct_0016", "yct_0034", "yct_0036", "yct_0016_rerun"):
        assert set(clip_gate(runs[vid], "t1")["failures"]) == p4_only, vid
        fixed = {**runs[vid], "revisions": {"gpu": GPU_NAME, "bug018_word_fix": True}}
        assert clip_gate(fixed, "t1")["pass"] and clip_gate(fixed, "t3")["pass"]
    f = clip_gate(runs["long160"], "t3")["failures"]
    assert "Audio chunks = 3, need exactly 1" in f and "Video chunks = 3, need exactly 1" in f
