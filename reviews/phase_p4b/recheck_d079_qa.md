# D-079 v2 re-check: QA (cycle 2)

Reviewer: QA, 2026-11-21. Read: d079_v2.md, d079_v2_response.md, `git show d46d6b5 2370c0e`, my cycle-1 review,
the v1 logs and the flip file. I did not read sealed data, labels, transcripts or outputs/.
Ran: `pytest -q tests/test_refstim_d079.py tests/test_refstim_bug036.py tests/test_refstim_d078.py` (65 passed);
`tests/test_guards_frozen_config.py` (10 passed).

**Verdict: REVISE, one small blocking item (B1).** Everything else from cycle 1 is resolved.

## Cycle-1 items
1. Audit baseline and exemptions: resolved. `ra.audit_v2` compares against every v1 log of the category, keyed
   by sha256(title). It exempts only `duplicate` and the committed, sha-checked flip list. Each case in the §3
   table has a test. D-078 §3/§5 are amended explicitly.
2. Routing: mostly resolved. `image_log_v2` and `check_d079_routing` work, and so do the schema checks (`_v2.jsonl`
   suffix, no overlap with the superseded logs). The routing refusals and unfrozen/unset-sha STOPs are tested.
   The source test shows `run()` and `finalise()` never use `image_log_rel`, and `finalise` is strict on
   `log_version`. One gap remains (B1).
3. Fail-closed tests: resolved. Tests now cover missing/invalid pages, unrequested pages, normalized titles,
   a continue that never ends, Personality rights arriving only in a continuation, lastrevid changing during
   paging, and `page_meta_c4` with a truncated extmetadata reply.
4. Offline C1 audit: resolved. Each row now logs `templates`, `templates_sha256`, `snapshot_revid`, `read_revid`,
   `revid_drift` and `commons_sha1`. `revid` is the read revid. A missing `read_revid` is a STOP.

## Blocking
- **B1. `preload_v2` accepts a row with no `log_version` key** (`refstim_auto.py:532`,
  `r.get("log_version", "v2")`). Real v1 rows carry no `log_version`, so a v1 row copied into a v2 log is
  preloaded into C3 state and resumed from. Only `finalise` would catch it, after the whole run. The test uses
  `"log_version": "v1"`, a value no real row has.
  - Fix: use `r.get("log_version") != "v2"`.
  - Add a test with a real v1-shaped row (no key).
  - This can go in the freeze commit.

## Open questions
- **(a) Revid drift: keep it non-exempt. It reproduces.** The flip file's `revid_changed` holds 2 face keys.
  - 21b3c18c…: a v1 `licence` reject that is in `inadm_to_adm`, so any non-C1 v2 outcome is allowed.
  - 339c0793…: a v1 `licence` reject that is not in the list, and the re-check read it at the drifted
    revision as still inadmissible. Its earlier C1 decision reproduces at the drifted revision.
  - So no exemption is needed. The STOP still guards against edits made after 3310383, and it is the
    conservative reading.
  - Caveat: the re-check only checks admissibility. A licence → personality_rights reason change would still
    STOP, which is acceptable.
- **(b) File-identity mismatch: STOP, not reject.** A reject would put a new, unreviewed reason into the frozen
  `reject_reasons` and would judge a different file at the old rank without anyone seeing it.
  - The check runs before any rule and again on the downloaded bytes. Both points and the four failure shapes
    are tested.
  - Non-blocking: make the STOP message include the title (today it gives only the sha1s).

## Non-blocking
- Run-level coverage: helper tests plus the source-routing test are enough for this change. A fake-detector
  `run()` smoke test (2 categories, tmp ROOT) would still be worth adding later.
- The recommended items from cycle 1 still apply: stop on a repeated continue token, and an opt-in live probe.
