"""Campaign-cap guard for the P4b reference-clip campaign (D-071 (k); signoff_d071_qa.md T1).

campaign spend := sum over GPU-ledger launch records whose `name` starts with
config `controls.refclips.ledger_name_prefix` of ((terminate t, else now) - launch t) / 3600 * usd_per_hour
(`lambda_gpu.spent_usd()` semantics, restricted by name prefix). The cap and the acknowledgement level are
read only from the frozen config keys (no override parameter). The baseline (ledger line count + sha256 of
those lines, plus global spend, recorded once before session 1) is used for reconciliation and to prove the
ledger is append-only and that no reference instance predates the campaign; it is never subtracted.
A refusal is a SystemExit with a message (exit 1, a human decision), never exit 75.
"""
from __future__ import annotations

import hashlib
import json

BASELINE_KEY = "entries/campaign_baseline.json"


class CampaignCapError(SystemExit):
    """Exit 1: a human decides (raise the cap only through a DECISIONS entry)."""


def _sha(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def campaign_spend(records: list[dict], prefix: str, now: float) -> float:
    ends = {r["id"]: r["t"] for r in records if r.get("event") == "terminate"}
    total = 0.0
    for r in records:
        if r.get("event") == "launch" and str(r.get("name", "")).startswith(prefix):
            total += max(0.0, ends.get(r["id"], now) - r["t"]) / 3600 * r["usd_per_hour"]
    return total


def make_baseline(ledger_lines: list[str], spent_usd_total: float, now: float) -> dict:
    return {"n_lines": len(ledger_lines), "sha256": _sha(ledger_lines), "spent_usd_total": spent_usd_total,
            "t": now, "decision": "D-071"}


def write_baseline(store, baseline: dict) -> None:
    if store.s3_get_text(BASELINE_KEY) is not None:
        raise CampaignCapError(f"{BASELINE_KEY} already exists (written once before session 1)")
    store.s3_put_text(BASELINE_KEY, json.dumps(baseline, sort_keys=True, indent=1))


def check_baseline(ledger_lines: list[str], baseline: dict, prefix: str) -> None:
    n = int(baseline["n_lines"])
    if len(ledger_lines) < n or _sha(ledger_lines[:n]) != baseline["sha256"]:
        raise CampaignCapError("GPU ledger does not extend the recorded baseline (rewritten or truncated)")
    for line in ledger_lines[:n]:
        r = json.loads(line)
        if r.get("event") == "launch" and str(r.get("name", "")).startswith(prefix):
            raise CampaignCapError(f"a {prefix} instance was launched before the baseline")


def guard_launch(cfg: dict, records: list[dict], ledger_lines: list[str], baseline: dict, *,
                 price: float, max_hours: float, now: float, ack: bool = False) -> dict:
    rc = cfg["controls"]["refclips"]
    prefix = rc["ledger_name_prefix"]
    cap, warn = float(rc["campaign_cap_usd"]), float(rc["campaign_warn_usd"])
    check_baseline(ledger_lines, baseline, prefix)
    spend = campaign_spend(records, prefix, now)
    planned = price * max_hours
    if spend + planned > cap + 1e-9:
        raise CampaignCapError(f"campaign cap: spend {spend:.2f} + planned {planned:.2f} > ${cap:g} "
                               "(D-071 k)")
    if spend >= warn and not ack:
        raise CampaignCapError(f"campaign spend {spend:.2f} >= ${warn:g}: relaunch with --ack-cap-80")
    return {"campaign_spend_usd": spend, "planned_usd": planned, "cap_usd": cap, "ack": bool(ack)}
