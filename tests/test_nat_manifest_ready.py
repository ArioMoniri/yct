"""NAT manifest pre-freeze validation (D-075 §3, D-084): the committed data/refstim/nat_manifest.json is
exactly what the frozen rules give from the committed NAT log, every row carries what the clip build needs,
and no row text carries an outcome word. Runs on the committed files only (no network, no pod)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
from pathlib import Path

import pytest

from yct.config import load_config
from yct.curate import natstim as ns
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "refstim" / "nat_auto_log.jsonl"
MAN = ROOT / "data" / "refstim" / "nat_manifest.json"
spec = importlib.util.spec_from_file_location("check_blinding", ROOT / "scripts" / "check_blinding.py")
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)

CFG = load_config()
NEED = CFG["controls"]["refclips"]["nat_n"]
REQ = ("title", "pageid", "read_revid", "url", "source_sha1", "source_sha256", "t1_name", "t1_sha256",
       "wav_sha256", "attribution", "licence", "licence_template", "values", "session")


@pytest.fixture(scope="module")
def log():
    return ns.load_log(LOG)


@pytest.fixture(scope="module")
def man():
    return json.loads(MAN.read_text())


def split(log):
    g = ns.gpu_rows(log)
    ids = {id(r) for r in g}
    return [r for r in log if id(r) not in ids], g


def test_manifest_equals_the_frozen_rule_output(log, man):
    assert man == json.loads(json.dumps(ns.nat_manifest(log, CFG)))
    assert len(man) == NEED == 15


def test_selection_is_the_first_15_passes_by_cpu_rank(log, man):
    rank = {t: j for j, t in enumerate(ns.cpu_passes(log))}
    ids = [r["t1_name"] for r in man]
    assert ids == sorted(ids, key=rank.__getitem__)
    passes = sorted((r["t1_name"] for r in ns.gpu_rows(log) if r["decision"] == "pass"), key=rank.__getitem__)
    assert ids == passes[:NEED]
    assert {s: sum(r["session"] == s for r in man) for s in (0, 1, 2)} == {0: 4, 1: 4, 2: 7}


def test_selection_invariant_to_row_order(log):
    base = ns.nat_selection(log, CFG)
    cpu, gpu = split(log)
    for seed in range(5):
        g = gpu[:]
        random.Random(seed).shuffle(g)
        assert ns.nat_selection(cpu + g, CFG) == base


def test_every_row_has_what_the_build_needs_and_passes_the_frozen_thresholds(man):
    lic = CFG["controls"]["refclips"]["image_licences"]
    nat = CFG["controls"]["refclips_auto"]["nat"]
    for r in man:
        assert all(r.get(k) not in (None, "") for k in REQ), r["t1_name"]
        assert r["t1_sha256"].startswith(r["t1_name"]) and len(r["t1_sha256"]) == 64
        assert len(r["source_sha256"]) == 64 and len(r["wav_sha256"]) == 64 and len(r["source_sha1"]) == 40
        assert any(r["licence"] == x or (x.endswith("*") and r["licence"].startswith(x[:-1])) for x in lic)
        v = r["values"]
        assert v["p_en"] >= nat["lang_id"]["min_prob_en"]
        assert v["main_frac"] >= nat["diarization"]["min_main_speaker_frac"]
        assert v["max_other_s"] <= nat["diarization"]["max_other_speaker_s"]
        assert v["face_present_crop_w"] >= ns.N3_MIN


def test_no_outcome_words_in_row_text(man):
    for r in man:
        for k in ("title", "url", "attribution"):
            assert cb.outcome_words(str(r[k])) == [], (r["t1_name"], k)


def test_manifest_sha_is_the_reviewed_one(man):
    sha = hashlib.sha256(MAN.read_bytes()).hexdigest()
    assert sha == "2fbe3421696d37a027d13dcf7d8b9116fa607b07a6e7ad3919fe5b6848da825e"
    assert CFG["controls"]["refclips_artifacts"]["nat_manifest_sha256"] in (None, sha)


def test_selection_refuses_a_duplicate_or_gap(log):
    cpu, g = split(log)
    with pytest.raises(ra.StopError, match="twice"):
        ns.nat_selection(cpu + g + [g[0]], CFG)
    with pytest.raises(ra.StopError, match="gap"):
        ns.nat_selection(cpu + g[1:], CFG)
