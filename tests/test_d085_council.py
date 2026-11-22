"""D-085 council blocking items (council_d085_*.md, all REVISE) and owner decisions of 2026-11-22.

Owner: (1) IEEE/Harvard list kept, "copyright not cleared, non-commercial research", texts private, ids +
sha256s public; (2) SPK 3-word leads only at 175 wpm; (3) TALKFACE internal only (TRIBE input, never
published, numbers + hash only, labelled synthetic). Council: constructive SPK/BURST audio gate on the
rendered 48 kHz audio with speech_envelope descriptive and T-ENV frozen before any speech build; decoded twin
differences descriptive; Wav2Lip weights pinned with a private mirror; TALKFACE face rule with fallback;
YuNet never run on built frames before the freeze; family-pooled ruling recorded; rebuild sha check before
YuNet; TALKFACE worst case in the cost projection; two-part freeze."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run import refclips_qc85 as Q  # noqa: N812
from yct.tribe_run import speech_corpus as S  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
D85 = CFG["controls"]["refclips_d085"]
SPEC = D85["speech"]
CLIPS = {c.name: c for c in R.plan(CFG)}


# ---------------------------------------------------------------- (b) SPK 3-word leads only (owner)
def test_spk_uses_three_word_leads_only_and_the_2_3_rule_is_gone():
    assert SPEC["spk_words"] == 3 and "spk_words_rule" not in SPEC
    n = CFG["controls"]["refclips"]["families"]["SPK"]
    assert {S.spk_words(i, k) for i in range(n) for k in range(3)} == {3}
    doc = json.loads((ROOT / SPEC["corpus_file"]).read_text())
    assert doc["rules"]["spk_words"] == 3 and "spk_words_rule" not in doc["rules"]


def _fake(durs, default=1.2):
    sr = 16000

    def synth(text):
        d = durs.get(text, default)
        x = np.zeros(int(sr * (d + 0.4)))
        x[int(0.2 * sr):int(0.2 * sr) + int(round(d * sr))] = 0.3
        return x, sr
    return synth


def _queue(n):
    return [{"text": f"w{j}a w{j}b w{j}c w{j}d w{j}e.", "sha256": f"{j:064x}"} for j in range(n)]


def test_select_fills_spk_with_three_words_and_logs_pass_rates():
    spec = dict(SPEC, counts={"SPK": 6, "BURST": 1, "TALKFACE": 1})
    durs = {"w0a w0b w0c": 0.9}                          # too short -> replaced in order
    for j in range(40):
        durs[f"w{j}a w{j}b w{j}c w{j}d w{j}e. w{j + 1}a w{j + 1}b w{j + 1}c w{j + 1}d w{j + 1}e."] = 5.0
        durs[f"w{j}a w{j}b w{j}c w{j}d w{j}e."] = 3.0
    sel = S.select(_queue(40), _fake(durs), spec)
    assert [it["n_words"] for it in sel["items"]["SPK"]] == [3] * 6
    pr = sel["pass_rates"]
    assert pr["SPK"] == {"tried": 7, "kept": 6} and pr["BURST"] == {"tried": 1, "kept": 1}


def test_spk_exhaustion_is_still_a_stop():
    spec = dict(SPEC, counts={"SPK": 3, "BURST": 0, "TALKFACE": 0})
    with pytest.raises(S.CorpusStopError, match="exhausted"):
        S.select(_queue(5), _fake({}, default=0.5), spec)


def test_public_record_strips_every_text_field():
    sel = {"items": {"SPK": [{"text": "a b c", "source_sha256": ["0" * 64]}]},
           "rejects": [{"text": "x y z", "reason": "duration"}]}
    pub = S.public_record(sel)
    assert "text" not in json.dumps(pub) and pub["items"]["SPK"][0]["source_sha256"] == ["0" * 64]


# ---------------------------------------------------------------- (a) licence wording
def test_licence_is_recorded_as_not_cleared_never_as_public_domain():
    assert SPEC["licence_status"] == "copyright_not_cleared_non_commercial_research"
    lic = (ROOT / "docs" / "stimuli" / "LICENSES.md").read_text()
    sec = lic[lic.index("## Speech corpus (D-085)"):]
    assert "copyright not cleared" in sec and "37 CFR 202.1(a)" in sec and "IEEE Std 297-1969" in sec
    assert "not asserted public domain" in sec
    assert "Wav2Lip" in sec and "non-commercial" in sec and "LRS2" in sec


def test_no_ieee_harvard_text_in_the_public_corpus_file():
    doc = json.loads((ROOT / SPEC["corpus_file"]).read_text())
    assert all(set(r) == {"list", "item", "sha256"} for r in doc["queue"])
    assert all(set(r) == {"list", "item", "sha256", "reasons"} for r in doc["excluded"])
    assert SPEC["private_raw_s3"].startswith("s3://yct-research-235229001983/")


# ---------------------------------------------------------------- (c) constructive SPK/BURST audio gate
def _bed(n=48000 * 4, seed=1):
    return np.random.default_rng(seed).standard_normal(n) * 0.05


def _utt(n, seed=2):
    t = np.arange(n) / 48000
    return np.sin(2 * np.pi * 220 * t) * np.hanning(n)


def test_speech_gate_passes_the_constructed_mix():
    bed = _bed()
    plc = [(1.0, _utt(24000)), (2.5, _utt(12000, 3))]
    mix = bed
    for t0, u in plc:
        mix = R.place_speech(mix, u, t0)
    g = Q.speech_gate(Q.pcm16(mix), Q.pcm16(bed), bed, plc)
    assert g["pass"] and g["outside_identical"] and g["reconstructed"]
    assert len(g["window_rms_ratio"]) == 2 and g["gating"] == ["outside_identical", "reconstructed"]


def test_speech_gate_fails_on_any_change_outside_a_window_or_a_misplaced_utterance():
    bed = _bed()
    plc = [(1.0, _utt(24000))]
    mix = R.place_speech(bed, plc[0][1], 1.0)
    p = Q.pcm16(mix)
    p[100] += 1                                           # outside the window
    g = Q.speech_gate(p, Q.pcm16(bed), bed, plc)
    assert not g["pass"] and not g["outside_identical"]
    late = R.place_speech(bed, plc[0][1], 1.01)          # utterance 10 ms late
    g2 = Q.speech_gate(Q.pcm16(late), Q.pcm16(bed), bed, plc)
    assert not g2["pass"] and not g2["reconstructed"]


def test_speech_envelope_is_descriptive_and_tenv_must_be_frozen_before_speech_builds():
    env = SPEC["envelope"]
    assert env["gating"] is False and env["burst_kernel_envelope"] == "per_utterance_pre_mix_hilbert"
    assert "controls.refclips_d085.tenv" in SPEC["requires_frozen_before_build"]
    with pytest.raises(SystemExit, match="not frozen"):
        S.speech_build_preconditions(CFG)


# ---------------------------------------------------------------- (d) decoded twin differences descriptive
def test_decoded_twin_differences_are_reported_and_never_gate():
    loc = CLIPS["loc_00"]
    pa = [(t / 2, np.zeros((8, 8), np.uint8)) for t in range(116)]
    pb = [(t, p.copy()) for t, p in pa]
    pb[0][1][0, 0] = 5
    d = Q.twin_decoded_descriptive(pa, pb, loc, CFG)
    assert d["gating"] is False and d["max_abs_diff"] == 5 and d["n_frames"] > 0
    rendered = [np.zeros((R.H, R.W), np.uint8) for _ in range(int(R.DUR * R.FPS))]
    dec = [(t / 2, np.full((R.PATCH, R.PATCH), 2, np.uint8)) for t in range(116)]
    v = Q.decoded_vs_rendered(dec, rendered, loc)
    assert v["gating"] is False and v["max_abs_diff"] == 2 and len(v["frames"]) == len(loc.onsets)


def test_run_qc_pass_ignores_non_gating_checks():
    row = {"checks": {"haar": {"pass": False, "gating": False}, "twin_decoded": {"gating": False},
                      "yunet": {"pass": True}}}
    assert Q.row_pass(row)
    row["checks"]["yunet"]["pass"] = False
    assert not Q.row_pass(row)


# ---------------------------------------------------------------- (e) TALKFACE
def test_talkface_is_internal_only_with_pinned_wav2lip_and_a_face_fallback():
    t = D85["talkface"]
    assert t["weights_file"] == "wav2lip.pth" and t["fps"] == 30
    assert t["publish"] is False and t["synthetic_label"] is True
    assert t["mirror_s3"].startswith("s3://yct-research-235229001983/") and "private" in t["mirror_s3"]
    fr = t["face_rule"]
    assert fr["rule"] == "first_face_pass_after_v4_rank_492" and fr["max_skips"] == 5
    assert set(fr["skip_on"]) == {"s3fd_no_face", "wav2lip_error", "licence_not_adaptable"}
    assert fr["on_exhausted"] == "stop_owner" and fr["visual_review"] is False
    assert t["session_worst_usd"] == pytest.approx(1.99 * 1.75)


def test_talkface_publish_true_is_refused_by_the_schema():
    from yct.config_schema import D085Talkface

    t = copy.deepcopy(D85["talkface"])
    t["publish"] = True
    with pytest.raises(ValueError):
        D085Talkface(**t)


def test_talkface_face_rule_takes_the_next_pass_and_stops_after_five_skips():
    passes = [{"title": f"F{j}", "rank": 492 + j} for j in range(1, 10)]
    rule = D85["talkface"]["face_rule"]
    pick = Q.talkface_face(passes, {"F1": "s3fd_no_face", "F2": "wav2lip_error"}, rule)
    assert pick["face"]["title"] == "F3" and [s["title"] for s in pick["skipped"]] == ["F1", "F2"]
    bad = {f"F{j}": "s3fd_no_face" for j in range(1, 6)}
    with pytest.raises(SystemExit, match="STOP"):
        Q.talkface_face(passes, bad, rule)
    with pytest.raises(ValueError, match="after rank 492"):
        Q.talkface_face([{"title": "X", "rank": 100}] + passes, {}, rule)


# ---------------------------------------------------------------- watchdog C1-C3, R1b, cost, freeze plan
def test_no_yunet_output_exists_on_any_built_frame():
    Q.assert_no_yunet_outputs(ROOT / "outputs")


def test_assert_no_yunet_outputs_detects_one(tmp_path):
    d = tmp_path / "runs" / "refclips_x"
    d.mkdir(parents=True)
    (d / "qc.json").write_text(json.dumps({"rows": [{"checks": {"yunet": {"hits": []}}}]}))
    with pytest.raises(SystemExit, match="YuNet"):
        Q.assert_no_yunet_outputs(tmp_path)


def test_r1b_no_frozen_computation_reads_refclip_face_area():
    allowed = {"src/yct/confounds/core.py", "src/yct/tribe_run/refclips58.py",
               "src/yct/tribe_run/refclips_qc85.py", "scripts/refclips_qc_diag.py"}
    users = {str(p.relative_to(ROOT)) for d in ("src", "scripts") for p in (ROOT / d).rglob("*.py")
             if "face_area_crop_frac" in p.read_text()}
    assert users <= allowed, users - allowed


def test_owner_family_pooled_ruling_is_recorded():
    q = D85["qc"]
    assert q["face_hit_scope"] == "family" and q["face_hit_scope_ruled_by"] == "owner_2026-11-22"


def test_rebuild_sha_check_runs_before_yunet_and_stops_on_mismatch(tmp_path, monkeypatch):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("refclips_build_c3", ROOT / "scripts" / "refclips_build.py")
    B = importlib.util.module_from_spec(spec)  # noqa: N806
    sys.modules["refclips_build_c3"] = B
    spec.loader.exec_module(B)
    cfg = copy.deepcopy(CFG)
    cfg["frozen"] = list(cfg["frozen"]) + [{"key": "controls.refclips_d085.qc", "frozen_at": "x"}]
    clip = CLIPS["flash_00"]
    monkeypatch.setattr(B.R, "build_clip", lambda c, out, cfg, images=None: {
        "name": c.name, "family": c.family, "sha256": {"mp4": "0" * 64, "wav": "0" * 64, "tsv": "0" * 64}})

    def no_qc(*a, **k):
        raise AssertionError("YuNet QC ran before the rebuild sha check")
    monkeypatch.setattr(B.refclips_qc85, "run_qc", no_qc)
    rc = B.build_all([clip], tmp_path, cfg, qc="d085", yunet=lambda *a: [])
    assert rc == 1 and "rebuild" in (tmp_path / "STOP_NOTE.md").read_text()
    rec = json.loads((ROOT / D85["build1_sha_record"]).read_text())["files"]
    assert B.rebuild_mismatches({"flash_00": {"name": "flash_00", "sha256": {
        "mp4": rec["flash_00.mp4"], "wav": rec["flash_00.wav"], "tsv": rec["flash_00.tsv"]}}}, rec) == []


def test_two_part_freeze_plan():
    fp = D85["freeze_plan"]
    assert fp["part1"] == ["controls.refclips_d085.qc", "controls.refclips_d085.build1_sha_record"]
    assert set(fp["part2"]) == {"controls.refclips_d085.speech", "controls.refclips_d085.talkface",
                                "controls.refclips_artifacts.speech_corpus_sha256"}
    cfg = copy.deepcopy(CFG)
    cfg["frozen"] = list(cfg["frozen"]) + [{"key": k, "frozen_at": "x"} for k in fp["part1"]]
    Q.require_frozen(cfg)                                 # part 1 alone unlocks the visual rebuild
    with pytest.raises(SystemExit, match="not frozen"):
        S.speech_build_preconditions(cfg)                 # speech still needs part 2 + T-ENV


def test_d085_v2_doc_and_response_matrix_exist():
    doc = (ROOT / "reviews" / "phase_p4b" / "d085_v2.md").read_text()
    mat = (ROOT / "reviews" / "phase_p4b" / "d085_v2_response.md").read_text()
    for w in ("copyright not cleared", "3-word", "internal only", "wav2lip.pth", "rendered 48 kHz"):
        assert w in doc, w
    assert re.search(r"Neuro B1", mat) and "owner" in mat
