"""check_prereg.py: preregistration frozen at the prereg-lock tag (owner edits go via SSM, D-030)."""
S = "check_prereg.py"
P = "docs/preregistration.md"


def test_no_tag_passes(repo):
    base = repo.head()
    repo.commit("draft", {P: "draft\n"})
    repo.commit("edit", {P: "draft 2\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0
    assert "prereg-lock" in res.stdout


def test_unchanged_after_lock_passes(repo):
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    base = repo.head()
    repo.commit("other", {"x.txt": "1\n"})
    assert repo.run_script(S, "--base", base).returncode == 0


def test_edit_after_lock_fails(repo):
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    base = repo.head()
    repo.commit("sneaky", {P: "locked\nnew hypothesis\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "preregistration" in res.stdout


def test_edit_then_revert_passes(repo):
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    repo.commit("oops", {P: "changed\n"})
    repo.commit("revert", {P: "locked\n"})
    assert repo.run_script(S).returncode == 0


def test_deleted_after_lock_fails(repo):
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    repo.rm(P)
    repo.commit("rm")
    assert repo.run_script(S).returncode == 1


def test_tag_without_prereg_fails(repo):
    repo.tag("prereg-lock")
    assert repo.run_script(S).returncode == 1
