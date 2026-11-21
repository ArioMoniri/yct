# D-079 v3 sign-off: QA (final)

Reviewer: QA, 2026-11-21. Read: recheck_d079_qa.md, d079_v3.md, d079_recheck_response.md, `git show 542768b`.
No sealed data, labels, transcripts or outputs/ read. Ran: `pytest -q tests/test_refstim_d079_recheck.py
tests/test_refstim_d079.py tests/test_refstim_bug036.py`: 71 passed.

**Verdict: REVISE, one small blocking item (B1). It can go in the freeze commit.**

## My re-check items
- QA B1 (strict `log_version` in preload): resolved. `r.get("log_version") != "v2"`, no default. It is tested with a real v1-shaped row, and the three committed v1 logs are shown to carry no key.
- STOP messages name the title: done (identity, read_revid, revid move, no URL, decode; batch first/last).

## Identity: reject instead of STOP (change from my open question (b))
- Acceptable. I objected to an unreviewed reason entering the frozen list. Now the reason is pre-stated before any v2 call and kept in `extra_reject_reasons`, so the D-071 list is untouched. The schema refuses an overlap with the frozen list. `finalise` passes the reason to `check_log`, and the audit exempts the row. The rule does not depend on outcomes, so it is not a selection.
- Missing sha1 is still a STOP (`identity_ok`). The metadata-stage check runs before C0. The bytes-stage `RejectError` is raised inside `evaluate_image`'s try, so it logs D1, adds nothing to C3 state and moves to the next rank. All of this is tested.

## Blocking
- **B1. A bytes-stage `identity_changed` row cannot be disclosed as §A promises** ("title, both sha1s and the stage").
  - The row logs `sha1` and `commons_sha1`, which are equal at the bytes stage. It logs no downloaded-bytes sha1 and no stage, and `source_sha256` is written only for a pass.
  - Fix: on a D1 row, log `identity_stage` (`metadata` | `bytes`) and `data_sha1`, so the row records what was actually found.
  - Add a test for each stage.

## Non-blocking
- A bytes-only mismatch while Commons sha1 == snapshot sha1 is more likely a bad download than a re-upload. Treating it as a reject is acceptable because the rule is stated in advance, but the report should note how many such rows there are. Delete the cached file of a D1 row so a later resume cannot reuse it.
- `ra.check_identity` is now dead code in the runner: remove it or mark it superseded. Still open: a fake-detector `run()` smoke test.
