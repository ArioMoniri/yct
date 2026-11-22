# Council: biostatistician (normalisation recheck)

Verified against src/yct/features/{networks,m0}.py, controls/kernels.py, interpret/localize.py, config.yaml and
v2.md §1. Label-free; firewall D-063 B2 respected (no sealed data, no outputs).

## Verdicts on the inventory (verified in code unless marked spec)
- **M-12 per-TR spatial z (keep, but add a diagnostic).** Code matches (networks.py:42-60). It is needed: TRIBE
  units are relative (M-05). But it is a ratio transform. Network mean = (raw net mean − cortical mean) / cortical SD,
  so it can *create* group differences: a group difference in spatial SD, driven by any region, rescales every network
  contrast. It can also *erase* them, because it removes G. Adding raw spatial SD linearly (M-16) does not undo a
  multiplicative effect. Add a descriptive H1 companion, S-CENTRE: centre only, no division. The Hedges g of the
  centred and the z-scored network means is reported side by side. Not in Holm.
- **M-15 / H1 compositional (keep, wording).** The W-mean of per-TR z maps has a vertex-weighted mean of exactly 0. So
  one true network effect produces opposite-sign "effects" elsewhere. maxT handles the dependence. The report must say
  "relative to the cortical mean" (v2.md already does) and never count opposite-sign networks as independent findings.
- **Order of operations M-12 → M-14 → M-15 (keep).** z then average gives each TR weight 1/SD_t. That is acceptable, and
  W-mean then z is not equivalent. Freeze the order as implemented.
- **M-16 spatial SD (keep)** restores the lost contrast. **M-17 G (keep)**: a mediator, so never a covariate. Correct.
- **M-12b (fix).** Zero SD → /1, no finiteness check. Production d_std must call networks.spatial_standardize (test it).
- **M-20 H2 composite (fix, blocking for P5).** Specify a vertex-weighted mean on the standardised map, consistent with
  M-15. An area-weighted mean would up-weight small areas (44/45 left only). Add a config key, a test and a freeze.
- **A-06 M0 z-score (keep; statistically neutral).** With an intercept, span{1, x, x²} = span{1, z, z²}. var(z²) and
  var(z_a·z_b) are affine-invariant, so the optional-term order is too. R does not depend on z. z matters only for
  numerics (rank, cond) and for the merge composites. Constant columns → 0 are aliased and dropped. Correct.
- **A-04 imputation (keep, note).** The missing-indicator design makes the median choice irrelevant for linear and
  square pitch terms. It is not irrelevant for products pitch·x, which can enter as optional terms (I·x is not in the
  span). It is minor: disclose, or bar pitch from products when `voiced_any` varies.
- **A-05 lag imputation (keep).** Linear only, so the median is irrelevant given `lag_unknown`. `hdr_source`: wire it in
  or record "0 HDR in the analysis set" as a label-free fact (S-10).
- **A-09 residualisation once, full set (keep, plus a P5b check).** It is transductive but label-free, so there is no
  leakage. Note: observed R ⟂ Q exactly, while row-permuted R* is not, so the null has a different geometry. P5b
  (A-25) should also run the variant R* ← (I − H_Q)R*, report FPR for both, and keep the current construction unless its
  FPR is outside the 3.1–7.1% band.
- **A-10 CV scaling (fix, blocking).** L2 is not scale-invariant. R mixes z-unit network means with raw spatial SD, and
  M0 binaries are raw. Pre-specify: StandardScaler fit on the training fold only (inside the nested C loop), applied to
  all M0 + R columns including binaries, and refit in every permutation. This matches h4sim.py. The same applies to H3.
- **A-11 M0b (clarify).** "Block z-scored" is ambiguous. Pre-specify per-column centring on the training fold, then PCA
  per block. Per-column z of ~1,000 embedding dims would inflate noisy dimensions. Then the 7 scores are scaled as in A-10.
- **A-15 Freedman–Lane (fix).** An unscaled PCA would be dominated by pitch (Hz) and rms_db. Use the nuisance set
  [1, era dummy, platform_nonYT] + the first ⌊N/15⌋ (≤ 5) PCs of z(continuous M0) from A-06. Era and platform go in
  directly, not via the PCs.
- **A-17 subset scope (fix).** ⌊N/3⌋ changes with N, so the "same Q rule" implies rebuilding. Pre-specify: every subset
  sensitivity (S-LOWFPS, S-LAG, S-PREDECISION, YouTube-only, OPEN, S-T1SHORT) and wave 2 re-run assemble_m0 + q_m0 on
  the subset (z, medians, merges, optional terms). Only T3 reuses T1 (same videos, paired nulls; v2.md).
- **A-18 no drift (fix).** Across videos, mean z is biased upward when the ROI course and a smoothed regressor share a
  slow trend inside W. Add a linear trend (Legendre order 1) to `partial_out`. Freeze partial_out and the regressors.
- **A-21 envelope (fix).** Specify band, smoothing and 2→1 Hz decimation before the P4b run. Freeze them.
- **A-22 map scale (fix, small).** Two group-mean maps shown side by side must share one vmax, or a visual group
  difference can be created or hidden. Keep per-map scales for single maps.
- **S-14 loudnorm (keep; one check).** It is a double normalisation with M-01 and harmless for TRIBE, except in the
  dynamic-mode fallback. That fallback is a per-video nonlinearity plausibly correlated with production quality, and
  hence with group. Count `loudnorm_mode` = dynamic now, label-free. If > 0, add a descriptive exclusion sensitivity.
  Give the label × mode table only at unblinding.
- **A-01 (keep).** rms_db post-loudnorm: TRIBE z-scores audio per chunk, so absolute loudness cannot confound R–y.
  scene_cuts on the full frame: a cut is global, so disclose only.
- **S-07 / S-08 recorded only (clarify).** Either demote them to QC in v2.md, or add crop-coverage area as a P10 negative
  control. Do not add them to M0: Q is already saturated at N = 51–53.
- **A-03 (keep)**: label-free selection on a covariate; report label × exclusion at unblinding. **S-19/26/27**: disclose.
- **N1 freezes (fix).** P2/P3 already consumed normalize.*, vad, confounds, stimulus.*, features.* and atlases. Freeze them
  now (two-commit). Freeze m0.* at prereg, as planned.
