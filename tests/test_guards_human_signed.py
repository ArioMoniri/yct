"""check_human_signed.py: human-only paths require a commit signed by an owner key."""
from conftest import allowed_signers_line

S = "check_human_signed.py"
AS = "docs/allowed_signers"


def _bootstrap(repo, owner_key):
    return repo.commit("owner setup", {AS: allowed_signers_line(owner_key),
                                       "docs/owner_signing_key.pub": owner_key.with_suffix(".pub").read_text()},
                       sign_key=owner_key)


def test_bootstrap_warns_and_passes(repo):
    base = repo.head()
    repo.commit("budget", {"infra/BUDGET_USD": "200\n", "DATA_DECISION.md": "ok\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0
    assert "WARNING" in res.stdout and "owner key not yet committed" in res.stdout


def test_bootstrap_unblind_token_always_fails(repo):
    base = repo.head()
    repo.commit("unblind", {"UNBLIND_TOKEN": "go\n"})
    assert repo.run_script(S, "--base", base).returncode == 1


def test_owner_signed_protected_change_passes(repo, owner_key):
    base = _bootstrap(repo, owner_key)
    repo.commit("budget", {"infra/BUDGET_USD": "300\n"}, sign_key=owner_key)
    repo.commit("unblind", {"UNBLIND_TOKEN": "go\n"}, sign_key=owner_key)
    repo.commit("unrelated agent work", {"src/a.py": "x = 1\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout + res.stderr


def test_owner_bootstrap_commit_itself_passes(repo, owner_key):
    base = repo.head()
    _bootstrap(repo, owner_key)
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout + res.stderr


def test_unsigned_protected_change_fails(repo, owner_key):
    base = _bootstrap(repo, owner_key)
    for path in ["infra/BUDGET_USD", "DATA_DECISION.md", "UNBLIND_TOKEN", "docs/owner_age.pub", AS]:
        repo.git("reset", "-q", "--hard", base)
        extra = allowed_signers_line(owner_key) if path == AS else "agent\n"
        repo.commit(f"agent touches {path}", {path: extra + "x\n" if path == AS else extra})
        res = repo.run_script(S, "--base", base)
        assert res.returncode == 1, path
        assert path in res.stdout


def test_agent_signed_protected_change_fails(repo, owner_key, agent_key):
    base = _bootstrap(repo, owner_key)
    repo.commit("budget", {"infra/BUDGET_USD": "9999\n"}, sign_key=agent_key)
    assert repo.run_script(S, "--base", base).returncode == 1


def test_agent_cannot_add_own_key(repo, owner_key, agent_key):
    base = _bootstrap(repo, owner_key)
    repo.commit("add key", {AS: allowed_signers_line(owner_key) + allowed_signers_line(agent_key, "agent")},
                sign_key=agent_key)
    repo.commit("budget", {"infra/BUDGET_USD": "9999\n"}, sign_key=agent_key)
    assert repo.run_script(S, "--base", base).returncode == 1


def test_deleting_protected_file_needs_signature(repo, owner_key):
    repo.commit("dd", {"DATA_DECISION.md": "signed\n"})
    base = _bootstrap(repo, owner_key)
    repo.rm("DATA_DECISION.md")
    repo.commit("rm")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_prereg_protected_only_after_lock(repo, owner_key):
    base = _bootstrap(repo, owner_key)
    repo.commit("draft", {"docs/preregistration.md": "draft\n"})
    repo.commit("lock", {"docs/preregistration.md": "final\n"})
    repo.tag("prereg-lock")
    assert repo.run_script(S, "--base", base).returncode == 0
    repo.commit("post-lock edit", {"docs/preregistration.md": "final\nmore\n"})
    assert repo.run_script(S, "--base", base).returncode == 1


def test_signed_merge_of_unsigned_branch_fails(repo, owner_key):
    base = _bootstrap(repo, owner_key)
    repo.git("checkout", "-q", "-b", "feature")
    repo.commit("agent budget", {"infra/BUDGET_USD": "1\n"})
    repo.git("checkout", "-q", "main")
    repo.commit("other", {"z.txt": "z\n"})
    repo.git("-c", "gpg.format=ssh", "-c", f"user.signingkey={owner_key}", "merge", "-q", "--no-edit", "-S",
             "feature")
    assert repo.run_script(S, "--base", base).returncode == 1
