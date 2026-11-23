"""T-NAT0 session-0 driver (D-075 §3, D-071 k), dry run only: the real infra/lambda_gpu.py code with a fake
Lambda API (gpu_wave1_p4.FakeLG), an in-memory campaign store and a fake box. No network, no GPU."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from yct.config import load_config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gpu_p4b_nat0", ROOT / "scripts" / "gpu_p4b_nat0.py")
nat0 = importlib.util.module_from_spec(spec)
sys.modules["gpu_p4b_nat0"] = nat0
spec.loader.exec_module(nat0)
p4 = nat0.ref.p4
from _pre_d087 import pre_d087  # noqa: E402

HEAD = "c" * 40
EN, ONE = {"en": 0.99}, [[0.0, 50.0, "S0"]]


def cfg(pyannote=True):
    c = pre_d087(copy.deepcopy(load_config()))
    if pyannote:
        for k in nat0.PYANNOTE_KEYS:
            c["controls"]["refclips_auto_artifacts"][k] = "a" * 64
            c["frozen"].append({"key": f"controls.refclips_auto_artifacts.{k}", "frozen_at": "x"})
        c["frozen"].append({"key": "controls.refclips_d082", "frozen_at": "x"})     # D-082 draft
    else:   # the repo config has the real D-082 shas set + frozen (0c3057c): the unset case clears them
        drop = {f"controls.refclips_auto_artifacts.{k}" for k in nat0.PYANNOTE_KEYS}
        for k in nat0.PYANNOTE_KEYS:
            c["controls"]["refclips_auto_artifacts"][k] = None
        c["frozen"] = [r for r in c["frozen"] if r["key"] not in drop]
    return c


class Store:
    def __init__(self):
        self.d = {}

    def s3_get_text(self, k):
        return self.d.get(k)

    def s3_put_text(self, k, t):
        self.d[k] = t

    def s3_list(self, prefix):
        return {k: 1 for k in self.d if k.startswith(prefix)}


class Box:
    def __init__(self, ids, bad=(), fail=None):
        self.ids, self.bad, self.fail, self.calls = ids, set(bad), fail, []

    def start(self, iid, deadline):
        self.calls.append("start")

    def step(self, name, buffer):
        self.calls.append(name)
        if name == self.fail:
            raise RuntimeError("box died")
        if name == "nat0":
            return {"results": {i: {"lang_probs": {"en": 0.1} if i in self.bad else EN, "segments": ONE}
                                for i in buffer}}

    def n3(self, i):
        return 0.9


@pytest.fixture
def env(tmp_path):
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    log = tmp_path / "nat_auto_log.jsonl"
    ids = [f"t1_{i:02d}" for i in range(40)]
    log.write_text("".join(json.dumps({"stage": "cpu", "decision": "pass", "t1_name": i, "title": f"File:{i}",
                                       "values": {"licence": "CC0", "licence_template": "Template:Cc-zero"}})
                           + "\n" for i in ids))
    return SimpleNamespace(clock=clock, lg=lg, log=log, ids=ids, store=Store(), tmp=tmp_path)


def args(env, **kw):
    a = {"max_hours": 1.75, "usd_limit": 8.0, "external_terminator_at": env.clock() + 1.75 * 3600 + 1000,
         "ci_green_sha": HEAD, "ack_cap_80": False, "run_id": "p4bnat0_test"}
    a.update(kw)
    return SimpleNamespace(**a)


def run(env, c=None, box=None, head=HEAD, pushed=True, **kw):
    # council D-082: a fresh L4 reconciliation record and a finished pod CPU stage whose log is the
    # committed one (their refusals are tested in tests/test_nat0_council_d082.py)
    import hashlib

    c = c or cfg()
    recon = nat0.reconcile(env.lg, c, env.clock)
    cpu_state = {"alive": False, "pod_log_sha256": hashlib.sha256(env.log.read_bytes()).hexdigest()}
    return nat0.run_session0(args(env, **kw), c, env.lg, env.store, box or Box(env.ids), env.clock,
                             env.log, head, pushed, recon=recon, cpu_state=cpu_state)


def rows(env, stage="session0"):
    return [json.loads(x) for x in env.log.read_text().splitlines() if json.loads(x).get("stage") == stage]


def test_full_dry_session_selects_15_and_writes_baseline_first(env):
    box = Box(env.ids, bad={"t1_00", "t1_02"})
    rc, res = run(env, box=box)
    assert rc == 0, res
    r = rows(env)
    assert sum(x["decision"] == "pass" for x in r) == 15 and len(r) == 17
    assert box.calls == ["start", *nat0.STEPS], "no TRIBE job in session 0"
    base = json.loads(env.store.d["entries/campaign_baseline.json"])
    (iid,) = env.lg.launched
    assert env.lg.api.inst[iid]["name"].startswith("yct-p4b-ref")
    led = [json.loads(x) for x in Path(env.lg.mod.LEDGER).read_text().splitlines()]
    launch_line = next(i for i, x in enumerate(led) if x.get("event") == "launch")
    assert base["n_lines"] <= launch_line, "baseline written before the first yct-p4b-ref launch"
    assert env.lg.status[iid] == "terminated" and res["pre_launch"]["cap_usd"] == 75


def test_fewer_than_15_is_stop_exit_1_and_rows_logged(env):
    rc, res = run(env, box=Box(env.ids, bad=set(env.ids[:26])))
    assert rc == 1 and res["status"] == "stop" and res["n_pass"] == 14
    assert len(rows(env)) == 40


@pytest.mark.parametrize("kw,match", [
    ({"max_hours": 2.0}, "launcher_max_hours"),
    ({"usd_limit": 9.0}, "usd-limit"),
    ({"usd_limit": 3.0}, "exceeds"),
    ({"external_terminator_at": None}, "external-terminator"),
    ({"external_terminator_at": 1_800_000_000.0 + 1.75 * 3600}, "must fire between"),
    ({"ci_green_sha": "d" * 40}, "CI-green"),
])
def test_preflight_refusals_launch_nothing(env, kw, match):
    rc, res = run(env, **kw)
    assert rc == 1 and res["status"] == "refused" and match in res["error"], res
    assert env.lg.launched == [] and "entries/campaign_baseline.json" not in env.store.d


def test_unpushed_commit_refused(env):
    rc, res = run(env, pushed=False)
    assert rc == 1 and "remote branch" in res["error"] and env.lg.launched == []


def test_unset_pyannote_shas_refused(env):
    rc, res = run(env, c=cfg(pyannote=False))
    assert rc == 1 and "pyannote shas not set" in res["error"] and env.lg.launched == []


def test_terminator_time_reuse_refused(env):
    ext = env.clock() + 1.75 * 3600 + 1000
    env.store.d["runs/old/child_metrics.json"] = json.dumps({"run_id": "old", "terminator": {"fire_at": ext}})
    rc, res = run(env, external_terminator_at=ext)
    assert rc == 1 and "already used" in res["error"]


def test_cap_guard_refuses_over_75(env):
    env.lg.mod._append({"event": "launch", "id": "old1", "name": "yct-p4b-ref-x", "usd_per_hour": 100.0,
                        "t": env.clock() - 3600})
    env.lg.mod._append({"event": "terminate", "id": "old1", "t": env.clock() - 1})
    rc, res = run(env)
    assert rc == 1 and ("campaign cap" in res["error"] or "before the baseline" in res["error"])
    assert env.lg.launched == []


def test_prefixed_launch_before_baseline_refused(env):
    env.lg.mod._append({"event": "launch", "id": "old2", "name": "yct-p4b-ref-early", "usd_per_hour": 1.99,
                        "t": env.clock() - 100})
    env.lg.mod._append({"event": "terminate", "id": "old2", "t": env.clock() - 50})
    rc, res = run(env)
    assert rc == 1 and "before the baseline" in res["error"]


def test_box_failure_is_exit_75_nothing_logged_instance_terminated(env):
    rc, res = run(env, box=Box(env.ids, fail="nat0"))
    assert rc == 75 and res["status"] == "box_failed" and rows(env) == []
    (iid,) = env.lg.launched
    assert env.lg.status[iid] == "terminated"


def test_no_capacity_is_exit_75(env, monkeypatch):
    def nocap(*a, **k):
        raise SystemExit("gpu_1x_a100_sxm4 has no capacity in eu-central-1")

    monkeypatch.setattr(env.lg.mod, "launch", nocap)
    rc, res = run(env)
    assert rc == 75 and res["status"] == "no_capacity"


def test_second_session_refused_once_rows_logged(env):
    assert run(env)[0] == 0
    rc, res = run(env, external_terminator_at=env.clock() + 1.75 * 3600 + 1500)
    assert rc == 1 and "already logged" in res["error"]


def test_driver_has_no_tribe_job():
    src = (ROOT / "scripts" / "gpu_p4b_nat0.py").read_text()
    for word in ("run_clip", "remote_setup.sh", "tribe_run.run_clip", "Campaign("):
        assert word not in src


def test_type_missing_from_types_is_exit_75_without_launch(env, monkeypatch):
    """BUG-047: lg.types() briefly omitted gpu_1x_a100_sxm4 before NAT session 2 and the driver died with a
    KeyError (exit 1). A type missing from the list is a capacity miss: exit 75, nothing launched or logged."""
    monkeypatch.setattr(env.lg.mod, "types", lambda: {})
    before = env.log.read_text()
    rc, res = run(env)
    assert rc == 75 and res["status"] == "no_capacity"
    assert "not in available types" in res["error"]
    assert env.lg.api.inst == {} and env.log.read_text() == before
