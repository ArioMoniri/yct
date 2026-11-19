"""T-DRV (D-071, design_v2 §8): a capacity miss leaves no debris; the real lambda_gpu.launch capacity race
exits 75; three consecutive non-capacity HTTP-400 launch refusals exit 1 (a human looks).
Dry run only: in-memory Lambda (the real infra/lambda_gpu.py code), local pod/box/S3."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

from yct.config import load_config, with_overrides

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("gpu_wave1_p4", ROOT / "scripts" / "gpu_wave1_p4.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_wave1_p4"] = mod
    spec.loader.exec_module(mod)
    return mod


p4 = _load()

SMALL = {"p4": {"launcher_max_hours": 4, "run_set_t1": ["yct_0016", "yct_0040"],
                "run_set_t3": ["yct_0016", "yct_0040"], "t1_excluded": {}, "d038_clips": ["yct_0016"],
                "flags": {"low_fps_source": {"rule": "r", "videos": [], "sensitivity": "S-LOWFPS"}}}}


@pytest.fixture
def env(tmp_path):
    cfg = with_overrides(load_config(), SMALL)
    clock = p4.FakeClock(1_800_000_000.0)
    return {"cfg": cfg, "clock": clock, "lg": p4.FakeLG(clock, tmp_path / "ledger.jsonl"),
            "backend": p4.DryRunBackend(tmp_path / "dry", cfg, clock), "tmp": tmp_path}


def _run(env, run_id="p4_test"):
    a = p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id=run_id)
    return p4.run_session(a, env["cfg"], env["lg"], env["backend"], env["clock"],
                          env["tmp"] / "runs" / run_id)


def _snapshot(env):
    lg, b = env["lg"], env["backend"]
    led = lg.mod.LEDGER
    return {"ledger": led.read_text() if led.exists() else "", "spent": lg.mod.spent_usd(),
            "manifest": b.s3_get_text("manifest.jsonl"), "keys": set(b.s3_list("")),
            "inst": dict(lg.api.inst)}


def _assert_no_debris(env, before, run_id="p4_test"):
    after = _snapshot(env)
    assert after["inst"] == before["inst"] == {}, "no instance may exist after a capacity miss"
    assert after["ledger"] == before["ledger"], "no ledger line on a capacity miss"
    assert after["spent"] == before["spent"]
    assert after["manifest"] == before["manifest"]
    assert after["keys"] - before["keys"] == {f"runs/{run_id}/child_metrics.json"}
    rec = json.loads(env["backend"].s3_get_text(f"runs/{run_id}/child_metrics.json"))
    assert rec["status"] == "no_capacity" and rec["exit_code"] == p4.EXIT_INCOMPLETE


def _http400(body: bytes):
    def bad(*a, **k):
        raise urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(body))
    return bad


@pytest.mark.parametrize("where", ["price_lookup", "launch_no_capacity", "launch_http_400"])
def test_capacity_miss_leaves_no_instance_ledger_line_or_manifest_change(env, where):
    if where == "price_lookup":
        env["lg"].mod.types = lambda: {}
    elif where == "launch_no_capacity":
        def gone(*a, **k):
            raise SystemExit("gpu_1x_a100_sxm4 has no capacity now; available: []")
        env["lg"].mod.launch = gone
    else:
        env["lg"].mod.launch = _http400(b'{"error":"insufficient capacity"}')
    before = _snapshot(env)
    rc, res = _run(env)
    assert rc == p4.EXIT_INCOMPLETE and res["status"] == "no_capacity"
    _assert_no_debris(env, before)


def test_capacity_race_through_the_real_lambda_launch_exits_75(env):
    """Capacity listed at the driver's price lookup, gone when the real lambda_gpu.launch re-checks it."""
    calls = {"n": 0}
    avail = {"gpu_1x_a100_sxm4": {"usd_per_hour": 1.99, "regions": ["eu-central-1"]}}

    def racing_types():
        calls["n"] += 1
        return avail if calls["n"] == 1 else {}
    env["lg"].mod.types = racing_types
    before = _snapshot(env)
    rc, res = _run(env)
    assert calls["n"] >= 2, "the real launch must have re-checked capacity"
    assert rc == p4.EXIT_INCOMPLETE and res["status"] == "no_capacity"
    assert "has no capacity" in res["capacity_miss"]
    _assert_no_debris(env, before)


def test_three_consecutive_non_capacity_http_400_misses_exit_1(env):
    env["lg"].mod.launch = _http400(b'{"error":{"code":"global/invalid-parameters"}}')
    for i in (1, 2):
        rc, res = _run(env, run_id=f"p4_m{i}")
        assert rc == p4.EXIT_INCOMPLETE and res["status"] == "no_capacity", (i, res)
        env["clock"].advance(60)
    rc, res = _run(env, run_id="p4_m3")
    assert rc == p4.EXIT_FAIL and res["status"] == "failed"
    assert "3 consecutive" in res["error"]
    assert env["lg"].api.inst == {}


def test_a_capacity_400_in_between_resets_the_non_capacity_streak(env):
    seq = [b'{"error":"bad param"}', b'{"error":"insufficient capacity"}', b'{"error":"bad param"}',
           b'{"error":"bad param"}']
    for i, body in enumerate(seq):
        env["lg"].mod.launch = _http400(body)
        rc, res = _run(env, run_id=f"p4_a{i}")
        assert rc == p4.EXIT_INCOMPLETE, (i, res)
        env["clock"].advance(60)
