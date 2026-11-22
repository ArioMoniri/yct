"""Fixture helper: the config as it was before the D-087 freeze (24bf885).

Freezing controls.refclips_d087 switches ref_campaign.guard_launch to the p4b_ref/v2 cap with the $0.39 NAT
session-0 spend carried (T-DRV-V2), which requires the ledger to hold that spend. The D-071/D-082/D-084
driver fakes start from empty ledgers; they keep testing their own logic on the pre-D-087 config, and the
frozen-D-087 path is tested explicitly (tests/test_d087_v2.py, test_nat_d084, test_gpu_p4b_ref)."""


def pre_d087(c: dict) -> dict:
    c["frozen"] = [r for r in c["frozen"] if not r["key"].startswith("controls.refclips_d087")]
    return c
