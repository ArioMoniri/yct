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
  * Cumulative spend cap BUDGET_USD (default 50; raising it is a human-only action, see v2 §2)
    blocks new launches; a warning is emitted at >=80% of the cap.
  * The ledger is tracked in git (infra/gpu_ledger.jsonl) so spend survives fresh checkouts.
  * `reap` terminates yct-* instances past deadline; `watch` runs reap every 60 s.
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
BUDGET_USD = float(os.environ.get("BUDGET_USD", "50"))
BUDGET_MAX_HOURS = 4.0
ALERT_FRACTION = 0.8


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
    if spent_usd() + price * max_hours > BUDGET_USD:
        raise SystemExit(f"budget cap: spent {spent_usd():.2f} + {price*max_hours:.2f} > {BUDGET_USD}")
    if spent_usd() + price * max_hours >= ALERT_FRACTION * BUDGET_USD:
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


def terminate(iid: str) -> None:
    inst = _req("GET", f"/instances/{iid}")["data"]
    if not inst.get("name", "").startswith(PREFIX):
        raise SystemExit("refusing to terminate a non-project instance")
    _req("POST", "/instance-operations/terminate", {"instance_ids": [iid]})
    _append({"event": "terminate", "id": iid, "t": time.time()})


def list_ours() -> list[dict]:
    return [{k: i.get(k) for k in ("id", "name", "status", "ip")}
            for i in _req("GET", "/instances")["data"] if i.get("name", "").startswith(PREFIX)]


def foreign() -> list[dict]:
    """Running instances on the account that are not ours: reported, never touched."""
    return [{k: i.get(k) for k in ("id", "name", "status")}
            for i in _req("GET", "/instances")["data"] if not i.get("name", "").startswith(PREFIX)]


def watch(interval: int = 60) -> None:
    while True:
        killed = reap()
        if killed:
            print(json.dumps({"t": time.time(), "reaped": killed}), flush=True)
        if not [i for i in list_ours() if i["status"] not in ("terminated", "terminating")]:
            return
        time.sleep(interval)


def reap() -> list[str]:
    deadlines = {r["id"]: r["deadline"] for r in _ledger() if r["event"] == "launch"}
    killed = []
    for i in list_ours():
        if i["status"] in ("terminated", "terminating"):
            continue
        if time.time() > deadlines.get(i["id"], 0):  # unknown instance => past deadline
            terminate(i["id"])
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
