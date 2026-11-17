"""check_guard_config.py: the guard exceptions (config.yaml `guards:` / `owner:`) are frozen (FIX-C3-ENG).

Reproduces the two bypasses shown at gate G-D032 cycle 2 and asserts that they now FAIL:
  * Watchdog: commit BUDGET_USD=9999, a harmless commit Y, then move `human_signed_since` to Y;
  * QA: commit A adds a test skip, commit B adds an allowlist entry for A under an existing ticket.
"""
import pytest

GC = "check_guard_config.py"
HS = "check_human_signed.py"
TW = "check_test_weakening.py"
BUGS = "- BUG-010 | P0 | x\n- BUG-011 | P0 | y\n"
TOKEN = "[QA-approved guard change: BUG-011]"


def _cfg(since=None, allow=(), exempt=(), pin=None) -> str:
    out = ["guards:\n"]
    if since:
        out.append(f"  human_signed_since: {since}\n")
    out.append("  test_weakening_allowlist:\n" if allow else "  test_weakening_allowlist: []\n")
    for a in allow:
        out.append(f"    - {{commit: {a[0]}, path: {a[1]}, kind: {a[2]}, ticket: {a[3]}}}\n")
    out.append("  human_only_exempt:\n" if exempt else "  human_only_exempt: []\n")
    for e in exempt:
        out.append(f"    - {{commit: {e[0]}, path: {e[1]}, ticket: {e[2]}}}\n")
    if pin:
        out.append(f"owner:\n  arn_pin: \"{pin}\"\n")
    return "".join(out)


@pytest.fixture
def base(repo):
    return repo.commit(f"setup {TOKEN}", {"BUGS.md": BUGS, "config.yaml": _cfg(),
                                 "tests/test_a.py": "def test_a():\n    assert 1\n"})


def test_watchdog_bypass_move_since_forward_fails(repo, base):
    """Watchdog cycle 2: BUDGET_USD=9999, harmless Y, human_signed_since -> Y."""
    repo.commit("budget", {"infra/BUDGET_USD": "9999\n"})
    y = repo.commit("harmless", {"x.txt": "1\n"})
    repo.commit("move since", {"config.yaml": _cfg(since=y)})
    hs = repo.run_script(HS)  # the bypass itself still "works" on check_human_signed ...
    assert hs.returncode == 0, hs.stdout
    res = repo.run_script(GC)  # ... but the guard-config guard catches it
    assert res.returncode == 1 and "human_signed_since" in res.stdout, res.stdout


def test_moving_since_forward_fails_even_with_qa_token(repo, base):
    a = repo.commit("a", {"x.txt": "1\n"})
    repo.commit(f"since a {TOKEN}", {"config.yaml": _cfg(since=a)})
    b = repo.commit("b", {"x.txt": "2\n"})
    repo.commit(f"move since {TOKEN}", {"config.yaml": _cfg(since=b)})
    res = repo.run_script(GC)
    assert res.returncode == 1 and "moved later" in res.stdout


def test_qa_bypass_self_allowlisting_fails(repo, base):
    """QA cycle 2: commit A adds a skip, commit B allowlists A under an existing ticket (no approval)."""
    a = repo.commit("A", {"tests/test_a.py": "import pytest\n\n\ndef test_a():\n    pytest.skip('x')\n"
                                             "    assert 1\n"})
    repo.commit("B", {"config.yaml": _cfg(allow=[(a, "tests/test_a.py", "skip", "BUG-010")])})
    tw = repo.run_script(TW)
    assert tw.returncode == 0 and "ALLOWLISTED" in tw.stdout  # the allowlist itself is honoured ...
    res = repo.run_script(GC)  # ... but adding the entry without QA approval fails
    assert res.returncode == 1 and "QA-approved guard change" in res.stdout, res.stdout


def test_qa_token_with_ticket_and_past_commit_passes(repo, base):
    a = repo.commit("A", {"tests/test_a.py": "import pytest\n\n\ndef test_a():\n    pytest.skip('x')\n"
                                             "    assert 1\n"})
    repo.commit(f"allowlist A {TOKEN}",
                {"config.yaml": _cfg(allow=[(a, "tests/test_a.py", "skip", "BUG-010")])})
    res = repo.run_script(GC)
    assert res.returncode == 0, res.stdout


def test_token_with_unknown_ticket_fails(repo, base):
    a = repo.commit("A", {"x.txt": "1\n"})
    repo.commit("allow [QA-approved guard change: BUG-999]",
                {"config.yaml": _cfg(allow=[(a, "tests/test_a.py", "skip", "BUG-010")])})
    res = repo.run_script(GC)
    assert res.returncode == 1 and "BUG-999" in res.stdout


def test_entry_for_own_or_future_commit_fails_even_with_token(repo, base):
    """An exception can only excuse a strict ancestor: never the allowlisting commit itself."""
    repo.write("tests/test_a.py", "import pytest\n\n\ndef test_a():\n    pytest.skip('x')\n")
    head_cfg = _cfg(allow=[("0" * 40, "tests/test_a.py", "skip", "BUG-010")])
    repo.commit(f"skip + allowlist {TOKEN}", {"config.yaml": head_cfg})
    res = repo.run_script(GC)
    assert res.returncode == 1 and "strict ancestor" in res.stdout


def test_human_only_exempt_entry_needs_token(repo, base):
    b = repo.commit("budget", {"infra/BUDGET_USD": "1\n"})
    repo.commit("exempt it", {"config.yaml": _cfg(exempt=[(b, "infra/BUDGET_USD", "BUG-011")])})
    assert repo.run_script(HS).returncode == 0
    res = repo.run_script(GC)
    assert res.returncode == 1 and "QA-approved guard change" in res.stdout


def test_owner_pin_cannot_change(repo, base):
    repo.commit(f"pin {TOKEN}", {"config.yaml": _cfg(pin="arn:aws:iam::1:root")})
    assert repo.run_script(GC).returncode == 0
    repo.commit(f"re-pin {TOKEN}", {"config.yaml": _cfg(pin="arn:aws:iam::2:root")})
    res = repo.run_script(GC)
    assert res.returncode == 1 and "arn_pin" in res.stdout


def test_removing_exceptions_needs_token_but_is_allowed(repo, base):
    a = repo.commit("A", {"x.txt": "1\n"})
    repo.commit(f"allow {TOKEN}", {"config.yaml": _cfg(allow=[(a, "tests/test_a.py", "skip", "BUG-010")])})
    repo.commit(f"drop {TOKEN}", {"config.yaml": _cfg()})
    assert repo.run_script(GC).returncode == 0


def test_unrelated_config_changes_pass(repo, base):
    repo.commit("tune", {"config.yaml": _cfg() + "window:\n  start: 5\n"})
    assert repo.run_script(GC).returncode == 0


def test_merge_bringing_guard_change_fails(repo, base):
    repo.git("checkout", "-q", "-b", "side")
    y = repo.commit("y", {"y.txt": "1\n"})
    repo.commit("since", {"config.yaml": _cfg(since=y)})
    repo.git("checkout", "-q", "main")
    repo.commit("other", {"z.txt": "1\n"})
    repo.git("merge", "-q", "--no-edit", "side")
    assert repo.run_script(GC).returncode == 1


def test_makefile_runs_guard_config():
    from pathlib import Path

    mk = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
    assert "check_guard_config" in mk.split("GUARDS =", 1)[1].splitlines()[0]
