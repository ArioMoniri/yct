"""BUG-038 test helper: real refstim log rows always carry the rule that decided them, and the audit now
classifies C1 by rule. Fixtures written before BUG-038 gave only (decision, reason) and meant the C1 rule for
licence / personality_rights; this maps a fixture reason to the rule it stood for, from the frozen
rule_reasons map (C1 first for the C1 reasons)."""
from __future__ import annotations

from yct.config import load_config

_MAP = load_config()["controls"]["refclips_auto"]["rule_reasons"]
_FIRST: dict[str, str] = {"identity_changed": "D1"}
for _rule, _reasons in _MAP.items():
    for _x in (_reasons if isinstance(_reasons, list) else [_reasons]):
        _FIRST.setdefault(_x, _rule)


def rule_for(decision: str, reason: str | None) -> str | None:
    if decision != "reject":
        return None
    return _FIRST.get(reason or "", "C0")
