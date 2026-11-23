"""Shared pre-launch checks for the P4b GPU drivers (D-071 (k); council refcampaign U5).

One implementation, imported (not copied) by scripts/gpu_p4b_nat0.py, scripts/gpu_p4b_talk.py (through
gpu_p4b_nat0) and scripts/gpu_p4b_ref.py:
  * check_commit: launch only from the pushed, CI-green commit (HEAD == --ci-green-sha, HEAD on the remote);
  * reconcile / check_reconcile: the L4 ledger reconciliation record (every ledger launch has a terminate
    record, no live yct-* instance; spend figures against the ledger line count + sha), committed before a
    launch and checked against the ledger at launch time.
A refusal is `Refused` (exit 1 before any launch: a human decides), never exit 75.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from yct.tribe_run import ref_campaign as rcmp


class Refused(SystemExit):
    """Exit 1 before any launch: a human decides."""


def check_commit(head: str, ci_green_sha: str | None, pushed: bool) -> None:
    if not ci_green_sha or head != ci_green_sha:
        raise Refused(f"HEAD {head[:12]} is not the CI-green commit {str(ci_green_sha)[:12]} (D-071 k)")
    if not pushed:
        raise Refused(f"HEAD {head[:12]} is not on the remote branch (launch only from a pushed commit)")


def ledger_lines(lg) -> list[str]:
    path = Path(lg.LEDGER)
    return [x for x in (path.read_text().splitlines() if path.exists() else []) if x.strip()]


def lines_sha(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def reconcile(lg, cfg: dict, clock) -> dict:
    """L4: every ledger launch has a terminate record, no yct-* instance is alive on the Lambda API, and the
    spend figures (global, budget cap, campaign by prefix) are recorded against the ledger's line count and
    sha. Refuses (exit 1) on an open launch or a live instance. The D-071 (k) $ tolerance needs an external
    invoice, which no API in this project exposes (disclosed in t_nat0_ready.md)."""
    lines = ledger_lines(lg)
    recs = [json.loads(x) for x in lines]
    ended = {r["id"] for r in recs if r.get("event") == "terminate"}
    open_ = [r["id"] for r in recs if r.get("event") == "launch" and r["id"] not in ended]
    live = [i.get("id") for i in lg._live(lg.list_ours())]
    if open_ or live:
        raise Refused(f"ledger not reconciled: open launches {open_}, live yct-* instances {live}")
    prefix = cfg["controls"]["refclips"]["ledger_name_prefix"]
    return {"ledger_n_lines": len(lines), "ledger_sha256": lines_sha(lines), "open_launches": open_,
            "live": live, "spent_usd": round(lg.spent_usd(), 4), "budget_cap_usd": lg.budget_cap(),
            "campaign_spend_usd": round(rcmp.campaign_spend(recs, prefix, clock()), 4), "t": clock()}


def check_reconcile(rec: dict | None, lg) -> None:
    if rec is None:
        raise Refused("no L4 ledger reconciliation record: run --reconcile-only and commit it")
    lines = ledger_lines(lg)
    if rec.get("ledger_n_lines") != len(lines) or rec.get("ledger_sha256") != lines_sha(lines):
        raise Refused(f"the ledger reconciliation record is stale ({rec.get('ledger_n_lines')} lines vs "
                      f"{len(lines)} now): re-run --reconcile-only")
    if rec.get("open_launches") or rec.get("live"):
        raise Refused("the ledger reconciliation record shows open launches or live instances")
