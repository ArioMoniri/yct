"""The REAL repo's guard exceptions are pinned here (Watchdog G-D032 c2: "hard-code the exceptions and pin
them with a test"). Changing config.yaml `guards:`/`owner:` must change this file too (visible in review)
and needs '[QA-approved guard change: <TICKET>]' in the commit (scripts/check_guard_config.py)."""
import importlib.util
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("cgc", ROOT / "scripts" / "check_guard_config.py")
cgc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cgc)

EXPECTED_HUMAN_ONLY_EXEMPT = {
    ("6c16d89381b4533336ea83d1f4adc7127a7c2387", "infra/BUDGET_USD", "BUG-011"),
    ("6c16d89381b4533336ea83d1f4adc7127a7c2387", "DATA_DECISION.md", "BUG-011"),
    ("4c194c79f14adc75d86940525c112ec0a3a6041d", "docs/owner_age.pub", "BUG-011"),
}
EXPECTED_ALLOWLIST = {
    ("c35c53c533705c080718410cbad001f43ff83247", "tests/_atlas.py", "skip", "BUG-008"),
    ("e4cdc4eedbbbe0c468eed87c10f7548641180147", "tests/conftest.py", "skip", "BUG-009"),
    ("8005ceb0224dc776f19d996a88ea4311b22affd3", "tests/test_guards_human_signed.py", "assertion", "BUG-009"),
    ("8005ceb0224dc776f19d996a88ea4311b22affd3", "tests/test_guards_human_signed.py", "testdef", "BUG-009"),
    ("8005ceb0224dc776f19d996a88ea4311b22affd3", "tests/test_guards_prereg.py", "assertion", "BUG-009"),
    ("8005ceb0224dc776f19d996a88ea4311b22affd3", "tests/test_guards_prereg.py", "testdef", "BUG-009"),
}


def _cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def test_guard_exceptions_are_exactly_the_reviewed_set():
    gd = _cfg()["guards"]
    assert set(gd) == {"human_only_exempt", "test_weakening_allowlist"}  # no human_signed_since any more
    got_ex = {(e["commit"], e["path"], e["ticket"]) for e in gd["human_only_exempt"]}
    assert got_ex == EXPECTED_HUMAN_ONLY_EXEMPT
    assert len(gd["human_only_exempt"]) == len(EXPECTED_HUMAN_ONLY_EXEMPT)
    got = {(e["commit"], e["path"], e["kind"], e["ticket"]) for e in gd["test_weakening_allowlist"]}
    assert got == EXPECTED_ALLOWLIST and len(gd["test_weakening_allowlist"]) == len(EXPECTED_ALLOWLIST)


def test_owner_pin_is_recorded():
    assert _cfg()["owner"] == {"arn_pin": "arn:aws:iam::235229001983:root"}


def test_guard_config_baseline_is_pinned():
    assert cgc.GUARDS_BASELINE == "18b39c279222308b316d34ba42157c6c4c9c3cda"
    assert cgc.GUARDS_BASELINE_SHA256 == "07dd709dc043603bffef8e081a240ee6dc908503d49715f05d5d68ebc9251d0b"
    have = subprocess.run(["git", "cat-file", "-e", f"{cgc.GUARDS_BASELINE}^{{commit}}"], cwd=ROOT).returncode
    if have == 0:  # full clones (CI fetch-depth 0): the pinned hash really is the baseline's content
        import os
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            assert cgc.canonical_sha256(cgc.sections(cgc.GUARDS_BASELINE)) == cgc.GUARDS_BASELINE_SHA256
        finally:
            os.chdir(cwd)


def test_every_exempted_commit_predates_the_baseline():
    gd = _cfg()["guards"]
    for e in gd["human_only_exempt"] + gd["test_weakening_allowlist"]:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", e["commit"], cgc.GUARDS_BASELINE], cwd=ROOT)
        assert r.returncode == 0, e
