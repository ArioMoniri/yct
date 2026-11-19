# P4b design v1 — council cycle 1 — Neuroscientist / TRIBE v2 review

Reviewer: Neuroscientist (TRIBE v2). Scope: reviews/phase_p4b/design_v1.md (commit bb3b1c6) against v2.md §5 P4b, docs/tribe_requirements.md, docs/tribe_known_issues.md, ROADMAP P4/P4b, DECISIONS (D-039, D-055, D-062, D-063 Q4/B2, D-065), config `controls:`, src/yct/tribe_run/{enh002,make_reference_clips,latency}.py, src/yct/confounds/core.py, and the ENH-002 reference-clip summary outputs/runs/wave1p2b_20261118T002855Z/enh002_latency.json. That file is a summary of synthetic reference clips only: no analysis-set array, label, sealed file or wave-2 pool was opened. `pytest tests/test_enh002_latency.py tests/test_controls_config.py`: 14 passed.

## Verdict: GO-with-conditions

The architecture is right:
- 58 s single-chunk clips (one Audio and one Video chunk, T = 58);
- control subtraction;
- one GPU type and one revisions set;
- a prefix outside pred_clampv1/;
- kernels derived on CPU with STOP rules frozen in advance.

The stimulus design as written would still produce kernels that are partly artefacts. Two findings settle this. The ENH-002 courses have not returned to baseline by +8 TR. The audio front end z-scores each chunk, so a "bit-identical bed" is not identical in TRIBE's input. The motion and face/place events are also confounded with pattern-onset transients, which TRIBE's FFC, PH and MT+ already respond to strongly. All of these are cheap to fix before the run and expensive to fix after it, and fixing them after seeing kernels would count as tuning. Build and run the reference-clip GPU job once B1–B6 are closed in the T-REF58 / T-KERNEL code and tests, with council sign-off on that diff. A full new design cycle is not needed.

## Blocking items

**B1. Event spacing of 13 s is shorter than TRIBE's measured response support.**
- Evidence (ENH-002, events 20 s apart, enh002_latency.json mean courses, lags −4…+8):
  - AUD to speech, standardised: −0.69, 0.17, 1.51, 2.48, **3.14 (lag 0)**, 3.14, 2.58, 1.79, 0.54, −0.39, −0.81, −0.94, **−1.07 (lag +8, still falling)**.
  - V1–V3 to flash, raw: a plateau of 0.065–0.076 from lag 0 to +6, still 0.015 at +8. Standardised: still 0.07 at +8.
  - The rise starts about 3 TR before onset (D-055: up to 4 TR backward leakage).
  - So the support is at least [−4, +8] and probably wider. The mechanism is V-JEPA2's 4 s look-back per 0.5 s bin (tribe_requirements §2.3), plus a 1 s event, plus the bidirectional transformer over the 100-TR context, plus the 5 s offset.
- With 13 s spacing, event i's +9…+12 tail falls in event i+1's −4…−1 pre-onset lags. Those lags are used by K3 and by the kernel's left flank. Event i+1's backward leakage (from about +9) sits right at the end of event i's window.
- Required: spacing of ≥ 20 s between onsets, the spacing ENH-002 validated. For example, 3 events per clip at base onsets [9, 29, 49] with a per-clip jitter of 0/±1 s:
  - first window start ≥ 4 s, which also keeps clear of the clip-onset transient (tribe_requirements §3 "Context window");
  - last window end ≤ 57;
  - 7 clips per family, giving ≥ 20 events.
- Alternatively, estimate the kernel by FIR least squares with jittered ISIs, support −6…+12 and one intercept per clip, then truncate to −4…+8 (config `kernel.window_tr` is unchanged).
- Add a QC test: the control-subtracted ROI course in event-free spans (≥ +12 after an event) has |mean| ≤ 10% of the kernel peak. Otherwise the kernel's zero is not the baseline.
- Cost: about 37 clips instead of 27, roughly +1 h, under $10 in total.

**B2. Audio per-chunk z-scoring breaks the "identical bed" assumption for every clip with sound.**
- Evidence: tribe_requirements §2.3 says "each chunk is z-scored (`norm_audio: true`)". In ref_control58 the −43 dBFS bed (BED_AMP 0.01) is normalised to unit variance, so w2v-BERT receives loud white noise for all 58 s. In a speech clip the chunk SD is dominated by speech (SPEECH_GAIN 0.8), so the bed reaches the model about 15–20 dB quieter than in the control.
- So speech − control carries a sustained "less noise" signal in A4/A5 outside the bursts. The ENH-002 AUD course shows this: a negative baseline at −4 (raw −0.094, standardised −0.69) and a negative tail (raw −0.18 at +8), i.e. 17–33% of the peak.
- Peak normalisation folds this offset into the kernel as a fake undershoot. It also inflates K3, because the pre-onset lags have a shifted mean.
- Required, choose one and test it:
  - (i) RMS-matched audio: speech replaces the bed at matched local RMS, or the bed is raised (e.g. about −25 dBFS) and the clip is rescaled so that the 58 s waveform SD equals ref_control58 within 1%. Test: chunk SD ratio in [0.99, 1.01] for every clip.
  - (ii) Pre-register a per-clip intercept (FIR option in B1) and report the offset.
- Visual-only families share the control's audio exactly, so B2 does not affect them as long as the AAC encode is bit-identical. Test this too: the extracted wav sha equals the control's.

**B3. The motion stimulus confounds motion with pattern and contrast onset.**
- A drifting grating or dot field that appears from a black frame for 1 s changes spatial contrast from 0 to about 100% and creates a full-pattern onset, even with Δ mean luma ≈ 0.
- ENH-002 shows TRIBE's MT+ already responds to a plain luminance flash (standardised lag 0–3: MT+ 0.46, FFC 1.25, PH 0.88, V1–V3 0.06). The proposed MT+ kernel would therefore be an onset kernel, which is what D-063 Q4 rules out ("not a luminance kernel").
- Required, the classic moving-vs-static MT localiser logic:
  - the same high-contrast pattern (random dots, or a grating inside the central crop) is present and static for the whole clip;
  - events are coherent motion for 1–2 s;
  - the motion family gets its own control, ref_static58 (same pattern, never moving), instead of the black ref_control58.
- Temporal frequency ≤ 4 Hz and speed chosen so the pattern does not alias at V-JEPA2's 16 frames/s sampling (64 frames over 4 s, tribe_requirements §2.3). Encode at low CRF so x264 does not smear dots.
- Tests (with the real P3 code, src/yct/confounds/core.py): `luminance_crop` and `contrast_crop` per TR are constant within 1% across the whole clip; `motion_energy_crop` is ≥ 10× the static level during events and at static level elsewhere. The current test (Δ mean luma within 1%) is necessary but not sufficient.

**B4. Face/place events: luminance onset, unrealistic stimuli, and the missing body category.**
- Line drawings and cartoon faces shown as 1 s flashes on black are, first of all, large luminance and contrast onsets, and TRIBE's FFC and PH respond more to a bare flash than V1–V3 does (B3 evidence). So an FFC kernel or a (d) contrast built this way mostly measures onset transients plus whatever weak category signal V-JEPA2 extracts from a geq ellipse.
- (d) depends on that category signal. The paper's in silico localisers (tribe_requirements §9) used real photographs.
- v2.md §5 P4b (d) also specifies **face/place/body** flashes with readout "minus the other categories". The design drops body without a DECISIONS entry.
- Required for this job, either of:
  - (i) include licensed photographic localiser clips (Q2). Requirements:
    - face/place/body, ≥ 20 distinct exemplars per category, never repeated within a clip;
    - grayscale, with mean luminance and RMS contrast equated (SHINE-style) inside the crop;
    - on a persistent mid-gray background, with its own gray control clip;
    - placed in the model's crop, i.e. the central about 316×316 source px of a 640×360 frame (the short edge goes to 292, then a 256 crop);
    - a per-image licence and sha256 in the clip manifest.
  - (ii) drop ref_face58/ref_place58 from this job and run the localiser in a second small job once the licences are cleared.
- Do not run the line drawings as the (d) stimulus. They may be kept only as a labelled descriptive sensitivity.
- The FFC kernel should come from the same luminance-matched face onsets on the gray background (cf. v2.md "talking face" kernel source; ref_talkface58 stays descriptive).

**B5. The K1–K5 STOP rules must be meaningful and frozen before the run.**
- TRIBE is deterministic and the events are identical copies on an identical bed. Event-to-event variance reflects only position in context.
- So K1's one-sample t across 20 events (p < .001), K3's pre-onset SD, and K4's leave-one-clip-out r ≥ 0.8 will pass almost trivially for any non-zero response, artefactual or not. This is pseudo-replication.
- K2 as an argmax lag fails on plateaus: the ENH-002 standardised flash had all 5 peaks at +4, the exact edge of [−1, +4]. A STOP would then be triggered for a benign reason.
- Required (frozen in the T-KERNEL tests before the GPU job):
  - **K1′ magnitude.** The peak of the control-subtracted ROI course is ≥ 0.25 × that ROI's temporal SD in the naturalistic reference clips (Q3), or, if those are unavailable, ≥ 2× the |mean| of the event-free control-subtracted course (B1 QC). Keep the split-half t as a secondary report.
  - **K2′ timing.** The lag of the first crossing of 50% of the peak on the rising flank lies in [−4, +2], and the mean over readout lags 0–3 is ≥ 0.5 × peak. Report the argmax lag descriptively.
  - **K3′ baseline.** The B1 event-free-span criterion replaces the pre-onset SD.
  - Keep K4 and K5.
  - Add **K6 specificity (report, and STOP only for MT+).** The MT+ motion kernel peak (moving − static) is greater than the MT+ response to the luminance flash family, on the standardised map. Otherwise the motion control is not a motion control.

**B6. Stimulus QC with the real regressor code.**
- Control (a) on reference clips (ENH-002 dry run) and the P10 low-SD rule use the P3 regressors, so the clips must actually move them.
- In particular, `face_area_crop_frac` comes from an OpenCV Haar frontal cascade (confounds/core.py l.14). It may not fire on a geq ellipse with box eyes. If it does not, the (a)-face dry run on ref_talkface58 is void.
- Required T-REF58 test, running yct.confounds on the built clips. Each family moves its intended regressor and no other beyond tolerance:
  - face → face_area_crop_frac > 0 on ≥ 90% of event TRs;
  - motion → motion_energy_crop (B3);
  - speech → speech_envelope;
  - flash → luminance_change.
- Run the speech_envelope (T-ENV) on the exact wav TRIBE ingests.
- Build the clips once, hash them, and ship them to S3 by sha256. The GPU box must consume the hashes rather than rebuild, because bit-identity across ffmpeg, x264 or espeak-ng versions is not guaranteed. Pin and record those versions.

## Non-blocking items

- **N1 Speech kernel event duration.** A 4–6 s burst gives a boxcar-convolved response, not an impulse response. Convolving it again with the speech envelope in (a) double-smooths. Derive the AUD impulse kernel from short speech events (1–1.5 s, 2–3 words, matching the 1 s visual impulses). Keep 4–6 s bursts as a validation: the 1 s kernel ⊗ the burst envelope should predict the burst course (r ≥ 0.8, reported). This directly tests the linear-convolution assumption behind (a). ENH-002's single-TR spike at speech onset (tribe_requirements §10, likely the text pathway) is consistent with word onsets dominating the full-model AUD kernel.
- **N2 Audio-only kernels.** If B1 is chosen for (b), derive the AUD kernel for the audio-only track from audio-only runs of the speech reference clips and their control. The full-model AUD kernel is shaped by Llama word features (N1) and is the wrong kernel for an audio-only prediction.
- **N3 Black frame + near-silent bed is out of distribution for TRIBE.** A mid-gray persistent background (B4) is closer to training video. Keep one family-specific control per background (black flash/speech, gray localiser, static-pattern motion) and say in the design which control each family subtracts.
- **N4 Standardised-map caveat.** A full-field flash raises most vertices. Per-TR spatial z-scoring then turns a global increase into relative patterns: this is the ENH-002 negative V1–V3 pre-onset (−0.35) together with FFC 1.25. Report the raw and standardised flash kernels side by side and do not interpret the standardised V1–V3 kernel shape (it is descriptive anyway).
- **N5 Low-SD P10 rule.** "P10 of the reference clips" must mean the naturalistic reference clips (Q3). Synthetic clips have degenerate regressor SDs (zero outside events), which would make the rule meaningless. Fix the wording in §4(a) and §8.5.
- **N6 Include the ≥ 5 naturalistic reference clips (Q3) in this same GPU job** if they can be curated in time. They are needed for K1′, the P10 rule, the (a) fallback and the OOD check, and running them now avoids another session. If they are not ready, K1′ uses its fallback and they run later.
- **N7 Phase shift.** Integer 1 s phases keep onsets on TR (segment-start) boundaries, which is good for kernel lags. They do not "decorrelate from chunk position" in any meaningful way, because there is one chunk. Use the jitter mainly to break periodicity, which matters for the FIR option.
- **N8 ROIs.** These match config `controls.rois` and D-063 Q4:
  - FFC 104;
  - PH 113;
  - AUD = A4 ∪ A5, 223;
  - V1–V3 1,148 (descriptive);
  - MT+ = MT ∪ MST ∪ FST, 139 (MT 38, MST 45, FST 56).

  The §8.3 freeze should cite these counts and the per-hemisphere counts used by (d)'s "both hemispheres" rule (FFC and PH are only about 50 vertices per hemisphere on fs5, so give per-hemisphere n). Small ROIs are fine for model predictions (no noise) but are sensitive to the medial-wall union. Report `mw_removed_frac` per ROI.
- **N9 Talking face.** The mouth toggles at 4 Hz (sin > 0, 30 fps), which is resolved at 16 frames/s sampling. Keep it as descriptive. ENH-002 talkface − control: FFC 0.25, MT+ 0.23, AUD 0.21, so the mouth motion drives MT+ as much as FFC. Disclose this.
- **N10 Permutation blocks for (c).** The discovery route is sealed (D-040, data/sealed) and outcome-correlated, so it cannot be used before unblinding without breaking the blind. See Q4.

## Answers to Q1–Q6

**Q1 (b) audio-only: B1.**
- v2.5 C3 exists because ENH-002/P0 suggest that speech responses in the full model run substantially through the text pathway. B3 would test the leak it was designed to exclude. B2 tests selectivity only on synthetic speech, which is not the claim.
- Zeroing two of three modalities is in-distribution enough: training dropout was p = 0.3 per modality (tribe_requirements §5). Disclose that it is an inference-time ablation, not the paper's retrained unimodal model.
- Conditions:
  - same stack, GPU and revisions;
  - the gate verifies that the text and video extractors were not called (events/extractor log), and n_words is recorded but unused;
  - the audio-only ref clips are included for N2 kernels;
  - the run covers the track on which (b)-face is evaluated, so both (b) parts use the same video set.

**Q2 (d) localiser stimuli: a public photographic set under a verified open licence, not synthetic line drawings.**
- Neuro reasoning: V-JEPA2 was trained on natural video. TRIBE's own localiser replication used real images, and in TRIBE's feature space the category signal for a geq ellipse or a perspective line drawing will be small next to the onset transient that FFC and PH already show (B3/B4). A failure would then be uninterpretable, and a pass would be suspect.
- Licence: if fLoc (VPNL) has no explicit open licence covering redistribution and derivative clips, do not use it. Open-licence candidates to verify include CC-BY-4.0 face sets (e.g. the Face Research Lab London Set) and CC0 / public-domain scene and body images (e.g. Wikimedia Commons CC0, THINGSplus public-domain images). Any such image set must have no link to YC or the study videos.
- Presentation (B4):
  - face/place/body, ≥ 20 exemplars each, no repeats in a clip;
  - grayscale, luminance- and RMS-contrast-matched in the crop, on a persistent gray background with its own control;
  - 1 s flashes, ≥ 20 s spacing (B1), readout lags 0–3 (config).
- This is a stimulus change and needs a DECISIONS entry before the run. That is a pre-lock, label-free change of exactly the kind v2.md allows.
- Line drawings may be kept only as a descriptive sensitivity.

**Q3 Reference naturalistic clips: non-analysis public talking-head videos with no YC link. Never non-primary wave-1 rows.**
- Wave-1 rows have sealed labels and were found by outcome-dependent routes (D-035/D-040). Their predictions feeding thresholds (P10, K1′, OOD) would be a leakage path, and the orchestrator has label exposure (BUG-013).
- Requirements:
  - ≥ 5 clips (ideally 8–10), open licence, English speech, single speaker mostly frontal (so the Haar detector fires);
  - 58 s trimmed through the same P2 normalisation and pinned WhisperX P2b path;
  - selected by a pre-written rule (e.g. the first N search results meeting the criteria) before any is run;
  - sha256 recorded.
- They also serve as the OOD reference.

**Q4 (c) permutation.** This is mainly Biostat's call. Neuro/firewall view: **never use route blocks for a control**, because route is sealed and outcome-correlated (D-040). Use within-`era_block` permutation, which is label-free (config `era_blocks`, from the YC batch calendar), as the primary method if each block has ≥ 6 videos, and report unrestricted as well. Otherwise use unrestricted only. Fix the choice, n_perm and seed in the design entry.

**Q5 K1–K5 thresholds: not acceptable as written.** They are pseudo-replicated (B5): with deterministic model outputs and identical events, p < .001, SNR ≥ 3 and LOCO r ≥ 0.8 are near-automatic. The argmax-lag window [−1, +4] would STOP on a plateau (ENH-002 flash: +4.0). Replace them with K1′–K3′ and add K6 as in B5, frozen in tests before the run. The split-half peak selection is fine and can stay. K4 and K5 stay.

**Q6 Motion stimulus.**
- As designed (pattern appearing from black, luminance-matched only): not adequate. It yields an onset kernel (B3).
- With the moving-vs-static design: plausibly adequate, and better placed than V1–V3. V-JEPA2 is a video model whose features are strongly motion-sensitive. Known issue #9 (mean-pooled patch tokens) mainly hurts retinotopic or spatial selectivity. A global coherent-motion signal survives mean pooling, so MT ∪ MST ∪ FST is a reasonable target. It is still a model prediction, not cortex.
- If K1′ or K6 fails for MT+, then under v2.md ("FAIL on any = STOP") this is a **STOP**. The motion control cannot be evaluated without a valid kernel. It must not be fixed by re-tuning the stimulus after seeing the result.
- To avoid an ad hoc ruling later, the P4b design entry should pre-register the consequence now, before the run:
  - if a correctly built moving-vs-static stimulus (B3 tests pass) fails K1′ or K6 in MT+, the motion control is demoted to descriptive, with a P9 limitation ("TRIBE's predicted MT+ is not driven by isolated coherent motion");
  - the FFC, AUD and (d) controls still gate;
  - one DECISIONS entry records the event;
  - no stimulus iteration is allowed.
- The council may instead keep it as a hard STOP. Either way it must be decided before the kernels exist.
