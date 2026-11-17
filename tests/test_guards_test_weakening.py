"""check_test_weakening.py: flag deleted asserts / loosened tolerances in tests/."""
import pytest

S = "check_test_weakening.py"
T = "tests/test_x.py"
BASE_TEST = """\
import pytest


def test_a():
    x = compute()
    assert x == pytest.approx(1.0, rel=1e-6)
    assert abs(x - 1) < 0.01
    assert x > 0.5


def test_b():
    assert True
"""


@pytest.fixture
def base(repo):
    return repo.commit("tests", {T: BASE_TEST})


def _edit(repo, old, new, msg="edit"):
    repo.commit(msg, {T: BASE_TEST.replace(old, new)})


def test_adding_asserts_passes(repo, base):
    _edit(repo, "    assert True\n", "    assert True\n    assert 1 == 1\n")
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout


def test_rewording_assert_passes(repo, base):
    _edit(repo, "assert x > 0.5", "assert x > 0.5, 'too small'")
    assert repo.run_script(S, "--base", base).returncode == 0


def test_tightening_passes(repo, base):
    _edit(repo, "rel=1e-6", "rel=1e-9")
    assert repo.run_script(S, "--base", base).returncode == 0


def test_deleted_assert_fails(repo, base):
    _edit(repo, "    assert x > 0.5\n", "")
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert T in res.stdout


def test_deleted_test_file_fails(repo, base):
    repo.rm(T)
    repo.commit("rm tests")
    assert repo.run_script(S, "--base", base).returncode == 1


@pytest.mark.parametrize("old,new", [
    ("rel=1e-6", "rel=1e-2"),
    ("< 0.01", "< 0.1"),
    ("x > 0.5", "x > 0.1"),
])
def test_loosened_tolerance_fails(repo, base, old, new):
    _edit(repo, old, new)
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "loosen" in res.stdout.lower()


def test_added_skip_fails(repo, base):
    _edit(repo, "def test_a():", "@pytest.mark.skip\ndef test_a():")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_qa_approved_commit_passes(repo, base):
    _edit(repo, "    assert x > 0.5\n", "", msg="Drop flaky check [QA-approved test change]")
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0
    assert "QA-approved" in res.stdout


def test_approval_is_per_commit(repo, base):
    _edit(repo, "    assert x > 0.5\n", "", msg="approved [QA-approved test change]")
    cur = BASE_TEST.replace("    assert x > 0.5\n", "").replace("rel=1e-6", "rel=0.5")
    repo.commit("sneak", {T: cur})
    assert repo.run_script(S, "--base", base).returncode == 1


def test_non_test_files_ignored(repo):
    base = repo.commit("src", {"src/a.py": "assert x\n"})
    repo.commit("rm", {"src/a.py": "\n"})
    assert repo.run_script(S, "--base", base).returncode == 0


def test_staged_mode_with_msg_file(repo, base, tmp_path):
    repo.write(T, BASE_TEST.replace("    assert x > 0.5\n", ""))
    repo.git("add", T)
    assert repo.run_script(S, "--staged").returncode == 1
    msg = tmp_path / "MSG"
    msg.write_text("fix [QA-approved test change]\n")
    assert repo.run_script(S, "--staged", str(msg)).returncode == 0
