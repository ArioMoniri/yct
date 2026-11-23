# Council watchdog: NAT manifest pre-freeze (D-075 §3, D-084) — APPROVE

Read: nat_manifest_ready.md, nat_manifest.json, nat_auto_log.jsonl, f92490a d00871d 5901ff7 0feabcb, test_nat_manifest_ready.py, D-084. No sealed data, labels, transcripts or predictions read.
- Rule output: sha256 of the committed manifest = 2fbe3421…825e (matches the prepared freeze). 72 tests pass (ready, dryrun, nat0, talk, frozen-config). The manifest equals `natstim.nat_manifest(log, cfg)`; ids are CPU-rank-ordered = the first 15 passes; per session 4/4/7.
- Log append-only: the committed log at 03de683 (192 lines) and 0bac6cb (314) are byte prefixes of HEAD (354). 120 CPU passes = 3 full buffers, each evaluated once (40/40/40): no gap, no early stop.
- Exactly 15 passes in 120, so truncation never applied. The selection does not depend on rank ties or on where sessions start and end.
- Disclosure: covers the post-hoc rule, the owner's "continue" after the STOP, that max_sessions was chosen after seeing 4/40, the per-session N1/N2/N3 counts, the Wilson CI, spend, the multi-session/pod origin and the BUG-047 non-launch. Adequate.
- BUG-047: tests came first (f92490a before d00871d). The price lookup is the first preflight step, so a missing type gives 75/no_capacity before any launch, log write or baseline. `NoCapacityError` is not a SystemExit, so the refusal handler cannot swallow it. The older launchers return 75. Correct.
- Freeze plan (A: set the sha; B: frozen row + guard test row) follows the image_manifest precedent. Nothing blocks it.

Non-blocking:
1. D-084's v1 disclosure list requires the CPU rank range of the selected clips. That range is missing from §3. 0-based ranks are 12–115 of 120 CPU passes; add them to the record or to the v1 report.
2. In commit B, keep `test_manifest_sha_is_the_reviewed_one` (its `in (None, sha)` check). After commit A, tighten it to `== sha`.
3. Freeze only after every member who asked for revisions has re-signed (the D-084 note).
