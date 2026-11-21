"""BUG-038 test helper: real refstim log rows always carry the rule that decided them, and the audit
classifies C1 by rule. Fixtures written before BUG-038 gave only (decision, reason) and meant the C1 rule for
licence / personality_rights. D-081 council (biostat nit): the reason -> rule mapping is PINNED here
explicitly (the first rule of the frozen rule_reasons map that uses the reason, C1 first for the C1
reasons) instead of following YAML key order; test_refstim_d081 checks it against the frozen map."""
from __future__ import annotations

PINNED: dict[str, str] = {
    "not_photo": "C0", "licence": "C1", "personality_rights": "C1", "too_small": "C2", "duplicate": "C3",
    "text_or_logo": "C4", "no_face_detected": "F1", "multi_subject": "F1", "face_not_frontal": "F4",
    "face_detected": "B3", "person_present": "P1", "not_english": "N1", "not_single_speaker": "N2",
    "identity_changed": "D1",
}


def rule_for(decision: str, reason: str | None) -> str | None:
    if decision != "reject":
        return None
    return PINNED[reason or ""]
