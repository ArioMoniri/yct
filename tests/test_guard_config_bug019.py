"""BUG-019: hash-pinned post-hoc QA approval lifts only the missing-tag finding for exactly one commit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_guard_config as cgc  # noqa: E402

C = "0e3ed3ee313c1c252f6bcdfc950957280f264494"


def test_only_one_pinned_commit():
    assert set(cgc.APPROVED_UNTAGGED) == {C}
    assert cgc.APPROVED_UNTAGGED[C][0] == "BUG-019"


def test_unknown_commit_not_approved():
    assert not cgc.approved_untagged("f" * 40, {"guards": {}, "owner": {}})


def test_content_mismatch_not_approved(monkeypatch):
    monkeypatch.setattr(cgc.g, "parents", lambda c: [cgc.GUARDS_BASELINE])
    monkeypatch.setattr(cgc.g, "ticket_exists", lambda t: True)
    assert not cgc.approved_untagged(C, {"guards": {"tampered": True}, "owner": {}})


def test_wrong_parent_not_approved(monkeypatch):
    monkeypatch.setattr(cgc.g, "parents", lambda c: ["0" * 40])
    monkeypatch.setattr(cgc.g, "ticket_exists", lambda t: True)
    monkeypatch.setattr(cgc, "canonical_sha256", lambda sec: cgc.APPROVED_UNTAGGED[C][1])
    assert not cgc.approved_untagged(C, {})


def test_missing_tag_still_fails_for_other_commits(monkeypatch):
    monkeypatch.setattr(cgc.g, "commit_message", lambda c: "no tag")
    old, new = {"guards": {"a": 1}, "owner": {}}, {"guards": {"a": 2}, "owner": {}}
    bad = cgc.check_commit("e" * 40, [old], new, False)
    assert any("without" in b for b in bad)
