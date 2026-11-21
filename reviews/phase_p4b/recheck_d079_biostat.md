# Re-check D-079 v2, Biostatistician (2026-11-21)

Read: council_d078_d079_biostat.md (cycle 1), d079_v2.md, d079_v2_response.md, d46d6b5 + 2370c0e (code, tests,
config, DECISIONS/d078 addenda). Not read: data/sealed/*, labels, transcripts, outputs/, log contents.
Ran tests/test_refstim_{d079,bug036,d078}.py: 65 passed. Snapshot entries all carry sha1 (face 4445, body
568 + 966, place 323), so the identity rule cannot STOP on a missing snapshot sha1.

**Verdict: REVISE** (2 small blocking items, B1–B2). R1–R5 are otherwise resolved.

## Cycle-1 items
- R1 audit: resolved in substance. `ra.audit_v2` vs every v1 log of the category, committed sha-checked flip
  list keyed by sha256(title), `adm_to_inadm` non-empty refused; one test per table case. One gap, B2.
- R2 order / C3: resolved. `preload_v2` reads only the v2 log, refuses out-of-order `ran`, refuses a non-v2
  row; the runner STOPs before the next category when < 20. (Nit: `r.get("log_version", "v2")` lets a row
  with no version through preload; finalise is strict. Make preload strict too. Non-blocking.)
- R3 finality: resolved as text and config (`finality: v2_is_selection`). Gap on non-defect STOPs, B1.
- R4 a/b/c: resolved. Trigger artefact and §6 withdrawal in DECISIONS note and d078 addendum; no new
  expectation; `source_counts` + manifest `source` give the realised per-source mix of the 20 body passes.
- R5: resolved. 14 = truncated vs truncated (shifted batch boundaries); 0 = truncated vs complete. Coherent.
- Advisory revid: resolved by §2.6 (current revision, both revids logged, STOP if lastrevid moves in paging).

## Open questions
(a) Revid-drift files non-exempt: **yes, keep them non-exempt.** Drift is a page edit, unrelated to the
    image bytes (identity rule covers those), and the re-check already read them at the current revision
    with 0 adm→inadm. A non-reproducing decision there is unexpected and should STOP. Condition: B1 and B2.
(b) Identity mismatch, STOP vs reject: **STOP is acceptable** and consistent with the fail-closed design. A
    pre-stated reject would also be outcome-blind (re-uploads are not driven by our filters). The only risk
    with STOP is an owner choice made after seeing partial v2 results. B1 removes that.

## Blocking
B1. **Pre-state the resolution of a non-defect STOP.** Finality allows a v3 only for a code defect, but an
    identity STOP, a drift-caused audit STOP, or a lastrevid-during-paging STOP is not a code defect. As
    written the path after such a STOP is undefined, so it would be decided with v2 outcomes in view.
    State now, before the freeze, one rule for each (suggested: identity mismatch -> the title is recorded
    `identity_changed`, counted as a reject, run resumes at the next rank, disclosed; lastrevid moving
    in paging -> retry that title once, then STOP to the council; any other audit STOP -> treated as a
    defect, BUG entry, v3 from rank 1). Any choice is fine if fixed in advance and tested where it is code.
B2. **Duplicate exemption must not hide a C1 change.** C1 runs before C3, so a v1 `duplicate` means v1
    passed C1. `audit_v2` currently allows v1 `duplicate` vs v2 `licence`/`personality_rights` (silent
    adm→inadm) and v1 unlisted C1 reject vs v2 `duplicate` (silent unlisted flip). Exempt `duplicate` only
    when the other side's reason is not in `c1_reasons`; add the two tests. This matters most for the 2
    drift files in (a).
