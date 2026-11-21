"""BUG-038: the determinism audit must classify a C1 reject by its RULE, not by its reason code.
`personality_rights` is the reason for C1 (Template:Personality rights) and for F7/B4 (the CLIP adult proxy,
after the download). Written before the fix (TDD)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
EX, C1 = ("duplicate",), ("licence", "personality_rights")


def r(title, decision="reject", reason=None, rule=None, key=None):
    return {"title": title, "sha256_title": key or title, "decision": decision, "reason": reason,
            "rule": rule}


def audit(row, prior, flips=frozenset(), c1_equiv=True):
    return ra.audit_v2(row, [("L", {p["title"]: p for p in prior})], {"L": set(flips)}, EX, C1,
                       c1_equiv=c1_equiv)


def test_flip_then_b4_adult_reject_is_a_flip_not_a_contradiction():
    # the BUG-038 STOP: v1 C1 licence reject (flip-listed); v3 passes C1 and B4 rejects (personality_rights)
    notes = audit(r("a", "reject", "personality_rights", "B4"), [r("a", "reject", "licence", "C1")], {"a"})
    assert notes == [("L", "flip", "licence")]
    notes = audit(r("a", "reject", "personality_rights", "F7"), [r("a", "reject", "licence", "C1")], {"a"})
    assert notes == [("L", "flip", "licence")]


def test_flip_still_contradicted_by_a_real_c1_reject():
    with pytest.raises(ra.StopError, match="flip list contradiction"):
        audit(r("a", "reject", "personality_rights", "C1"), [r("a", "reject", "licence", "C1")], {"a"})


def test_flip_listed_title_must_be_a_v1_c1_reject_by_rule():
    with pytest.raises(ra.StopError, match="flip list contradiction"):
        audit(r("a", "pass"), [r("a", "reject", "personality_rights", "F7")], {"a"})


def test_c1_vs_post_download_personality_reason_is_not_c1_equivalent():
    # v1 C1 licence (not flip-listed) vs v3 B4: v3 passed C1 = an admissibility change -> STOP
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(r("a", "reject", "personality_rights", "B4"), [r("a", "reject", "licence", "C1")])
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(r("a", "reject", "licence", "C1"), [r("a", "reject", "personality_rights", "F7")])


def test_both_c1_by_rule_stay_c1_equivalent():
    notes = audit(r("a", "reject", "personality_rights", "C1"), [r("a", "reject", "licence", "C1")])
    assert notes == [("L", "c1_equivalent", "licence")]


def test_duplicate_vs_post_download_personality_reason_is_exempt():
    # C3 runs after C1: a duplicate passed C1; an F7 reject also passed C1 -> no admissibility change
    notes = audit(r("a", "reject", "personality_rights", "F7"), [r("a", "reject", "duplicate", "C3")])
    assert notes == [("L", "duplicate_exempt", None)]
    with pytest.raises(ra.StopError):
        audit(r("a", "reject", "personality_rights", "C1"), [r("a", "reject", "duplicate", "C3")])


def test_reject_row_without_rule_fails_closed():
    with pytest.raises(ra.StopError, match="no rule"):
        audit(r("a", "reject", "licence"), [r("a", "reject", "licence", "C1")])
    with pytest.raises(ra.StopError, match="no rule"):
        audit(r("a", "reject", "licence", "C1"), [r("a", "reject", "licence")])


def test_dry_pair_flip_requires_v1_c1_rule():
    assert ra.dry_pair(("continue", None, None), r("a", "reject", "licence", "C1"), True, EX, C1) == "flip"
    assert ra.dry_pair(("continue", None, None), r("a", "reject", "personality_rights", "F7"), True, EX,
                       C1) == "would_stop"


def test_stop_evidence_is_written_before_the_stop(tmp_path):
    row = r("a", "reject", "personality_rights", "B4") | {"templates": ["Template:Cc-zero"],
                                                          "templates_sha256": "x" * 64}
    p = tmp_path / "image_body_auto_log_v3.jsonl"
    out = ra.write_stop_evidence(p, row, ra.StopError("boom"))
    doc = json.loads(out.read_text())
    assert out.name == "image_body_auto_log_v3.stop.json"
    assert doc["row"]["templates"] == ["Template:Cc-zero"] and doc["row"]["rule"] == "B4"
    assert doc["stop"] == "boom"


def test_runner_writes_stop_evidence_around_the_audit():
    src = (ROOT / "scripts" / "refstim_auto_run.py").read_text()
    assert "ra.write_stop_evidence(log_path, row, exc)" in src


def test_real_logs_classify_bug038_title_as_flip():
    # regression on the committed evidence: the replayed B4 row of the STOP title against the v1 body log
    v1 = {json.loads(x)["title"]: json.loads(x)
          for x in (ROOT / "data/refstim/image_body_auto_log.jsonl").read_text().splitlines() if x.strip()}
    t = "File:Mohammad Bagher Adib Behrooz 2016 (Unsplash).jpg"
    old = v1[t]
    row = r(t, "reject", "personality_rights", "B4", key=old["sha256_title"])
    notes = ra.audit_v2(row, [("image_body_auto_log.jsonl", v1)],
                        {"image_body_auto_log.jsonl": {old["sha256_title"]}}, EX, C1, c1_equiv=True)
    assert notes == [("image_body_auto_log.jsonl", "flip", "licence")]
