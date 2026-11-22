"""Fixture helper: the config as it was before the D-085 part-2 freeze (84d741d).

The "refused until frozen" tests keep testing the refusal on a config copy without the part-2 freeze rows;
the frozen state itself is tested in tests/test_d085_part2.py and tests/test_d085p2_council.py."""
import copy

D085P2_SHA = "84d741d3d4a5dc3d4e7045ed5e0e4416e0cdc2c2"


def pre_d085p2(c: dict) -> dict:
    c = copy.deepcopy(c)
    c["frozen"] = [r for r in c["frozen"] if r.get("frozen_at") != D085P2_SHA]
    return c
