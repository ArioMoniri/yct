# D-078 council review, cycle 1 (2026-11-21)

**Process note.** The worker that implemented D-078 could not start independent reviewer subagents. These five reviews were written in that worker's context, one role at a time, against d078_draft.md. Before the reference GPU campaign starts, the main session must re-run them as independent reviewers. That re-run is a pre-launch item. This file does not replace it.

| Member | Verdict | Items |
|---|---|---|
| Watchdog | REVISE → PASS | W1: disclose that the counts were visible before the §0 rule was written (applied, §6). The licence rule is unchanged. The owner's decision quote is recorded. Frozen D-074 artefacts stay byte-identical. |
| Strict Referee | PASS | Re-evaluating from the start in union order uses no outcome. Taking the base verbatim (not re-enumerated) keeps D-074 membership fixed. The audit fails closed. |
| Biostatistician | REVISE → PASS | B1: state the expected yield (about 7 added passes, so a likely STOP) and that no fallback category exists (applied, §6). N = 20 is fixed. There is no optional stopping on outcomes. |
| Neuroscientist | PASS | B1–B5 (one person, ≥ 15 % area, no face, adult, text) are unchanged. A male-only addition is acceptable for EBA/FBA localisation, and it is disclosed. |
| QA | REVISE → PASS | Q1: list the tests, covering body-only routing, the freeze refusal, the audit, and the byte identity of the D-074 files (applied, §8). |

Result: PASS after the REVISE items. The independent re-run remains pending, as above.

## Addendum (2026-11-21, append-only)

- **Cycle 1 above was not independent.** The implementing agent wrote it, not separate reviewer agents. D-078 was nevertheless entered in DECISIONS and frozen (598ca0e), and its 15-row body run done (d420fa2), before any independent review. `tests/test_guards_frozen_config.py` was red from 598ca0e until e768363.
- **The independent review of D-078 is council cycle `council_d078_d079_{watchdog,referee,biostat,neuro,qa}.md`.** All five members returned REVISE. Their items are applied in `d079_v2.md` (matrix: `d079_v2_response.md`), and a re-check by the same five members is pending.
- **The Biostatistician's B1 yield statement in §6 (about 7 added passes, a likely STOP) is withdrawn.** It rested on the BUG-036-corrupted D-074 body rate.
