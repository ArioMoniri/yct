"""check_blinding.py: no outcome column outside sealed/curate; no UNBLIND_TOKEN before prereg-lock."""
import pytest

S = "check_blinding.py"


def test_clean_repo_passes(repo):
    repo.commit("manifest", {"data/manifest.csv": "video_id,company,era\nv1,c1,E2\n",
                             "docs/notes.md": "We never look at the outcome.\n"})
    res = repo.run_script(S)
    assert res.returncode == 0, res.stdout + res.stderr


HEADERS = ["video_id,outcome", "video_id,Outcome ", "video_id\toutcome", '"outcome",x']


@pytest.mark.parametrize("header", HEADERS)
def test_manifest_outcome_column_fails(repo, header):
    sep = "\t" if "\t" in header else ","
    repo.commit("leak", {"data/manifest.csv": f"{header}\nv1{sep}1\n"})
    res = repo.run_script(S)
    assert res.returncode == 1
    assert "data/manifest.csv" in res.stdout


@pytest.mark.parametrize("path", ["outputs/features.csv", "analysis/x.tsv", "src/yct/stats/t.csv"])
def test_outcome_header_anywhere_fails(repo, path):
    sep = "\t" if path.endswith(".tsv") else ","
    repo.commit("leak", {path: f"a{sep}outcome\n1{sep}0\n"})
    assert repo.run_script(S).returncode == 1


def test_outcome_key_in_jsonl_fails(repo):
    repo.commit("leak", {"outputs/rows.jsonl": '{"video_id": "v1", "outcome": 1}\n'})
    assert repo.run_script(S).returncode == 1


def test_outcome_in_allowed_dirs_passes(repo):
    repo.commit("curate", {"src/yct/curate/schema.csv": "video_id,outcome\n",
                           "data/sealed/README.csv": "video_id,outcome\n"})
    assert repo.run_script(S).returncode == 0


def test_outcome_not_in_header_passes(repo):
    repo.commit("ok", {"outputs/x.csv": "a,b\noutcome,1\n"})
    assert repo.run_script(S).returncode == 0


def test_untracked_file_ignored(repo):
    repo.write("scratch.csv", "outcome\n")
    assert repo.run_script(S).returncode == 0


def test_unblind_token_without_lock_fails(repo):
    repo.commit("unblind", {"UNBLIND_TOKEN": "x\n"})
    res = repo.run_script(S)
    assert res.returncode == 1
    assert "UNBLIND_TOKEN" in res.stdout


def test_unblind_token_in_worktree_without_lock_fails(repo):
    repo.write("UNBLIND_TOKEN", "x\n")
    assert repo.run_script(S).returncode == 1


def test_unblind_token_after_lock_passes(repo):
    repo.commit("prereg", {"docs/preregistration.md": "p\n"})
    repo.tag("prereg-lock")
    repo.commit("unblind", {"UNBLIND_TOKEN": "x\n"})
    assert repo.run_script(S).returncode == 0
