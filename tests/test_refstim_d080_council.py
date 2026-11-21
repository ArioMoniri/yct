"""D-080 council REVISE items (council_d080_{watchdog,referee,biostat}.md). Written before the fix (TDD).

Watchdog B1: Commons revision drift after the dry audit has a pre-stated non-defect resolution
(stop_resolution.audit_revid_drift). Referee B1 / Biostat: the runner enforces the dry-audit launch rule in
code (sha, would_stop == [], every superseded log present, code unchanged since the dry-audit commit)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests._refstim_rules import rule_for
from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
EX, C1 = ("duplicate",), ("licence", "personality_rights")


def row(title, decision="reject", reason=None, read_revid=None, revid=None):
    d = {"title": title, "sha256_title": title, "decision": decision, "reason": reason,
         "rule": rule_for(decision, reason)}   # BUG-038: real rows carry their rule
    if read_revid is not None:
        d["read_revid"] = read_revid
    if revid is not None:
        d["revid"] = revid
    return d


def audit(r, prior, dry_revids=None):
    return ra.audit_v2(r, [("L", {p["title"]: p for p in prior})], {"L": set()}, EX, C1, c1_equiv=True,
                       dry_revids=dry_revids)


# ------------------------------------------------------------------ Watchdog B1: revid drift
def test_config_states_the_revid_drift_resolution():
    sr = CFG["controls"]["refclips_d080"]["stop_resolution"]
    assert sr["audit_revid_drift"] == "current_revision_stands_log_both_resume_next_rank"


def test_drift_past_both_revids_resolves_and_is_reported():
    v3 = row("a", "pass", None, read_revid=30)
    v1 = row("a", "reject", "licence", revid=10)          # v1 rows carry the snapshot revid only
    notes = audit(v3, [v1], dry_revids={"a": 20})
    assert notes == [("L", "revid_drift", "licence")]


def test_drift_against_a_v2_row_uses_its_read_revid():
    v3 = row("a", "reject", "licence", read_revid=30)
    v2 = row("a", "pass", None, read_revid=20, revid=10)
    assert audit(v3, [v2], dry_revids={"a": 25}) == [("L", "revid_drift", None)]


def test_no_drift_when_read_revid_equals_the_dry_audit_revid():
    v3 = row("a", "pass", None, read_revid=20)
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(v3, [row("a", "reject", "licence", revid=10)], dry_revids={"a": 20})


def test_no_drift_when_read_revid_equals_the_superseded_revid():
    v3 = row("a", "pass", None, read_revid=10)
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(v3, [row("a", "reject", "licence", revid=10)], dry_revids={"a": 20})


def test_title_missing_from_the_dry_audit_is_not_exempt():
    v3 = row("a", "pass", None, read_revid=30)
    with pytest.raises(ra.StopError):
        audit(v3, [row("a", "reject", "licence", revid=10)], dry_revids={})


def test_without_dry_revids_the_d080_draft_behaviour_holds():
    v3 = row("a", "pass", None, read_revid=30)
    with pytest.raises(ra.StopError):
        audit(v3, [row("a", "reject", "licence", revid=10)])


def test_matching_pairs_are_unchanged_under_drift():
    v3 = row("a", "reject", "licence", read_revid=30)
    assert audit(v3, [row("a", "reject", "licence", revid=10)], dry_revids={"a": 20}) == \
        [("L", "equal", None)]


def test_revid_drift_disclosure_lists_rows():
    rows = [{"title": "a", "sha256_title": "k", "decision": "pass", "read_revid": 30,
             "audit_revid_drift": {"L": {"superseded_revid": 10, "dry_audit_revid": 20,
                                         "superseded": ["reject", "licence"]}}},
            {"title": "b", "sha256_title": "j", "decision": "reject"}]
    assert ra.revid_drift_disclosure(rows) == [
        {"title": "a", "sha256_title": "k", "decision": "pass", "read_revid": 30,
         "logs": {"L": {"superseded_revid": 10, "dry_audit_revid": 20, "superseded": ["reject", "licence"]}}}]
    assert ra.revid_drift_disclosure(rows[1:]) == "none"


# ------------------------------------------------------------------ Referee B1 / Biostat: launch rule
def _cfg_with(tmp: Path, doc: dict) -> tuple[dict, Path]:
    p = tmp / "data/refstim/d080_dry_audit.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))
    cfg = rs.effective_cfg(copy.deepcopy(CFG))
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    cfg["controls"]["refclips_d080_artifacts"]["dry_audit_sha256"] = sha
    return cfg, p


def _good_doc(cfg: dict) -> dict:
    d9 = cfg["controls"]["refclips_d079"]
    cats = {}
    for cat in d9["category_order"]:
        if d9["superseded_logs"][cat]:
            cats[cat] = {"logs": {Path(q).name: {"equal": 1} for q in d9["superseded_logs"][cat]},
                         "would_stop": [], "read_revids": {}}
    return {"decision": "D-080", "code_commit": "c0ffee", "categories": cats}


def no_change(a, b, paths):
    return []


def test_launch_rule_accepts_a_good_dry_audit(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    cfg, _ = _cfg_with(tmp_path, _good_doc(cfg0))
    doc = ra.check_dry_audit(cfg, tmp_path, "abc", no_change)
    assert doc["code_commit"] == "c0ffee"


def test_launch_rule_refuses_a_sha_mismatch(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    cfg, p = _cfg_with(tmp_path, _good_doc(cfg0))
    p.write_text(p.read_text() + " ")
    with pytest.raises(ra.StopError, match="sha"):
        ra.check_dry_audit(cfg, tmp_path, "abc", no_change)


def test_launch_rule_refuses_would_stop(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    doc = _good_doc(cfg0)
    doc["categories"]["face"]["would_stop"] = [{"log": "x", "sha256_title": "k"}]
    cfg, _ = _cfg_with(tmp_path, doc)
    with pytest.raises(ra.StopError, match="would_stop"):
        ra.check_dry_audit(cfg, tmp_path, "abc", no_change)


def test_launch_rule_refuses_a_missing_superseded_log(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    doc = _good_doc(cfg0)
    doc["categories"]["face"]["logs"].pop(next(iter(doc["categories"]["face"]["logs"])))
    cfg, _ = _cfg_with(tmp_path, doc)
    with pytest.raises(ra.StopError, match="superseded log"):
        ra.check_dry_audit(cfg, tmp_path, "abc", no_change)


def test_launch_rule_refuses_a_missing_category(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    doc = _good_doc(cfg0)
    doc["categories"].pop("body")
    cfg, _ = _cfg_with(tmp_path, doc)
    with pytest.raises(ra.StopError, match="body"):
        ra.check_dry_audit(cfg, tmp_path, "abc", no_change)


def test_launch_rule_refuses_without_a_code_commit(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    doc = _good_doc(cfg0)
    doc.pop("code_commit")
    cfg, _ = _cfg_with(tmp_path, doc)
    with pytest.raises(ra.StopError, match="code_commit"):
        ra.check_dry_audit(cfg, tmp_path, "abc", no_change)


def test_launch_rule_refuses_changed_code(tmp_path):
    cfg0 = rs.effective_cfg(copy.deepcopy(CFG))
    cfg, _ = _cfg_with(tmp_path, _good_doc(cfg0))
    seen = {}

    def changed(a, b, paths):
        seen.update(a=a, b=b, paths=tuple(paths))
        return ["src/yct/curate/refstim_auto.py"]

    with pytest.raises(ra.StopError, match="changed since the dry audit"):
        ra.check_dry_audit(cfg, tmp_path, "abc", changed)
    assert seen["a"] == "c0ffee" and seen["b"] == "abc"
    assert set(seen["paths"]) == set(ra.DRY_AUDIT_CODE_PATHS)


def test_dry_audit_code_paths_cover_the_client_and_the_script():
    assert "src/yct/curate/refstim*.py" in ra.DRY_AUDIT_CODE_PATHS
    assert "scripts/refstim_d080_dry_audit.py" in ra.DRY_AUDIT_CODE_PATHS


def test_runner_calls_the_launch_rule_and_passes_dry_revids():
    src = (ROOT / "scripts/refstim_auto_run.py").read_text()
    assert "ra.check_dry_audit(cfg, ROOT, run_commit" in src
    assert "dry_revids=" in src
    assert "revid_drift_disclosure" in src


def test_dry_audit_script_records_commit_and_read_revids():
    src = (ROOT / "scripts/refstim_d080_dry_audit.py").read_text()
    assert '"code_commit"' in src and '"read_revids"' in src


def test_committed_dry_audit_matches_config_sha_and_launch_rule():
    cfg = rs.effective_cfg(copy.deepcopy(CFG))
    doc = ra.check_dry_audit(cfg, ROOT, cfg_commit := "HEAD", no_change)
    assert cfg_commit and all(c["would_stop"] == [] for c in doc["categories"].values())
    assert all(c["read_revids"] for c in doc["categories"].values())
