# Reference session 1 (p4bref_20261124T001557Z): aborted by a session-container restart (BUG-027 recurrence)

- Launched 2026-11-24 00:16:54Z from 1abf218 (CI green; check-only passed, projection $66.33 <= $75), instance eeef8965… `yct-p4b-ref-t1795479414-dl1795485714` (gpu_1x_a100_sxm4, $1.99/h), launch deadline 02:01:54Z, external terminator trig_01XA8WKRyUju9hhkdswytUUm at 02:36Z.
- The container running the driver restarted at about 01:00Z while MOT_00_ref was at ~272 s. The coordinator found the instance active with no controller and terminated it by hand at 01:02:58Z (ledger `terminate`, reason manual, 8c4bbd1). Orphaned ≤ ~3 min. The list was empty afterwards; the external terminator was then deleted.
- Backstops that would have acted: the box dead-man switch (grace 1200 s after the last driver touch → halt at about 01:20Z; a halted box keeps billing until terminated) and the external terminator (02:36Z). The launch-deadline halt (02:01:54Z) also applies.
- Completed before the restart (S3 `wave1/derived/p4b_ref/v1/manifest.jsonl`, rows written per job): GREY_CTRL_00.ref and SPK_00.ref, both gate_pass true, gate_failures [], D-038 pass (cached rerun bit-identical; fresh gate pass). The `_ref_rerun` lines in the driver log are the by-design D-038 Gate-1 rerun for the first clips (`gate1_rerun=n < GATE1_N`), not failures.
- Lost: MOT_00.ref (in flight; no MOT_00 object in S3). It is still pending and runs from the start in the next session.
- Spend this session ≈ $1.53 (2764 s); campaign total ≈ $3.38.
- U6: only gate fields and shas were read; no prediction content.
