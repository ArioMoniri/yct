"""D-081 council (wf_0b4d3341-8ef): the audit_pair equal hole (biostat/neuro/QA B1), a frozen-map test that
every reason shared between C1 and a non-C1 rule is classified by rule (watchdog 1), the v4 routing, and the
post-download re-audit launch precondition in code (watchdog 2). Written before the fix (TDD)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
EX, C1 = ("duplicate",), ("licence", "personality_rights")
CFG = load_config()


def r(title, decision="reject", reason=None, rule=None, key=None, **kw):
    return {"title": title, "sha256_title": key or title, "decision": decision, "reason": reason,
            "rule": rule, **kw}


def audit(row, prior, flips=frozenset(), c1_equiv=True):
    return ra.audit_v2(row, [("L", {p["title"]: p for p in prior})], {"L": set(flips)}, EX, C1,
                       c1_equiv=c1_equiv)


# ------------------------------------------------------------------ B1: equal only within one C1 class
@pytest.mark.parametrize("post", ["B4", "F7"])
def test_c1_vs_post_download_same_reason_stops_v4_side(post):
    with pytest.raises(ra.StopError, match="C1 class"):
        audit(r("a", "reject", "personality_rights", post), [r("a", "reject", "personality_rights", "C1")])


@pytest.mark.parametrize("post", ["B4", "F7"])
def test_c1_vs_post_download_same_reason_stops_superseded_side(post):
    with pytest.raises(ra.StopError, match="C1 class"):
        audit(r("a", "reject", "personality_rights", "C1"), [r("a", "reject", "personality_rights", post)])


def test_audit_pair_direct_both_directions():
    a = ("reject", "personality_rights")
    for a_c1, b_c1 in ((True, False), (False, True)):
        with pytest.raises(ra.StopError, match="C1 class"):
            ra.audit_pair(a, a, False, EX, C1, True, "t", "L", a_c1=a_c1, b_c1=b_c1)


def test_same_class_same_reason_is_still_equal():
    assert audit(r("a", "reject", "personality_rights", "C1"),
                 [r("a", "reject", "personality_rights", "C1")]) == [("L", "equal", None)]
    assert audit(r("a", "reject", "personality_rights", "B4"),
                 [r("a", "reject", "personality_rights", "B4")]) == [("L", "equal", None)]
    assert audit(r("a", "pass"), [r("a", "pass")]) == [("L", "equal", None)]


def test_dry_pair_c1_pred_vs_post_download_same_reason_would_stop():
    v1 = r("a", "reject", "personality_rights", "B4")
    assert ra.dry_pair(("reject", "C1", "personality_rights"), v1, False, EX, C1, True) == "would_stop"


# ------------------------------------------------------------------ watchdog 1: frozen-map test
def _shared_reasons() -> dict[str, set[str]]:
    rr = CFG["controls"]["refclips_auto"]["rule_reasons"]
    by: dict[str, set[str]] = {}
    for rule, v in rr.items():
        for x in (v if isinstance(v, list) else [v]):
            by.setdefault(x, set()).add(rule)
    c1 = {x for x, rules in by.items() if "C1" in rules}
    return {x: by[x] - {"C1"} for x in c1 if by[x] - {"C1"}}


def test_every_reason_shared_between_c1_and_another_rule_is_classified_by_rule():
    shared = _shared_reasons()
    assert shared, "the frozen map shares no C1 reason: this test would test nothing"
    for reason, rules in shared.items():
        assert ra.is_c1_reject(r("a", "reject", reason, "C1"), C1) is True
        for other in rules:
            assert ra.is_c1_reject(r("a", "reject", reason, other), C1) is False
            with pytest.raises(ra.StopError, match="C1 class"):
                audit(r("a", "reject", reason, other), [r("a", "reject", reason, "C1")])
            with pytest.raises(ra.StopError, match="C1 class"):
                audit(r("a", "reject", reason, "C1"), [r("a", "reject", reason, other)])


def test_c1_reason_codes_equal_the_frozen_c1_rule_reasons():
    rr = CFG["controls"]["refclips_auto"]["rule_reasons"]["C1"]
    assert set(rr) == set(CFG["controls"]["refclips_d079"]["audit"]["c1_reasons"])


def test_fixture_rule_for_mapping_is_pinned_and_agrees_with_the_frozen_map():
    from tests._refstim_rules import PINNED, rule_for

    rr = CFG["controls"]["refclips_auto"]["rule_reasons"]
    for reason, rule in PINNED.items():
        if reason == "identity_changed":
            assert rule == "D1"
            continue
        v = rr[rule]
        assert reason in (v if isinstance(v, list) else [v]), (reason, rule)
    assert rule_for("reject", "licence") == "C1" and rule_for("reject", "personality_rights") == "C1"
    assert rule_for("pass", None) is None
    with pytest.raises(KeyError):
        rule_for("reject", "no_such_reason")


# ------------------------------------------------------------------ re-audit (post-download, offline)
def _reaudit(logs, baseline, flips=None, dry=None):
    return ra.post_download_reaudit({"face": logs}, {"face": set(baseline)}, flips or {}, EX, C1,
                                    dry_revids={"face": dry or {}})


def test_reaudit_clean_logs_has_no_stops_and_counts_kinds():
    v1 = ("v1.jsonl", [r("a", "reject", "licence", "C1"), r("b", "pass")])
    v3 = ("v3.jsonl", [r("a", "reject", "personality_rights", "C1",
                         audit_c1_equivalent={"v1.jsonl": "licence"}), r("b", "pass")])
    doc = _reaudit([v1, v3], {"v1.jsonl"})
    face = doc["face"]
    assert face["stops"] == [] and face["same_reason_diff_class"] == 0
    assert face["logs"]["v3.jsonl"]["audit_kinds"] == {"c1_equivalent": 1, "equal": 1}
    assert "v1.jsonl" not in face["logs"]          # baseline logs are never re-audited, only compared
    assert face["logs"]["v3.jsonl"]["adult_proxy_rejects"] == 0


def test_reaudit_counts_adult_proxy_rejects():
    v1 = ("v1.jsonl", [r("a", "pass")])
    v3 = ("v3.jsonl", [r("b", "reject", "personality_rights", "B4"),
                       r("c", "reject", "personality_rights", "F7")])
    assert _reaudit([v1, v3], {"v1.jsonl"})["face"]["logs"]["v3.jsonl"]["adult_proxy_rejects"] == 2


def test_reaudit_records_a_stop_and_counts_same_reason_diff_class():
    v1 = ("v1.jsonl", [r("a", "reject", "personality_rights", "C1")])
    v3 = ("v3.jsonl", [r("a", "reject", "personality_rights", "B4")])
    face = _reaudit([v1, v3], {"v1.jsonl"})["face"]
    assert face["same_reason_diff_class"] == 1
    assert len(face["stops"]) == 1 and face["stops"][0]["log"] == "v3.jsonl"


def test_reaudit_compares_each_log_with_every_earlier_log():
    v1 = ("v1.jsonl", [r("a", "pass")])
    v2 = ("v2.jsonl", [r("a", "pass")])
    v3 = ("v3.jsonl", [r("a", "reject", "too_small", "C2")])
    face = _reaudit([v1, v2, v3], {"v1.jsonl"})["face"]
    assert {s["log"] for s in face["stops"]} == {"v3.jsonl"}
    assert face["logs"]["v2.jsonl"]["audit_kinds"] == {"equal": 1}


def test_reaudit_checks_logged_c1_equivalent_notes():
    v1 = ("v1.jsonl", [r("a", "reject", "licence", "C1")])
    v3 = ("v3.jsonl", [r("a", "reject", "personality_rights", "C1")])     # note not logged
    face = _reaudit([v1, v3], {"v1.jsonl"})["face"]
    assert face["stops"] and "c1_equivalent notes" in face["stops"][0]["stop"]
    v3 = ("v3.jsonl", [r("a", "reject", "personality_rights", "C1",
                         audit_c1_equivalent={"v1.jsonl": "licence"})])
    assert _reaudit([v1, v3], {"v1.jsonl"})["face"]["stops"] == []


# ------------------------------------------------------------------ watchdog 2: launch precondition
def _cfg_d081(frozen=True, sha="0" * 64):
    cfg = copy.deepcopy(CFG)
    arts = cfg["controls"].setdefault("refclips_d081_artifacts", {})
    arts["reaudit_sha256"] = sha
    arts["dry_audit_sha256"] = "1" * 64
    # the repo config carries the real D-081 freeze rows since 86be45a: drop them so frozen=False means it
    cfg["frozen"] = [r for r in cfg.get("frozen") or [] if r["key"] not in ra.D081_FROZEN_KEYS]
    if frozen:
        cfg["frozen"] = list(cfg.get("frozen") or []) + [
            {"key": k, "frozen_at": "x"} for k in ra.D081_FROZEN_KEYS]
    return cfg


def _doc(stops=(), diff=0):
    return {"face": {"stops": list(stops), "same_reason_diff_class": diff, "logs": {}}}


def test_check_frozen_d081_refuses_unfrozen_keys():
    with pytest.raises(ra.StopError, match="not frozen"):
        ra.check_frozen_d081(_cfg_d081(frozen=False), _doc())


def test_check_frozen_d081_refuses_a_sha_mismatch():
    with pytest.raises(ra.StopError, match="re-audit sha"):
        ra.check_frozen_d081(_cfg_d081(sha="0" * 64), _doc())


def test_check_frozen_d081_refuses_stops_and_diff_class_pairs():
    for doc in (_doc(stops=[{"log": "v3", "title": "a", "stop": "x"}]), _doc(diff=1)):
        sha = hashlib.sha256(rs.canonical(doc).encode()).hexdigest()
        with pytest.raises(ra.StopError, match="re-audit"):
            ra.check_frozen_d081(_cfg_d081(sha=sha), doc)


def test_check_frozen_d081_accepts_a_clean_recomputed_doc():
    doc = _doc()
    sha = hashlib.sha256(rs.canonical(doc).encode()).hexdigest()
    ra.check_frozen_d081(_cfg_d081(sha=sha), doc)


def test_check_frozen_d081_refuses_a_missing_sha():
    with pytest.raises(ra.StopError, match="reaudit_sha256 not set"):
        ra.check_frozen_d081(_cfg_d081(sha=None), _doc())


# ------------------------------------------------------------------ v4 routing
def test_effective_cfg_routes_v4_logs_and_the_d081_dry_audit():
    cfg = rs.effective_cfg(CFG)
    d8, d81 = CFG["controls"]["refclips_d080"], CFG["controls"]["refclips_d081"]
    d9 = cfg["controls"]["refclips_d079"]
    assert d9["log_version"] == "v4" and d9["logs"] == d81["logs"]
    assert d9["finality"] == d81["finality"]
    for cat in d9["category_order"]:
        for p in d81["superseded_logs_add"][cat]:
            assert p in d9["superseded_logs"][cat]
        for p in d8["superseded_logs_add"][cat]:
            assert p in d9["superseded_logs"][cat]
    assert d9["flip_logs"] == CFG["controls"]["refclips_d079"]["superseded_logs"]
    assert cfg["controls"]["refclips_d080"]["dry_audit_file"] == d81["dry_audit_file"]
    assert (cfg["controls"]["refclips_d080_artifacts"]["dry_audit_sha256"]
            == CFG["controls"]["refclips_d081_artifacts"]["dry_audit_sha256"])
    # the input (incl. the frozen D-080 keys) is never mutated
    assert CFG["controls"]["refclips_d080"]["dry_audit_file"] == "data/refstim/d080_dry_audit.json"


def test_d081_superseded_adds_are_the_v3_evidence_logs():
    d81 = CFG["controls"]["refclips_d081"]
    v3 = CFG["controls"]["refclips_d080"]["logs"]
    for cat, paths in d81["superseded_logs_add"].items():
        assert set(paths) <= {v3[cat]}
        for p in paths:
            assert (ROOT / p).exists(), p
    assert all(p.endswith("_v4.jsonl") for p in d81["logs"].values())


def test_reaudit_from_cfg_runs_on_the_committed_logs():
    doc = rs.post_download_reaudit_cfg(CFG, ROOT)
    for cat in ("face", "body"):
        assert doc[cat]["stops"] == [] and doc[cat]["same_reason_diff_class"] == 0
    assert set(doc["face"]["logs"]) == {"image_face_auto_log_v2.jsonl", "image_face_auto_log_v3.jsonl"}
    assert set(doc["body"]["logs"]) == {"image_body_auto_log_v3.jsonl"}
    want = CFG["controls"]["refclips_d081_artifacts"]["reaudit_sha256"]
    p = ROOT / CFG["controls"]["refclips_d081"]["reaudit_file"]
    assert hashlib.sha256(rs.canonical(doc).encode()).hexdigest() == want == rs.file_sha(p)
    assert json.loads(p.read_text()) == doc


def test_runner_enforces_the_d081_launch_precondition_in_run_and_finalise():
    src = (ROOT / "scripts/refstim_auto_run.py").read_text()
    assert src.count("ra.check_frozen_d081(cfg, rs.post_download_reaudit_cfg(load_config(), ROOT))") == 2


def test_runner_refuses_while_d081_is_not_frozen():
    cfg = rs.effective_cfg(CFG)
    cfg["frozen"] = [f for f in cfg.get("frozen") or [] if not f["key"].startswith("controls.refclips_d081")]
    with pytest.raises(ra.StopError, match="not frozen"):
        ra.check_frozen_d081(cfg, rs.post_download_reaudit_cfg(CFG, ROOT))


def test_reaudit_code_is_under_the_dry_audit_code_change_guard():
    assert "scripts/refstim_d081_reaudit.py" in ra.DRY_AUDIT_CODE_PATHS
    assert "src/yct/curate/refstim*.py" in ra.DRY_AUDIT_CODE_PATHS


def test_committed_d081_dry_audit_passes_the_launch_rule():
    cfg = rs.effective_cfg(CFG)
    doc = ra.check_dry_audit(cfg, ROOT, "HEAD", lambda a, b, paths: [])
    assert doc["decision"] == "D-081"
    assert all(c["would_stop"] == [] for c in doc["categories"].values())
    names = {Path(q).name for q in CFG["controls"]["refclips_d081"]["superseded_logs_add"]["face"]}
    assert names <= set(doc["categories"]["face"]["logs"])
