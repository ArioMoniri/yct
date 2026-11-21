# Sign-off D-079 v3, Biostatistician (2026-11-21)

Read: recheck_d079_biostat.md, d079_v3.md, d079_recheck_response.md, 542768b (config, schema, refstim,
refstim_auto, runner, tests). Not read: data/sealed/*, labels, transcripts, outputs/. Ran
tests/test_refstim_{d079,d079_recheck,bug036,d078}.py: 87 passed.

**Verdict: APPROVE.** No blocking items.

- **B1 resolved.** All three non-defect STOP classes have a rule fixed before any v2 call, in config
  (`stop_resolution`, Literal-typed in the schema) and tested. Batch-level retry instead of the per-title
  retry I suggested is equivalent: it runs before evaluation and does not depend on filter outcomes.
- **Identity change from STOP to pre-stated reject: acceptable.** I accepted either rule if stated in advance.
  The reject is outcome-blind (a re-upload is not driven by our filters), fixed at every rank, carries no
  detector values (so C3 state is untouched), and is disclosed with both sha1s and stage. The frozen D-071
  list is not edited: `extra_reject_reasons` is schema-checked against duplicates and passed to `check_log`.
  Audit exemption for a v2 `identity_changed` row is correct (different file from the one v1 judged).
  Missing sha1 stays a STOP. This also removes the post-hoc owner choice that motivated B1.
- **B2 resolved.** `dup_ok` exempts `duplicate` only against a non-C1 reason; both cases and the listed-flip
  case are tested.

Non-blocking:
- N1. A bytes-stage mismatch when snapshot == Commons sha1 is a download fault, not a re-upload, yet it is
  logged as `identity_changed`. It is outcome-blind and the disclosed stage shows it; consider naming the
  stage in the row (e.g. `values: {identity_stage: bytes}`) so the report can split the two.
- N2. `ra.check_identity` is now dead code in the runner; remove at freeze or mark superseded.
