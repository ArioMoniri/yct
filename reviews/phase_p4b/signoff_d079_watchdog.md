# Sign-off: D-079 v3, Watchdog (final, 2026-11-21)

Read: recheck_d079_watchdog.md (mine), d079_v3.md, d079_recheck_response.md, `git show 542768b` (config, schema,
refstim, refstim_auto, runner, tests). Not read: data/sealed/*, labels, transcripts, outputs/. `pytest -q` at 542768b: 1047 passed.

**Verdict: APPROVE** (no blocking items)

## The change from my re-check: identity mismatch is a reject, not a STOP
I asked for a STOP so that an external re-upload could not quietly remove a ranked candidate. v3 meets that concern
another way, and I accept it:
- It is stated before any v2 call, it is one fixed rule for every rank, and it is triggered by a sha1 comparison
  made before any filter value exists (the bytes check runs in `load`, before decode). It cannot depend on outcomes.
- It is not silent. Every row is a D1 `identity_changed` reject in the log, and v3 §A commits to listing each one in the v1 report.
- A STOP would leave the owner choosing a next step after the event, which is the ad-hoc fork my N1 warned against.
- The frozen D-071 list is not edited. `extra_reject_reasons` is schema-restricted, the schema refuses overlap, and
  `check_log` takes it only by an explicit argument. Missing sha1 stays a STOP. Audit exemption is correct (different file).

## Re-check items
N1 resolved (v3 §B, `stop_resolution` literals, tested). N2 resolved (§E). N3 resolved (§D, `rs.page_meta_c4`
compares C4 lastrevid to read_revid; one batch retry, then STOP). N4 still open, as intended: it goes in the freeze commit.

## Non-blocking (fix in the freeze commit)
W1. The disclosure promises "both sha1s and the stage". For a bytes-stage mismatch the row logs snapshot and Commons
    sha1 (equal), but not the downloaded sha1 or the stage. Log `data_sha1` and `identity_stage` on D1 rows.
W2. A bytes-stage D1 row keeps the `values` of the metadata rules that already ran (`evaluate_image`'s except path).
    v3 §A says "no detector values". Either clear them or correct the text.
