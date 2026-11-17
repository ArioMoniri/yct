"""Lambda Cloud GPU lifecycle with hard cost guards.

Usage:
  python infra/lambda_gpu.py types
  python infra/lambda_gpu.py launch --type gpu_1x_a100_sxm4 --name yct-tribe --max-hours 3
  python infra/lambda_gpu.py watch           # foreground reaper loop (run in background during jobs)
  python infra/lambda_gpu.py list
  python infra/lambda_gpu.py terminate --id <instance_id>
  python infra/lambda_gpu.py reap            # terminate yct-* instances past their deadline

Guards (watchdog rules W-COST):
  * API key only from env LAMBDA_API_KEY; never printed or logged.
  * Every launched instance is recorded in outputs/infra/gpu_ledger.jsonl with a deadline.
  * --max-hours is mandatory; HARD cap 4 h (not overridable from env).
  * Cumulative spend cap = min(infra/BUDGET_USD, owner SSM /yct/owner/budget_usd verified via
    yct.owner_actions). FAILS CLOSED (Watchdog P0 #5): if the owner budget cannot be verified, `launch`
    refuses (SystemExit), it never falls back to the file. A warning is emitted at >=80% of the cap.
  * The ledger is tracked in git (infra/gpu_ledger.jsonl) so spend survives fresh checkouts.
  * Heartbeats come FROM THE GPU INSTANCE (Watchdog P0 #4): infra/gpu_heartbeat.sh runs on the box and
    appends "<epoch> <gpu_util%> <mem_used_MiB>" to ~/yct_heartbeat.log every 30 s. `watch` polls that
    file over ssh (from the pod: YCT_HB_VIA_POD=1 routes through infra/pod_exec.sh) and appends one
    {"event": "heartbeat", "id", "t", "gpu_util", "mem_mib", "source": "instance"} ledger record per new
    line. The watcher itself never writes heartbeats, so a hung box or dead loop stops them.
  * `reap` terminates yct-* instances (a) past deadline, (b) whose last instance heartbeat (or launch, if
    none) is older than HEARTBEAT_TIMEOUT_S = 10 min, or (c) idle: GPU util < IDLE_UTIL_PCT = 5 % for
    IDLE_WINDOW_S = 15 min (v2.md §3), counted from the last busy heartbeat, or from launch +
    IDLE_GRACE_S - IDLE_WINDOW_S if the GPU was never busy (setup/downloads get 30 min). `watch` runs it
    every 60 s; `reap` also runs at session start, every gate and after every job.
  * Non-yct instances are reported (never terminated) so orphans are visible.
  * A10 is disallowed until the P0 smoke test records peak VRAM < 20 GB (A10_ALLOWED=1).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API = "https://cloud.lambda.ai/api/v1"
LEDGER = Path(__file__).resolve().parent / "gpu_ledger.jsonl"
PREFIX = "yct-"
# File ceiling (human-only, D-030); env vars cannot raise it. The effective cap also needs the owner's SSM value.
BUDGET_USD = float((Path(__file__).resolve().parent / "BUDGET_USD").read_text().strip())


class BudgetUnverified(SystemExit):
    pass


def _ssm_budget() -> float:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from yct.owner_actions import budget_usd
    return budget_usd()


def budget_cap() -> float:
    """min(file ceiling, owner-verified SSM budget). Fails closed: any verification error -> SystemExit."""
    try:
        owner = float(_ssm_budget())
    except Exception as exc:  # noqa: BLE001 - every failure means "unverified" -> refuse
        raise BudgetUnverified(f"budget unverified ({type(exc).__name__}: {exc}); refusing to launch") from exc
    return min(BUDGET_USD, owner)


BUDGET_MAX_HOURS = 4.0
ALERT_FRACTION = 0.8
HEARTBEAT_TIMEOUT_S = 600.0  # v2.md §3: killed after 10 minutes of silence (hard rule, not env-tunable)
IDLE_UTIL_PCT = 5.0          # v2.md §3: idle GPU (< 5 % util) ...
IDLE_WINDOW_S = 900.0        # ... for 15 min is killed
IDLE_GRACE_S = 1800.0        # a never-busy instance is idle-killed 30 min after launch (setup + downloads)
HB_LOG = "~/yct_heartbeat.log"
HB_SSH_KEY = "/root/.ssh/yct_lambda"


def _req(method: str, path: str, body: dict | None = None) -> dict:
    key = os.environ["LAMBDA_API_KEY"]
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={"Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json",
                                        "User-Agent": "yct-gpu-manager/0.1"})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read() or b"{}")


def _ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]


def _append(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def spent_usd() -> float:
    total = 0.0
    for rec in _ledger():
        if rec["event"] == "launch":
            end = next((r["t"] for r in _ledger() if r["event"] == "terminate" and r["id"] == rec["id"]),
                       time.time())
            total += (end - rec["t"]) / 3600 * rec["usd_per_hour"]
    return total


def types() -> dict:
    d = _req("GET", "/instance-types")["data"]
    return {k: {"usd_per_hour": v["instance_type"]["price_cents_per_hour"] / 100,
                "regions": [x["name"] for x in v["regions_with_capacity_available"]]}
            for k, v in d.items() if v["regions_with_capacity_available"]}


def launch(itype: str, name: str, max_hours: float, ssh_key: str | None, region: str | None) -> dict:
    if not name.startswith(PREFIX):
        raise SystemExit(f"name must start with {PREFIX}")
    if max_hours > BUDGET_MAX_HOURS:
        raise SystemExit(f"--max-hours {max_hours} exceeds cap {BUDGET_MAX_HOURS}")
    avail = types()
    if itype not in avail:
        raise SystemExit(f"{itype} has no capacity now; available: {sorted(avail)}")
    if "a10" in itype and "a100" not in itype and os.environ.get("A10_ALLOWED") != "1":
        raise SystemExit("A10 disallowed until P0 smoke test measures peak VRAM < 20 GB")
    price = avail[itype]["usd_per_hour"]
    cap = min(BUDGET_USD, budget_cap())
    if spent_usd() + price * max_hours > cap:
        raise SystemExit(f"budget cap: spent {spent_usd():.2f} + {price*max_hours:.2f} > {cap}")
    if spent_usd() + price * max_hours >= ALERT_FRACTION * cap:
        print(f"WARNING budget >= {ALERT_FRACTION:.0%}: notify human", file=sys.stderr)
    keys = [k["name"] for k in _req("GET", "/ssh-keys")["data"]]
    ssh_key = ssh_key or os.environ.get("LAMBDA_SSH_KEY_NAME") or (keys[0] if keys else None)
    body = {"region_name": region or avail[itype]["regions"][0], "instance_type_name": itype,
            "ssh_key_names": [ssh_key], "name": name, "quantity": 1}
    iid = _req("POST", "/instance-operations/launch", body)["data"]["instance_ids"][0]
    rec = {"event": "launch", "id": iid, "name": name, "type": itype, "usd_per_hour": price,
           "t": time.time(), "deadline": time.time() + max_hours * 3600}
    _append(rec)
    return rec


def terminate(iid: str, reason: str = "manual") -> None:
    inst = _req("GET", f"/instances/{iid}")["data"]
    if not inst.get("name", "").startswith(PREFIX):
        raise SystemExit("refusing to terminate a non-project instance")
    _req("POST", "/instance-operations/terminate", {"instance_ids": [iid]})
    _append({"event": "terminate", "id": iid, "t": time.time(), "reason": reason})


def list_ours() -> list[dict]:
    return [{k: i.get(k) for k in ("id", "name", "status", "ip")}
            for i in _req("GET", "/instances")["data"] if i.get("name", "").startswith(PREFIX)]


def foreign() -> list[dict]:
    """Running instances on the account that are not ours: reported, never touched."""
    return [{k: i.get(k) for k in ("id", "name", "status")}
            for i in _req("GET", "/instances")["data"] if not i.get("name", "").startswith(PREFIX)]


def _live(insts: list[dict]) -> list[dict]:
    return [i for i in insts if i["status"] not in ("terminated", "terminating")]


def parse_box_log(text: str) -> list[tuple[float, float, float | None]]:
    """Lines "<epoch> <gpu_util%> [<mem_used_MiB>]" written by infra/gpu_heartbeat.sh; junk ignored."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        try:
            t, u = float(parts[0]), float(parts[1])
            mem = float(parts[2]) if len(parts) > 2 else None
        except (IndexError, ValueError):
            continue
        out.append((t, u, mem))
    return out


def fetch_box_heartbeat(inst: dict) -> list[tuple[float, float, float | None]]:
    """Tail of the instance's heartbeat log via ssh (directly, or through the pod with YCT_HB_VIA_POD=1)."""
    import subprocess

    ip = inst.get("ip")
    if not ip:
        return []
    ssh = (f"ssh -i {os.environ.get('YCT_HB_SSH_KEY', HB_SSH_KEY)} -o BatchMode=yes -o ConnectTimeout=15 "
           f"-o StrictHostKeyChecking=accept-new ubuntu@{ip} 'tail -n 60 {HB_LOG}'")
    if os.environ.get("YCT_HB_VIA_POD") == "1":
        cmd = [str(Path(__file__).resolve().parent / "pod_exec.sh"), ssh, "120"]
    else:
        cmd = ["bash", "-c", ssh]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return parse_box_log(res.stdout)


def poll_heartbeats(insts: list[dict], fetch=None) -> int:
    """Append each new instance heartbeat line to the ledger; returns the number of new records."""
    fetch = fetch or fetch_box_heartbeat
    led = _ledger()
    n = 0
    for i in insts:
        last = max((r["t"] for r in led if r["event"] == "heartbeat" and r["id"] == i["id"]
                    and r.get("source") == "instance"), default=0.0)
        try:
            lines = fetch(i)
        except Exception as exc:  # noqa: BLE001 - an unreachable box simply produces no heartbeat
            print(f"WARNING heartbeat fetch failed for {i['id']}: {type(exc).__name__}", file=sys.stderr)
            continue
        now = time.time()
        for t, u, mem in lines:
            if last < t <= now + 60:  # never accept heartbeats from the future (clock skew > 1 min)
                _append({"event": "heartbeat", "id": i["id"], "t": t, "gpu_util": u, "mem_mib": mem,
                         "source": "instance"})
                last, n = t, n + 1
    return n


def watch(interval: int = 60, fetch=None) -> None:
    """Poll instance heartbeats into the ledger, then reap; exits when no yct-* instance is alive."""
    while True:
        live = _live(list_ours())
        if live:
            poll_heartbeats(live, fetch)
        killed = reap()
        if killed:
            print(json.dumps({"t": time.time(), "reaped": killed}), flush=True)
        if not _live(list_ours()):
            return
        time.sleep(interval)


def _last_seen(ledger: list[dict]) -> dict[str, float]:
    seen: dict[str, float] = {}
    for r in ledger:
        if r["event"] in ("launch", "heartbeat"):
            seen[r["id"]] = max(seen.get(r["id"], 0.0), r["t"])
    return seen


def _idle(led: list[dict], iid: str, now: float) -> bool:
    """GPU util < IDLE_UTIL_PCT for IDLE_WINDOW_S (from the last busy heartbeat; launch + grace if none)."""
    launch = next((r["t"] for r in led if r["event"] == "launch" and r["id"] == iid), None)
    util = [r for r in led if r["event"] == "heartbeat" and r["id"] == iid and "gpu_util" in r]
    if launch is None or not util:
        return False  # no utilisation data: the heartbeat/deadline rules apply
    busy = [r["t"] for r in util if r["gpu_util"] >= IDLE_UTIL_PCT]
    last_busy = max(busy) if busy else launch + IDLE_GRACE_S - IDLE_WINDOW_S
    return now - last_busy > IDLE_WINDOW_S


def reap() -> list[str]:
    led = _ledger()
    deadlines = {r["id"]: r["deadline"] for r in led if r["event"] == "launch"}
    seen = _last_seen(led)
    killed = []
    for i in _live(list_ours()):
        now = time.time()
        if now > deadlines.get(i["id"], 0):  # unknown instance => past deadline
            reason = "deadline"
        elif now - seen.get(i["id"], 0.0) > HEARTBEAT_TIMEOUT_S:
            reason = "heartbeat"
        elif _idle(led, i["id"], now):
            reason = "idle_gpu"
        else:
            continue
        terminate(i["id"], reason)
        killed.append(i["id"])
    return killed


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("types"); sub.add_parser("list"); sub.add_parser("reap"); sub.add_parser("spent"); sub.add_parser("foreign"); sub.add_parser("watch")
    lp = sub.add_parser("launch")
    lp.add_argument("--type", default="gpu_1x_a100_sxm4"); lp.add_argument("--name", required=True)
    lp.add_argument("--max-hours", type=float, required=True)
    lp.add_argument("--ssh-key"); lp.add_argument("--region")
    tp = sub.add_parser("terminate"); tp.add_argument("--id", required=True)
    a = p.parse_args(argv)
    out = {"types": types, "list": list_ours, "reap": reap, "spent": spent_usd, "foreign": foreign, "watch": watch}.get(a.cmd)
    if out:
        print(json.dumps(out(), indent=1))
    elif a.cmd == "launch":
        print(json.dumps(launch(a.type, a.name, a.max_hours, a.ssh_key, a.region), indent=1))
    elif a.cmd == "terminate":
        terminate(a.id)


if __name__ == "__main__":
    main(sys.argv[1:])
