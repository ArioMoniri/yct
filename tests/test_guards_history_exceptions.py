"""Documented history exceptions for the guards (FIX-D032-1), configured in config.yaml `guards:`.

* guards.human_signed_since: commits strictly before the D-030 adoption commit are not checked by
  check_human_signed (they predate SSM owner actions); that commit and everything after still are.
* guards.test_weakening_allowlist: exact (full commit SHA, path, finding kind, ticket) entries; the
  ticket must exist in BUGS.md/ENHANCEMENTS.md. Anything not matching exactly still FAILS.
"""
import pytest

HS = "check_human_signed.py"
TW = "check_test_weakening.py"
BUGS = "- BUG-008 | P0 | tests/_atlas.py skip without ticket\n"


def _cfg(since=None, allow=None) -> str:
    lines = ["guards:\n"]
    if since:
        lines.append(f"  human_signed_since: {since}\n")
    if allow is not None:
        lines.append("  test_weakening_allowlist:\n")
        for a in allow:
            lines.append(f"    - {{commit: {a['commit']}, path: {a['path']}, kind: {a['kind']}, "
                         f"ticket: {a['ticket']}, note: x}}\n")
    return "".join(lines)


# ---------------------------------------------------------------- human_signed_since
def test_commits_before_since_are_ignored(repo):
    repo.commit("old budget", {"infra/BUDGET_USD": "200\n"})
    since = repo.commit("adopt D-030", {"x.txt": "1\n"})
    repo.commit("config", {"config.yaml": _cfg(since=since)})
    res = repo.run_script(HS)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "before guards.human_signed_since" in res.stdout


def test_without_since_old_commit_still_fails(repo):
    repo.commit("old budget", {"infra/BUDGET_USD": "200\n"})
    repo.commit("adopt D-030", {"x.txt": "1\n"})
    assert repo.run_script(HS).returncode == 1


def test_since_commit_itself_and_later_still_checked(repo):
    repo.commit("pre", {"x.txt": "0\n"})
    since = repo.commit("adopt D-030 + budget", {"infra/BUDGET_USD": "200\n"})
    repo.commit("config", {"config.yaml": _cfg(since=since)})
    assert repo.run_script(HS).returncode == 1
    repo.commit("later token", {"UNBLIND_TOKEN": "x\n"})
    res = repo.run_script(HS)
    assert res.returncode == 1 and "UNBLIND_TOKEN" in res.stdout


def test_since_not_a_commit_is_an_error(repo):
    repo.commit("config", {"config.yaml": _cfg(since="deadbeef" * 5)})
    assert repo.run_script(HS).returncode == 2


def test_since_not_in_history_is_an_error(repo):
    repo.git("checkout", "-q", "-b", "side")
    other = repo.commit("side", {"y.txt": "1\n"})
    repo.git("checkout", "-q", "main")
    repo.commit("config", {"config.yaml": _cfg(since=other)})
    assert repo.run_script(HS).returncode == 2


# ---------------------------------------------------------------- test_weakening_allowlist
@pytest.fixture
def skip_commit(repo):
    repo.commit("tests", {"tests/_h.py": "def f():\n    return 1\n", "tests/test_a.py": "def test_a():\n"
                          "    assert 1\n", "BUGS.md": BUGS})
    return repo.commit("add skip", {"tests/_h.py": "import pytest\n\n\ndef f():\n    pytest.skip('x')\n"})


def test_unlisted_skip_fails(repo, skip_commit):
    assert repo.run_script(TW).returncode == 1


def test_exact_allowlist_entry_passes(repo, skip_commit):
    repo.commit("cfg", {"config.yaml": _cfg(allow=[{"commit": skip_commit, "path": "tests/_h.py",
                                                    "kind": "skip", "ticket": "BUG-008"}])})
    res = repo.run_script(TW)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "ALLOWLISTED (BUG-008)" in res.stdout and skip_commit[:12] in res.stdout


@pytest.mark.parametrize("field,value", [("commit", "short"), ("path", "tests/other.py"),
                                         ("kind", "assertion"), ("ticket", "BUG-999")])
def test_inexact_allowlist_entry_still_fails(repo, skip_commit, field, value):
    entry = {"commit": skip_commit, "path": "tests/_h.py", "kind": "skip", "ticket": "BUG-008"}
    entry[field] = skip_commit[:7] if value == "short" else value
    repo.commit("cfg", {"config.yaml": _cfg(allow=[entry])})
    assert repo.run_script(TW).returncode == 1


def test_allowlist_covers_only_its_finding(repo, skip_commit):
    repo.commit("cfg", {"config.yaml": _cfg(allow=[{"commit": skip_commit, "path": "tests/_h.py",
                                                    "kind": "skip", "ticket": "BUG-008"}])})
    repo.commit("weaken", {"tests/test_a.py": "def test_a():\n    pass\n"})
    res = repo.run_script(TW)
    assert res.returncode == 1 and "assertion line(s) deleted" in res.stdout


def test_unused_allowlist_entry_fails(repo, skip_commit):
    """QA G-D032 c2 #4: a dead allowlist entry (matches no finding) must not be accepted silently."""
    harmless = repo.commit("harmless", {"tests/test_b.py": "def test_b():\n    assert 2\n"})
    repo.commit("cfg", {"config.yaml": _cfg(allow=[
        {"commit": skip_commit, "path": "tests/_h.py", "kind": "skip", "ticket": "BUG-008"},
        {"commit": harmless, "path": "tests/test_b.py", "kind": "skip", "ticket": "BUG-008"}])})
    res = repo.run_script(TW)
    assert res.returncode == 1 and "unused allowlist entry" in res.stdout and harmless[:12] in res.stdout
