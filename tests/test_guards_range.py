"""guard_range.py + Makefile default: `make guards` never checks an empty range (QA G-D032 D4)."""
import re
from pathlib import Path

S = "guard_range.py"


def test_empty_range_refused(repo):
    res = repo.run_script(S, "--base", "HEAD")
    assert res.returncode == 2 and "empty" in res.stdout


def test_upstream_ahead_of_head_refused(repo):
    old = repo.head()
    repo.commit("ahead", {"a.txt": "1\n"})
    ahead = repo.head()
    repo.git("checkout", "-q", old)
    assert repo.run_script(S, "--base", ahead).returncode == 2


def test_nonempty_range_ok(repo):
    base = repo.head()
    repo.commit("work", {"a.txt": "1\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0 and "1 commit(s)" in res.stdout


def test_whole_history_default(repo):
    res = repo.run_script(S, "--base", "EMPTY")
    assert res.returncode == 0 and "whole history" in res.stdout


def test_makefile_default_base_is_whole_history_and_checked():
    mk = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
    assert re.search(r"^BASE \?= EMPTY$", mk, re.M)
    assert "@{upstream}" not in mk
    guards = mk.split("\nguards:", 1)[1]
    assert guards.index("guard_range.py") < guards.index("for g in $(GUARDS)")
