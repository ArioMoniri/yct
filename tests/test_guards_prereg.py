"""check_prereg.py: preregistration frozen at the prereg-lock tag unless owner-signed."""
from conftest import allowed_signers_line

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


def test_unsigned_edit_after_lock_fails(repo):
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    base = repo.head()
    repo.commit("sneaky", {P: "locked\nnew hypothesis\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "preregistration" in res.stdout


def test_deleted_after_lock_fails(repo):
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    repo.rm(P)
    repo.commit("rm")
    assert repo.run_script(S).returncode == 1


def test_owner_signed_edit_passes(repo, owner_key):
    repo.commit("keys", {"docs/allowed_signers": allowed_signers_line(owner_key)}, sign_key=owner_key)
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    base = repo.head()
    repo.commit("owner amendment", {P: "locked\namended\n"}, sign_key=owner_key)
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout + res.stderr


def test_agent_signed_edit_fails(repo, owner_key, agent_key):
    repo.commit("keys", {"docs/allowed_signers": allowed_signers_line(owner_key)}, sign_key=owner_key)
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    base = repo.head()
    repo.commit("agent amendment", {P: "locked\namended\n"}, sign_key=agent_key)
    assert repo.run_script(S, "--base", base).returncode == 1


def test_mixed_signed_and_unsigned_edits_fail(repo, owner_key):
    repo.commit("keys", {"docs/allowed_signers": allowed_signers_line(owner_key)}, sign_key=owner_key)
    repo.commit("prereg", {P: "locked\n"})
    repo.tag("prereg-lock")
    repo.commit("agent edit", {P: "locked\nagent\n"})
    repo.commit("owner edit", {P: "locked\nagent\nowner\n"}, sign_key=owner_key)
    assert repo.run_script(S).returncode == 1
