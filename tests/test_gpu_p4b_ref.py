"""T-REFRUN + T-ABL (D-071): the P4b reference-clip wrapper scripts/gpu_p4b_ref.py, dry run only
(in-memory Lambda running the real infra/lambda_gpu.py code, local pod/box/S3). No network, no GPU, no
prediction read."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from yct.config import load_config, with_overrides

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "gpu_p4b_ref.py"


def _load():
    spec = importlib.util.spec_from_file_location("gpu_p4b_ref", WRAPPER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_p4b_ref"] = mod
    spec.loader.exec_module(mod)
    return mod


ref = _load()
p4 = ref.p4

P4_SMALL = {"p4": {"launcher_max_hours": 4, "run_set_t1": ["yct_0016", "yct_0040"],
                   "run_set_t3": ["yct_0016", "yct_0040"], "t1_excluded": {}, "d038_clips": ["yct_0016"],
                   "flags": {"low_fps_source": {"rule": "r", "videos": [], "sensitivity": "S-LOWFPS"}}}}
FAMS = {"LOC": 1, "LOC_SCR": 1, "MOT": 1, "MOT_STAT": 1, "SPK": 4, "BURST": 1, "FLASH": 1, "TALKFACE": 1,
        "GREY_CTRL": 1, "NAT": 1}


def _cfg(manifest_sha=None, **refclips):
    over = {**P4_SMALL, "controls": {"refclips": {"families": FAMS, **refclips},
                                     "refclips_artifacts": {"manifest_sha256": manifest_sha}}}
    return with_overrides(load_config(), over)


@pytest.fixture
def env(tmp_path):
    cfg0 = _cfg()
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    # the P4 store: one full P4 dry run (the source of the seeded revisions)
    p4_store = p4.DryRunBackend(tmp_path / "p4dry", cfg0, clock)
    a = p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id="p4_seed")
    rc, res = p4.run_session(a, cfg0, lg, p4_store, clock, tmp_path / "runs" / "p4_seed")
    assert rc == 0, res
    backend = ref.RefDryRunBackend(tmp_path / "refdry", cfg0, clock)
    text = ref.write_synthetic_clips(backend.pod, cfg0)
    cfg = _cfg(ref.sha256_text(text))
    return {"cfg": cfg, "clock": clock, "lg": lg, "p4": p4_store, "backend": backend, "text": text,
            "tmp": tmp_path, "n_launched0": len(lg.launched)}


def _no_new_launch(env):
    return len(env["lg"].launched) == env["n_launched0"] and all(
        v["status"] == "terminated" for v in env["lg"].api.inst.values())


def _run(env, run_id="ref_s1", ack=False, **kw):
    a = {"max_hours": 3.5, "usd_limit": 25.0, "external_terminator_at": None, "run_id": run_id, "limit": None}
    a.update(kw)
    env["clock"].advance(60)
    return ref.run_ref_session(p4.SessionArgs(**a), env["cfg"], env["lg"], env["backend"], env["p4"],
                               env["clock"], env["tmp"] / "runs" / run_id, env["text"], ack=ack)


def _rows(env):
    return [json.loads(x) for x in (env["backend"].s3_get_text("manifest.jsonl") or "").splitlines()]


def _p4_bytes(env):
    return env["p4"].s3_get_text("manifest.jsonl"), sorted(env["p4"].s3_list(""))


# ---------------------------------------------------------------- frozen inputs
def test_manifest_sha_must_equal_the_frozen_value(env):
    with pytest.raises(SystemExit, match="manifest sha256"):
        ref.load_clip_manifest(env["text"] + " ", env["cfg"])
    with pytest.raises(SystemExit, match="not set"):
        ref.load_clip_manifest(env["text"], _cfg(None))


def test_plan_follows_job_order_d038_first_and_conditions_on_spk(tmp_path):
    cfg0 = _cfg()
    text = ref.write_synthetic_clips(tmp_path, cfg0)
    cfg = _cfg(ref.sha256_text(text))
    jobs = ref.plan_ref_jobs(cfg, ref.load_clip_manifest(text, cfg))
    assert [j.id for j in jobs[:3]] == ["GREY_CTRL_00.ref", "SPK_00.ref", "MOT_00.ref"] and all(
        j.d038 for j in jobs[:3])
    ids = [j.id for j in jobs]
    assert len(ids) == len(set(ids)) == sum(FAMS.values()) + 2 * FAMS["SPK"]
    for cond in ("audioonly", "textonly"):
        cj = [j for j in jobs if j.condition == cond]
        assert {j.video_id for j in cj} == {f"SPK_{i:02d}" for i in range(FAMS["SPK"])}
        assert [j.gate1_rerun for j in cj] == [True, True, True, False]
    assert ids.index("SPK_03.ref") < ids.index("SPK_00.ref.audioonly") < ids.index("BURST_00.ref")
    assert all(j.qc_track == "t1" for j in jobs)


def test_pod_clip_differing_from_manifest_is_refused_before_launch(env):
    (env["backend"].pod / "refclips" / "NAT_00.mp4").write_bytes(b"rebuilt")
    with pytest.raises(SystemExit, match="never rebuilt"):
        _run(env)
    assert _no_new_launch(env)


def test_wrapper_never_builds_clips_and_uses_only_load_config():
    src = WRAPPER.read_text()
    main_src = src[src.index("def main("):]
    assert "cfg = load_config()" in main_src and "with_overrides" not in src
    for word in ("make_reference_clips", "espeak", "ffmpeg"):
        assert word not in src


# ---------------------------------------------------------------- full dry campaign
def test_full_dry_campaign_syncs_every_job_under_the_ref_root_and_leaves_p4_unchanged(env):
    before = _p4_bytes(env)
    rc, res = _run(env)
    assert rc == 0, {k: res.get(k) for k in ("error", "errors", "gate_failures", "remaining")}
    assert _p4_bytes(env) == before, "the P4 store must not change"
    rows = _rows(env)
    assert len(rows) == sum(FAMS.values()) + 2 * FAMS["SPK"] and all(r["gate_pass"] for r in rows)
    revs = {r["revisions_sha256"] for r in rows}
    p4_text = env["p4"].s3_get_text("manifest.jsonl")
    p4_revs = {json.loads(x)["revisions_sha256"] for x in p4_text.splitlines()}
    assert revs == p4_revs and len(revs) == 1, "seeded from the P4 manifest: one stack for P4 and P4b"
    assert {r["gpu"] for r in rows} == {p4.GPU_NAME}
    (iid,) = env["lg"].launched[env["n_launched0"]:]
    assert env["lg"].api.inst[iid]["name"].startswith("yct-p4b-ref")
    assert res["pre_launch"]["cap_usd"] == 75
    assert env["backend"].s3_get_text("entries/campaign_baseline.json") is not None


def test_ablation_conditions_predict_from_the_full_cache_without_extraction(env):
    rc, res = _run(env)
    assert rc == 0, res
    rows = {r["job"]: r for r in _rows(env)}
    keys = set(env["backend"].s3_list(""))
    ext = env["backend"].extractions_per_job()
    for cond in ("audioonly", "textonly"):
        cj = [r for j, r in rows.items() if j.endswith("." + cond)]
        assert len(cj) == FAMS["SPK"]
        for r in cj:
            full = rows[r["job"].rsplit(".", 1)[0]]
            assert r["cache_key"] == full["cache_key"] and r["cache_reused"] is True
            assert r["revisions_sha256"] == full["revisions_sha256"] and r["gpu"] == full["gpu"]
            assert r["pred_shape"] == full["pred_shape"] and r["pred_sha256"] != full["pred_sha256"]
            assert ext.get(r["job"], 0) == 0, "the extractor must not be called for a condition job"
            assert r["pred_key"].startswith(f"{cond}/ref/") and r["condition"] == cond
        g1 = [r for r in cj if r.get("gate1")]
        assert len(g1) >= 3 and all(r["gate1"]["cached_rerun_bit_identical"] for r in g1)
    cond_keys = {k for k in keys if k.startswith(("audioonly/", "textonly/"))}
    assert cond_keys and all(".ref.npy" not in k for k in cond_keys)
    assert not [k for k in keys if k.startswith("full/") and ("audioonly" in k or "textonly" in k)]
    assert not [k for k in keys if k.startswith("entries_ref/") and ("audioonly" in k or "textonly" in k)]


def test_condition_job_without_a_full_cache_entry_fails(env):
    jobs = [p4.Job("SPK_01", "ref", condition="audioonly", qc_track="t1")]
    cfg, text = env["cfg"], env["text"]
    manifest = ref.load_clip_manifest(text, cfg)
    camp = ref.build_campaign(cfg, manifest, ref.seed_revisions(env["p4"], cfg), env["backend"], env["lg"],
                              env["clock"], False)
    camp.plan = lambda _c: jobs
    ref.ensure_baseline(env["backend"], env["lg"], cfg, env["clock"])
    a = p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id="ref_x")
    rc, res = p4.run_session(a, cfg, env["lg"], env["backend"], env["clock"], env["tmp"] / "runs" / "ref_x",
                             camp)
    assert rc == p4.EXIT_FAIL and "no synced full-model cache entry" in (res.get("error") or "")


def test_session_1_limit_3_runs_the_d038_clips(env):
    rc, res = _run(env, limit=3)
    assert rc == p4.EXIT_INCOMPLETE and res["jobs_run"] == ["GREY_CTRL_00.ref", "SPK_00.ref", "MOT_00.ref"]
    assert all(r["d038"] and r["d038"]["pass"] for r in _rows(env))


# ---------------------------------------------------------------- cost guards
def test_baseline_written_once_before_session_1(env):
    _run(env, limit=3)
    b1 = env["backend"].s3_get_text("entries/campaign_baseline.json")
    _run(env, run_id="ref_s2", limit=1)
    assert env["backend"].s3_get_text("entries/campaign_baseline.json") == b1


def _fake_ref_spend(env, usd):
    """Append a closed yct-p4b-ref instance to the ledger costing `usd` (after the baseline)."""
    led = Path(env["lg"].mod.LEDGER)
    t = env["clock"]()
    hours = usd / 1.99
    recs = [{"event": "launch", "id": "x1", "name": "yct-p4b-ref-t0-dl1", "t": t - hours * 3600,
             "usd_per_hour": 1.99, "deadline": t},
            {"event": "terminate", "id": "x1", "t": t, "reason": "job_done"}]
    with led.open("a") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def test_campaign_cap_refuses_launch_with_exit_1_and_no_instance(env):
    _run(env, limit=3)
    n = len(env["lg"].launched)
    _fake_ref_spend(env, 73.0)
    with pytest.raises(SystemExit, match="campaign cap") as e:
        _run(env, run_id="ref_s2", ack=True)
    assert e.value.code != p4.EXIT_INCOMPLETE
    assert len(env["lg"].launched) == n


def test_warn_level_needs_ack(env):
    _run(env, limit=3)
    _fake_ref_spend(env, 61.0)
    with pytest.raises(SystemExit, match="ack"):
        _run(env, run_id="ref_s2", max_hours=1.0)
    rc, res = _run(env, run_id="ref_s3", max_hours=1.0, ack=True, limit=1)
    assert rc in (p4.EXIT_INCOMPLETE, p4.EXIT_OK) and res["pre_launch"]["ack"] is True


def test_cap_refusal_process_exit_status_is_1(env):
    _run(env, limit=3)
    _fake_ref_spend(env, 74.0)
    # run the refused launch in a child process built from the same on-disk state
    state = {"tmp": str(env["tmp"]), "text": env["text"], "sha": ref.sha256_text(env["text"]),
             "t": env["clock"]()}
    (env["tmp"] / "state.json").write_text(json.dumps(state))
    child = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'src')!r})
sys.path.insert(0, {str(ROOT / 'tests')!r})
import test_gpu_p4b_ref as t
s = json.loads(Path({str(env['tmp'] / 'state.json')!r}).read_text())
tmp = Path(s["tmp"])
clock = t.p4.FakeClock(s["t"] + 60)
lg = t.p4.FakeLG(clock, tmp / "ledger.jsonl")
cfg0 = t._cfg()
p4_store = t.p4.DryRunBackend(tmp / "p4dry", cfg0, clock)
backend = t.ref.RefDryRunBackend(tmp / "refdry", cfg0, clock)
a = t.p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id="ref_child")
t.ref.run_ref_session(a, t._cfg(s["sha"]), lg, backend, p4_store, clock, tmp / "runs" / "ref_child",
                      s["text"], ack=True)
"""
    r = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=300)
    assert r.returncode == 1, (r.returncode, r.stderr[-800:])
    assert "campaign cap" in r.stderr


def test_launcher_limit_applies_to_ref_sessions(env):
    env["cfg"] = with_overrides(env["cfg"], {"p4": {"launcher_max_hours": 1.75}})
    with pytest.raises(SystemExit, match="launcher"):
        _run(env, max_hours=1.76)
    assert _no_new_launch(env)


def test_terminator_must_be_rearmed_on_each_retry(env):
    t_ext = env["clock"]() + 60 + 3.5 * 3600 + 900 + 60
    rc, res = _run(env, limit=3, external_terminator_at=t_ext)
    assert rc == p4.EXIT_INCOMPLETE and res["terminator"]["fire_at"] == t_ext
    with pytest.raises(SystemExit, match="already used"):
        _run(env, run_id="ref_s2", limit=1, external_terminator_at=t_ext)


def test_capacity_miss_on_ref_leaves_no_debris_and_p4_unchanged(env):
    before = _p4_bytes(env)
    ref.ensure_baseline(env["backend"], env["lg"], env["cfg"], env["clock"])
    keys0 = set(env["backend"].s3_list(""))
    env["lg"].mod.types = lambda: {}
    rc, res = _run(env, run_id="ref_miss")
    assert rc == p4.EXIT_INCOMPLETE and res["status"] == "no_capacity"
    assert set(env["backend"].s3_list("")) - keys0 == {"runs/ref_miss/child_metrics.json"}
    assert _p4_bytes(env) == before and _no_new_launch(env)


# ---------------------------------------------------------------- T-ABL box side (run_clip)
def test_run_clip_condition_flag_maps_to_features_to_use():
    from yct.tribe_run import run_clip as rc

    assert rc.condition_config_update("full") == {}
    assert rc.condition_config_update("audioonly") == {"data.features_to_use": ["audio"]}
    assert rc.condition_config_update("textonly") == {"data.features_to_use": ["text"]}
    a = rc.build_parser().parse_args(["--video", "v", "--feature-cache", "f", "--out", "o", "--weights", "w",
                                      "--condition", "audioonly"])
    assert a.condition == "audioonly"
    assert rc.build_parser().parse_args(["--video", "v", "--feature-cache", "f", "--out", "o",
                                         "--weights", "w"]).condition == "full"
    with pytest.raises(SystemExit):
        rc.build_parser().parse_args(["--video", "v", "--feature-cache", "f", "--out", "o", "--weights", "w",
                                      "--condition", "videoonly"])


def test_run_clip_condition_never_extracts_and_box_command_passes_it():
    src = (ROOT / "src" / "yct" / "tribe_run" / "run_clip.py").read_text()
    ext = src[src.index("    def extract(video"):src.index("    def predict(video")]
    assert 'if a.condition != "full":' in ext and "raise RuntimeError" in ext
    drv = (ROOT / "scripts" / "gpu_wave1_p4.py").read_text()
    cmd = drv[drv.index("class PodBackend"):]
    assert "--condition {job.condition}" in cmd and "--qc-gate {job.qc_track or job.track}" in cmd
