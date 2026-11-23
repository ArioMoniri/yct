# Council D-089: neuro review (draft d089_draft.md; commits bb059b0, 5cf52d0)

Read: draft, both diffs, the v1 STOP record (410 SPK `span_s` values and counts only; no texts, labels, sealed data or predictions). **Verdict: REVISE.**

1. **140 wpm is not fit for purpose (blocking, owner question).** It was offered as "median ~1.0–1.1 s". On the same 410 spans the projection gives median 0.985 s (linear) or 0.946 s (80% efficiency), so 45% or 36% in range. My recomputation matches the referee's and the watchdog's figures (130: 1.061 s/62%; 125: 1.103 s/67%; 120: 1.149 s/73%, 19 too long; 115: 1.199 s/75%). 140 wpm sits on the floor, and every extra SPK item it uses comes out of the unmeasured BURST and TALKFACE budget.
2. **Neuro acceptability of a slower rate.** At about 1.4–1.5 syllables per word, 175 wpm is about 4.2–4.4 syl/s, 140 is about 3.4–3.5 and 120 is about 2.9–3.0. All three are inside the range of natural speech: 120 wpm is slow, clear speech, not a distortion. The syllabic envelope stays at the delta/theta boundary, the band cortical speech tracking follows. So I have no neural objection to ~120 wpm for 1.0–1.5 s, 3-word items. The thing that drives the response at this time scale is total duration and energy, and `ranges_s` and the −40 dBFS gate already control those.
3. **Recommend a rule, not a number.** Before any new synthesis, pick the fastest 5-wpm step whose v1-projected median at 80% efficiency is ≥ 1.05 s and ≤ 1.25 s and whose linear too-long share is ≤ 5%. That gives **120 wpm** (median 1.077/1.149 s, 19/410 = 4.6% too long). It matches the watchdog's [1.10, 1.25] s linear rule. Quote the rule and the v1 span sha in DECISIONS. The owner decides between 140 and the rule. Disclose that 140 was offered on a median the projection did not support.
4. **Rate mismatch (Q1).** At 120 wpm SPK is 1.46x slower than BURST/TALKFACE (1.25x at 140). The SPK-vs-BURST contrast is already confounded by duration (1–1.5 s vs 4–6 s), and the mismatch adds a confound in the modulation spectrum. Required: a descriptive-only report of the envelope modulation spectrum (peak syl/s) per family, plus a sentence in the limitations. No inferential use, and no rate-normalised kernel claim.
5. **Second exhaustion = final STOP:** right for SPK, because it stops rate-shopping. For BURST and TALKFACE it is a first-ever measurement, so the owner must confirm explicitly that their exhaustion is also final. The STOP's downstream meaning must be written down before the re-run: the speech control is reported as absent, and the SPK/BURST/TALKFACE readouts drop. Record `queue_used` and exhaustion per family.
6. **Restart at 0, no carry-over:** right. The v1 keeps (1.00–1.26 s at 175) scale to 1.25–1.58 s at 140 and 1.46–1.84 s at 120, and carrying them over would mix rates inside SPK. Add a test that no v1 keep id appears in the D-089 record unless it was re-measured.
7. **Build condition is not enough as prose (blocking).**
   - (a) `EspeakSynth` must refuse `rate_wpm=None` when the spec has `rate_wpm_by_family`. Today it silently falls back to 175.
   - (b) The build reads the rates from the frozen selection record and asserts that they equal `effective_spec`.
   - (c) The manifest records the rate for each clip.
   - (d) Frozen QC re-measures each SPK span and requires it to be in [1.0, 1.5] s and equal to the selection span (±1 sample), otherwise STOP.
   - (e) The guard row pins `rate_wpm_by_family`, `on_exhausted` and `restart_queue_at`.
   - Tests for all of these land before the build ticket.
8. Optional, owner-approved only: before the freeze, check the real `-s` scaling on the pin's non-corpus determinism string at 175/140/120. It adds no corpus data.

Owner questions: (Q1) keep 140 or take the rule rate (120)? (Q2) is a BURST/TALKFACE exhaustion also final, and does it mean the speech control is reported as absent? (Q3) allow the non-corpus scaling check?
