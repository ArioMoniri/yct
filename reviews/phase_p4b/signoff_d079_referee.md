# Sign-off on D-079 v3: Strict Referee

Date: 2026-11-21. Read: recheck_d079_referee.md, d079_v3.md, d079_recheck_response.md, `git show 542768b`.
Ran tests d079, d079_recheck, bug036: 71 passed. Did not read sealed data, labels, transcripts or outputs/.

**Verdict: REVISE** (two small blocking items; everything else in v3 is accepted).

## Identity: reject instead of STOP
- Acceptable at the metadata stage. My re-check precondition was a rule stated by name/sha before any
  re-uploaded image is seen. `reject_identity_changed` is fixed in config, schema-locked, applied at every
  rank, and never looks at the image. The ranked list then means "first N admissible snapshot files still
  identical to the snapshot", which is well defined, provided every such row is disclosed.
- The frozen D-071 list is amended, not edited (`extra_reject_reasons`, overlap refused). Accepted.

## Blocking
1. **Byte-stage mismatch is not a re-upload.** In `load()`, snapshot sha1 == Commons sha1 already holds,
   so a differing sha1(bytes) means a bad or stale download, not a changed file. Logging it as
   `identity_changed` turns a transfer defect into a silent reject (download failures are STOPs elsewhere).
   Fix: when metadata sha1s agree and bytes differ, delete the file, re-download once, then STOP. Test it.
2. **The promised disclosure is not implemented.** §A says each `identity_changed` row is reported with
   title, both sha1s and the stage. The row has no stage and no bytes sha1, and `finalise` does not list
   these rows. Fix: log `identity_stage` (metadata) on the row, and have `finalise` write the list (or
   "none") into the report. Test it.

- Not blocking: §B, §C, §D, §E, §F verified in code and tests; at freeze add the `flip_sha256` test.
