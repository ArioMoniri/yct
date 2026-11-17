"""check_human_signed.py: human-only actions must never arrive through git (D-030: owner uses SSM)."""
S = "check_human_signed.py"


def test_ordinary_commits_pass(repo):
    base = repo.head()
    repo.commit("work", {"src/a.py": "x = 1\n", "DECISIONS.md": "d\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout + res.stderr


def test_adding_unblind_token_fails(repo):
    base = repo.head()
    repo.commit("unblind", {"UNBLIND_TOKEN": "go\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "UNBLIND_TOKEN" in res.stdout


def test_unblind_token_added_and_removed_in_range_still_fails(repo):
    base = repo.head()
    repo.commit("unblind", {"UNBLIND_TOKEN": "go\n"})
    repo.rm("UNBLIND_TOKEN")
    repo.commit("hide it")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_budget_change_fails(repo):
    base = repo.commit("budget", {"infra/BUDGET_USD": "200\n"})
    repo.commit("raise", {"infra/BUDGET_USD": "9999\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "infra/BUDGET_USD" in res.stdout


def test_budget_create_and_delete_fail(repo):
    base = repo.head()
    repo.commit("create", {"infra/BUDGET_USD": "50\n"})
    assert repo.run_script(S, "--base", base).returncode == 1
    base = repo.head()
    repo.rm("infra/BUDGET_USD")
    repo.commit("delete")
    assert repo.run_script(S, "--base", base).returncode == 1


def test_prereg_protected_only_after_lock(repo):
    base = repo.head()
    repo.commit("draft", {"docs/preregistration.md": "draft\n"})
    repo.commit("lock", {"docs/preregistration.md": "final\n"})
    repo.tag("prereg-lock")
    assert repo.run_script(S, "--base", base).returncode == 0
    repo.commit("post-lock edit", {"docs/preregistration.md": "final\nmore\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "preregistration" in res.stdout


def test_merge_bringing_in_budget_change_fails(repo):
    base = repo.commit("budget", {"infra/BUDGET_USD": "50\n"})
    repo.git("checkout", "-q", "-b", "feature")
    repo.commit("agent budget", {"infra/BUDGET_USD": "1\n"})
    repo.git("checkout", "-q", "main")
    repo.commit("other", {"z.txt": "z\n"})
    repo.git("merge", "-q", "--no-edit", "feature")
    assert repo.run_script(S, "--base", base).returncode == 1
