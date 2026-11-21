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

## Re-sign-off (2026-11-21; read `git show 2277786`, d079_v3.md §H, d079_signoff_response.md)
- Ran `pytest -q tests/test_refstim_d079_signoff.py tests/test_refstim_d079_recheck.py tests/test_refstim_d079.py`: 63 passed.
- B1: resolved by a different route that I accept. identity_changed now exists only at the metadata stage. Rows carry `identity_stage: "metadata"` and `data_sha1: null`, and the runner adds `sha1`/`commons_sha1`. The byte stage produces no rows: `fetch_verified` re-downloads once, then STOPs and names the title. So there is no unrecorded bytes-stage row left to disclose.
- §A disclosure: `finalise` writes `image_identity_changed_v2.json` (a list per category, or "none"). A row without stage or data sha1 STOPs it. This is tested.
- My non-blocking items are covered as well: the bad cached file is deleted and re-fetched, and a bytes-only mismatch is now a STOP, not a reject, so no report count is needed.
- Non-blocking, still open: `test_byte_identity_mismatch_in_load_becomes_a_reject_row` (recheck) describes the old byte-stage behaviour. Rename it to say the reject comes from load() in general. `ra.check_identity` is still dead code. A fake-detector `run()` smoke test is still missing.
- **Verdict: APPROVE.**
