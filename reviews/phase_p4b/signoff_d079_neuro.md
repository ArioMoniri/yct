# Sign-off D-079 v3 — Neuroscientist

Date: 2026-11-21. Read: recheck_d079_neuro.md (mine), d079_v3.md, d079_recheck_response.md, `git show 542768b`
(config, schema, refstim.py, refstim_auto.py, runner, tests). Ran tests/test_refstim_d079*.py: 54 passed. I did
not read data/sealed/*, labels, transcripts or outputs/ predictions.

**Verdict: APPROVE.** No blocking items.

## Identity mismatch: pre-stated reject instead of STOP (the one change since my re-check)
Acceptable. I preferred STOP because a reject makes the set depend on the state of Commons on the run day and
a re-upload may be a re-crop of the same photograph. Neither is a validity problem once the rule is stated now:
- C1 is already read at the current revision, so the set already depends on run-day Commons state. One more
  run-day rule, fixed before any v2 call, adds no researcher degree of freedom.
- Rejecting a re-upload is the conservative side. The file at the next rank is judged under all of
  C0–C5/F/B/P and the contact sheet, so the reference set loses no stimulus validity. Admitting it under its
  old rank, the outcome I wanted to avoid, cannot happen.
- My other concern was that a resolution would be made for one title. That is met: the rule is the same at
  every rank, every row is disclosed (title, both sha1s, stage), and any other audit STOP is a defect leading
  to a v3 from rank 1 (§B).
- The code matches the text. Metadata mismatch -> `identity_reject_row` (D1, `identity_changed`, no values).
  Bytes mismatch in `load()` -> `RejectError("D1", identity_changed)`. Missing sha1 -> still a STOP. The reason
  goes in `extra_reject_reasons` and the frozen list is unchanged, and the schema refuses a duplicate. The
  audit exempts these rows.

## Non-blocking
- A bytes-stage reject row is not explicitly labelled with its stage or the sha1 of the bytes. The stage
  follows from `sha1 == commons_sha1`. For the disclosure, log `data_sha1`/`stage`, or derive them in the report.
- As before: record the outcome of the contact sheet in the launch note. No code enforces it.
