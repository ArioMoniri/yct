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


# ---------------------------------------------------------------- FIX-P1 (BUG-016): outcome words in URLs
# Outcome words are split in this source so the repo-wide URL scan does not flag the test file itself.
REJ, ACC, INTO, DIDNT = "rej" + "ect", "acc" + "epted", "into" + "-yc", "didnt" + "-get"
OUTCOME_URLS = [
    f"https://cdn.example.org/blog/my-yc-{REJ}ion-full-application/intro.mp4",
    f"https://www.youtube.com/watch?v=abc&t={REJ.upper()}ED",
    f"https://www.linkedin.com/posts/x_we-got-{ACC}-activity-1",
    "https://example.org/how-we-got" + "-in-to-yc.mp4",
    f"https://example.org/getting-{INTO}-after-6-tries/v.mp4",
    f"https://example.org/we-{DIDNT}-in/v.mp4",
    "https://example.org/we-didn%27t" + "-get-in/v.mp4",
]


@pytest.mark.parametrize("url", OUTCOME_URLS)
def test_manifest_url_with_outcome_word_fails_and_names_video_id(repo, url):
    repo.commit("leak", {"data/manifest.csv": f"video_id,url,era\nyct_0001,https://youtu.be/x,E3\n"
                                              f"yct_0644,{url},E3\n"})
    res = repo.run_script(S)
    assert res.returncode == 1, res.stdout
    assert "yct_0644" in res.stdout
    assert "yct_0001" not in res.stdout


def test_neutral_and_sealed_urls_pass(repo):
    repo.commit("ok", {"data/manifest.csv": "video_id,url\nyct_0001,https://www.youtube.com/watch?v=jU-G69EV4kU\n"
                                            "yct_0644,sealed:yct_0644\n"
                                            "yct_0002,https://www.linkedin.com/feed/update/urn:li:activity:7\n"})
    res = repo.run_script(S)
    assert res.returncode == 0, res.stdout


def test_url_column_in_other_tracked_csv_fails(repo):
    repo.commit("leak", {"data/curation/exclusions.csv":
                         f"url,reason\nhttps://example.org/w26-{REJ}ion-activity-1,dup\n"})
    res = repo.run_script(S)
    assert res.returncode == 1
    assert "data/curation/exclusions.csv" in res.stdout


def test_url_in_any_tracked_text_file_fails(repo):
    repo.commit("leak", {"docs/notes.md": f"see https://example.org/my-yc-{REJ}ion/v.mp4 for context\n"})
    res = repo.run_script(S)
    assert res.returncode == 1
    assert "docs/notes.md" in res.stdout


def test_outcome_words_outside_urls_pass(repo):
    """Prose about the study ('accepted vs rejected') is not a leak; only URLs/url columns are scanned."""
    repo.commit("ok", {"docs/notes.md": "Do TRIBE responses separate accepted from rejected videos?\n",
                       "outputs/x.csv": "a,b\nrejected,1\n"})
    assert repo.run_script(S).returncode == 0


def test_url_scan_skips_sealed_dir(repo):
    repo.commit("ok", {"data/sealed/x.csv": f"video_id,url\nyct_0644,https://example.org/my-yc-{REJ}ion.mp4\n"})
    assert repo.run_script(S).returncode == 0


def test_url_scan_report_never_prints_the_outcome_word(repo):
    repo.commit("leak", {"data/manifest.csv": f"video_id,url\nyct_0644,https://example.org/my-yc-{REJ}ion.mp4\n"})
    res = repo.run_script(S)
    assert res.returncode == 1
    assert REJ not in res.stdout.lower() and "example.org" not in res.stdout
