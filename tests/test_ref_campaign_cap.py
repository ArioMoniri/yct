"""D-071 (k): campaign-cap guard of the P4b reference-clip campaign (T1 of signoff_d071_qa.md).

campaign spend := sum over ledger launch records whose name starts with controls.refclips.ledger_name_prefix
of (terminate t, else now) - launch t, times usd_per_hour. The baseline (line count + sha of the ledger
before session 1) is for reconciliation and proves the ledger is append-only; it is never subtracted."""
import inspect
import json

import pytest

from yct.config import load_config
from yct.tribe_run import ref_campaign as rc

PFX = "yct-p4b-ref"
CFG = load_config()


def _launch(iid, name, t, price=2.0):
    return {"event": "launch", "id": iid, "name": name, "usd_per_hour": price, "t": t, "deadline": t + 6300}


def _term(iid, t):
    return {"event": "terminate", "id": iid, "t": t, "reason": "job_done"}


def _lines(recs):
    return [json.dumps(r) for r in recs]


class Store:
    def __init__(self):
        self.d = {}

    def s3_get_text(self, k):
        return self.d.get(k)

    def s3_put_text(self, k, v):
        self.d[k] = v


PRE = [_launch("a", "yct-p4-t1-dl2", 0.0), _term("a", 3600.0)]          # P4, before the baseline


def test_config_cap_keys():
    r = CFG["controls"]["refclips"]
    assert r["campaign_cap_usd"] == 75 and r["campaign_warn_usd"] == 60 and r["ledger_name_prefix"] == PFX


def test_spend_counts_only_prefixed_launches_and_orphans_to_now():
    recs = PRE + [_launch("b", f"{PFX}-t1-dl2", 0.0), _term("b", 1800.0),
                  _launch("c", "yct-p4ablation-t1-dl2", 0.0), _term("c", 3600.0),     # D-073: not counted
                  _launch("d", f"{PFX}-t5-dl6", 7200.0)]                               # orphan, no terminate
    assert rc.campaign_spend(recs, PFX, now=9000.0) == pytest.approx(1.0 + 1.0)


def test_baseline_written_once(tmp_path):
    s = Store()
    b = rc.make_baseline(_lines(PRE), spent_usd_total=2.0, now=1.0)
    rc.write_baseline(s, b)
    with pytest.raises(SystemExit, match="already"):
        rc.write_baseline(s, b)
    assert json.loads(s.d[rc.BASELINE_KEY])["n_lines"] == 2


def _guard(recs, price=2.0, hours=1.75, ack=False, now=1e5, base_recs=PRE):
    base = rc.make_baseline(_lines(base_recs), spent_usd_total=0.0, now=0.0)
    return rc.guard_launch(CFG, recs, _lines(recs), base, price=price, max_hours=hours, now=now, ack=ack)


def test_launch_at_exactly_the_cap_is_allowed_and_above_is_refused_exit_1():
    # spent 71.50 on ref instances; 71.50 + 2 x 1.75 = 75.00 -> allowed (with the >= $60 acknowledgement)
    recs = PRE + [_launch("b", f"{PFX}-t1-dl2", 0.0, price=71.5), _term("b", 3600.0)]
    assert _guard(recs, ack=True)["campaign_spend_usd"] == pytest.approx(71.5)
    recs2 = PRE + [_launch("b", f"{PFX}-t1-dl2", 0.0, price=71.51), _term("b", 3600.0)]
    with pytest.raises(rc.CampaignCapError) as e:
        _guard(recs2, ack=True)
    assert isinstance(e.value, SystemExit) and e.value.code != 75


def test_ack_required_at_warn_level():
    recs = PRE + [_launch("b", f"{PFX}-t1-dl2", 0.0, price=60.0), _term("b", 3600.0)]
    with pytest.raises(rc.CampaignCapError, match="ack"):
        _guard(recs)
    assert _guard(recs, ack=True)["ack"] is True
    low = PRE + [_launch("b", f"{PFX}-t1-dl2", 0.0, price=59.0), _term("b", 3600.0)]
    assert _guard(low)["ack"] is False


def test_cap_has_no_override_parameter():
    params = set(inspect.signature(rc.guard_launch).parameters)
    assert not params & {"cap", "cap_usd", "campaign_cap_usd", "warn", "warn_usd"}


def test_rewritten_ledger_prefix_is_refused():
    recs = PRE + [_launch("b", f"{PFX}-t1-dl2", 0.0), _term("b", 600.0)]
    tampered = [dict(PRE[0], usd_per_hour=0.5), PRE[1]] + recs[2:]
    with pytest.raises(rc.CampaignCapError, match="baseline"):
        rc.guard_launch(CFG, tampered, _lines(tampered), rc.make_baseline(_lines(PRE), 0.0, 0.0),
                        price=2.0, max_hours=1.0, now=1e5)


def test_ref_instance_before_baseline_is_refused():
    early = PRE + [_launch("z", f"{PFX}-t1-dl2", 0.0), _term("z", 60.0)]
    with pytest.raises(rc.CampaignCapError, match="before the baseline"):
        _guard(early, base_recs=early)
