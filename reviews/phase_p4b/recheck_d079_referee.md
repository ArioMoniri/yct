# Re-check of D-079 v2: Strict Referee

Date: 2026-11-21. Read: council_d078_d079_referee.md (my cycle 1), d079_v2.md, d079_v2_response.md, and
`git show d46d6b5 2370c0e`. I ran the d079, bug036 and d078 tests and the frozen-config guard: 75 passed. I
did not read sealed data, labels, transcripts or any outputs/ predictions.

**Verdict: APPROVE.** No blocking items.

## My cycle-1 items
1. **Audit. Resolved.**
   - `ra.audit_v2` runs on every v2 row before the row is appended. The baseline is every superseded log of
     the category: face gets the face log, body gets both body logs, place gets none (no v1 place log).
   - Exemptions are only `duplicate` and the committed flip list (`bug036_c1_flips.json`, keyed by
     sha256(title)). Its sha matches `flip_sha256` e7ce5c2a…2067. List sizes are 260 / 108 / 3 and
     `adm_to_inadm` is empty, which matches §4.
   - A listed title that was not a v1 C1 reject, or is still C1 in v2, is a STOP. Anything else is a STOP.
   - `prior` is now `superseded_logs` and `exempt_reasons` is in config. Keying by sha256(title) instead of
     the title meets my "listed by title" requirement, and nothing is inferred at run time.
2. **Disclosure. Resolved.** d079_v2.md §0 and §5.2–5.4 and the D-078 note in DECISIONS cover all of it:
   - the trigger (10/568) and the 1.8 % yield came from BUG-036, and the §6 expectation is withdrawn;
   - the outcome-blind principle is stated, and the owner's answer (A) is recorded before any v2 call;
   - `finalise` writes the per-source counts and the source of each body pass.
3. **Revid rule. Resolved.**
   - `evaluate_current_log_both` applies to every category. lastrevid comes in the same request as the
     templates, and a lastrevid that changes during paging is a STOP.
   - Each row logs both revids, the drift flag and the full template list with its sha.
4. **Process. Resolved.**
   - The signoff_d078.md addendum says cycle 1 was not independent and names this council as the
     independent review.
   - The red guard test (598ca0e..e768363) is disclosed in DECISIONS, the addendum and BUGS.
   - D-079 is not in DECISIONS, and `controls.refclips_d079*` has no frozen row.
   - `check_frozen_d079` stops both `run` and `finalise` until the freeze commit.

## Open questions
**(a) Face revid drift (2 files): keep them non-exempt.**
- An exemption would be the only case where an edited page is allowed to change a v1 non-C1 decision
  without an explanation.
- A non-C1 rule (detector, area, OCR, C3) depends on the bytes, not the page text, and identity is checked
  separately. So a correct client should reproduce the decision. If it does not, either a template edit or a
  code defect made the difference, and both need the owner.
- If a drifted title is in the flip list, the flip rule already covers it. If its earlier decision does not
  reproduce, it is a STOP as specified.
- The owner's resolution of such a STOP must be a stated rule, applied to every such title, and disclosed. It
  must not be chosen per image after looking at it.

**(b) File-identity mismatch: STOP, not reject.**
- A pre-stated reject would also be outcome-blind. But a re-upload means the snapshot no longer fixes the
  population, and that is a decision about the frozen D-074 / D-078 snapshot, not about one row. A STOP
  sends it to the owner without changing what the ranked list means.
- The precondition is the same as in (a): the STOP is resolved by a rule stated by name or sha alone, before
  any re-uploaded image is looked at, and any v3 follows §2.8.

## Not blocking
- Freeze commit: also add a test asserting that `flip_sha256` equals the sha of the committed file at HEAD.
  That way a later edit to the file fails both the guard and the runner.
- The flip file was made at 3310383 and the counts at e768363. They reproduce each other, and §4 states
  this. No action is needed.
