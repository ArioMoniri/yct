"""D-080 draft (BUG-037): C1-equivalence in the determinism audit, v3 routing, and the metadata-stage dry
audit. Written before the fix (TDD)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests._refstim_rules import rule_for
from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
# these tests pin the D-080 (v3) layer; the D-081 v4 layer is tested in test_refstim_d081
CFG["controls"].pop("refclips_d081", None)
EX, C1 = ("duplicate",), ("licence", "personality_rights")


def r(title, decision="reject", reason=None, key=None):
    return {"title": title, "sha256_title": key or title, "decision": decision, "reason": reason,
            "rule": rule_for(decision, reason)}   # BUG-038: real rows carry their rule


def audit(row, prior_rows, flips=frozenset(), c1_equiv=True):
    return ra.audit_v2(row, [("L", {p["title"]: p for p in prior_rows})], {"L": set(flips)}, EX, C1,
                       c1_equiv=c1_equiv)


# ------------------------------------------------------------------ audit rule (option b)
def test_bug037_pair_is_c1_equivalent_and_reported():
    notes = audit(r("a", "reject", "personality_rights"), [r("a", "reject", "licence")])
    assert notes == [("L", "c1_equivalent", "licence")]
    notes = audit(r("a", "reject", "licence"), [r("a", "reject", "personality_rights")])
    assert notes == [("L", "c1_equivalent", "personality_rights")]


def test_c1_equivalence_off_keeps_d079_behaviour():
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(r("a", "reject", "personality_rights"), [r("a", "reject", "licence")], c1_equiv=False)


@pytest.mark.parametrize("v1,v2", [(("pass", None), ("reject", "licence")),
                                   (("reject", "multi_subject"), ("reject", "personality_rights")),
                                   (("reject", "licence"), ("pass", None)),
                                   (("reject", "licence"), ("reject", "multi_subject")),
                                   (("reject", "duplicate"), ("reject", "licence"))])
def test_c1_equivalence_does_not_cover_admissibility_changes(v1, v2):
    with pytest.raises(ra.StopError):
        audit(r("a", *v2), [r("a", *v1)])


def test_flip_list_still_takes_precedence_and_contradiction_still_stops():
    assert audit(r("a", "pass"), [r("a", "reject", "licence")], {"a"}) == [("L", "flip", "licence")]
    with pytest.raises(ra.StopError, match="flip list"):
        audit(r("a", "reject", "personality_rights"), [r("a", "reject", "licence")], {"a"})


def test_audit_note_kinds():
    assert audit(r("a", "pass"), [r("a", "pass")]) == [("L", "equal", None)]
    assert audit(r("a", "reject", "duplicate"), [r("a", "pass")]) == [("L", "duplicate_exempt", None)]
    assert audit(r("a", "pass"), []) == []
    assert audit(r("a", "reject", ra.IDENTITY_REASON), [r("a", "reject", "licence")]) == []


# ------------------------------------------------------------------ v3 routing (effective config)
def d080_cfg():
    cfg = copy.deepcopy(CFG)
    cfg["controls"]["refclips_d080"] = copy.deepcopy(CFG["controls"].get("refclips_d080") or {
        "decision": "D-080", "amends": ["D-079"], "log_version": "v3",
        "logs": {c: f"data/refstim/image_{c}_auto_log_v3.jsonl" for c in ("face", "body", "place")},
        "superseded_logs_add": {"face": ["data/refstim/image_face_auto_log_v2.jsonl"], "body": [],
                                "place": []},
        "audit_c1_equivalence": True, "dry_audit_file": "data/refstim/d080_dry_audit.json",
        "finality": "v3_is_selection"})
    return cfg


def test_effective_cfg_without_d080_is_d079():
    cfg = copy.deepcopy(CFG)
    cfg["controls"].pop("refclips_d080", None)
    e = rs.effective_cfg(cfg)
    assert e["controls"]["refclips_d079"]["log_version"] == "v2"
    assert e["controls"]["refclips_d079"]["audit"].get("c1_equivalence", False) is False


def test_effective_cfg_routes_v3_and_extends_superseded():
    e = rs.effective_cfg(d080_cfg())
    d = e["controls"]["refclips_d079"]
    assert d["log_version"] == "v3" and d["finality"] == "v3_is_selection"
    assert rs.image_log_v2("face", e) == "data/refstim/image_face_auto_log_v3.jsonl"
    assert d["superseded_logs"]["face"] == ["data/refstim/image_face_auto_log.jsonl",
                                            "data/refstim/image_face_auto_log_v2.jsonl"]
    assert d["flip_logs"] == CFG["controls"]["refclips_d079"]["superseded_logs"]
    assert d["audit"]["c1_equivalence"] is True
    assert CFG["controls"]["refclips_d079"]["log_version"] == "v2"      # the input is not mutated


def test_v3_routing_refuses_a_superseded_or_mislabelled_path():
    cfg = d080_cfg()
    cfg["controls"]["refclips_d080"]["logs"]["face"] = "data/refstim/image_face_auto_log_v2.jsonl"
    with pytest.raises(rs.CurationError):
        rs.image_log_v2("face", rs.effective_cfg(cfg))
    cfg = d080_cfg()
    cfg["controls"]["refclips_d080"]["logs"]["body"] = "data/refstim/image_body_auto_log_v4.jsonl"
    with pytest.raises(rs.CurationError):
        rs.image_log_v2("body", rs.effective_cfg(cfg))


def test_preload_is_strict_on_the_effective_version(tmp_path):
    e = rs.effective_cfg(d080_cfg())
    (tmp_path / "data" / "refstim").mkdir(parents=True)
    p = tmp_path / rs.image_log_v2("face", e)
    p.write_text(json.dumps({"title": "a", "decision": "pass", "sha1": "s", "values": {"dhash": "f"},
                             "log_version": "v2"}) + "\n")
    with pytest.raises(ra.StopError, match="log_version"):
        ra.preload_v2(ra.State(), "face", e, tmp_path, ran=[])
    p.write_text(json.dumps({"title": "a", "decision": "pass", "sha1": "s", "values": {"dhash": "f"},
                             "log_version": "v3"}) + "\n")
    assert len(ra.preload_v2(ra.State(), "face", e, tmp_path, ran=[])) == 1


def test_check_frozen_d080_refuses_until_frozen():
    cfg = d080_cfg()
    cfg["frozen"] = [f for f in cfg.get("frozen") or [] if not f["key"].startswith("controls.refclips_d080")]
    with pytest.raises(ra.StopError, match="not frozen"):
        ra.check_frozen_d080(cfg)


def test_runner_uses_effective_cfg_c1_equivalence_and_d080_freeze():
    src = (ROOT / "scripts" / "refstim_auto_run.py").read_text()
    assert src.count("rs.effective_cfg(load_config())") >= 2           # run() and finalise()
    assert "ra.check_frozen_d080(cfg)" in src
    assert 'c1_equiv=d9["audit"].get("c1_equivalence", False)' in src
    assert 'd9["flip_logs"]' in src


# ------------------------------------------------------------------ metadata-stage dry audit
ENTRY = {"mediatype": CFG["controls"]["refclips_d074"]["bitmap_mediatype"],
         "mime": CFG["controls"]["refclips_auto"]["common"]["mimes"][0], "width": 2000, "height": 2000,
         "sha1": "s1"}


def meta_cand(title="File:a.jpg", tpl=None, adm=True, entry=None, desc=""):
    return ra.Candidate(title, title, dict(entry or ENTRY), {"description": desc, "categories": ""},
                        "CC0" if adm else None, tpl, adm, None)


def test_metadata_stage_stops_at_the_download():
    assert ra.metadata_stage("face", meta_cand(), CFG, set(), 1) == ("continue", None, None)


def test_metadata_stage_c1_reasons_match_evaluate_image():
    assert ra.metadata_stage("face", meta_cand(tpl="Template:Personality rights"), CFG, set(), 1) == \
        ("reject", "C1", "personality_rights")
    assert ra.metadata_stage("body", meta_cand(adm=False), CFG, set(), 1) == ("reject", "C1", "licence")


def test_metadata_stage_c2_and_c4():
    small = dict(ENTRY, width=100)
    assert ra.metadata_stage("place", meta_cand(entry=small), CFG, set(), 1)[1] == "C2"
    assert ra.metadata_stage("face", meta_cand(desc="Y Combinator demo day"), CFG, set(), 1)[1] == "C4"


def v(decision="reject", reason=None, rule=None):
    return {"title": "a", "sha256_title": "a", "decision": decision, "reason": reason, "rule": rule}


def dry(v1, pred, flipped=False):
    return ra.dry_pair(pred, v1, flipped, EX, C1, c1_equiv=True)


def test_dry_pair_classification():
    assert dry(v("reject", "licence", "C1"), ("reject", "C1", "personality_rights")) == "c1_equivalent"
    assert dry(v("reject", "licence", "C1"), ("reject", "C1", "licence")) == "equal"
    assert dry(v("reject", "licence", "C1"), ("continue", None, None), flipped=True) == "flip"
    assert dry(v("pass"), ("continue", None, None)) == "reaches_download"
    assert dry(v("reject", "multi_subject", "F2"), ("continue", None, None)) == "reaches_download"
    assert dry(v("reject", "too_small", "B2"), ("continue", None, None)) == "reaches_download"
    assert dry(v("reject", "duplicate", "C3"), ("continue", None, None)) == "reaches_download"
    assert dry(v("reject", "duplicate", "C3"), ("reject", "C4", "text_or_logo")) == "duplicate_exempt"
    assert dry(v("pass"), ("reject", "D1", ra.IDENTITY_REASON)) == "identity_changed"


@pytest.mark.parametrize("v1,pred", [(v("reject", "licence", "C1"), ("continue", None, None)),
                                     (v("pass"), ("reject", "C1", "licence")),
                                     (v("reject", "too_small", "C2"), ("continue", None, None)),
                                     (v("reject", "text_or_logo", "C4"), ("continue", None, None)),
                                     (v("reject", "text_or_logo", "F8"), ("reject", "C4", "text_or_logo"))])
def test_dry_pair_would_stop(v1, pred):
    assert dry(v1, pred) == "would_stop"


def test_metadata_rules_are_the_pre_download_rules():
    assert ra.METADATA_RULES == ("C0", "C1", "C2", "C3", "C4")
    for cat in ("face", "body", "place"):
        assert ra.IMAGE_RULES[cat][:5] == list(ra.METADATA_RULES)


# ------------------------------------------------------------------ dry-audit script core
def _load_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("d080dry", ROOT / "scripts" / "refstim_d080_dry_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _m(sha1, templates=("Template:CC-zero",)):
    return {"templates": list(templates), "license_short": "CC0", "commons_sha1": sha1, "description": "",
            "categories": ""}


def test_dry_audit_category_counts_and_bug037_pair():
    mod = _load_script()
    e = rs.effective_cfg(d080_cfg())
    ent = {t: dict(ENTRY, title=t, sha1=f"s{t}") for t in ("A", "B", "C", "D")}
    meta = {"A": _m("sA", ("Template:Personality rights", "Template:CC-zero")), "B": _m("sB"),
            "C": _m("other"), "D": _m("sD")}
    rows = [{"title": "A", "sha256_title": "A", "decision": "reject", "rule": "C1", "reason": "licence"},
            {"title": "B", "sha256_title": "B", "decision": "pass", "rule": None, "reason": None},
            {"title": "C", "sha256_title": "C", "decision": "pass", "rule": None, "reason": None},
            {"title": "D", "sha256_title": "D", "decision": "reject", "rule": "C2", "reason": "too_small"}]
    out = mod.audit_category("face", [("L", rows)], ent, meta, {"L": set()}, e, set(), 1)
    assert out["logs"]["L"] == {"c1_equivalent": 1, "identity_changed": 1, "reaches_download": 1,
                                "would_stop": 1}
    assert [w["sha256_title"] for w in out["would_stop"]] == ["D"]


def test_dry_audit_reads_metadata_only():
    src = (ROOT / "scripts" / "refstim_d080_dry_audit.py").read_text()
    for banned in ("_dl(", "RealDetectors", "append_jsonl", "load_rgb()", "urlretrieve", "fetch_verified"):
        assert banned not in src, banned
    assert "rs.page_meta_c4(" in src and "ra.metadata_stage(" in src and "ra.dry_pair(" in src
