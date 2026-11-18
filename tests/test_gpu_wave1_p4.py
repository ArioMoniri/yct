"""FIX-P4E (D-063 engineering blockers + Q7): the resumable P4 batch driver scripts/gpu_wave1_p4.py, run in
its dry-run mode (in-memory Lambda, local-directory pod/box/S3; the box "runs" run_cached with a synthetic
extractor/predictor and the real cache_archive). No network, no GPU.

Covered: job plan from the frozen run sets; per-video S3 sync; skip of already-synced videos; resume after
a crash restores the cache entry from S3 + pod media (no re-extraction, bit-identical predictions);
manifest appended, never overwritten; immutable S3 objects; non-zero exit on any gate failure (per-clip
gate, D-038 Gate 1/2); <= 4 h sessions; refusal without a driver-independent terminator (D-063 Q7);
orphan sweep at every session start; output firewall (D-063 B2)."""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from yct.config import load_config, with_overrides

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "gpu_wave1_p4.py"


def _load():
    spec = importlib.util.spec_from_file_location("gpu_wave1_p4", DRIVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_wave1_p4"] = mod
    spec.loader.exec_module(mod)
    return mod


p4 = _load()

SMALL = {"p4": {"run_set_t1": ["yct_0016", "yct_0040", "yct_0043"],
                "run_set_t3": ["yct_0016", "yct_0040", "yct_0043", "yct_0483"],
                "t1_excluded": {"yct_0483": "short"}, "d038_clips": ["yct_0016"],
                "flags": {"low_fps_source": {"rule": "r", "videos": [], "sensitivity": "S-LOWFPS"}}}}


@pytest.fixture
def cfg():
    return with_overrides(load_config(), SMALL)


@pytest.fixture
def env(tmp_path, cfg):
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock)
    backend = p4.DryRunBackend(tmp_path / "dry", cfg, clock)
    return {"cfg": cfg, "clock": clock, "lg": lg, "backend": backend, "tmp": tmp_path}


def _args(**kw):
    a = {"max_hours": 3.5, "usd_limit": 25.0, "external_terminator_at": None, "run_id": "p4_test",
         "limit": None}
    a.update(kw)
    return p4.SessionArgs(**a)


def _run(env, run_id="p4_test", **kw):
    return p4.run_session(_args(run_id=run_id, **kw), env["cfg"], env["lg"], env["backend"], env["clock"],
                          env["tmp"] / "runs" / run_id)


def _manifest(env):
    return [json.loads(x) for x in (env["backend"].s3_get_text("manifest.jsonl") or "").splitlines()]


# ---------------------------------------------------------------- plan
def test_plan_uses_the_frozen_run_sets_d038_first():
    jobs = p4.plan_jobs(load_config())
    ids = [j.id for j in jobs]
    assert len(jobs) == 51 + 52 and len(set(ids)) == len(ids)
    assert [j.id for j in jobs[:3]] == ["yct_0016.t1", "yct_0034.t1", "yct_0036.t1"]
    assert all(j.d038 for j in jobs[:3])
    assert not any(j.d038 for j in jobs[3:])
    assert "yct_0483.t3" in ids and "yct_0483.t1" not in ids
    assert not [i for i in ids if i.startswith(("yct_0644", "yct_0641"))]


# ---------------------------------------------------------------- full session
def test_full_dry_run_session_syncs_every_video_and_terminates(env):
    rc, res = _run(env)
    assert rc == 0, res
    b, lg = env["backend"], env["lg"]
    keys = set(b.s3_list(""))
    for vid in SMALL["p4"]["run_set_t1"]:
        assert f"pred/t1/{vid}.npy" in keys and f"pred/t1/{vid}.segments.csv" in keys
    for vid in SMALL["p4"]["run_set_t3"]:
        assert f"pred/t3/{vid}.npy" in keys
    rows = _manifest(env)
    assert len(rows) == 7 and all(r["gate_pass"] for r in rows)
    assert all(r["gpu"] == "NVIDIA A100-SXM4-40GB" and r["run_id"] == "p4_test" for r in rows)
    assert len({r["revisions_sha256"] for r in rows}) == 1
    for r in rows:
        assert f"feature_cache/{r['cache_key']}.tar" in keys
        assert f"feature_cache/{r['cache_key']}.FILES_SHA256SUMS" in keys
        assert f"entries/{r['job']}.json" in keys and r["pred_sha256"] == b.s3_sha(r["pred_key"])
    # D-038: fresh-extraction predictions persisted (Gate 2 re-scored on M1 after P4), Gate 1 checked
    assert "d038_fresh/yct_0016.fresh_pred.npy" in keys and "d038_fresh/yct_0016.fresh_feat.tar" in keys
    d = next(r for r in rows if r["job"] == "yct_0016.t1")["d038"]
    assert d["cached_rerun_bit_identical"] and d["fresh_gate_pass"] and d["fresh_pred_sha256"]
    # instance: name deadline, terminated, terminator scheduled at deadline + 15 min
    (iid,) = lg.launched
    assert lg.status[iid] == "terminated" and res["instance_id"] == iid
    assert b.terminators == [(iid, lg.deadline[iid] + 900)]
    assert not [k for k in keys if k.endswith((".mp4", ".wav"))]                   # no media in S3
    assert (env["tmp"] / "runs" / "p4_test" / "child_metrics.json").exists()


def test_second_session_skips_everything_already_synced(env):
    assert _run(env, "p4_a")[0] == 0
    n = env["backend"].n_extractions
    rc, res = _run(env, "p4_b")
    assert rc == 0 and res["jobs_run"] == [] and res["status"] == "complete"
    assert env["backend"].n_extractions == n and len(env["lg"].launched) == 1     # nothing to launch for


def test_session_time_cap_then_resume_appends_manifest(env):
    rc, res = _run(env, "p4_a", max_hours=0.75)        # setup + ~2 jobs fit, then a clean stop
    assert rc == p4.EXIT_INCOMPLETE and 0 < len(res["jobs_run"]) < 7 and res["remaining"]
    first = env["backend"].s3_get_text("manifest.jsonl")
    lg = env["lg"]
    assert all(lg.terminated_at[i] <= lg.deadline[i] for i in lg.launched)        # stopped inside the session
    rc2, res2 = _run(env, "p4_b")
    assert rc2 == 0 and set(res2["jobs_run"]) == set(res["remaining"])
    after = env["backend"].s3_get_text("manifest.jsonl")
    assert after.startswith(first) and len(after.splitlines()) == 7               # appended, not overwritten
    per = env["backend"].extractions_per_job()                                    # D-038 clip: + 1 fresh
    assert len(per) == 7 and per == {j: 2 if j == "yct_0016.t1" else 1 for j in per}


def test_max_hours_above_4_refused(env):
    with pytest.raises(SystemExit, match="4"):
        _run(env, max_hours=4.5)
    assert env["lg"].launched == []


# ---------------------------------------------------------------- crash -> restore from S3
def test_crash_after_entry_sync_restores_cache_on_new_box_no_reextraction(env):
    b = env["backend"]
    b.faults["yct_0040.t1"] = "crash_after_entry"
    rc, res = _run(env, "p4_a")
    assert rc == 1 and "error" in res
    assert env["lg"].status[env["lg"].launched[0]] == "terminated"                 # always terminated
    assert "entries/yct_0040.t1.json" in b.s3_list("entries/")
    assert "pred/t1/yct_0040.npy" not in b.s3_list("pred/")
    box1_sha = b.box_pred_sha["yct_0040.t1"]
    b.faults.clear()
    rc2, res2 = _run(env, "p4_b")
    assert rc2 == 0, res2
    assert "yct_0040.t1" in res2["restored"]
    assert b.extractions_per_job()["yct_0040.t1"] == 1                            # restored, not re-extracted
    row = next(r for r in _manifest(env) if r["job"] == "yct_0040.t1")
    assert row["cache_reused"] is True and row["pred_sha256"] == box1_sha        # Gate 1 across boxes


# ---------------------------------------------------------------- gates -> non-zero exit
def test_chunk_gate_failure_exits_nonzero_and_is_retried_next_session(env):
    b = env["backend"]
    b.faults["yct_0043.t3"] = "two_audio_chunks"
    rc, res = _run(env, "p4_a")
    assert rc == 1 and res["gate_failures"]["yct_0043.t3"]
    row = next(r for r in _manifest(env) if r["job"] == "yct_0043.t3")
    assert row["gate_pass"] is False and any("Audio" in f for f in row["gate_failures"])
    assert "pred/t3/yct_0043.npy" not in b.s3_list("pred/")                     # failed clip not published
    assert len([r for r in _manifest(env) if r["gate_pass"]]) == 6
    b.faults.clear()
    rc2, res2 = _run(env, "p4_b")
    assert rc2 == 0 and res2["jobs_run"] == ["yct_0043.t3"]


def test_d038_gate1_failure_is_a_stop(env):
    env["backend"].faults["yct_0016.t1"] = "rerun_differs"
    rc, res = _run(env)
    assert rc == 1 and res["stop"].startswith("D-038")
    assert res["jobs_run"] == ["yct_0016.t1"]                                  # nothing after a STOP


def test_existing_s3_object_with_other_sha_is_never_overwritten(env):
    b = env["backend"]
    b.s3_put_text("pred/t1/yct_0040.npy.sha256", "0" * 64 + "\n")
    rc, res = _run(env)
    assert rc == 1 and "yct_0040.t1" in res["errors"] and "overwrite" in res["errors"]["yct_0040.t1"]
    assert b.s3_get_text("pred/t1/yct_0040.npy.sha256").strip() == "0" * 64


def test_manifest_append_refuses_a_changed_remote():
    assert p4.append_manifest("a\n", [{"x": 1}]) == 'a\n{"x": 1}\n'
    with pytest.raises(p4.ManifestConflictError):
        p4.check_append("a\nb\n", "a\nc\n{}\n")


# ---------------------------------------------------------------- D-063 Q7: terminator + sweep
def test_refuses_to_launch_without_driver_independent_terminator(env):
    env["backend"].terminator_ok = False
    with pytest.raises(SystemExit, match="terminator"):
        _run(env)
    assert env["lg"].launched == []
    now = env["clock"]()
    with pytest.raises(SystemExit, match="terminator"):                       # fires before deadline + 15 min
        _run(env, external_terminator_at=now + 3.5 * 3600 + 60)
    with pytest.raises(SystemExit, match="terminator"):                       # far too late: exposure > 1 h
        _run(env, external_terminator_at=now + 3.5 * 3600 + 3 * 3600)
    rc, res = _run(env, external_terminator_at=now + 3.5 * 3600 + 1200)
    assert rc == 0 and res["terminator"]["kind"] == "external_scheduled_session"
    assert env["backend"].terminators == []


def test_failed_terminator_scheduling_terminates_at_once(env):
    env["backend"].faults["schedule_terminator"] = "fail"
    rc, res = _run(env)
    assert rc == 1 and "terminator" in res["error"]
    (iid,) = env["lg"].launched
    assert env["lg"].status[iid] == "terminated" and res["jobs_run"] == []


def test_session_start_sweeps_orphans_and_respects_a_live_concurrent_run(env):
    lg = env["lg"]
    orphan = lg.add_instance("yct-p4", age_s=7200, touch_age=None)
    rc, res = _run(env, "p4_a")
    assert rc == 0 and orphan in res["orphans_at_start"]["sweep"] and lg.status[orphan] == "terminated"
    live = lg.add_instance("yct-p4", age_s=600, touch_age=30)
    with pytest.raises(SystemExit, match="one instance at a time"):
        _run(env, "p4_b")
    assert lg.status[live] == "active"


# ---------------------------------------------------------------- D-063 B2 output firewall
FORBIDDEN = ("yct.features", "yct.interpret", "yct.stats", "yct.predict", "yct.report", "yct.confounds")


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


@pytest.mark.parametrize("path", ["scripts/gpu_wave1_p4.py", "src/yct/tribe_run/qc.py",
                                  "src/yct/tribe_run/cache_archive.py", "src/yct/tribe_run/feature_cache.py",
                                  "scripts/gpu_p0_rerun.py"])
def test_firewall_driver_imports_no_analysis_code(path):
    bad = [m for m in _imports(ROOT / path) if m.startswith(FORBIDDEN)]
    assert not bad, bad


def test_firewall_driver_reads_no_window_roi_or_control_config():
    src = DRIVER.read_text()
    for token in ('["window"]', '["controls"]', '["features"]', '["localize"]', "start_tr", "end_tr",
                  "window_average", "parcel", "network_means"):
        assert token not in src, token


def test_firewall_records_hold_no_prediction_statistics(env):
    assert _run(env)[0] == 0
    b = env["backend"]
    recs = [json.loads(b.s3_get_text(k)) for k in b.s3_list("records/")]
    assert recs and all(set(r) == {"record", "gate", "d038"} for r in recs)
    assert not [k for r in recs for k in r["record"] if k in ("pred_mean", "pred_std", "feature_sha256")]
    child = json.loads((env["tmp"] / "runs" / "p4_test" / "child_metrics.json").read_text())
    assert "pred_mean" not in json.dumps(child)


def test_cli_dry_run_loads_no_analysis_module(tmp_path):
    code = (f"import runpy, sys\nroot = sys.argv[1]\n"
            f"sys.argv = ['gpu_wave1_p4.py', '--dry-run', '--dry-run-root', root, '--limit', '3']\n"
            f"try:\n    runpy.run_path({str(DRIVER)!r}, run_name='__main__')\n    rc = 0\n"
            f"except SystemExit as e:\n    rc = e.code\n"
            f"bad = [m for m in sys.modules if m.startswith({FORBIDDEN!r})]\nprint('RC', rc, 'BAD', bad)\n")
    res = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True,
                         timeout=600, env={"YCT_RUN_DIR": str(tmp_path / "run"), "PATH": "/usr/bin:/bin",
                                           "PYTHONPATH": str(ROOT / "src")})
    assert "RC 75 BAD []" in res.stdout or "RC 0 BAD []" in res.stdout, res.stdout + res.stderr
    assert (tmp_path / "run" / "child_metrics.json").exists()


# ---------------------------------------------------------------- cycle-2 QA N1: the D-038 STOP is latched
def _decisions(tmp, text):
    p = tmp / "DECISIONS.md"
    p.write_text("# DECISIONS\n" + text)
    return p


def test_d038_stop_is_latched_until_cleared_by_a_decisions_entry(env):
    """QA c2 N1 (reproduced in the dry run): STOP -> plain re-run must refuse (no launch), not retry."""
    b, lg = env["backend"], env["lg"]
    b.faults["yct_0016.t1"] = "rerun_differs"
    rc, res = _run(env, "p4_a")
    assert rc == 1 and res["stop"]
    assert "stops/p4_a.json" in b.s3_list("stops/")
    b.faults.clear()                                       # a passing retry must not be reachable
    with pytest.raises(SystemExit, match="STOP"):
        _run(env, "p4_b")
    assert len(lg.launched) == 1
    dec = _decisions(env["tmp"], "- D-901 something else entirely\n")
    with pytest.raises(SystemExit, match="D-999"):         # unknown decision id
        _run(env, "p4_c", clear_stop="D-999", decisions_path=dec)
    with pytest.raises(SystemExit, match="p4_a"):          # entry exists but does not name the stopped run
        _run(env, "p4_c", clear_stop="D-901", decisions_path=dec)
    assert len(lg.launched) == 1
    dec = _decisions(env["tmp"], "- D-901 D-038 STOP of run p4_a reviewed: rerun allowed (human).\n")
    rc, res = _run(env, "p4_d", clear_stop="D-901", decisions_path=dec)
    assert rc == 0 and res["stop_cleared"] == {"p4_a": "D-901"}
    clr = json.loads(b.s3_get_text("stops_cleared/p4_a.json"))
    assert clr["decision"] == "D-901" and clr["cleared_by_run"] == "p4_d"
    assert b.s3_get_text("stops/p4_a.json")                # the marker itself is immutable, never deleted
    assert _run(env, "p4_e")[0] == 0                       # cleared once; later runs need no flag


def test_failed_d038_row_latches_even_without_the_marker(env):
    """A crash between the failing manifest row and the STOP marker must still latch."""
    b = env["backend"]
    b.faults["yct_0016.t1"] = "rerun_differs"
    _run(env, "p4_a")
    (b.s3 / "stops" / "p4_a.json").unlink()
    (b.s3 / "stops" / "p4_a.json.sha256").unlink(missing_ok=True)
    b.faults.clear()
    with pytest.raises(SystemExit, match="STOP"):
        _run(env, "p4_b")


def test_clear_stop_without_a_stop_is_refused(env):
    dec = _decisions(env["tmp"], "- D-901 p4_x\n")
    with pytest.raises(SystemExit, match="no latched"):
        _run(env, clear_stop="D-901", decisions_path=dec)


def test_docstring_says_exit_1_needs_a_human():
    doc = DRIVER.read_text().split('"""')[1]
    assert "re-run until it exits 0" not in doc
    assert "re-run while it exits 75" in doc and "exit 1 needs a human" in doc


# ---------------------------------------------------------------- cycle-2 QA N2: S3 read errors fail closed
class _CP:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _pod_backend(monkeypatch, result):
    pb = p4.PodBackend(load_config(), "p4_t", Path("/nonexistent"))
    calls = []

    def fake_aws(*args, inp=None, check=True):
        calls.append(args)
        r = result(args) if callable(result) else result
        if check and r.returncode:
            raise subprocess.CalledProcessError(r.returncode, args, r.stdout, r.stderr)
        return r

    monkeypatch.setattr(pb, "_aws", fake_aws)
    return pb, calls


@pytest.mark.parametrize("err", ["An error occurred (403) when calling the HeadObject operation: Forbidden",
                                 "Could not connect to the endpoint URL",
                                 "An error occurred (SlowDown) when calling the GetObject operation",
                                 "An error occurred (500) when calling the HeadObject operation",
                                 "Unable to locate credentials", ""])
def test_s3_get_text_raises_on_anything_but_not_found(monkeypatch, err):
    pb, _ = _pod_backend(monkeypatch, _CP(1, "", err))
    with pytest.raises(p4.S3ReadError):
        pb.s3_get_text("manifest.jsonl")


@pytest.mark.parametrize("err", ["fatal error: An error occurred (404) when calling the HeadObject "
                                 "operation: Key \"x\" does not exist",
                                 "An error occurred (NoSuchKey) when calling the GetObject operation"])
def test_s3_get_text_none_only_for_not_found(monkeypatch, err):
    pb, _ = _pod_backend(monkeypatch, _CP(1, "", err))
    assert pb.s3_get_text("x") is None
    pb, _ = _pod_backend(monkeypatch, _CP(0, "content\n", ""))
    assert pb.s3_get_text("x") == "content\n"


def test_transient_read_error_never_truncates_manifest_or_overwrites(env):
    """QA c2 N2: both manifest reads failing transiently used to replace the manifest by one row."""
    b = env["backend"]
    assert _run(env, "p4_a")[0] == 0
    before = b.s3_get_text("manifest.jsonl")
    store = p4.Store(b)
    real = b.s3_get_text

    def flaky(key):
        if key == "manifest.jsonl" or key.endswith(".sha256"):
            raise p4.S3ReadError(f"transient read error on {key}")
        return real(key)

    b.s3_get_text = flaky
    with pytest.raises(p4.S3ReadError):
        store.append_rows([{"job": "x", "gate_pass": True}], "p4_z")
    with pytest.raises(p4.S3ReadError):
        store.put_file(str(b.s3 / "manifest.jsonl"), "pred/t1/yct_0016.npy", "0" * 64)
    b.s3_get_text = real
    assert b.s3_get_text("manifest.jsonl") == before and "rows/p4_z/x.json" not in b.s3_list("rows/")


def test_missing_manifest_with_existing_rows_refuses(env):
    """A manifest that reads as absent while immutable rows exist is inconsistent: refuse, never rewrite."""
    b = env["backend"]
    assert _run(env, "p4_a")[0] == 0
    (b.s3 / "manifest.jsonl").unlink()
    with pytest.raises(SystemExit, match="manifest"):
        _run(env, "p4_b")
    assert len(env["lg"].launched) == 1
    with pytest.raises(p4.ManifestConflictError):
        p4.Store(b).append_rows([{"job": "x"}], "p4_c")
