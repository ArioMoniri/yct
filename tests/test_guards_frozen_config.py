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
D074_SHA = "698b64a0e6c3cbc98ac6490fd10bc202a1647733"   # T-D074 commit 1 (D-074 key)
D074_FROZEN = [("controls.refclips_d074", D074_SHA),
               ("controls.refclips_artifacts.image_snapshot_sha256",
                "3ca6b2e7fa32bb7e56ad05592c76ab44788c0221")]   # D-074 snapshot commit
D075_FROZEN = [("controls.refclips_auto", "e835191e5e1661ded49d68380bfeb1950347928f")]   # D-075 commit 1
D075_ART_SHA = "8cb678e9c6a9c6e73015a55ea34c2cc44c169a34"   # D-075 step 3
D075_FROZEN += [(f"controls.refclips_auto_artifacts.{k}", D075_ART_SHA) for k in (
    "yunet_sha256", "frcnn_sha256", "clip_sha256", "tessdata_eng_sha256", "haar_face_sha256",
    "haar_eye_sha256")]
D075_FROZEN += [("controls.refclips_artifacts.nat_snapshot_sha256", D075_ART_SHA)]   # D-075 step 0
D078_SHA = "a18b246f457f025713d43a4dcaa296bf71624e9e"   # D-078 step 1
D075_FROZEN += [("controls.refclips_d078", D078_SHA),
                ("controls.refclips_d078_artifacts.body_snapshot_sha256", D078_SHA)]   # D-078 step 2
D079_SHA = "a4709e34ec30c82c9e3cc67a378c3edbe0ab981c"   # D-079 DECISIONS entry (5/5 sign-off at fb89535)
D075_FROZEN += [("controls.refclips_d079", D079_SHA),
                ("controls.refclips_d079_artifacts.flip_sha256", D079_SHA)]   # D-079 step 2
D080_SHA = "cb960bc9c1880d76ad4c84269812bf9c6db27ed7"   # D-080 DECISIONS entry (5/5 sign-off at 78c738a)
D075_FROZEN += [("controls.refclips_d080", D080_SHA),
                ("controls.refclips_d080_artifacts.dry_audit_sha256", D080_SHA)]   # D-080 step 2
D081_SHA = "f305da8814e8a682115972a5303dee6dd4a231a1"   # D-081 DECISIONS entry (5/5 sign-off at caf46de)
D075_FROZEN += [("controls.refclips_d081", D081_SHA),
                ("controls.refclips_d081_artifacts.dry_audit_sha256", D081_SHA),
                ("controls.refclips_d081_artifacts.reaudit_sha256", D081_SHA)]   # D-081 step 2
IMG_MAN_SHA = "376966a7aed15ac7db4aa3fd4d7e7a4cb4d9b665"   # D-081 v4 finalise (image manifests set)
D075_FROZEN += [("controls.refclips_artifacts.image_manifest_sha256", IMG_MAN_SHA)]
D082_SHA = "0c3057cdb33aeb33a51f187ba2eed5f23f6894fe"   # D-082 DECISIONS entry + pyannote shas set
D075_FROZEN += [("controls.refclips_d082", D082_SHA)] + [
    (f"controls.refclips_auto_artifacts.pyannote_{k}_sha256", D082_SHA)
    for k in ("diarization", "segmentation", "embedding", "plda")]   # D-082 step 2
D084_SHA = "7deeeff74a323857a936e740729b3ff6dad21dcc"   # D-084 DECISIONS entry (council v2)
D075_FROZEN += [("controls.refclips_d084", D084_SHA)]   # D-084 step 2
P2RUN_SHA = "b24fc1cf1a697d5345354fe36836c787a98715bb"   # D-060 wave-1 P2/P3 run commit
P2B_SHA = "4db5895d5b85b0e7f293852d0a6bc4e80abe54f8"     # D-061 WhisperX 3.8.6 pin
D075_FROZEN += [(k, P2RUN_SHA) for k in (
    "normalize", "stimulus.fps", "stimulus.min_short_side_px", "stimulus.center_crop_px",
    "stimulus.t1_trim_s", "stimulus.t1_max_probe_s", "vad", "confounds", "atlases",
    "localize")]   # D-086 FIX-NORM-0
D075_FROZEN += [("transcribe.whisperx", P2B_SHA)]
D075_FROZEN += [(k, D071_SHA) for k in (
    "controls.kernel.window_tr", "controls.kernel.type", "controls.kernel.shift_by_L",
    "controls.readout_lag_tr",
    "controls.rois.FFC", "controls.rois.PH", "controls.rois.AUD", "controls.rois.V1_V3",
    "controls.regressors.face", "controls.regressors.motion", "controls.regressors.luminance_change",
    "controls.partial_out")]   # D-086 FIX-NORM-P4B item 6 (unchanged since T-D071 commit 1)
D086_SHA = "1a3cff74f8a4b3fb866ae0ee07c58563be1112a4"   # D-086 entry (sets the two keys below)
D075_FROZEN += [("controls.partial_out_nuisance", D086_SHA),
                ("controls.regressors.speech_envelope", D086_SHA)]   # D-086 step 2
D085_SHA = "0d01a59d8b60b3185b98c3db9ad3b97b8b71fbde"   # D-085 part-1 DECISIONS entry
D075_FROZEN += [(k, D085_SHA) for k in (
    "controls.refclips_d085.qc", "controls.refclips_d085.build1_sha_record",
    "controls.refclips_d085.build1_decoded_sha_record",
    "controls.partial_out_nuisance_descriptive")]   # D-085 part 1
D087_SHA = "24bf885e51a0209de3e3f725921161725fc3d7c8"   # D-087 DECISIONS entry
D075_FROZEN += [("controls.refclips_d087", D087_SHA)]   # D-087 rule
D087A_SHA = "eb458aa49a847657b4f954ca93129cbdd7747443"   # D-087 screen run 1 (sets the v2 artifact shas)
D075_FROZEN += [("controls.refclips_d087_artifacts", D087A_SHA)]   # D-087 artifacts


def test_repo_config_has_v22_defaults_and_only_the_d063_freeze():
    """Nothing was frozen until Gate P4-entry; FIX-P4E froze exactly the D-063 rulings at c616a9d, then
    T-D071 exactly the D-071 P4b keys (commit pair 976e8ab -> its child; launcher limit at ca63a9d)."""
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    sha = "c616a9d33b7eb861795aa9fb64f6314d95e379f8"
    assert cfg["frozen"] == [{"key": k, "frozen_at": sha} for k in D063_FROZEN] + [
        {"key": k, "frozen_at": s} for k, s in D071_FROZEN + D074_FROZEN + D075_FROZEN]
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
