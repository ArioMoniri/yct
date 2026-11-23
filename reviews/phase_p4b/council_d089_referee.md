# Council D-089: referee review (draft d089_draft.md, commits bb059b0 and 5cf52d0)

Verdict: **REVISE**. The mechanics are sound: a layered block, the frozen key left untouched, a refusal until frozen, and tests. But the rate the owner agreed to was offered on a number that the draft's own projection contradicts. Inputs used: the v1 STOP record (410 SPK spans only) and the diff. I read no texts, labels or sealed data.

**Rate.** The owner was offered "median ~1.0–1.1 s". The draft's linear projection gives 0.985 s, which is below the 1.0 s floor. My recomputation from the same 410 spans (linear / at 80% slowdown efficiency, the sub-linear case the draft names):
- 140 wpm: median 0.985 s, 44.9% / 36.1% in range, 2 / 1 above 1.5 s.
- 130 wpm: median 1.061 s, 62.0% / 50.7%.
- 120 wpm: median 1.149 s, 72.7% / 64.9%, 19 / 9 above 1.5 s.
- 115 wpm: median 1.199 s, 75.4% / 67.8%. This is the linear argmax of in-range share.

140 wpm is *probably sufficient* for SPK. It needs only about 15%. But it is not centred, and every extra SPK item it burns comes out of the unmeasured BURST and TALKFACE budget. That budget is where a final STOP is most likely. At 140 wpm, SPK uses about 134–166 items; at 120 wpm, about 83–92.
- **Counter-argument for 140:** a smaller SPK/BURST rate mismatch (1.25x against 1.46x at 120). That matters for the Q1 kernel contrast.

**Recommendation.** Take the choice back to the owner with accurate numbers. Offer 140 wpm, or a rate set by a rule stated before any new synthesis. The rule I propose: the lowest 5-wpm step of at least 120 wpm whose projected median at 80% efficiency is at least 1.10 s and whose share above 1.5 s is at most 5%. That gives about 120 wpm. The rule is computed only from the v1 spans and is quoted in DECISIONS. Do not run any calibration synthesis on queue items, because that would be a second post-hoc look.

**Second exhaustion = final STOP:** right in principle, since it stops the forking. Not acceptable as written, though.
- BURST and TALKFACE were never measured, so a STOP there would end the control on an untested key.
- Required: a stated downstream meaning, written before the re-run (the speech control is reported as failed or absent, and which analyses drop).
- Required: a per-family exhaustion record, numbers only.

**Restart at 0, no carry-over:** correct and necessary. The v1 keeps were measured at 175 wpm. At 140 wpm, their spans scale to 1.25–1.875 s, so many would now be over 1.5 s. Keep v1 as evidence only.

**Build condition:** not enough as prose. It should be a mechanical guard:
- (a) `EspeakSynth` must refuse `rate_wpm=None` whenever the spec has `rate_wpm_by_family`. Today a forgotten argument silently falls back to 175.
- (b) The build reads its per-family rates from the frozen selection record (`rate_wpm_by_family`) and asserts that they equal `effective_spec`.
- (c) The build QC re-measures each built SPK span and checks it against the selection span (tolerance stated) and against [1.0, 1.5] s.
- (d) A test for each of (a)–(c) lands before the build ticket.

**Q1:** yes. Disclose the rate mismatch in the SPK/BURST kernel readouts. Add a descriptive-only check that compares SPK and BURST envelopes after time-normalising them by rate, with no inferential use.

## Re-sign-off (d089_v2, commits 470418d and d8d02b0)

Verdict: **REVISE**, one blocking item. Everything else I asked for is closed. The rate is 120 wpm by a stated rule that is recomputed from the sha-pinned v1 spans and pinned in the schema. That is the owner's ruling, and it matches my own rule's answer. An exhaustion in any family is a final STOP, and the control is then reported as failed and its dependent analyses named. The per-family STOP record and guards (a)–(c) are in place. Q1 is disclosed. 28/28 tests pass.
- **Blocking: `spk_span_qc` fails on correct builds.**
  - **Cause:** `select` stores `span_s` rounded to 4 decimals. 0.1 ms is 4.8 samples at 48 kHz, so the rounding error alone is up to 2.4 samples. The ±1-sample tolerance is compared against `round(span_s*sr)`.
  - **Check:** I fed the same 57602-sample utterance back in with its selection span (1.2 s stored). The gate returned `pass=False`.
  - **Effect:** the gate is gating, so a deterministic, correct build can STOP.
  - **Fix:** store the span in samples (`span_n`) in the selection record and compare integers within ±1. A rounded-seconds record cannot support the ±1 tolerance.
  - **Test needed:** add one where the span is not a multiple of 0.1 ms.
- Non-blocking: §7 should say that the rule's form was written after the 120/115 figures were known.
