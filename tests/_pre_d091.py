"""Fixture helper: the config as it was before D-091 (the block and its freeze rows removed).

With controls.refclips_d091 present, the reference driver's pre-launch record must hold the main-campaign
D-071 (k) projection (spend + session + remaining $61 plan <= $75, council refcampaign U4), and an unfrozen
block refuses the launch (fail closed). The D-071 cap and warn-level fakes in tests/test_gpu_p4b_ref.py fake
$61-$74 of spend to test guard_launch itself; they keep testing that logic on the pre-D-091 config. The D-091
projection and the fail-closed refusal are tested explicitly (tests/test_ref_session1.py)."""


def pre_d091(c: dict) -> dict:
    c["frozen"] = [r for r in c["frozen"] if not r["key"].startswith("controls.refclips_d091")]
    c["controls"].pop("refclips_d091", None)
    return c
