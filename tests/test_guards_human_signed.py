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


# ---------------------------------------------------------------- FIX-C3-ENG: blinding root + data decision
import pytest  # noqa: E402

BUGS = "- BUG-011 | P0 | exemptions\n"


@pytest.mark.parametrize("path", ["docs/owner_age.pub", "DATA_DECISION.md"])
def test_owner_key_and_data_decision_changes_fail(repo, path):
    """QA G-D032 c2 #2: swapping the owner age key / editing DATA_DECISION.md must fail."""
    base = repo.commit("orig", {path: "age1ownerkey\n"})
    repo.commit("attacker key", {path: "age1attackerkey\n"})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1 and path in res.stdout


@pytest.mark.parametrize("path", ["docs/owner_age.pub", "DATA_DECISION.md"])
def test_owner_key_and_data_decision_create_delete_fail(repo, path):
    base = repo.head()
    repo.commit("create", {path: "x\n"})
    assert repo.run_script(S, "--base", base).returncode == 1
    base = repo.head()
    repo.rm(path)
    repo.commit("delete")
    assert repo.run_script(S, "--base", base).returncode == 1


def _exempt_cfg(entries) -> str:
    lines = ["guards:\n  human_only_exempt:\n"]
    lines += [f"    - {{commit: {c}, path: {p}, ticket: {t}}}\n" for c, p, t in entries]
    return "".join(lines)


def test_exact_exemption_passes_only_its_pair(repo):
    c = repo.commit("budget+decision", {"infra/BUDGET_USD": "200\n", "DATA_DECISION.md": "ok\n",
                                        "BUGS.md": BUGS})
    repo.commit("cfg", {"config.yaml": _exempt_cfg([(c, "infra/BUDGET_USD", "BUG-011")])})
    res = repo.run_script(S)
    assert res.returncode == 1  # DATA_DECISION.md in the same commit is not excused
    assert "EXEMPT (BUG-011)" in res.stdout and "DATA_DECISION.md changed via git" in res.stdout
    repo.commit("cfg2", {"config.yaml": _exempt_cfg([(c, "infra/BUDGET_USD", "BUG-011"),
                                                     (c, "DATA_DECISION.md", "BUG-011")])})
    res = repo.run_script(S)
    assert res.returncode == 0, res.stdout


def test_later_change_to_exempted_path_still_fails(repo):
    c = repo.commit("budget", {"infra/BUDGET_USD": "200\n", "BUGS.md": BUGS})
    repo.commit("cfg", {"config.yaml": _exempt_cfg([(c, "infra/BUDGET_USD", "BUG-011")])})
    repo.commit("raise", {"infra/BUDGET_USD": "9999\n"})
    res = repo.run_script(S)
    assert res.returncode == 1 and "infra/BUDGET_USD" in res.stdout


def test_unused_exemption_fails(repo):
    c = repo.commit("harmless", {"x.txt": "1\n", "BUGS.md": BUGS})
    repo.commit("cfg", {"config.yaml": _exempt_cfg([(c, "infra/BUDGET_USD", "BUG-011")])})
    res = repo.run_script(S)
    assert res.returncode == 1 and "unused" in res.stdout


@pytest.mark.parametrize("entry", [("short", "infra/BUDGET_USD", "BUG-011"),
                                   ("FULL", "README.md", "BUG-011"),
                                   ("FULL", "infra/BUDGET_USD", "BUG-999")])
def test_malformed_exemption_is_an_error(repo, entry):
    c = repo.commit("budget", {"infra/BUDGET_USD": "200\n", "BUGS.md": BUGS})
    sha = {"short": c[:7], "FULL": c}[entry[0]]
    repo.commit("cfg", {"config.yaml": _exempt_cfg([(sha, entry[1], entry[2])])})
    assert repo.run_script(S).returncode == 2
