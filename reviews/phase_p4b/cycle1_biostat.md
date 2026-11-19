# P4b design v1: Biostatistician review (council cycle 1)

Reviewed: reviews/phase_p4b/design_v1.md, against docs/prompts/v2.md §5 P4b (v2.5 C3, v2.7 P4E), ROADMAP P4/P4b, DECISIONS D-035, D-039, D-040, D-047, D-055, D-063, D-065(d), D-066, D-067(c), config.yaml `controls:` / `era_blocks:` / `seeds:` / `frozen:`, src/yct/tribe_run/enh002.py, src/yct/tribe_run/make_reference_clips.py and scripts/owner_label_qc.sh (block codes).
Scope respected: no AWS, no sealed data, no labels, no wave-2 pool, no prediction arrays. `pytest tests/test_controls_config.py`: 8 passed.
Simulations: synthetic event courses only (13 lags, AR(1) ρ = 0.7 noise with unit per-event SD, a Gaussian kernel peaking at lag +1 with amplitude d in per-event SD units, 4 events per clip, 1,500–3,000 reps). No project data was used. The scripts are in the session scratchpad and are not committed. The numbers below are their output.

## Verdict: GO-with-conditions

The reference-clip job is label-free, cheap (≈ $6–16) and kept outside pred_clampv1/, and the firewall plan is sound. But as specified, the job would produce data that cannot meet its own acceptance rules with useful power. One rule (K4) passes on pure noise. Another (K3) fails on almost any realistic kernel. Several things that change the job's inputs are still undecided.

Before launch:
- Build T-REF58 and T-REFRUN only after B1 and B5 are folded into design v2.
- Freeze B2–B4 in config and tests in the launch commit, so that no acceptance rule can be written after a reference prediction has been seen.

No further full council cycle is needed if v2 adopts these items as written. Any other resolution goes back to the council.

## Blocking items

**B1. Too few independent replicates per gating kernel (K1 power). Blocks the clip build.**
- Evidence (§1 and §3 K1): 5 clips × 4 events, peak lag picked on clips k = 0, 2, 4 and tested on k = 1, 3. That leaves 8 test events, with a one-sided α = .001 at df 7 (t > 4.79).
- Simulated K1 pass rate (peak lag in [−1, 4] and p < .001), by clips per family:

  | clips per family | d = 1 | d = 1.5 | d = 2 |
  |---|---|---|---|
  | 5 | 0.12 | 0.38–0.41 | 0.75 |
  | 8 | 0.54 | 0.95 | |
  | 10 | 0.72 | 0.99 | |

- The null pass rate is 0.000 in every arm, so the extra clips cost no specificity.
- The face and place stimuli are weak by construction (§1 table), so d ≈ 1–1.5 is the realistic range for FFC and PH. A STOP at 5 clips would most likely be a power failure, not a pipeline failure.
- Replication is pseudo-replication. TRIBE is deterministic, and the bed and frame are bit-identical. The 5 clips of a family differ only by the phase shift φ_k, and identical exemplars are reused (one white flash, 5 SENTENCES across 20 bursts). So the across-event variance measures positional heterogeneity, not generalisation across stimuli.
- More clips cannot come from more phases either. The window rule onset + 8 ≤ 57 with base onset 45 caps k at 4, and a duplicate clip gives a bit-identical prediction, which adds nothing.
- Required:
  - At least 8, preferably 10, clips per gating family (FFC face, AUD speech, MT+ motion).
  - Each clip and each event uses a distinct exemplar: different sentences, face images, motion patterns or directions, place images.
  - Phases cycle k mod 5.
  - The flash family (descriptive only) may stay at 5.
- Cost at 10 per gating family: about +15–25 clips × ~6.5 min ≈ +2–3 GPU-h ≈ +$5. That is well inside budget.

**B2. K4 (leave-one-clip-out r ≥ 0.8 vs the full kernel) is non-diagnostic. Blocks reading the reference outputs.**
- Evidence: each LOCO kernel shares 16 of its 20 events with the full kernel. For independent noise the expected part–whole correlation is √(16/20) = 0.89.
- Simulated with pure noise (d = 0):
  - median of the minimum LOCO r over the 5 folds: 0.80;
  - K4 pass rate: 0.51 with 5 clips and 0.81 with 10 clips.
- So K4 accepts noise kernels, and it gets worse as clips are added.
- Replace it with held-out criteria:
  - K4a: for each LOCO fold, r(kernel from the training clips, the held-out clip's mean course). Require the median over folds ≥ 0.5.
  - K4b: split-half r(even-k clips, odd-k clips) ≥ 0.7.
- Simulated pass rates, null vs d = 1:

  | clips | K4a null | K4a d = 1 | K4b null | K4b d = 1 |
  |---|---|---|---|---|
  | 5 | 0.05 | 0.80 | 0.02 | 0.52 |
  | 8 | 0.02 | 0.91 | 0.02 | 0.75 |
  | 10 | 0.01 | 0.94 | 0.03 | 0.86 |

- Add a T-KERNEL test asserting that K4 fails a pure-noise input at a rate below 0.05 over seeded replicates.

**B3. K3 (SNR ≥ 3) is a per-event effect size of 3, and its baseline is contaminated. Blocks reading the reference outputs.**
- Evidence: "peak / SD(pre-onset lags −4…−1 across events)" divides the mean peak by the per-event SD, so it requires d ≥ 3.
  - Simulated pass rate: 0.00 at d ≤ 2, 0.52 at d = 3, for both 5 and 10 clips. It does not improve with more clips, because it measures the per-event SNR, not the precision of the kernel.
- D-055 documents a backward leakage of up to 4 TR before the event, so the pre-onset lags hold real signal. The SD is also undefined:
  - Pooling 4 lags × 20 events adds the leakage ramp to the SD.
  - A per-lag SD across events does not.
- Required: redefine K3 as a kernel-precision SNR: mean peak / √(mean over lags −4…−2 of the across-event variance at each lag / n_events) ≥ 3. This excludes lag −1, which K2 allows as a peak lag.
  - Simulated: null 0.02, d = 1 → 0.95 with 5 clips.
- If the council judges this redundant with K1, drop K3. Do not keep it as written.

**B4. K1, K2 and K5 are not specified exactly enough to freeze. Blocks reading the reference outputs.**
- Evidence: §3 K1 says "one-sample t across the 20 events at that lag" and also "tested on the other half". Using all 20 events reintroduces the selection bias that the split is meant to remove.
- Also unspecified:
  - the peak definition. kernel = mean / max|·| (enh002.analyse), so the peak should be the signed argmax over −4…+8, not argmax|·|;
  - which data K2 uses (the selection half, the full data, or both);
  - sidedness;
  - whether K5 also requires the same sign of the peak.
- Required, written as formulas in config (e.g. `controls.kernel.acceptance`), tested, and listed in `frozen:` in the launch commit:
  - The halves are the even-k and odd-k clips.
  - The peak lag is the signed argmax of the selection-half mean course.
  - K1: one-sided one-sample t over the test-half events only at that lag, p < .001. In addition, every test-half clip mean must be > 0 (a clip-level sign check, given B1's pseudo-replication).
  - K2: both the selection-half peak lag and the full-data peak lag lie in [−1, +4].
  - K3: as in B3.
  - K4: as in B2.
  - K5: the standardised and raw peak lags differ by ≤ 1 TR, with the same sign at the peak.
  - The thresholds must also be committed before any ref-clip .npy is opened. This is the label-free analogue of "thresholds fixed in advance": choosing K rules after seeing kernels is a forking path even without labels.

**B5. Stimulus-set decisions that change the GPU job's inputs are open. Blocks the clip build.**
- (i) The (d) body category is missing. v2.md §5 P4b (d) specifies "1 s face/place/body image flashes … minus the other categories", but design v1 has face and place families only.
  - Add a body family (same count as place) or record the deviation in a DECISIONS entry.
  - With only two categories, "minus the other categories" changes meaning.
- (ii) Q2, the localiser image source, decides what the ref_face58, ref_place58 and body clips contain (see Q2).
- (iii) Q3, the naturalistic reference clips. The low-SD rule ("P10 of the reference clips"), the < 15 fallback and the OOD check (L5) all need them, but the job has none.
  - If "reference clips" means the synthetic event clips, the rule breaks. Their regressors are binary on/off with large SD, so P10 of them would exceed most naturalistic within-video SDs and exclude most analysis videos.
  - (a) would then fall back to the reference set. With 5 clips at p < .001 that needs t > 7.17 at df 4.
  - Required:
    - P10 is computed per regressor over the naturalistic reference set, with the method fixed (numpy `percentile`, linear) and ddof fixed.
    - That set has ≥ 15 clips (see Q3), so the fallback sees the same `min_videos` floor as the main rule.
    - Either include them in this GPU job (≈ 15 × 6.5 min ≈ 1.6 h ≈ $3.5) or name the separate job that delivers them before the lock.
- (iv) Q1: if B1 is chosen, the audio-only reference runs (at least the speech family and ref_talkface58) belong in the same build, so the (b)-speech kernel can be derived on the audio-only track (N3).

## Non-blocking items

**N1. Gating set and map.**
- Design v1 gates on "T3 52; T1 51 reported". v2.md makes T1 the primary input and T3 a sensitivity outside Holm (§1 T3 rules). (c) exists to "check the same aggregation that the hypotheses use", which is T1 and standardised maps.
- Recommend: gate on T1 (51) with standardised maps. Report T3 and raw maps alongside, as non-gating.
- Requiring all of T1, T3, raw and standardised to pass would multiply the false-STOP risk with no gain in validity.

**N2. Sidedness and p-value conventions.**
- All control tests are one-sided in the predicted direction: (a) mean z > 0; (b) target − comparison > 0; (c) r > 0.
- Permutation p = (1 + #{r* ≥ r_obs}) / (1 + B), with B = 10,000. Fisher z = atanh(r), clipped at |r| ≤ 0.999999.

**N3. Kernels in (b).**
- In "z(FFC, face) > z(V1_V3, face)", v2.md's one-kernel-per-ROI rule convolves the face regressor with the flash-derived V1_V3 kernel for the V1_V3 arm. That kernel is descriptive and may fail K1–K5, and its timing differs, so the paired difference mixes ROI with kernel.
- Recommend: within each comparison, both arms use the gating ROI's kernel (FFC for face; for speech, AUD derived on the audio-only reference run). The own-kernel version is reported as a sensitivity. Fix the choice in the design entry.
- Both arms of each paired test use the same video set, after the union of exclusions.

**N4. The speech kernel is a burst response, not an impulse response.**
- Averaging 4–6 s bursts of varying length gives impulse ⊗ boxcar(D). Convolving the continuous speech envelope with that kernel smooths it a second time by D.
- Recommend: estimate each kernel by FIR least squares (lags −4…+8) of the control-subtracted ROI course on the same 1 Hz regressor that (a) uses. Event-averaging remains descriptive. The current 13 s spacing keeps the FIR identifiable.
- The K rules then apply to the FIR estimate. Event-level values for K1 come from the per-event residual-plus-fit, or K1 stays event-averaged; either way, state which.

**N5. Convolution and partial-r details to state.**
- Define the model as ŷ(t) = Σ_l k(l) x(t − l) for l = −4…+8. At t = 5, lag +8 needs x(−3).
  - Recommend zero-padding for t < 0: no stimulus exists before the clip start.
  - Lag −4 at t = 44 needs x(48), which exists.
- The partial-out regressors are convolved with the same target-ROI kernel.
- The intercept is included.
- The target regressor is removed from `partial_out` for its own control.
- The residualisation is OLS over W.

**N6. Multiplicity.**
- All controls must pass, so the gate is an intersection–union test. Testing each component at its own α already controls the probability of wrongly declaring the controls passed at that α.
- No Holm or Bonferroni adjustment across controls, ROIs or maps is needed, and adding one would only raise the false-STOP rate. The ROIs are fixed in config with no search, so there is no ROI multiplicity.
- The real cost is conjunctive power. About 4 kernels × 5 rules plus (a) ×3, (b) ×2, (c) ×2 and (d) ×4 signs: at 0.9 each, the end-to-end pass rate falls below 0.5.
- Recommend:
  - The PH kernel is descriptive. PH gates only through (d), whose readout uses the fixed lags 0–3, not the kernel.
  - T-CTRL reports the end-to-end gate pass probability under the planted effect sizes, alongside the per-test PASS/FAIL tests.

**N7. The (d) sign rule has low specificity.**
- Four signs (2 ROIs × 2 hemispheres) pass by chance with probability 1/16 if independent. TRIBE's left and right are strongly correlated, so the chance rate approaches 1/4.
- Report event-bootstrap 95% CIs of each contrast (seeded).
- Consider a DECISIONS amendment before the lock: sign rule and CI excluding 0 in each hemisphere. The gate stays as v2.md states unless amended.

**N8. Blocks for (c) (see Q4).**
- Report only the pooled r and the block-restricted p. Before unblinding, report no per-block r, mean or table: route is outcome-associated (D-035, D-040).
- Block codes for the 52-row set are listed in D-063 as a "before P5" owner action. If (c) uses blocks, that action moves before the P4b controls run.

**N9. Freezing.**
- `controls.pass`, `kernel`, `readout_lag_tr`, `maps`, `dry_run` and `rois` (except MT_plus) are not in `frozen:`. There is no controls permutation seed in `seeds:`.
- Add `seeds.controls_perm` (and a kernel-bootstrap seed). Freeze every `controls.*` key with the design entry, as §8 intends; the K rules go in the launch commit (B4).

**N10. Motion stimulus identifiability.**
- A grating or dot field that appears for 1 s is a contrast-onset event as well as a motion event. Δ mean luma ≤ 1% is necessary but not sufficient.
- Recommend: the pattern is present and static for the whole clip, and the event is a 1 s drift (static → moving → static). Mean luma and RMS contrast are then constant, tested in T-REF58.

**N11. The dry run is diagnostic.**
- (a) on 5 reference clips, or on the single ref_talkface58, cannot reach p < .001 with useful power (df 4 needs t > 7.17; n = 1 has no across-video test).
- State the dry run as a feasibility check whose outcomes map to pre-declared actions (proceed / DECISIONS entry), not as a fifth gate.

**N12. Low-SD exclusion and power for face.**
- Talking-head videos have near-constant face presence, so within-video face-area SD over W may be small. Expect exclusions and a modest mean z.
- This is no reason to move the 0.2 / .001 thresholds, but T-CTRL's planted-effect simulation should use a realistic within-video SD range.

## Answers to Q1–Q6

**Q1: (b) audio-only.**
- **B1.** Only B1 keeps v2.md's estimand (a paired test across analysis videos) and its N.
- B2 changes the unit to 5–6 synthetic clips. A paired test at p < .01 with n ≈ 6 is underpowered and draws on a different population. B3 is confounded by the text pathway (v2.5 C3).
- Specify:
  - Run on the T1 inputs (51) that form the gating set, plus yct_0483 only if T3 is reported.
  - Run the reference speech family and ref_talkface58 audio-only too, for the audio-only AUD kernel (N3).
  - Apply the D-038 Gate 1 cached rerun on 3 clips of the new track.
  - D-065(d) requires its own spec entry and a GPU test before the analysis-set audio-only run. The reference audio-only clips can ride in this job.

**Q2: (d) localiser stimuli.**
- Use a public localiser set with a verified open licence (fLoc's licence must be checked and recorded), covering face, place and body (B5 i).
- Each category gets ≥ 20 distinct exemplars, each shown once, as 1 s flashes in the 58 s design. Real exemplars supply the stimulus variation that B1 needs.
- Synthetic line drawings make a STOP from low power likely, a failure unrelated to the pipeline. Either choice needs a DECISIONS entry before the build.

**Q3: Reference naturalistic clips.**
- Use non-YC public talking-head videos with an open licence: ≥ 15 (B5 iii), matched to the analysis set on format (58 s T1 trim, crop, speech present), with a sha256 manifest frozen at the design entry.
- Do not use non-primary wave-1 rows:
  - They have sealed labels.
  - Several are same-company siblings of analysis rows (company_pick keeps one per company), so for the OOD check they are near-duplicates, not references.
  - Using them would bar them permanently from any later use.
- No wave-2 pool rows (D-069).

**Q4: (c) permutation.**
- **Within the D-040 era × route blocks**, as the gating test. Report the unrestricted test as well.
- Reasons:
  1. v2.md says "every permutation uses these blocks". (c) exists to check the hypotheses' own aggregation, and the hypotheses are permuted within blocks.
  2. The restricted null removes the between-block confounding (era-linked production style moving both face fraction and predicted FFC) that an unrestricted test would count as a pass. Gating on the stricter test is conservative in the right direction for a STOP gate.
  3. The codes are opaque (owner_label_qc.sh, secret salt), and the test reads no label.
- Conditions:
  - Use the pooled Pearson r with the r > 0.3 threshold, and permute the regressor within blocks.
  - Report no per-block statistics before unblinding (N8).
  - The owner issues 52-row codes before the run.
  - If the codes are unavailable at run time, the control waits. Do not substitute era-only blocks ad hoc.
  - The era-only fallback is allowed only if the design entry names it now.
- Power is unaffected by the restriction in practice. At N = 51, P(r > 0.3) is 0.95 at ρ = 0.5 and 0.79 at ρ = 0.4 (Fisher z), and r > 0.3 already implies one-sided p ≈ .016. The r threshold binds, not the permutation p.

**Q5: K1–K5 thresholds.**
- **Do not tighten. As written they are both too lax and too strict in the wrong places:**
  - K4 passes on noise (B2).
  - K3 fails on realistic kernels (B3).
  - K1 is underpowered at 5 clips (B1) and ambiguous (B4).
- With B1–B4 the rules have known operating characteristics, simulated:
  - pass rate under the null ≤ 0.03 per rule;
  - pass rate at d = 1 with 10 clips: about 0.72 (K1), 0.94 (K4a), 0.86 (K4b), 1.0 (K3').
- Keep α = .001 for K1, the [−1, +4] lag range for K2 (it constrains the peak, not the onset, so it is consistent with D-055), and the ≤ 1 TR rule (plus sign) for K5.
- Freeze all of them before any reference output is read. If a K rule fails, that is a STOP and goes to the council, with no re-tuning.

**Q6: Motion stimulus and an MT+ K-failure.**
- The stimulus needs the static → drift design (N10), and its exemplars are pooled across gratings and dot fields, varying direction (B1).
- If MT+ fails K1–K5, it is a **STOP**. v2.md says "FAIL on any means STOP", and MT+ is the only gating low-level visual control (D-063 Q4).
- Reclassifying it as a disclosed limitation is legitimate only if the rule is pre-specified in the design entry before any reference output is read. Deciding after the failure is post hoc.
- My recommendation is STOP, with no pre-specified escape. If the council wants an escape, it must name the exact alternative (e.g. "(a)-motion becomes descriptive and the limitation is disclosed in the abstract") now.
