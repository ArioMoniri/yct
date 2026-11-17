"""Watchdog W-COST guards for the Lambda GPU wrapper; no network calls."""
import importlib

import pytest


@pytest.fixture
def lg(tmp_path, monkeypatch):
    mod = importlib.import_module("infra.lambda_gpu")
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(mod, "types", lambda: {"gpu_1x_a10": {"usd_per_hour": 1.29, "regions": ["r"]},
                                          "gpu_1x_a100": {"usd_per_hour": 1.99, "regions": ["r"]}})
    monkeypatch.setattr(mod, "_ssm_budget", lambda: 200.0)  # owner-verified SSM value (stub; no AWS)
    return mod


def test_name_prefix_required(lg):
    with pytest.raises(SystemExit):
        lg.launch("gpu_1x_a100", "other-name", 1, None, None)


def test_max_hours_hard_cap(lg, monkeypatch):
    monkeypatch.setenv("BUDGET_MAX_HOURS", "100")  # env must not raise the cap
    assert lg.BUDGET_MAX_HOURS == 4.0
    with pytest.raises(SystemExit):
        lg.launch("gpu_1x_a100", "yct-x", 4.5, None, None)


def test_a10_blocked_until_smoke(lg, monkeypatch):
    monkeypatch.delenv("A10_ALLOWED", raising=False)
    with pytest.raises(SystemExit, match="A10"):
        lg.launch("gpu_1x_a10", "yct-x", 1, None, None)


def test_budget_cap(lg, monkeypatch):
    monkeypatch.setattr(lg, "BUDGET_USD", 1.0)
    with pytest.raises(SystemExit, match="budget"):
        lg.launch("gpu_1x_a100", "yct-x", 1, None, None)


def test_spent_counts_open_instances(lg):
    import time
    lg._append({"event": "launch", "id": "a", "usd_per_hour": 3600.0, "t": time.time() - 2, "deadline": 0})
    assert lg.spent_usd() >= 2.0


def test_budget_from_file_not_env(monkeypatch):
    import importlib
    monkeypatch.setenv("BUDGET_USD", "999999")
    mod = importlib.reload(importlib.import_module("infra.lambda_gpu"))
    assert mod.BUDGET_USD == 200.0


# ---------------------------------------------------------------- heartbeat (v2.md §3, Watchdog G-D032)
class FakeLambda:
    """Stub of the Lambda Cloud API (no network): instances by id, terminations recorded."""

    def __init__(self, instances):
        self.inst = {i["id"]: dict(i) for i in instances}
        self.terminated: list[str] = []

    def __call__(self, method, path, body=None):
        if method == "GET" and path == "/instances":
            return {"data": list(self.inst.values())}
        if method == "GET" and path.startswith("/instances/"):
            return {"data": self.inst[path.rsplit("/", 1)[1]]}
        if method == "POST" and path == "/instance-operations/terminate":
            for iid in body["instance_ids"]:
                self.inst[iid]["status"] = "terminated"
                self.terminated.append(iid)
            return {"data": {}}
        raise AssertionError(f"unexpected API call {method} {path}")


def _launch_rec(lg, iid, t, hours=3.0):
    lg._append({"event": "launch", "id": iid, "name": f"yct-{iid}", "type": "gpu_1x_a100",
                "usd_per_hour": 1.99, "t": t, "deadline": t + hours * 3600})


def _events(lg, kind):
    return [r for r in lg._ledger() if r["event"] == kind]


def test_heartbeat_timeout_is_ten_minutes(lg):
    assert lg.HEARTBEAT_TIMEOUT_S == 600


def test_reap_kills_instance_with_stale_heartbeat(lg, monkeypatch):
    import time

    now = time.time()
    api = FakeLambda([{"id": "stale", "name": "yct-stale", "status": "active"},
                      {"id": "fresh", "name": "yct-fresh", "status": "active"},
                      {"id": "other", "name": "someone-else", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "stale", now - 3600)
    _launch_rec(lg, "fresh", now - 3600)
    _launch_rec(lg, "other", now - 3600)
    lg._append({"event": "heartbeat", "id": "stale", "t": now - 601})
    lg._append({"event": "heartbeat", "id": "fresh", "t": now - 30})
    killed = lg.reap()
    assert killed == ["stale"]
    assert api.terminated == ["stale"]  # never touches non-yct instances
    term = _events(lg, "terminate")
    assert [r["id"] for r in term] == ["stale"] and term[0]["reason"] == "heartbeat"


def test_reap_kills_never_heartbeated_instance_after_ten_minutes(lg, monkeypatch):
    import time

    now = time.time()
    api = FakeLambda([{"id": "a", "name": "yct-a", "status": "active"},
                      {"id": "b", "name": "yct-b", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "a", now - 11 * 60)  # launched 11 min ago, no heartbeat ever
    _launch_rec(lg, "b", now - 5 * 60)   # launched 5 min ago: within grace
    assert lg.reap() == ["a"]
    assert api.terminated == ["a"]


def test_reap_still_kills_past_deadline_despite_heartbeat(lg, monkeypatch):
    import time

    now = time.time()
    api = FakeLambda([{"id": "d", "name": "yct-d", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "d", now - 2 * 3600, hours=1.0)
    lg._append({"event": "heartbeat", "id": "d", "t": now - 5})
    assert lg.reap() == ["d"]
    assert _events(lg, "terminate")[0]["reason"] == "deadline"


def _box(lines_by_id):
    """Stub of the instance-side heartbeat log: fetch(inst) -> [(t, util, mem)]."""
    return lambda inst: list(lines_by_id.get(inst["id"], []))


def test_watch_writes_instance_heartbeat_each_loop(lg, monkeypatch):
    import time

    now = time.time()
    api = FakeLambda([{"id": "w", "name": "yct-w", "status": "active", "ip": "1.2.3.4"},
                      {"id": "x", "name": "not-ours", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "w", now - 60)
    box: dict[str, list] = {"w": []}
    loops = {"n": 0}

    def fake_sleep(_s):
        loops["n"] += 1
        box["w"].append((now + loops["n"], 87.0, 13000.0))  # the box writes a line
        if loops["n"] == 3:
            api.inst["w"]["status"] = "terminated"  # job finished; watch must then exit

    box["w"].append((now - 0.5, 90.0, 12000.0))
    monkeypatch.setattr(lg.time, "sleep", fake_sleep)
    lg.watch(interval=1, fetch=_box(box))
    hb = _events(lg, "heartbeat")
    assert len(hb) == 3 and {r["id"] for r in hb} == {"w"}
    assert all(set(r) == {"event", "id", "t", "gpu_util", "mem_mib", "source"} for r in hb)
    assert all(r["source"] == "instance" and r["gpu_util"] >= 87.0 for r in hb)
    assert all(abs(r["t"] - time.time()) < 60 for r in hb)
    assert api.terminated == []  # fresh heartbeats: nothing reaped


def test_watch_heartbeat_keeps_long_job_alive(lg, monkeypatch):
    """Simulated clock: a 30-min busy job whose box writes heartbeats is never reaped."""
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(lg.time, "time", lambda: clock["t"])
    api = FakeLambda([{"id": "j", "name": "yct-j", "status": "active", "ip": "h"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "j", clock["t"])
    box = {"j": [(clock["t"], 95.0, 1.0)]}

    def fake_sleep(s):
        clock["t"] += s
        box["j"].append((clock["t"], 95.0, 1.0))
        if clock["t"] >= 1_000_000.0 + 30 * 60:
            api.inst["j"]["status"] = "terminated"

    monkeypatch.setattr(lg.time, "sleep", fake_sleep)
    lg.watch(interval=60, fetch=_box(box))
    assert api.terminated == []
    assert len(_events(lg, "heartbeat")) == 30


def test_watcher_alone_never_heartbeats_hung_box_is_reaped(lg, monkeypatch):
    """Watchdog P0 #4: a running watcher must not keep a silent (hung) box alive."""
    clock = {"t": 2_000_000.0}
    monkeypatch.setattr(lg.time, "time", lambda: clock["t"])
    api = FakeLambda([{"id": "h", "name": "yct-h", "status": "active", "ip": "h"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "h", clock["t"])
    box = {"h": [(clock["t"], 99.0, 1.0)]}  # one line, then the box hangs

    def fake_sleep(s):
        clock["t"] += s

    monkeypatch.setattr(lg.time, "sleep", fake_sleep)
    lg.watch(interval=60, fetch=_box(box))
    assert api.terminated == ["h"]
    assert _events(lg, "terminate")[0]["reason"] == "heartbeat"
    assert 600 < clock["t"] - 2_000_000.0 <= 720
    assert len(_events(lg, "heartbeat")) == 1


def test_idle_gpu_killed_after_15_min(lg, monkeypatch):
    clock = {"t": 3_000_000.0}
    monkeypatch.setattr(lg.time, "time", lambda: clock["t"])
    api = FakeLambda([{"id": "i", "name": "yct-i", "status": "active", "ip": "h"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "i", clock["t"] - 3600)
    box = {"i": [(clock["t"] - 60, 80.0, 1.0)]}  # busy a minute ago, then util drops to 2 %

    def fake_sleep(s):
        clock["t"] += s
        box["i"].append((clock["t"], 2.0, 1.0))

    monkeypatch.setattr(lg.time, "sleep", fake_sleep)
    lg.watch(interval=60, fetch=_box(box))
    assert api.terminated == ["i"]
    assert _events(lg, "terminate")[0]["reason"] == "idle_gpu"
    assert 15 * 60 < clock["t"] - (3_000_000.0 - 60) <= 17 * 60


def test_idle_rule_allows_setup_grace_then_kills_never_busy(lg, monkeypatch):
    import time

    now = time.time()
    api = FakeLambda([{"id": "s", "name": "yct-s", "status": "active"},
                      {"id": "n", "name": "yct-n", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "s", now - 20 * 60)  # 20 min of setup at 0 %: within the 30-min grace
    _launch_rec(lg, "n", now - 31 * 60)  # never busy for 31 min: idle-killed
    for iid in ("s", "n"):
        lg._append({"event": "heartbeat", "id": iid, "t": now - 10, "gpu_util": 0.0, "source": "instance"})
    assert lg.reap() == ["n"]
    assert _events(lg, "terminate")[0]["reason"] == "idle_gpu"


def test_poll_ignores_duplicate_future_and_junk_lines(lg):
    import time

    now = time.time()
    lines = lg.parse_box_log(f"{now - 30} 50 100\ngarbage\n{now - 20} 60\n{now + 3600} 99 1\n")
    assert [(round(t), u) for t, u, _ in lines] == [(round(now - 30), 50.0), (round(now - 20), 60.0),
                                                     (round(now + 3600), 99.0)]
    inst = [{"id": "p", "ip": "h"}]
    assert lg.poll_heartbeats(inst, fetch=lambda i: lines) == 2  # the future line is refused
    assert lg.poll_heartbeats(inst, fetch=lambda i: lines) == 0  # already recorded
    assert [r["gpu_util"] for r in _events(lg, "heartbeat")] == [50.0, 60.0]


# ---------------------------------------------------------------- budget fails closed (Watchdog P0 #5)
def test_budget_unverified_refuses_launch(lg, monkeypatch):
    def boom():
        raise RuntimeError("no SSM access")

    monkeypatch.setattr(lg, "_ssm_budget", boom)
    calls = []
    monkeypatch.setattr(lg, "_req", lambda *a, **k: calls.append(a) or {"data": []})
    with pytest.raises(SystemExit, match="unverified"):
        lg.launch("gpu_1x_a100", "yct-x", 1, None, None)
    assert not any(a[:2] == ("POST", "/instance-operations/launch") for a in calls)


def test_budget_is_min_of_file_and_owner(lg, monkeypatch):
    monkeypatch.setattr(lg, "_ssm_budget", lambda: 3.0)  # owner lowered the cap below the file
    with pytest.raises(SystemExit, match="budget cap"):
        lg.launch("gpu_1x_a100", "yct-x", 2, None, None)  # 2 h * 1.99 > 3
    monkeypatch.setattr(lg, "_ssm_budget", lambda: 10_000.0)  # owner value can never exceed the file
    assert lg.budget_cap() == lg.BUDGET_USD == 200.0
