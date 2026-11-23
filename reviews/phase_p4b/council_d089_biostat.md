# Council D-089: biostat — REVISE (go back to the owner on the rate; the other mechanics are sound)

Inputs: d089_draft.md, bb059b0, 5cf52d0, and the v1 STOP record (ids, spans and counts only; 410 SPK spans, median 0.788 s, p95 1.014 s, max 1.261 s).
Projections scale the v1 spans by (175/w)^a. a=1 is the draft's linear model. a=0.8 and a=0.6 are sub-linear slowdowns, which espeak pauses and phoneme floors make plausible.

| SPK wpm | in [1.0,1.5] of 410, at a=1 / 0.8 / 0.6 | linear median | >1.5 s (linear) | queue items SPK uses to reach 60, at a=1 / 0.6 |
|---|---|---|---|---|
| 140 (draft) | 184 / 145 / 119 (45% / 35% / 29%) | 0.985 s | 2 | 134 / 207 |
| 120 | 298 / 258 / 186 (73% / 63% / 45%) | 1.149 s | 19 (4.6%) | 83 / 132 |
| 115 | 309 / 275 / 218 | 1.199 s | 35 (8.5%) | 80 / 113 |

1. **Is 140 wpm fit for purpose? Only marginally.** The owner was offered "median ~1.0–1.1 s", but the draft's own model puts it at 0.985 s, below the floor. Under sub-linearity the pass rate falls to about 29%.
   SPK would then use up to about half the queue. That leaves less for BURST (15 keeps at 2 sentences per attempt) and TALKFACE, whose pass rates are **unmeasured**, and a second exhaustion is final.
   The binding risk is not SPK filling. It is SPK starving BURST.
2. **Recommendation to the owner, not an override.** Choose the SPK rate by a rule stated before any synthesis and computed from the v1 spans alone: "the slowest 5-wpm step whose linear projection puts ≤5% of spans above 1.5 s".
   That rule gives **120 wpm** (median 1.15 s, centred in the range; 45–73% pass across the three slowdown models; ≤132 queue items).
   The owner should be told, in the AskUserQuestion, that the 140 wpm figure was mis-described. It is post hoc either way, so disclose both the rule and the earlier 140 pick.
3. **A second exhaustion as the final STOP: accept**, on two conditions. The STOP record must report per-family tried/kept/Wilson CI and the queue position. The owner must confirm, as a separate question, that a STOP in BURST or TALKFACE (a family that was never measured) is also final.
4. **Restart at 0 with no carry-over: correct.** Carrying over the 31 v1 keeps at 175 wpm would mix rates within SPK. Restarting keeps the frozen deterministic order, and v1 stays on file as evidence.
5. **The "build takes its rate from d089" condition is not enough as prose.** Four blocking items:
   - (a) The selection record stores `rate_wpm` for each item.
   - (b) A build test fails if the RawSpeech binding reads `speech.rate_wpm` for SPK.
   - (c) Frozen QC re-measures every built SPK span inside [1.0,1.5] and matching its selection span within a stated tolerance.
   - (d) The clip manifest records the rate for each clip.
6. **Schema:** `80 <= SPK < 175` accepts any value. Pin it to the exact rule-derived value at freeze. The draft test file also fixes 184/410; add the rule as a test that recomputes the chosen wpm from the STOP record.
7. **Q1 (rate mismatch):** add a descriptive SPK-vs-BURST check of span and envelope-rate per family, reported and not inferential. Also disclose that a 120 vs 175 wpm gap is larger than 140 vs 175.

## Re-sign-off (v2, 470418d + d8d02b0): REVISE (one blocking item)

Both owner rulings are applied as stated. The rule (spans × 175/w, ≤5% above 1.5 s, step 5) is recomputed from the sha-pinned STOP file and gives 120. The 115/120 boundary is tested, and the schema pins SPK = 120.
The final STOP covers all three families and says what follows downstream (control failed, dependent analyses dropped and named, no amendment). The STOP record carries tried/kept/Wilson, `queue_position` and `queue_used_by_family`.
My earlier 5(a)–(d), 6 and 7 are met (per-item rate, RawSpeech binding test, gating SPK span QC, rate in the manifest, sensitivity disclosure), and restart at 0 is kept. 28/28 D-089 tests pass.
**Blocking (B1):** `select` stores `span_s` rounded to 4 dp (0.1 ms = 4.8 samples at 48 kHz). `spk_span_qc` then compares the built span with `round(span_s*sr)` at ±1 sample.
Rounding alone can put the two up to 2.4 samples apart, so a correct, bit-identical rebuild can fail this gate. Under the final-STOP ruling, that false failure would sink the speech control for good.
Fix: store the span in integer samples (`span_n`) in the selection record and compare at ±1 sample, or set the tolerance to at least 3 samples. Add a test that uses a span which does not land on a 0.1 ms grid (e.g. 1.20003 s).
Non-blocking: the freeze row and `require_d089` whole-block check go in at freeze, as planned.
