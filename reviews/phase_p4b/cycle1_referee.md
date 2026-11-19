# P4b design v1 — council cycle 1 — STRICT REFEREE

Reviewer: Referee (hostile journal reviewer). Scope: reviews/phase_p4b/design_v1.md against docs/prompts/v2.md §5 P4b (v2.5 C3, v2.7 P4E), ROADMAP P4/P4b, DECISIONS (D-039, D-040, D-055, D-063 Q4/B2, D-065 d, D-066, D-067 c), config.yaml `controls:`.
Method: read-only (git, grep, pytest). I read the generator src/yct/tribe_run/make_reference_clips.py, the kernel code src/yct/tribe_run/enh002.py, and the ENH-002 *summary* JSON outputs/runs/wave1p2b_20261118T002855Z/enh002_latency.json. That file holds reference-clip ROI courses only; it has no analysis-set data. I opened no prediction array, nothing sealed, no label and nothing in wave2_pool. `pytest tests/test_controls_config.py tests/test_enh002_latency.py` gives 14 passed.

## Verdict: **NO-GO** for building and running the reference-clip GPU job as specified in v1

The job is cheap (about $7), but cost is not the reason for this verdict. Running it fixes the stimuli and shows us their predictions. The STOP criteria have to be frozen before that happens, and v1 has three problems:
- one stimulus spec is physically impossible (B1);
- the face, place and motion kernels cannot separate category or motion from a low-level onset (B2);
- the STOP criteria already contradict reference data we have seen (B3).

If the council accepts this v1 and changes things after the run, that is tuning on the test, and (d) in particular *is* evaluated on these clips (B8). Every blocker below can be fixed in the design alone, with no GPU. A v2 that closes B1–B8 can be a GO in cycle 2. B9–B12 do not block the GPU job, but they block the P4b design entry.

---

## Blocking items — before the reference-clip GPU job

**B1. The motion stimulus cannot exist as specified, and it has no static control.**
- Evidence:
  - make_reference_clips.py builds every clip on `color=c=black`. The "noise bed" is audio only (`_bed` → wav).
  - A "high-contrast grating / random-dot field" whose mean luma equals a black frame (Δ mean luma ≈ 0, ticket test "within 1% of the bed") is impossible: any visible pattern on black raises the mean luma.
  - Even with luma matched, a 1 s pattern appearing is a contrast onset. The MT_plus kernel would then measure "pattern appears", not motion. That is exactly the low-level confound D-063 Q4 removed by dropping V4t and the luminance kernel.
- Required:
  - Show a *static* grating or dot field on a mid-grey background for the whole clip in every motion clip, and also in a matched motion-family control clip.
  - Events are 1 s *drift* epochs, so mean luma and RMS contrast in the crop stay constant by construction.
  - Tests: Δ mean luma *and* Δ RMS contrast in the 256² V-JEPA2 view (292 short-edge resize, v2.md M0) are below 1% across event/non-event frames.
  - The kernel baseline is the static-grating control, not the black ref_control58.

**B2. The face and place kernels are not category-specific, and the body category is missing.**
- Evidence:
  - In ENH-002, a full-frame *white flash* (no face) gave a standardised lag-0–3 response of **FFC 1.25, PH 0.88, MT_plus 0.46, V1_V3 0.06** (enh002_latency.json, `mean_response_lag0_3_by_roi`). FFC is the most flash-responsive ROI in the map.
  - A 1 s cartoon face appearing on black (the ref_face geq also changes the whole background from 16 to 40 luma, and the ellipse is 225/185/155) will pass K1 in FFC from the luminance onset alone. "FFC kernel passes K1" therefore does not show that the pipeline carries a face signal.
  - The same applies to PH and the place drawing.
  - v2.md §5 (d) specifies "face/place/body image flashes". The design has no body family and no DECISIONS entry dropping it.
- Required:
  - Face and place events are a swap from a phase-scrambled version to the intact image, with matched luma, RMS contrast and amplitude spectrum, on a continuous background. Alternatively, add a scrambled family and make K1 use intact − scrambled.
  - Add a body family, or a DECISIONS entry that removes it.
  - Use real, openly licensed images (Q2).

**B3. The STOP criteria contradict existing reference data and are ill-defined.**
- Evidence:
  - (i) §3 K2 says "ENH-002 found 0 for both flash and speech". This is false. The flash (V1_V3) kernel peak lag is **+4 TR on standardised maps and +2 TR on raw**, with per-event lags 2–4 (raw) and 4,4,4,4,4 (standardised). Only speech is 0.
  - (ii) K5 (peak lag differs by ≤ 1 TR between maps) would therefore **already fail** on the ENH-002 flash (4 vs 2).
  - (iii) K2 [−1, +4] puts the flash exactly on the boundary.
  - (iv) "Peak" is undefined. §3 normalises by max|·|. The standardised flash kernel has its max|·| at lag −4 (−1.0), so max|·| would pick lag −4 and K2 fails. Taking max instead behaves differently.
  - (v) The K1 unit is inconsistent. The peak lag is chosen on clips k = 0, 2, 4 and "tested on k = 1, 3", which is 8 events from 2 clips, yet the same sentence says "t across the 20 events". If the test uses 20 events, the selection half leaks in.
  - (vi) The events are not independent. TRIBE is deterministic, the bed is bit-identical, and the clips differ only by a 1 s phase, so across-event variance is structured position and context variance, not noise. p < .001 is then close to automatic for any consistent response, however small. There is no effect-size floor.
  - (vii) K3 baseline: the pre-onset lags −4…−1 contain signal. D-055 says "the response can begin up to 4 TR before the event". The ENH-002 raw flash kernel is 0.61 at −1, and the speech kernel is 0.48 at −2 and 0.79 at −1 (standardised). The SD across near-identical deterministic events can also approach 0, which makes K3 either meaningless or a failure for the wrong reason.
  - (viii) K5 is called "polarity" but checks no sign. K1 does not say which map it gates on.
- Required: one table that fixes, per map:
  - "peak" as the argmax of the signed mean course over lags −1…+4;
  - the unit as the clip (n = 5), with selection and test on disjoint clips, or a clip-clustered test;
  - an effect floor (proposal: standardised peak ≥ 0.2, and ≥ 3 × the SD of the ref_control-matched ROI course over W, measured on the control clip and not on pre-onset lags);
  - K5 as a sign agreement at lags 0–3 on both maps, with lag agreement reported only;
  - the gating map as spatially_standardised (the hypothesis maps), with raw reported.
- Also: run the frozen K1–K5 code on the ENH-002 summary courses we have already seen, and disclose the outcome in the design. This makes the criteria's behaviour on known data explicit *before* the new run, instead of discovering it after.

**B4. Event spacing does not isolate events.**
- Evidence:
  - The spacing is 13 s with a −4…+8 window, but the responses do not end at +8. ENH-002 AUD speech is still −0.34 at +8 (standardised; −0.32 raw), and the raw flash is still 0.19 at +8. Speech bursts last up to 6 s (ENH-002 durations 3.8–5.3 s).
  - The pre-onset window of events 2–4 therefore holds the tail of the previous event, and event 1 does not. That gives baselines that differ by event index.
  - TRIBE's context is bidirectional over the chunk, so there is non-local coupling as well.
  - "Windows never overlap" (§1) is true but irrelevant: the *responses* overlap.
- Required: either
  - an FIR deconvolution (lags −4…+8, boxcar or envelope event regressors, on the control-subtracted course), or
  - ≤ 3 events per clip at ≥ 18 s spacing with more clips (≥ 7 per family, about +$3), plus a first-event-only kernel reported as a check.

**B5. The speech "impulse response" is a 4–6 s burst response.**
- Evidence:
  - v2.md and config `kernel.type: measured_impulse_per_roi` say "response kernel = the measured impulse response".
  - The AUD kernel is averaged over 4–6 s bursts and is then convolved in (a) with a continuous 1 Hz speech envelope, so it smooths twice (ENH-002 AUD kernel ≥ 0.48 from −2 to +3).
  - The visual events are 1 s, so this applies to speech (and to talkface latency).
- Required: estimate the AUD kernel by FIR regression on each burst's own 1 Hz envelope (B4's deconvolution covers this), or use ≤ 1 s speech events (single words or syllables). State the choice in the frozen spec.

**B6. The input path of the reference clips is unspecified (hidden circularity).**
- Evidence:
  - The kernels come from the same pipeline whose output they are used to test. Any constant timing or scaling error in the shared path (segments.csv times, trimming, audio resampling, the BUG-018 clamp) is absorbed into the kernel and becomes invisible to (a)–(c). K2 is the only guard.
  - The opposite risk: if the reference clips *skip* steps the T1 clips go through, the kernel does not transfer to them. Those steps are the P2 normalisation (T1 trim/encode, audio16k normalisation, 640×360 at 30 fps vs the q480 path), the pinned-transcript sha check and `--qc-gate t1`.
  - §2 says "reuse gpu_wave1_p4.py with track ref", but that driver hard-codes `PRED_PREFIX` and tracks t1/t3 (gpu_wave1_p4.py l.692–705, 893), so this is not a reuse.
- Required:
  - The reference clips go through the identical P2 T1 normalisation and run_clip flags as the analysis T1 clips, with a test that compares the normalisation log fields.
  - controls_report states that (a)–(c) test the pipeline's internal consistency (ROI mapping, alignment, regressors), and that they cannot detect a timing error shared by kernel and analysis.

**B7. The ablation runs of the reference clips are missing, and the cache rule is contradicted.**
- Evidence:
  - config `controls.dry_run.n_speech_bursts` says "audio-only, text-only, both".
  - (b)-speech is evaluated on the audio-only run, so it needs an audio-only AUD kernel. The full-model kernel includes the text path. The design derives no audio-only kernel.
  - §4 B1 proposes "a new cache key". D-038 (v2.md P4) says the features are extracted **once** and "every analysis (T1, T3, ablations, M0b) reads from it". Ablations change only `config_update` at prediction time.
- Required:
  - The reference job also writes the audio-only and text-only predictions for all reference clips, from the *same* cache entries (prefixes such as p4b_refclips_v1/{full,audioonly,textonly}/).
  - It runs a Gate-1-style cached-rerun bit-identity check on ≥ 3 reference clips per track.
  - It derives a separate audio-only AUD kernel for (b).

**B8. The criteria must be frozen before the reference outputs exist; (d) is evaluated on these clips.**
- Evidence:
  - §4 says (a)–(d) are "applied to the analysis set". (d) cannot be: it is a localiser on image flashes, so the reference run *is* the (d) test.
  - The ENH-002 dry run ("finalise before the lock") and the (d) test therefore share data. Any change after the dry run is tuning on the test.
  - §8 freezes the K1–K5 results and kernels hash in the design entry *after* the run, but the K-rules and the (d) rule have to be committed *before* it.
- Required: a pre-run DECISIONS entry (or a frozen config block, check_frozen_config) that fixes, before the launch:
  - the stimulus spec;
  - the K1–K5 code and thresholds;
  - the (d) readout and sign rule;
  - what each failure means (Q6);
  - the clip sha256 manifest.

  The post-run design entry only records hashes and results.

## Blocking items — before the P4b design entry (not the GPU job)

**B9. The gating set is inverted.** §4 gates on "T3 52; T1 51 reported", and B1 plans audio-only on T3. v2.md §1 makes T1 the primary analysis ("T3 never replaces the primary analysis", l.142), and (c) must "check the same aggregation the hypotheses use". The controls should gate on T1 (51), with T3 reported. The audio-only run should cover T1 51 (plus T3 if it is reported).

**B10. The negative controls, OOD and reliability mask are absent.**
- v2.md §5 P4b specifies negative-control labels "analysed blind with the full pipeline": upload-date parity (expected null) and aspect ratio (expected detectable). ROADMAP P4 lists "Positive and negative controls".
- The design has none. D-060 reports 9:16 = 0 videos, so aspect ratio may have no variance after normalisation. In that case "expected detectable" cannot be tested, and that needs a DECISIONS entry now, not after a null result.
- OOD has only a spec item (L5), and the reliability mask is missing.

**B11. The low-SD exclusion and the fallback cannot work as written.**
- "P10 of the reference clips" does not say which reference clips. If it means the synthetic event clips (face fraction 0 or 1 in 1 s events, so a large SD), continuous talking-head videos (low face-fraction SD) would mostly be excluded.
- The fallback "≥ 5 reference naturalistic clips" cannot meet p < .001 in a one-sample t: n = 5 needs t(4) > 8.61.
- In ref_talkface58 the face is always present, so face fraction has SD = 0 and (a)-face is undefined there, although §4 says it is used "for (a)/(b) on reference clips".
- Define the percentile reference set as the naturalistic clips, size the fallback at n ≥ 15 (Q3), or amend its inference by a DECISIONS entry.

**B12. Route blocks would expose a sealed variable.** The D-040 discovery route (OPEN/TARGETED) is sealed in data/sealed. Permuting within era × route for a label-free control means an agent reads a sealed, outcome-adjacent variable. That is forbidden (see Q4).

## Non-blocking items

- **N1.** The .tsv timings are uniform splits of the burst (make_reference_clips._words: `step = d/len(words)`), not "exact-time" as §1 claims. Disclose this. The text path receives approximate word onsets.
- **N2.** The espeak SENTENCES are pitch-style ("Our product helps small teams ship software faster…"). They are not a leak, but they are semantically close to the analysis domain. Keep the same five sentences, and either balance sentences across clips or use leave-one-sentence-out as a K4 variant.
- **N3.** The first event at 6 + k s has a window starting at 2 s, inside the encoder warm-up region that v2.md uses to justify W starting at 5. Report the kernels without event 1, or move the base onsets to ≥ 9 s if B4 allows.
- **N4.** ENH-002 event 5 of ref_flash has exact 0.0 values at lags 5–8 (a chunk boundary in the 120 s clip). The new kernel code must fail closed on zero-filled or NaN TRs inside a window instead of averaging them.
- **N5.** K4 (LOCO r ≥ 0.8) carries little evidence with bit-identical beds and a deterministic model. Keep it, but do not cite it as stability evidence.
- **N6.** (b)-face, "FFC > V1_V3 on standardised maps", has low diagnostic value. Spatial standardisation suppresses V1_V3 for full-field changes (ENH-002 flash: V1_V3 0.06 vs FFC 1.25). Add FFC vs PH (face) as a descriptive contrast. (v2.md fixes the gating contrast, so this does not block.)
- **N7.** State the circularity limit in controls_report. The kernels are TRIBE's own responses, so passing (a)–(c) shows the predicted maps carry the expected stimulus signals through *our* pipeline. It is not neural validity, and it does not detect shared-path timing errors (B6).
- **N8.** The cost estimate for B1 (about 4.5 h, $10) assumes re-extraction. From the D-038 cache, audio-only prediction is much cheaper. Re-estimate.
- **N9.** (c) predicts r > 0.3 in a stated direction. Fix one-sided vs two-sided p in the frozen spec.
- **N10.** L1–L4 are sound. In L2, "superseded objects" should list the D-067 c run ids explicitly so the manifest test can check completeness.

---

## Answers to the open questions

**Q1 — (b) audio-only: B1, amended.**
- Run the audio-only track on **T1 51** (gating, B9) plus T3 52 (reported) plus all reference clips (B7).
- Predict from the existing D-038 feature cache via `config_update={"data.features_to_use": ["audio"]}`, with the same cache key and a new prefix pred_audioonly_v1/. Do not re-extract.
- Include the Gate-1 cached-rerun check, and write the ablation spec and estimand label that D-063 requires ("ablations wait for their own spec + GPU test").
- Reject B2: it tests selectivity on synthetic espeak only and changes v2.md. Reject B3: it contradicts v2.5 C3.

**Q2 — (d) stimuli: real images, gating; synthetic drawings descriptive only.**
- Use a public image set with a *verified* open licence (CC0 or CC-BY). fLoc's licence has to be checked in writing; if it is unclear, use a CC0 source.
- Include face, place and body categories, each with a phase-scrambled counterpart, greyscale, with luma, contrast and spectrum matched (SHINE-style). Show them as 1 s flashes in 58 s clips through the T1 path.
- Use no YC-related or founder imagery.
- Use the same real face and place images for the FFC and PH kernel families. This also removes the weak-stimulus risk in B2.
- Record a DECISIONS entry and the image sha256 values **before** the job (B8).

**Q3 — reference naturalistic clips: public non-YC talking-head videos. Never wave-1 rows.**
- Non-primary wave-1 rows are YC applications whose labels sit in the sealed file, and the orchestrator has label exposure (BUG-013, D-063 Q2). Reject them.
- Use openly licensed, non-YC talking-head videos chosen by a rule written down before any of their predictions are read (source, query, licence filter, first-N, hashes). Pass them through identical P2/P3/P4 processing.
- Use n ≥ 15 if they are to serve as the (a) fallback (B11); n ≥ 5 is enough for OOD only.

**Q4 — (c) permutation: unrestricted, which gates; era-only blocks as a sensitivity; route never.**
- Route is a sealed D-040 variable (B12) and must not be read for a label-free control.
- Era is not sealed, so era-blocked permutation can be reported beside the gate.
- Use 10,000 permutations with the seed in config, and fix the direction (N9).

**Q5 — K1–K5: not acceptable as written (B3).**
The ENH-002 flash would already fail K5, the peak is undefined, the baseline overlaps documented pre-onset leakage, and K1 has no effect floor and a pseudo-replicated unit. Replace them with:
- **K1:** signed peak over −1…+4, selected on clips {0, 2, 4}, sign > 0 in every held-out clip {1, 3}, plus the effect floor in B3 (standardised peak ≥ 0.2, and ≥ 3 × control-clip SD);
- **K2:** [−1, +4], kept, with D-055 cited;
- **K3:** SNR against the matched control clip, not pre-onset lags;
- **K4:** reported;
- **K5:** sign agreement on both maps at lags 0–3, with lag agreement reported.

Gate on the standardised maps. Tightening p alone (p < .001) adds nothing for a deterministic model.

**Q6 — motion stimulus: inadequate as written (B1); adequate after the redesign.**
- The redesign is a static mid-grey grating for the whole clip with drift epochs, constant luma and contrast, and the static clip as baseline.
- If the MT_plus K1 still fails, that is a **STOP** (D-063 Q4 made MT_plus gating on purpose, and v2.md says "FAIL on any of them means STOP").
- Demoting the control to "disclosed limitation" after seeing the result is not allowed. If the council wants that route, it has to be written into the pre-run entry (B8) now, together with the rule that a failed motion kernel may not be replaced by a flash kernel.
