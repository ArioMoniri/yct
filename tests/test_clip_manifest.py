"""Full p4b_ref/v1 clip manifest assembly (D-071 (d)): every family present at its frozen count, every part
frozen-QC-passed, GREY_CTRL identical across the two builds, the 15 NAT rows from the frozen NAT manifest
with the pod dry-run shas, TALKFACE from its finish record, and the BUG-048 concrete PD template. The real
committed parts are used where they exist; TALKFACE (not built yet) is a fixture."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from yct.config import load_config
from yct.tribe_run import clip_manifest as cm

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()


def talk_record(ok=True):
    return {"qc": {"pass": ok}, "sha256": {"mp4": "a" * 64, "wav": "b" * 64, "tsv": "c" * 64},
            "decoded_sha256": "d" * 64, "n_frames": 1740, "frames_sha256": "e" * 64}


@pytest.fixture(scope="module")
def parts():
    return cm.load_parts(ROOT, CFG)


def test_assembles_120_clips_with_the_frozen_family_counts(parts):
    doc = cm.assemble(parts, talk_record(), CFG)
    fam = CFG["controls"]["refclips"]["families"]
    counts = {f: sum(c["family"] == f for c in doc["clips"]) for f in fam}
    assert counts == fam and len(doc["clips"]) == sum(fam.values()) == 120
    assert len({c["name"] for c in doc["clips"]}) == 120
    art = CFG["controls"]["refclips_artifacts"]
    assert doc["sources"]["nat_manifest_sha256"] == art["nat_manifest_sha256"]


def test_nat_entries_carry_the_manifest_and_dry_run_shas(parts):
    doc = cm.assemble(parts, talk_record(), CFG)
    nat = [c for c in doc["clips"] if c["family"] == "NAT"]
    man = json.loads((ROOT / "data" / "refstim" / "nat_manifest.json").read_text())
    assert [c["name"] for c in nat] == [f"nat_{i:02d}" for i in range(15)]
    for c, r in zip(nat, man, strict=True):
        assert c["sha256"]["mp4"] == r["t1_sha256"] and c["sha256"]["wav"] == r["wav_sha256"]
        assert len(c["sha256"]["transcript"]) == 64 and c["events"] == []
        if r["licence"] == "PD-*":
            assert c["licence_template_concrete"] not in (None, "Template:PD-Layout")
            assert c["licence_template_concrete"].startswith("Template:PD-")


def test_deterministic_sha(parts):
    a = cm.manifest_text(cm.assemble(parts, talk_record(), CFG))
    b = cm.manifest_text(cm.assemble(copy.deepcopy(parts), talk_record(), CFG))
    assert a == b and len(hashlib.sha256(a.encode()).hexdigest()) == 64


def test_refuses_without_talkface_or_on_a_failed_talkface_qc(parts):
    with pytest.raises(cm.ManifestError, match="TALKFACE"):
        cm.assemble(parts, None, CFG)
    with pytest.raises(cm.ManifestError, match="QC"):
        cm.assemble(parts, talk_record(ok=False), CFG)


def test_refuses_a_failed_part_qc_or_a_wrong_qc_sha(parts):
    p = copy.deepcopy(parts)
    p["visual_qc"]["pass"] = False
    with pytest.raises(cm.ManifestError, match="QC"):
        cm.assemble(p, talk_record(), CFG)
    p = copy.deepcopy(parts)
    p["speech"]["qc_sha256"] = "0" * 64
    with pytest.raises(cm.ManifestError, match="qc_sha256"):
        cm.assemble(p, talk_record(), CFG)


def test_refuses_grey_ctrl_mismatch_between_builds(parts):
    p = copy.deepcopy(parts)
    g = next(c for c in p["speech"]["clips"] if c["family"] == "GREY_CTRL")
    g["sha256"]["mp4"] = "f" * 64
    with pytest.raises(cm.ManifestError, match="GREY_CTRL"):
        cm.assemble(p, talk_record(), CFG)


def test_refuses_a_nat_dry_run_problem_or_sha_mismatch(parts):
    p = copy.deepcopy(parts)
    p["nat_dry"]["ok"] = False
    with pytest.raises(cm.ManifestError, match="dry run"):
        cm.assemble(p, talk_record(), CFG)
    p = copy.deepcopy(parts)
    p["nat_dry"]["manifest_sha256"] = "0" * 64
    with pytest.raises(cm.ManifestError, match="NAT manifest"):
        cm.assemble(p, talk_record(), CFG)


def test_refuses_an_unfrozen_nat_sha(parts):
    c = copy.deepcopy(CFG)
    c["frozen"] = [r for r in c["frozen"] if r["key"] != "controls.refclips_artifacts.nat_manifest_sha256"]
    with pytest.raises(cm.ManifestError, match="frozen"):
        cm.assemble(parts, talk_record(), c)


def test_concrete_pd_template_rule():
    t = ["Template:Information", "Template:PD-Layout", "Template:PD-USGov-VOA", "Template:PD-USGov-VOA/en"]
    assert cm.concrete_pd_template(t) == "Template:PD-USGov-VOA"
    assert cm.concrete_pd_template(["Template:PD-Layout"]) is None
    assert cm.concrete_pd_template(["Template:Cc-zero"]) is None


def test_committed_talkface_record_and_manifest_file():
    """Once committed: the TALKFACE finish record passed QC, and data/refstim/refclips_manifest.json is
    exactly what the assembler gives from the committed parts (its sha is the configured one once set)."""
    rec = ROOT / "data" / "refstim" / "talkface_finish_record.json"
    out = ROOT / "data" / "refstim" / "refclips_manifest.json"
    talk = json.loads(rec.read_text())
    assert talk["qc"]["pass"] is True and talk["n_frames"] == 1740
    text = cm.manifest_text(cm.assemble(cm.load_parts(ROOT, CFG), talk, CFG))
    if out.exists():
        assert out.read_text() == text
        want = CFG["controls"]["refclips_artifacts"]["manifest_sha256"]
        assert want in (None, hashlib.sha256(text.encode()).hexdigest())
