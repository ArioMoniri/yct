"""Watchdog W-COST guards for the Lambda GPU wrapper; no network calls."""
import importlib

import pytest


@pytest.fixture
def lg(tmp_path, monkeypatch):
    mod = importlib.import_module("infra.lambda_gpu")
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(mod, "types", lambda: {"gpu_1x_a10": {"usd_per_hour": 1.29, "regions": ["r"]},
                                          "gpu_1x_a100": {"usd_per_hour": 1.99, "regions": ["r"]}})
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


def test_watch_writes_heartbeat_each_loop(lg, monkeypatch):
    import time

    now = time.time()
    api = FakeLambda([{"id": "w", "name": "yct-w", "status": "active"},
                      {"id": "x", "name": "not-ours", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "w", now - 60)
    loops = {"n": 0}

    def fake_sleep(_s):
        loops["n"] += 1
        if loops["n"] == 3:
            api.inst["w"]["status"] = "terminated"  # job finished; watch must then exit

    monkeypatch.setattr(lg.time, "sleep", fake_sleep)
    lg.watch(interval=1)
    hb = _events(lg, "heartbeat")
    assert len(hb) == 3 and {r["id"] for r in hb} == {"w"}
    assert all(set(r) == {"event", "id", "t"} for r in hb)
    assert all(abs(r["t"] - time.time()) < 60 for r in hb)
    assert api.terminated == []  # fresh heartbeats: nothing reaped


def test_watch_heartbeat_keeps_long_job_alive(lg, monkeypatch):
    """Simulated clock: a 30-min job under a running watch is never heartbeat-reaped."""
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(lg.time, "time", lambda: clock["t"])
    api = FakeLambda([{"id": "j", "name": "yct-j", "status": "active"}])
    monkeypatch.setattr(lg, "_req", api)
    _launch_rec(lg, "j", clock["t"])

    def fake_sleep(s):
        clock["t"] += s
        if clock["t"] >= 1_000_000.0 + 30 * 60:
            api.inst["j"]["status"] = "terminated"

    monkeypatch.setattr(lg.time, "sleep", fake_sleep)
    lg.watch(interval=60)
    assert api.terminated == []
    assert len(_events(lg, "heartbeat")) == 30
