"""D-085 part 1 (council re-sign-off, non-blocking items): rebuild name-set equality (neuro), descriptive rebuild
record with the toolchain, ffprobe timing/colour metadata and the chroma deviation (watchdog, biostat, referee),
the intercept-only partial r pre-declared as descriptive (watchdog), and the §7 decoded-identity disclosure."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import refclips58 as R  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refclips_build_p1", ROOT / "scripts" / "refclips_build.py")
B = importlib.util.module_from_spec(spec)
sys.modules["refclips_build_p1"] = B
spec.loader.exec_module(B)
CFG = load_config()


def _rec(name, mp4="m", wav="w", tsv="t", dec="D"):
    return {"name": name, "sha256": {"mp4": mp4, "wav": wav, "tsv": tsv}, "decoded_sha256": dec}


# ---------------------------------------------------------------- neuro: name sets must be equal
def test_name_set_mismatches_flags_missing_and_extra_clips():
    rec1 = {"a.mp4": "m", "a.wav": "w", "a.tsv": "t", "b.mp4": "m", "b.wav": "w", "b.tsv": "t",
            "STOP_NOTE.md": "x"}
    assert B.name_set_mismatches({"a": _rec("a"), "b": _rec("b")}, rec1) == []
    assert B.name_set_mismatches({"a": _rec("a")}, rec1) == ["missing:b"]
    assert B.name_set_mismatches({"a": _rec("a"), "b": _rec("b"), "c": _rec("c")}, rec1) == ["extra:c"]


def test_rebuild_against_full_build1_record_stops_on_a_missing_clip(tmp_path, monkeypatch):
    import copy
    cfg = copy.deepcopy(CFG)
    cfg["frozen"] = list(cfg["frozen"]) + [{"key": "controls.refclips_d085.qc", "frozen_at": "x"}]
    rec1 = json.loads((ROOT / cfg["controls"]["refclips_d085"]["build1_sha_record"]).read_text())["files"]
    clips = {c.name: c for c in R.plan(cfg)}
    clip = clips["flash_00"]
    monkeypatch.setattr(B.R, "build_clip", lambda c, out, cfg, images=None: {
        "name": c.name, "family": c.family, "sha256": {k: rec1[f"{c.name}.{k}"] for k in ("mp4", "wav", "tsv")}})
    monkeypatch.setattr(B.R, "decoded_sha", lambda p: None)

    def no_qc(*a, **k):
        raise AssertionError("YuNet QC ran before the name-set check")
    monkeypatch.setattr(B.refclips_qc85, "run_qc", no_qc)
    rc = B.build_all([clip], tmp_path, cfg, qc="d085", yunet=lambda *a: [])
    note = (tmp_path / "STOP_NOTE.md").read_text()
    assert rc == 1 and "missing:flash_01" in note


# ---------------------------------------------------------------- watchdog / biostat / referee: descriptive record
def test_describe_mp4_reports_timing_colour_tags_and_chroma_deviation(tmp_path):
    frames = [np.full((R.H, R.W), R.GREY, np.uint8) for _ in range(30)]
    R.encode(frames, np.zeros(R.SR), [], tmp_path, "c", CFG)
    d = B.describe_mp4(tmp_path / "c.mp4")
    c = CFG["normalize"]["color"]
    assert d["r_frame_rate"] == f"{R.FPS}/1"
    assert int(d["nb_frames"]) >= 1
    assert d["color_space"] == c["matrix"] and d["color_range"] == c["range"]
    assert d["color_primaries"] == c["primaries"] and d["color_transfer"] == c["transfer"]
    assert d["max_abs_u_minus_128"] <= 1 and d["max_abs_v_minus_128"] <= 1   # grey frames: neutral chroma


def test_rebuild_record_holds_toolchain_and_per_mp4_descriptives(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "toolchain", lambda: {"ffmpeg": "ffmpeg version 6.1.1-3ubuntu5", "libx264": "x"})
    monkeypatch.setattr(B, "describe_mp4", lambda p: {"nb_frames": "1740", "r_frame_rate": "30/1"})
    (tmp_path / "a.mp4").write_bytes(b"x")
    rec = B.write_rebuild_record(tmp_path, ["a"], mismatches=[])
    doc = json.loads((tmp_path / "rebuild_record.json").read_text())
    assert doc == rec
    assert doc["toolchain"]["ffmpeg"].startswith("ffmpeg version 6.1.1-3ubuntu5")
    assert doc["descriptive"]["a.mp4"]["r_frame_rate"] == "30/1"
    assert doc["gating"] == {"rebuild_mismatches": []} and doc["descriptive_only"] is True


# ---------------------------------------------------------------- watchdog: intercept-only partial r descriptive
def test_intercept_only_partial_r_is_pre_declared_descriptive():
    from yct.controls.partial import partial_r, partial_r_report

    c = CFG["controls"]
    assert c["partial_out_nuisance_descriptive"] == ["intercept"]
    rng = np.random.default_rng(3)
    n = 58
    x, o = rng.normal(size=n), rng.normal(size=(n, 2))
    y = 0.5 * x + o @ np.array([0.3, -0.2]) + np.linspace(0, 2, n) + rng.normal(size=n)
    rep = partial_r_report(y, x, o, c)
    assert rep["gating"]["terms"] == ["intercept", "legendre_1"]
    assert np.isclose(rep["gating"]["r"], partial_r(y, x, o, ["intercept", "legendre_1"]))
    assert rep["descriptive"][0]["terms"] == ["intercept"] and rep["descriptive"][0]["gates"] is False
    assert np.isclose(rep["descriptive"][0]["r"], partial_r(y, x, o, ["intercept"]))


def test_d086_wording_corrected_and_section7_discloses_decoded_identity():
    dec = (ROOT / "DECISIONS.md").read_text()
    assert "can raise a partial r as well as lower it" in dec
    doc = (ROOT / "reviews" / "phase_p4b" / "d085_v2.md").read_text()
    s7 = doc[doc.index("## 7. Disclosures"):doc.index("## 8.")]
    assert "decoded" in s7 and "|U" in s7 and "|V" in s7
