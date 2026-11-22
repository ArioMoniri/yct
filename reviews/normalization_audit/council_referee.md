# Council: strict scientific referee. Normalisation recheck

Scope: I read inventory.md and checked it against src/yct/{features/networks.py, features/m0.py, normalize/core.py,
tribe_run/enh002.py, controls/kernels.py, confounds/core.py}, config.yaml (including the `frozen:` list), v2.md §1 and
ROADMAP P2–P9. I read nothing sealed and no outputs from the analysis set (D-063 B2). The inventory's facts held
wherever I checked them. Spot checks:
- M-12: z-scores per TR with ddof 0 and raises on non-finite values and SD 0.
- M-16 and M-17 use the raw map.
- S-14 linear gain = −23 − I_speech, which is correct.
- The Q construction matches D-037. Z² terms are uncentred, which is harmless because the intercept is in Q.
- A-01 scene cuts are on the full frame.
- None of normalize.*/m0.*/features.*/confounds.*/vad.* is in `frozen:`.

## Verdict on the core chain (a hostile reviewer would accept these as standard)
- KEEP:
  - S-01, S-03, S-05, S-06, S-09, S-10 (tone-map), S-11, S-12, S-13, S-16, S-21;
  - M-04, M-06, M-08–M-11, M-13–M-15, M-17, M-21, M-22;
  - A-02–A-04, A-06, A-08, A-09, A-12–A-14, A-16, A-23, A-25.

  Why they hold up:
  - Per-TR spatial z-scoring (M-12) is the usual "global scaling" choice. It is already disclosed as compositional. M-16 (raw spatial SD) and G restore what it removes.
  - Limbic as the omitted reference is exact: Yeo is derived from Schaefer, which labels every non-medial vertex.
  - Label-free z-scoring, residualisation and imputation on the full analysis set (A-06, A-09) are transductive, but they never see labels. The same R enters the observed and null statistics, so a reviewer will accept this once it is disclosed.
- Redundant for TRIBE, but justified for other consumers:
  - S-05 serves determinism;
  - S-06 serves the confounds and T3 geometry;
  - S-14 serves WhisperX and rms_db.

  Say this in the methods so nobody claims they "help TRIBE".

## Blocking before P5b/P6
1. **A-10, scaling in CV is unspecified.**
   - The feature scales differ: R holds 6 residualised network means in standardised units plus raw-unit spatial SD, and M0 enters as z.
   - An L2 penalty is therefore not scale-invariant, so AUC(M0+R) depends on an arbitrary unit choice.
   - Pre-register `StandardScaler` fitted on the training fold only, applied to all columns of [M0, R] and to M1 (H3), inside every permutation refit. This matches analysis/power/h4sim.py, which P5b power must reproduce.
   - State which M0 enters the logistic: the linear z block, not Q.
2. **N1, P2/P3 parameters are not frozen.**
   - These keys were consumed at b24fc1c: `normalize.*`, `stimulus.{fps,min_short_side_px,center_crop_px,t1_trim_s,t1_max_probe_s}`, `vad.*`, `confounds.*`, `features.*`, `atlases.*`, `localize.*`, `m0.*`.
   - Add every one of them to `frozen:` with frozen_at = b24fc1c, together with `controls.kernel.{window_tr,type,shift_by_L}`, `controls.readout_lag_tr`, `controls.partial_out`, `controls.regressors.*` and the FFC/PH/AUD/V1_V3 area lists.
   - At the moment, "protected by convention" would not survive a prereg audit.

## Major: specification gaps a reviewer will call researcher degrees of freedom
3. **M-20, H2 composite.**
   - Add a config key.
   - Specify vertex-weighted pooling of the areas on the standardised W-map, the same weighting as M-15.
   - Add an implementation with a vertex-count test.
4. **A-15, Freedman–Lane.**
   - Use the PCs of the A-06 z-scored linear M0, excluding binaries and era dummies, centred, computed once and label-free on the full set.
   - Write this into v2.md.
5. **A-17, re-estimation scope.** Use one rule: the rules are frozen and the values are re-estimated.
   - Each S-* subset and wave 2 re-estimates the z-scores, imputation medians and Q at its own N, using the table in v2.md.
   - The only exceptions are T3, which reuses T1 by design, and S-T1SHORT if it is paired.
   - Pre-register this rule.
6. **S-24/S-23, speech span trim (a real bug risk).** The SpeechProvider must do three things before placing speech, RMS matching and assigning uniform word times:
   - resample with a proper anti-aliased resampler (soxr/polyphase, not nearest-sample as in the superseded S-25);
   - trim to the −40 dBFS span;
   - compute RMS on the span only.

   Otherwise espeak's leading silence biases AUD kernel latency (K2) and the gain. Add tests.
7. **S-14, dynamic-mode fallback.**
   - Dynamic loudnorm changes dynamics within a chunk. It is the only way S-14 reaches TRIBE (M-01 z-scores each chunk).
   - The owner should authorise a label-free count of `loudnorm_mode=dynamic`. If it is above 0, disclose it and add those IDs to the S-* exclusion list. Do not re-run P2.
   - For wave 2, replace the fallback with pure gain capped at the true peak (flag the loudness as off-target).
8. **A-18, no drift term.**
   - Add a linear (Legendre order 1) detrend within W to the partial-r nuisance set.
   - This is standard in any fMRI GLM. TRIBE targets were detrended, but predictions can still trend across a 40-TR window.
9. **A-21, speech envelope undefined.**
   - Before coding it, freeze the definition: broadband |Hilbert| of the 16 kHz sidecar, low-pass 10 Hz, mean per 1 s TR on the M0 grid.
10. **S-10/A-05, `hdr_source` is not wired.**
    - Implement the D-056b conditional (an all-SDR set gives a constant column, which is omitted) and test it.
    - At present a spec claim has no code behind it.

## Minor: fix or disclose
- M-12b: delete `enh002.standardise`, or make it call `networks.spatial_standardize`. The P4b d_std builder must use M-12 (add a test).
- A-01: scene cuts on the full frame is defensible because cuts are global events. Disclose it; do not recompute.
- S-22: add bt709/tv tags to the reference clips in any future rebuild. The grey content makes this a no-op now; disclose it.
- Disclose S-19 (gamma-domain gain), S-27 (no aperture; edge energy enters specMatch), S-26 (no ICC handling) and A-22 (per-map scale; also give one shared-scale panel).
- M-12: add raw-map H1 network means as a descriptive companion. v2.md already does this for P4b.
- M-05: keep the wording "relative units".

## Remove or demote (recorded, but no consumer; v2.md overclaims)
- S-07 crop coverage and S-08 9:16 stratum:
  - At N ≈ 51, a stratum or an extra M0 column is not affordable; Q is saturated at rank 17.
  - Amend v2.md through DECISIONS so that both are descriptive QC, plus one S-* sensitivity that drops portrait clips.
  - The source-aspect negative control (A-24) stays.
- S-18 q480: no consumer. Drop it from the ROADMAP P2 tasks and log the deviation.
- S-15/S-17 flags: these are QC only, so say so.

## Missing normalisations / covariates a reviewer will ask for
- ADD: source quality. Upscaled sources (S-06 flag), source short side and bitrate are platform- and era-linked. They change V-JEPA2 input sharpness, and v2.md P2 promises them "as confounds". Add a label-free S-QUALITY sensitivity that excludes upscaled sources, or adds one binary `upscaled` column if rank allows. It should not go in primary M0.
- ADD: spatial-frequency / sharpness energy in the crop as a descriptive covariate for T3 and S-QUALITY, because T3 normalises luminance and contrast but not blur.
- ADD: a P5b check that the full A-06→A-10 chain, including the fold scaler, is what h4_null_sim exercises.
