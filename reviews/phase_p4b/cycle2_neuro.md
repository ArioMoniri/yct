# P4b design v2 — council cycle 2 — Neuroscientist / TRIBE v2 review

Reviewer: Neuroscientist (TRIBE v2). Scope:
- reviews/phase_p4b/design_v2.md, including its closing "Owner decisions" section;
- reviews/phase_p4b/d071_draft.md;
- my cycle-1 review, reviews/phase_p4b/cycle1_neuro.md.

I checked them against config.yaml `controls:` and `confounds:`, src/yct/confounds/core.py (Haar face detection at 2 Hz, motion energy at 10 fps, contrast inside the 256 crop) and the DECISIONS.md D-07x ids.

I opened no label, sealed file, wave-2 pool row or prediction array.

`pytest tests/test_controls_config.py tests/test_enh002_latency.py tests/test_guards_frozen_config.py`: 24 passed.

The owner decisions are binding inputs here: the $75 cap, the Wikimedia CC0/CC-BY photographs and the MT+ pre-registered demotion. I review only whether they are specified well enough to freeze.

## Verdict

1. **Commit D-071 as written: NO-GO. It becomes GO once the text amendments B7–B9 below (and the B5 residual) are made.**
   - Every amendment is a label-free text and config change made before any reference output exists.
   - None needs a new design cycle. The council can sign off on the amended D-071 diff alone.
   - As written, D-071 contradicts itself on Q6, cites a decision id that is already taken, and freezes a motion spec that cannot be built.
   - It also leaves two owner decisions open to interpretation after results exist: the demotion scope and the redesign-cap loophole, and the image candidate pool.
2. **Build the tickets: GO, once the amended D-071 is committed.**
   **Launch the reference-clip GPU job once the launch-blocking (G) tickets close with green CI: GO-with-conditions.** Green CI is necessary but not sufficient. Before session 1, the council (or I alone) must check four artefacts, in a one-pass check rather than a design cycle:
   - (i) the frozen T-LIC image manifest, including its rejection log (B9);
   - (ii) the T-REF58 stimulus-QC table from the built clips, plus a contact sheet of one frame per event per family;
   - (iii) the result of the known-data K-run on the ENH-002 summaries (§3.1 promised it "in the cycle-2 packet", and it is not there yet);
   - (iv) the job order under the cap (N16).

## Cycle-1 items

| item | status | evidence |
|---|---|---|
| **B1** spacing ≥ 20 s | **CLOSED** | §1 / D-071(a): onsets [9, 29, 49] + s, with s ∈ {0, −1}, giving 20 s spacing. First window ≥ 4 s, last window end 57 ≤ T−1, checked against each clip's segments.csv. The QC I asked for is K3′, with spans of ≥ +12 TR after an event and ≥ 5 TR before the next. The FIR alternative was not taken, which is acceptable. The exact span definition is N12. |
| **B2** audio z-scoring | **CLOSED** (spec); verified by tests in T-REF58 | The bed is at −23 LUFS, so P2 is a no-op (with a gain ≤ 0.1 dB test). Speech replaces the bed at matched local RMS, chunk SD is within ±1%, and the wav sha of visual-only clips equals the control's. K3′ also catches any residual offset. The contrast is now speech vs. equal-RMS noise, which is a standard auditory localiser contrast. |
| **B3** motion vs. onset | **CLOSED** (one spec defect, B7c) | The pattern is static for the whole clip and drifts for 1 s. MOT-STAT twins are the control. Temporal frequency ≤ 4 Hz is below the 8 Hz Nyquist of V-JEPA2's 16 frames/s and the 5 Hz Nyquist of the 10 fps confounds sampling. Low CRF. §1.5 tests that luminance_crop and contrast_crop are constant within 1% and that motion_energy_crop is ≥ 10× static. Defect: "10 directions" (B7c). Dot parameters are N20. |
| **B4** face/place/body stimuli | **PARTIAL** | The design closes it: photographs on grey; intact vs. phase-scrambled twin with a scramble→scramble swap in the control; SHINE matching; body is included; ≥ 20 exemplars per category; images in the central crop; licence and sha manifest; line drawings dropped. The owner's Wikimedia selection rule is not yet reproducible or category-valid (B9). |
| **B5** K rules meaningful and frozen | **PARTIAL** | The distinct-exemplar design (every event a new exemplar, unit = clip) removes most of my pseudo-replication objection: K1 and K3 now measure consistency across exemplars, and this is disclosed. K1′, K3′, K4a/b and K6 were adopted. **Residual:** v2 took the union, so K2 still requires the signed argmax to lie in [−1, +4]. That is exactly the plateau failure I flagged. §3.1 itself expects the ENH-002 flash to fail K2. For FFC and AUD, which are hard STOPs, a benign plateau peaking at +5 would STOP the campaign and use up the single redesign. **Fix required:** replace the argmax clause with "max over lags [−1, +4] ≥ 0.9 × the global signed max over −4…+8", keeping the 50%-crossing and lags 0–3 ≥ 0.5·peak clauses. The alternative is that the council records explicitly in D-071 that it accepts this STOP risk. K6 still needs a like-for-like definition (B8d). |
| **B6** stimulus QC with real regressor code | **CLOSED** | §1.5 runs yct.confounds and T-ENV on the built clips. The clips are built once with a pinned toolchain and bit-exact flags. The manifest sha is frozen. The GPU box only stages and never rebuilds. One linked point: the Haar cascade (core.py, min_size_frac 0.08 of 292 px, 2 Hz) must fire on the chosen face photos. B9 moves that check into curation, so it cannot fail only at QC time. |

Cycle-1 N items:
- Adopted: N1 (short utterances, BURST validation), N2 (audio-only AUD kernel), N3 (grey background, family-specific controls), N4 (K5 and raw/std side by side), N5 (P10 over NAT), N6 (15 NAT clips in the same job), N7, N9 and N10/Q4.
- **N8 is only partly adopted.** §4(d) says the per-hemisphere vertex counts "are listed in D-071", but D-071 does not list them, and §9 defers them to the post-run entry (see B7d).

## New blocking items (text and config, all before the build)

**B7. Internal consistency of D-071. It is frozen, so it must not contradict itself.**
- (a) D-071(j) says "Q6 = hard STOP", while (g) carries the owner's demotion. Rewrite (j) as "Q6 = pre-registered demotion for MT_plus only (g); FFC and AUD hard STOP".
- (b) D-071(j) Q1 and design §4(b) name the analysis-set audio-only ablation entry "D-072". **D-072 is already committed** (Curator round 4, DECISIONS.md l.152). Refer to it as "a later ablation entry (id assigned at commit)", or reserve the next free id.
- (c) MOT: "directions 0/45/…/315° (10 distinct)" gives only 8 directions. "Every event … a distinct exemplar" needs 30 distinct MOT events: 10 clips × 3. Specify the exemplar as a (pattern, direction) pair. For example, clip i holds pattern i, and its 3 events take 3 of the 8 directions by a fixed rotation, so all 30 pairs are distinct and each direction appears 3–4 times, balanced across the even and odd halves.
- (d) Put the per-hemisphere ROI vertex counts and `mw_removed_frac` for FFC, PH, AUD and MT_plus into D-071 (and config). They are atlas facts, label-free, and the (d) "each hemisphere" rule depends on them. FFC and PH are only about 50 vertices per hemisphere on fs5.
- (e) Design_v2 §1.2 (fLoc/London/THINGSplus, "sorted file name"), §2 ($50), §3.4 and §10 ("no demotion") are superseded. State in D-071 that D-071 is the only frozen text and that design_v2 body text conflicting with the owner decisions is void.

**B8. The MT_plus demotion rule must be closed against post-hoc use.** The owner's rule is sound and is what I proposed. As drafted in D-071(g) it leaves five gaps:
- (a) **Scope.** Demotion applies only to a valid **FAIL** of K1–K6. A **STOP_INVALID** in MOT, MOT-STAT or FLASH (NaN, zero SD, a truncated window, a zero-filled TR, a missing job) indicates a pipeline fault, so it is a P4b STOP and not a demotion. An incomplete MOT family under the $75 cap is likewise STOP_INVALID, not a demotion. The current "any other gating FAIL or STOP_INVALID" is ambiguous on this point.
- (b) **Precondition.** Demotion is allowed only if the MOT and MOT-STAT §1.5 QC passed on the uploaded clips (a correctly built moving-vs-static stimulus). This already holds because QC gates upload; state it as part of the rule.
- (c) **Redesign cap.** The demotion is final for this study. If a `p4b_ref/v2` redesign is triggered by an FFC or AUD failure, the MOT and MOT-STAT clips are carried over unchanged, by manifest sha, or not re-run at all. A demoted MT_plus cannot be re-gated through v2. Without this clause the single redesign is a route to iterating the motion stimulus after seeing it fail, which is what the owner rule forbids.
- (d) **K6 definition, like for like.** Use MT_plus, standardised map, unnormalised courses: the mean over lags 0–3 of (MOT − MOT-STAT) > the mean over lags 0–3 of (FLASH − GREY-CTRL). As written, the MOT side is the "kernel peak". The kernel is normalised to 1, and a peak compared with a mean is biased toward a pass. FLASH is descriptive, but it becomes an input to the MT_plus decision, so it must be complete and valid (a).
- (e) **What is reported and what stays.**
  - On demotion, MT_plus × motion_energy_crop (a) is still computed with the failed kernel and reported only as descriptive, labelled with the failing rule(s).
  - motion_energy_crop is **still partialled** out of FFC and AUD (a). Those use the target ROI's kernel (design §4(a)), so they are unaffected.
  - (b), (c) and (d) contain no motion arm and are unchanged.
  - Freeze the limitation sentence now: "TRIBE v2's predicted MT+ (MT ∪ MST ∪ FST) did not show a valid impulse response to isolated coherent motion (rule Kx); the motion control is descriptive."

**B9. The Wikimedia selection rule is not yet reproducible or category-valid.** "The first 20 per category by sha256 of the file title that pass the filters" is a good mechanical tie-breaker, but it needs a fixed candidate pool and operational filters. Otherwise the selection can drift or be steered.
- (a) **Pinned pool.** For each category, freeze in D-071:
  - the exact Commons categories (with recursion depth) or search query;
  - the licence filter (CC0, PD, CC-BY-x.x only; no -SA and no -ND);
  - the query date.

  The curator snapshots the full candidate title list and commits its sha256 **before** any filtering. Ordering is sha256(title) over that snapshot.
- (b) **Audit trail.** Candidates are inspected strictly in order. Each one inspected before the 20th pass is logged as pass or reject with a reason code from a fixed list, so any skipped candidate can be audited. The curator stops at 20 passes.
- (c) **Category filters (scientific).**
  - **Faces:** one real adult human face, frontal (about ±20°), eyes visible, no sunglasses or occlusion. After the standard crop the face height is ≥ 40% of the square, and the cascade must detect the face (config `confounds.face`: haarcascade_frontalface_default, scaleFactor 1.1, minNeighbors 5) on the **processed** 256-px greyscale, SHINE-matched image. This makes the B6/§1.5 "≥ 90% of event TRs" check pass by construction instead of failing at QC.
  - **Bodies:** one person, **with no face visible** (head out of frame or not visible), and the cascade must not detect a face. Bodies with faces would drive FFC and shrink the face − body contrast in (d).
  - **Places:** indoor or outdoor scenes with no prominent person or face (cascade negative) and no text.
  - **Objects:** the owner listed objects, but no LOC family uses them (3 events = face, place, body). D-071 must say either "objects: not curated in v1" or "curated as a reserve, never used in v1". I prefer "not curated".
- (d) **Processing, frozen.**
  - Centre-crop each image to a square around the subject.
  - Resize so it fills the central ≈316 source px, which maps to the 256 crop.
  - Greyscale.
  - SHINE luminance, RMS-contrast and amplitude-spectrum matching **across all 60 images together, not within category**.
  - Image mean luma = background = 128, at a fixed RMS contrast.
  - Phase scrambles keep the amplitude spectrum, and the scramble seeds are frozen.
- (e) **Licence record.** CC-BY requires attribution, so record the author/attribution string and the licence version per file as well as the URL, licence and sha256. Also record whether the Commons file page carries a personality-rights notice. That is the Watchdog's call, but it affects which face photos are usable.
- (f) **NAT uses the same rule.** NAT gets the same pinned query, snapshot sha, ordered audit log and an operational "mostly frontal single speaker" criterion. For example: face_present_crop ≥ 0.5 over W from yct.confounds, computed after P3, which is label-free. Lecture videos that show slides instead of the speaker would otherwise distort σ_nat and the P10 rule.

## New non-blocking items

- **N11 LOC scramble schedule.** Specify when the background scramble switches from exemplar i to exemplar i+1. The switch must happen at the same TR in both twins, so that it cancels, and outside every kernel window [onset−4, onset+8]. Report its effect on the K3′ spans.
- **N12 K3′ spans.** State that K3′ uses only the inter-event spans: onset+12 … next onset−5, i.e. TRs 21–24 and 41–44 for s = 0, so 8 TRs per clip. Neither the pre-first-event TRs (clip-onset warm-up) nor any post-last-event span is used, since none exists.
- **N13 K5 fragility.** "sign(std) = sign(raw) at every lag 0–3" can fail on a near-zero lag-0 value on the rising flank. Consider restricting the rule to lags where |std course| ≥ 0.2·peak, or disclose the risk. The expected K5 failure on the ENH-002 flash is the global-signal effect (cycle-1 N4). It should be less for FFC (intact − scrambled), which is a local contrast.
- **N14 σ_nat for the audio-only AUD kernel.** K1′ for the audio-only kernel should use σ_nat from the NAT **audio-only** predictions, which are already in the ablation set. Say so.
- **N15 Half balance.** Interleave dot fields and gratings by clip index, and the LOC Latin-square orders, so that the even (selection) and odd (test) halves are balanced. With a block order, 5 + 5 gives a 3/2 split of pattern types.
- **N16 Job order under the $75 cap.** Freeze the order:
  1. D-038 ×3;
  2. GREY-CTRL, SPK, LOC + LOC-SCR, MOT + MOT-STAT, FLASH (needed for K6) and NAT (needed for K1′ and P10);
  3. the audio-only and text-only ablations;
  4. BURST and TALKFACE last.

  A cap STOP then leaves the gating families either complete or explicitly STOP_INVALID (B8a), never half-run and reinterpreted.
- **N17 Linearity of the FFC kernel.** BURST validates kernel ⊗ envelope linearity only for AUD. The FFC impulse kernel (1 s face onset) convolved with a sustained face_area_crop_frac is an untested linearity assumption. Disclose it in controls_report.
- **N18 Text pathway on visual clips.** Visual families have empty or near-empty transcripts. Confirm in T-REFRUN that the T1 gate and the text extractor accept n_words = 0 without padding or fallbacks that differ between twins. The twins must have identical tsv sha.
- **N19 Out-of-distribution disclosure.** Grey-background synthetic clips with a −23 LUFS white-noise bed are far from TRIBE's training distribution. The kernels are model impulse responses under these conditions, not cortex. State this in controls_report next to the circularity statement.
- **N20 Dot parameters.** Freeze:
  - dot count and density, dot size and dot lifetime (≥ the 1 s event);
  - 100% coherence;
  - per-frame displacement below half the mean inter-dot spacing at both 16 fps (V-JEPA2) and 10 fps (confounds), to avoid correspondence aliasing;
  - grating spatial frequency and temporal frequency (≤ 4 Hz; ≤ 3 Hz gives margin under the 5 Hz confounds Nyquist).

## Summary for the orchestrator
- D-071: amend it (B7 a–e, B8 a–e, B9 a–f, plus the B5 K2 plateau clause), then commit. No cycle 3 is needed. Council sign-off on the amended D-071 diff is enough.
- Tickets: build them after the amended D-071 is committed.
- Launch: allowed once the G tickets have green CI **and** the one-pass check above has been done (T-LIC manifest and rejection log, T-REF58 QC table and contact sheet, ENH-002 known-data K-run, frozen job order). Session 1 stays `--limit 3`, watched, with a human check.
