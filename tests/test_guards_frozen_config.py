"""check_frozen_config.py: keys listed under `frozen:` may not change after their freeze commit."""
from pathlib import Path

import yaml

S = "check_frozen_config.py"
ROOT = Path(__file__).resolve().parents[1]

CFG = """\
tribe:
  tr_s: 1.0
window:
  start_tr: 5
  len_tr: 40
frozen: []
"""


def _freeze(cfg: str, entries: list[tuple[str, str]]) -> str:
    body = cfg.replace("frozen: []\n", "frozen:\n")
    for key, sha in entries:
        body += f"  - key: {key}\n    frozen_at: {sha}\n"
    return body


def test_unfrozen_change_passes(repo):
    base = repo.commit("cfg", {"config.yaml": CFG})
    repo.commit("tune", {"config.yaml": CFG.replace("start_tr: 5", "start_tr: 6")})
    assert repo.run_script(S, "--base", base).returncode == 0


def test_frozen_key_unchanged_passes(repo):
    sha = repo.commit("cfg", {"config.yaml": CFG})
    repo.commit("freeze", {"config.yaml": _freeze(CFG, [("window.start_tr", sha)])})
    base = repo.head()
    tuned = _freeze(CFG, [("window.start_tr", sha)]).replace("len_tr: 40", "len_tr: 41")
    repo.commit("tune other", {"config.yaml": tuned})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 0, res.stdout + res.stderr


def test_frozen_key_changed_fails(repo):
    sha = repo.commit("cfg", {"config.yaml": CFG})
    frozen = _freeze(CFG, [("window.start_tr", sha)])
    base = repo.commit("freeze", {"config.yaml": frozen})
    repo.commit("move goalpost", {"config.yaml": frozen.replace("start_tr: 5", "start_tr: 7")})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "window.start_tr" in res.stdout


def test_frozen_subtree_changed_fails(repo):
    sha = repo.commit("cfg", {"config.yaml": CFG})
    frozen = _freeze(CFG, [("window", sha)])
    base = repo.commit("freeze", {"config.yaml": frozen})
    repo.commit("move", {"config.yaml": frozen.replace("len_tr: 40", "len_tr: 30")})
    assert repo.run_script(S, "--base", base).returncode == 1


def test_frozen_key_removed_fails(repo):
    sha = repo.commit("cfg", {"config.yaml": CFG})
    frozen = _freeze(CFG, [("window.start_tr", sha)])
    base = repo.commit("freeze", {"config.yaml": frozen})
    repo.commit("drop key", {"config.yaml": frozen.replace("  start_tr: 5\n", "")})
    assert repo.run_script(S, "--base", base).returncode == 1


def test_unfreezing_fails(repo):
    sha = repo.commit("cfg", {"config.yaml": CFG})
    base = repo.commit("freeze", {"config.yaml": _freeze(CFG, [("window.start_tr", sha)])})
    repo.commit("unfreeze", {"config.yaml": CFG.replace("start_tr: 5", "start_tr: 9")})
    res = repo.run_script(S, "--base", base)
    assert res.returncode == 1
    assert "unfrozen" in res.stdout.lower()


def test_freeze_commit_rewritten_fails(repo):
    sha = repo.commit("cfg", {"config.yaml": CFG})
    other = repo.commit("cfg2", {"config.yaml": CFG.replace("start_tr: 5", "start_tr: 8")})
    base = repo.commit("freeze", {"config.yaml": _freeze(CFG.replace("start_tr: 5", "start_tr: 8"),
                                                          [("window.start_tr", other)])})
    repo.commit("repoint", {"config.yaml": _freeze(CFG, [("window.start_tr", sha)])})
    assert repo.run_script(S, "--base", base).returncode == 1


def test_frozen_at_must_be_ancestor_and_have_key(repo):
    repo.commit("cfg", {"config.yaml": CFG})
    bad = _freeze(CFG, [("window.start_tr", "deadbeef" * 5)])
    repo.commit("bogus freeze", {"config.yaml": bad})
    assert repo.run_script(S).returncode == 1
    sha = repo.commit("no key yet", {"config.yaml": CFG.replace("  len_tr: 40\n", "")})
    repo.commit("freeze missing", {"config.yaml": _freeze(CFG, [("window.len_tr", sha)])})
    assert repo.run_script(S).returncode == 1


D063_FROZEN = ["window.latency_l_tr", "window.start_tr", "window.end_tr", "window.min_tail_s",
               "stimulus.min_source_fps", "p4.analysis_excluded", "p4.t1_excluded", "p4.run_set_t3",
               "p4.run_set_t1", "p4.flags", "p4.d038_clips", "transcribe.wer", "controls.rois.MT_plus",
               "controls.regressors.motion", "controls.descriptive"]
D071_SHA = "976e8abdb07aa0c4b8f1c1b7eb45f3e598f99542"   # T-D071 commit 1 (D-071 config keys)
D071_FROZEN = [("p4.launcher_max_hours", "ca63a9d57857b68cf5c0f9dc7a51ce6d53882db2")] + [
    (k, D071_SHA) for k in ["seeds.controls_perm", "seeds.controls_boot", "seeds.refclips",
                            "controls.kernel.acceptance", "controls.kernel.min_reference_clips",
                            "controls.pass", "controls.rois_per_hemi", "controls.mw_removed_frac",
                            "controls.refclips"]]


def test_repo_config_has_v22_defaults_and_only_the_d063_freeze():
    """Nothing was frozen until Gate P4-entry; FIX-P4E froze exactly the D-063 rulings at c616a9d, then
    T-D071 exactly the D-071 P4b keys (commit pair 976e8ab -> its child; launcher limit at ca63a9d)."""
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    sha = "c616a9d33b7eb861795aa9fb64f6314d95e379f8"
    assert cfg["frozen"] == [{"key": k, "frozen_at": sha} for k in D063_FROZEN] + [
        {"key": k, "frozen_at": s} for k, s in D071_FROZEN]
    assert cfg["tribe"]["tr_s"] == 1.0
    assert cfg["stimulus"]["t1_trim_s"] == 58.0
    assert cfg["stimulus"]["fps"] == 30
    assert cfg["stimulus"]["min_short_side_px"] == 292
    assert cfg["window"]["default_start_tr"] == 5
    assert cfg["window"]["default_len_tr"] == 40
    assert set(cfg["era_strata"]) == {"E1", "E2", "E3"}
    assert cfg["budget"]["usd_file"] == "infra/BUDGET_USD"
    assert cfg["seeds"]["company_pick_salt"] == "yct-v2.1"


def test_repo_config_passes_guard():
    import subprocess
    import sys
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / S), "--base", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
