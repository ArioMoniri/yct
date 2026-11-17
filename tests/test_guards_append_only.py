"""check_append_only.py: logs may only grow by appending."""
import pytest

S = "check_append_only.py"
LOGS = ["DECISIONS.md", "BUGS.md", "CHANGELOG.md", "ENHANCEMENTS.md", "reviews/watchdog/audit_log.jsonl"]


@pytest.fixture
def base(repo):
    files = {f: "line 1\nline 2\n" for f in LOGS}
    return repo.commit("logs", files)


@pytest.mark.parametrize("log", LOGS)
def test_append_passes(repo, base, log):
    repo.append(log, "line 3\n")
    repo.commit("append")
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.parametrize("log", LOGS)
def test_modified_line_fails(repo, base, log):
    repo.write(log, "line 1\nline 2 EDITED\n")
    repo.commit("tamper")
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert log in res.stdout


def test_deleted_line_fails(repo, base):
    repo.write("DECISIONS.md", "line 2\n")
    repo.commit("delete first line")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_deleted_file_fails(repo, base):
    repo.rm("BUGS.md")
    repo.commit("rm log")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_insert_in_middle_fails(repo, base):
    repo.write("CHANGELOG.md", "line 1\ninserted\nline 2\n")
    repo.commit("insert")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_tamper_then_restore_in_range_passes_net(repo, base):
    # net diff is what matters; history is still checked by human review
    repo.write("BUGS.md", "x\n")
    repo.commit("tamper")
    repo.write("BUGS.md", "line 1\nline 2\nline 3\n")
    repo.commit("restore + append")
    assert repo.run_script(S, "--base", base).returncode == 0


def test_new_log_file_passes(repo):
    base = repo.head()
    repo.commit("create", {"DECISIONS.md": "# D\n"})
    assert repo.run_script(S, "--base", base).returncode == 0


def test_append_to_file_without_trailing_newline(repo):
    base = repo.commit("no nl", {"DECISIONS.md": "a"})
    repo.write("DECISIONS.md", "a\nb\n")
    repo.commit("append")
    assert repo.run_script(S, "--base", base).returncode == 0


def test_staged_mode(repo, base):
    repo.write("DECISIONS.md", "line 1 EDIT\nline 2\n")
    repo.git("add", "DECISIONS.md")
    assert repo.run_script(S, "--staged").returncode == 1
    repo.write("DECISIONS.md", "line 1\nline 2\nline 3\n")
    repo.git("add", "DECISIONS.md")
    assert repo.run_script(S, "--staged").returncode == 0


def test_bad_base_is_error_not_pass(repo, base):
    res = repo.run_script(S, "--base", "no-such-ref")
    assert res.returncode == 2
