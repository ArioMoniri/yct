# Council D-089: watchdog review (draft d089_draft.md; commits bb059b0, 5cf52d0)

Read: draft, both diffs, tests, the v1 STOP record (only the 410 SPK span_s values and counts; no texts). **Verdict: REVISE.**
The code is sound: the frozen key is untouched, `effective_spec` layers on top, the rate reaches `-s`, and selection is refused until the freeze.

1. **140 wpm does not do the job (blocking).** The owner was told the median would be "~1.0–1.1 s". The draft's own projection is 0.985 s, below the 1.0 s floor, so a 45% pass rate is a coin flip with no margin. I reran the same linear scaling on the v1 spans: 135→55%, 130→62%, 125→67% (median 1.10 s), 120→73% (1.15 s, 19 too long), 115→75% (1.20 s, the maximum), 110→72% (1.25 s, the range midpoint).
   If espeak slows down by only ~90% of linear, 140 wpm behaves like ~150 wpm (~33% pass). 120 wpm behaves like ~124 wpm (~68%). 140 is the most fragile choice that still projects a pass.
2. **Recommend a rule, not a number.** Take the slowest-to-fastest rate whose linear-projected SPK median falls in [1.10, 1.25] s and whose projected too-long share is ≤ 5%. On the v1 spans that gives **120 wpm** (median 1.15 s, 4.6% too long), stated before anyone synthesises.
   Optional and owner-approved only: measure the real `-s` scaling on the pin's non-corpus determinism string at 175/140/120 before the freeze. That adds no corpus data.
   Whichever rate is used, it is still post hoc. Disclose the rule, the v1 spans it was taken from, and the fact that the owner chose 140 on a description that the projection did not support.
3. **A second exhaustion as a final STOP is right for SPK** (no rate-shopping). **It is not yet right for BURST/TALKFACE.** Those families were never measured, and under this draft they get one shot with no evidence. At 140 wpm, SPK uses ~134 items and leaves ~276. At 120 wpm it uses ~82 and leaves ~328.
   The owner must confirm explicitly that a BURST/TALKFACE exhaustion is also final (blocking: an owner question). The draft's Q2 covers SPK only.
4. **Restarting at 0 with no carry-over is right.** Carrying over would mix 175 and 140 wpm clips inside SPK, and the v1 keeps (1.00–1.26 s) can exceed 1.5 s at the new rate. Add a test that the D-089 record contains no v1-keep ids unless they were re-measured under the new rate. Also record `queue_used` per family.
5. **The build condition is not enough as prose (blocking).** It needs code guards:
   (a) the build reads `rate_wpm_by_family` from the frozen selection record and asserts that it equals `effective_spec`;
   (b) the build calls the synth with `rate_wpm=` and has a test that fails if the SPK build ever sends `-s 175`;
   (c) the clip manifest records the rate for each clip;
   (d) frozen QC re-measures each built SPK span at −40 dBFS and requires it to be in [1.0, 1.5] s and equal to the selection span (±1 sample). Otherwise STOP.
6. Minor: `require_d089` only gates when the block exists. After the freeze, the guard row in `tests/test_guards_frozen_config.py` must pin `rate_wpm_by_family`, `on_exhausted` and `restart_queue_at`. The schema allows SPK at 80–174, so the freeze is the only thing that locks the value.

Owner questions:
- Q1: keep 140, or change to the stated-rule rate (120)?
- Q2: is an exhaustion in BURST/TALKFACE also final?
- Q3: allow the non-corpus scaling check before the freeze?
