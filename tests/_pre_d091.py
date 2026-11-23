"""Fixture helper: the config as it was before the D-091 freeze.

Freezing controls.refclips_d091 switches the reference driver's pre-launch record to the main-campaign
D-071 (k) projection (spend + session + remaining $61 plan <= $75, council refcampaign U4). The D-071 cap and
warn-level fakes in tests/test_gpu_p4b_ref.py fake $61-$74 of spend to test guard_launch itself; they keep
testing that logic on the pre-D-091 config, and the frozen-D-091 projection is tested explicitly
(tests/test_ref_session1.py)."""


def pre_d091(c: dict) -> dict:
    c["frozen"] = [r for r in c["frozen"] if not r["key"].startswith("controls.refclips_d091")]
    return c
