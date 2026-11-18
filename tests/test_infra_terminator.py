"""D-063 Q7 / QA P4-entry D3, D4, D12 (BUG-027 follow-up): deadline in the instance name, a ledger-free
deadline reaper for the driver-independent scheduled terminator, a liveness-aware sweep, and an absolute
deadline in the box dead-man switch. No network: the Lambda API is stubbed."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.test_infra_guards import FakeLambda, _events, lg  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]


def _name(base, launch, deadline):
    return f"{base}-t{int(launch)}-dl{int(deadline)}"


# ---------------------------------------------------------------- name-encoded launch/deadline
def test_launch_puts_launch_and_deadline_in_the_name(lg, monkeypatch):  # noqa: F811
    calls = []

    def api(method, path, body=None):
        calls.append((method, path, body))
        if path == "/ssh-keys":
            return {"data": [{"name": "yct-pod"}]}
        if path == "/instance-operations/launch":
            return {"data": {"instance_ids": ["i1"]}}
        raise AssertionError(path)

    monkeypatch.setattr(lg, "_req", api)
    rec = lg.launch("gpu_1x_a100", "yct-p4", 3.5, "yct-pod", None, name_deadline=True)
    name = calls[-1][2]["name"]
    t0, dl = lg.name_times(name)
    assert name.startswith("yct-p4-t") and rec["name"] == name
    assert dl == int(rec["deadline"]) and abs(dl - t0 - 3.5 * 3600) <= 1 and abs(t0 - time.time()) < 5
    assert len(name) <= 64
    assert lg.name_times("yct-wave1p2b") == (None, None) and lg.name_times("yct-x-t12-dl34") == (None, None)


def test_reap_deadline_needs_no_ledger_and_only_kills_past_name_deadline(lg, monkeypatch):  # noqa: F811
    now = time.time()
    api = FakeLambda([
        {"id": "late", "name": _name("yct-p4", now - 5 * 3600, now - 1000), "status": "active"},
        {"id": "ok", "name": _name("yct-p4", now - 3600, now + 3600), "status": "active"},
        {"id": "edge", "name": _name("yct-p4", now - 4 * 3600, now - 100), "status": "active"},
        {"id": "noname", "name": "yct-wave1p2b", "status": "active"},
        {"id": "dead", "name": _name("yct-p4", now - 9 * 3600, now - 5 * 3600), "status": "terminated"},
        {"id": "foreign", "name": _name("other", now - 5 * 3600, now - 1000), "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    assert not lg.LEDGER.exists()
    assert lg.reap_deadline(margin_s=600) == ["late"]          # "edge" is inside the margin
    assert api.terminated == ["late"]
    assert lg.reap_deadline(margin_s=0, ids=["ok", "edge"]) == ["edge"]
    assert [r["reason"] for r in _events(lg, "terminate")] == ["name_deadline", "name_deadline"]


# ---------------------------------------------------------------- liveness-aware sweep (D-063 Q7, QA D4)
def test_sweep_keeps_concurrent_run_with_fresh_touch(lg, monkeypatch):  # noqa: F811
    now = time.time()
    api = FakeLambda([{"id": "live_other", "name": _name("yct-p4", now - 3600, now + 3600),
                       "status": "active", "ip": "1.1.1.1"},
                      {"id": "orphan", "name": _name("yct-p4", now - 7200, now + 600), "status": "active",
                       "ip": "2.2.2.2"},
                      {"id": "unreach", "name": "yct-old", "status": "active", "ip": "3.3.3.3"}])
    monkeypatch.setattr(lg, "_req", api)
    ages = {"live_other": 45.0, "orphan": lg.DEADMAN_GRACE_S + 5, "unreach": None}
    killed = lg.sweep(touch_age=lambda i: ages[i["id"]])
    assert sorted(killed) == ["orphan", "unreach"] and "live_other" not in api.terminated


def test_sweep_keeps_booting_instance_without_touch_yet(lg, monkeypatch):  # noqa: F811
    now = time.time()
    api = FakeLambda([{"id": "boot", "name": _name("yct-p4", now - 300, now + 3 * 3600), "status": "booting"},
                      {"id": "oldboot", "name": _name("yct-p4", now - 3 * 3600, now + 3600),
                       "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    assert lg.sweep(touch_age=lambda i: None) == ["oldboot"]


def test_sweep_force_kills_regardless_of_touch(lg, monkeypatch):  # noqa: F811
    now = time.time()
    api = FakeLambda([{"id": "a", "name": _name("yct-p4", now - 60, now + 3600), "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    assert lg.sweep(touch_age=lambda i: 1.0, force=True) == ["a"]


def test_cli_sweep_is_liveness_aware_unless_forced(lg, monkeypatch):  # noqa: F811
    seen = {}
    def fake_sweep(keep=(), touch_age=None, force=False):
        seen["f"] = force
        return []

    monkeypatch.setattr(lg, "sweep", fake_sweep)
    lg.main(["sweep"])
    assert seen["f"] is False
    seen.clear()
    lg.main(["sweep", "--force"])
    assert seen["f"] is True


# ---------------------------------------------------------------- pod-side scheduled terminator
def test_terminator_script_reads_key_from_ssm_never_on_argv(tmp_path):
    """infra/gpu_terminator.sh (fired by a pod-side systemd-run timer at deadline + 15 min) gets the Lambda
    key from SSM into the ENVIRONMENT of the reaper, never into argv or stdout."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "aws").write_text("#!/bin/sh\necho FAKE-KEY-FOR-TEST\n")
    infra = tmp_path / "infra"
    infra.mkdir()
    (infra / "lambda_gpu.py").write_text(
        "import os, sys, pathlib\n"
        "pathlib.Path(sys.argv[0]).with_name('called.txt').write_text(repr(sys.argv[1:]) + '\\n' + "
        "str(os.environ.get('LAMBDA_API_KEY') == 'FAKE-KEY-FOR-TEST'))\n")
    for f in fake_bin.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
    res = subprocess.run(["bash", str(ROOT / "infra" / "gpu_terminator.sh"), "iid123", "300", str(infra)],
                         env=env, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    argv, key_in_env = (infra / "called.txt").read_text().splitlines()
    assert argv == "['reap-deadline', '--margin-s', '300', '--id', 'iid123']" and key_in_env == "True"
    assert "FAKE-KEY" not in res.stdout + res.stderr + argv


def test_terminator_schedule_script(lg):  # noqa: F811
    s = lg.pod_terminator_script("0123456789abcdef0123", fire_at=1_000_900.0, now=1_000_000.0,
                                 run_id="p4_x", repo="/work/yct/repo")
    assert "systemd-run" in s and "--on-active=900s" in s and "yct-term-0123456789ab" in s
    assert "gpu_terminator.sh 0123456789abcdef0123 300 /work/yct/p4/terminator/p4_x/infra" in s
    assert "cp -r /work/yct/repo/infra /work/yct/p4/terminator/p4_x/infra" in s
    assert "LAMBDA_API_KEY" not in s and "--query Parameter.Version" in s   # probe: never the value
    with pytest.raises(ValueError):
        lg.pod_terminator_script("x", fire_at=10.0, now=20.0, run_id="r", repo="/r")


# ---------------------------------------------------------------- dead-man: absolute deadline (QA D12)
def test_deadman_halts_at_absolute_deadline(tmp_path):
    script = ROOT / "infra" / "gpu_deadman.sh"
    marker = tmp_path / "halted"
    env = {**os.environ, "SHUTDOWN_CMD": f"touch {marker}", "CHECK_S": "1",
           "DEADMAN_LOG": str(tmp_path / "log")}
    p = subprocess.run(["bash", str(script), str(tmp_path / "t"), "3600", "3600", str(int(time.time()) + 2)],
                       env=env, timeout=20)
    assert p.returncode == 0 and marker.exists() and "deadline" in (tmp_path / "log").read_text()
