# Council: QA engineer (normalisation recheck)

Scope: I checked the code, config and tests against inventory.md. I did not read anything under data/sealed, any labels, any outputs/ statistics on the analysis set, or pred_clampv1 (firewall D-063 B2).
Tests: I ran 21 relevant files: atlas_networks, m0*, controls_kernels, medial_wall_union, enh002_latency, locimg, speech_corpus, reliability_mask, localize, normalize*, photometric*, confounds*, refclips58. **227 passed, 0 failed.**
I also ran probes in the scratchpad, using synthetic data only. Each one is cited below.

## Verified correct (keep)
- **S-14 loudness.** The linear gain is tgt − I_full = −23 − I_speech, so it is exactly the stated speech-gated target (core.py:557-566). Minor issue: `offset=` comes from pass 1 at −23. It only matters in the dynamic fallback, and there it is under 1 LU.
- **S-19 T3.** Σw_luma = 1, so meanY′ hits the 0.45 target exactly before clipping. When the gain is capped, b is re-solved, so the mean target still holds.
- **A-01 grey decode.** The probe gives black → 0, mid-grey → 127, white → 254. Range is expanded to full, which matches the rgb24 path used in T3.
- **S-23 in-repo BS.1770 is right.** A full-scale 997 Hz sine gives −3.01 LUFS. But the only test (`test_bed_is_minus_23_lufs`) checks the function against itself, so it would not catch a broken K-filter.
- **M-12 / M-15.** The rank-6 dependency is tested on the real atlas (`test_m1_real_yeo_rank`), and so is the union medial wall.
- **M-12b** is bit-identical to M-12 on cortex (probe: max |Δ| = 0). It differs only on zero SD and NaN input, and it leaves medial-wall values finite instead of NaN.
- **A-06 / A-08.** A constant binary (platform in a YouTube-only subset, or `voiced_any` ≡ 1) is aliased and dropped rather than counted (probe), and merges are re-z-scored.
- **S-10 HDR.** The zscale → linear → bt709 primaries → hable → bt709/tv chain is the standard recipe.

## Defects / gaps found by QA (new or sharper than the inventory)
1. **A-17 (blocking for the sensitivities).** Re-running the Q rule on a subset changes Q, or crashes it. `q_dimension_table` shows:
   - **S-LAG at N = 51–53:** 18 required columns > ⌊N/3⌋ = 17. So S-LAG silently applies the `photometric_crop` merge and drops the one optional quadratic. It therefore differs from the primary in three ways, not one.
   - **S-PREDECISION** (or any subset with N ≤ 38): the merge list is exhausted and the code raises a hard ValueError (N = 30 and N = 25 both fail).
   - **YouTube-only:** the table over-counts by one, because `platform_nonYT` is aliased in that subset.

   Fix: a DECISIONS entry. Every subset should reuse the primary Q columns, the merges and the full-set z/medians, restricted to the subset rows. S-LAG should add its 2 columns on top of that, not re-run the rule. Add tests at N = 51 for S-LAG and at N = 25 for a subset.
2. **A-10 / A-25 (blocking for P5b).** No production CV code exists (src/yct/stats is empty). The P5b H4 null sim (`h4_null_sim.cv_auc`) differs from v2.md §1 H4 in four ways:
   - λ is fixed at 1, with no nested C;
   - it uses StratifiedKFold, not StratifiedGroupKFold(company), 20 repeats;
   - it also z-scores binaries inside the fold;
   - the AUC(M0) baseline is Q's linear columns *without* the era dummies.

   An FPR measured on this sim does not validate the H4 pipeline. The fix:
   - pre-specify the H4/H3 design matrix: which M0 columns, and whether era is included;
   - fit the scaler on the training fold only, applied to all columns, inside the nested C loop, and refit it in every permutation;
   - make P5b call the production function, not a re-implementation.
3. **M-12b (fix).** No P4b d_std builder exists yet (kernels.py takes arrays). Add an import/AST test so that the builder can only call `networks.spatial_standardize`.
4. **Missing invariance tests (add).** These tests would catch a wrong normalisation:
   - **M-12:** M1 is unchanged under any per-TR affine map a_t·x + b_t with a_t > 0, and spatial_sd scales by a_t.
   - **A-09:** R is unchanged under a column-wise affine rescale of the continuous M0 columns, as long as no merge fires.
   - **S-14:** a loud/quiet pair of the same file gives the same 16 kHz sidecar to within 0.1 dB, and a high-crest input records `loudnorm_mode=dynamic`.
   - **S-23:** a reference-value test for BS.1770 (the 997 Hz sine at −3.01 LUFS).
5. **S-24 (fix before the build, confirmed).** `clip_audio` uses `len(wav)` for three things: the range gate, the RMS match and the uniform word timing (refclips58.py:328-334). Nothing trims to the −40 dBFS span. Chunk SD is preserved, because the RMS is matched over the same n samples. But word onsets shift and the speech peaks are inflated. The SpeechProvider must trim to the span, and a test should assert d == span.
6. **S-09 (add, minor).** The conversion is matrix-only, so SDR sources tagged with BT.2020 primaries (non-PQ/HLG) are not gamut-mapped. Add a flag, plus a label-free count from the P2 records.
7. **A-01 scene_cuts (disclose).** PySceneDetect decodes with its own OpenCV path. It has no BT.709/tv control, works on the full frame and runs at native 30 fps. It is a count, so the effect is small; it should be disclosed, not recomputed.
8. **A-18 (fix at implementation).** Add a linear (or DCT ≤ 1/40 Hz) drift term to `partial_out`. Specify how p for "p < .001" is computed under autocorrelation, for example as a between-video t on the atanh z values.
9. **M-20, A-15, A-21 (spec gaps, confirmed).** None of the three has code or config. M-20 should be a vertex-weighted mean on the standardised map, with a config key and a test. A-15 should use PCs of z(M0) from A-06. A-21 needs its band, smoothing and decimation pinned.
10. **A-05 / S-10.** `normalize.core.normalisation_covariates` exists but has no caller. Either wire it into `h4_m0`, or record "0 HDR in the analysis set" as a label-free assert.
11. **N1 freeze (fix).** The P2/P3-consumed keys are byte-identical to b24fc1c but not frozen. Add them to `frozen:`, together with `controls.kernel.{window_tr,type,shift_by_L}`, `controls.readout_lag_tr`, `controls.partial_out` and the ROI area lists. Use a two-commit freeze, and add a test that fails if any normalisation key leaves `frozen:`.

## Not needed / demote (QA view)
- **S-18 q480:** it has no consumer, so keep it as a QC artefact only.
- **S-07 crop coverage and S-08 `stratum_9x16`:** at N = 51–53 the Q rank budget is 16/17, so consuming either would force a merge. Demote both to descriptive/QC by a DECISIONS entry that amends v2.md P2 ("confound" / "own stratum").
- **S-15 and S-17:** QC flags only (keep).
- **S-05 CFR, S-06 upscale, S-14 loudnorm:** redundant for TRIBE but needed for determinism, the confounds and WhisperX (keep).

## Roadmap changes proposed
- **P5:** add FIX-NORM-QA before P5b:
  - the subset-Q DECISIONS entry and its tests (item 1);
  - production CV/scaling in src/yct/stats, with P5b using it (item 2);
  - the invariance and BS.1770 tests (item 4);
  - wiring or asserting `hdr_source` (item 10);
  - the M-20 key and test (item 9);
  - the freeze extension (item 11).
- **P4b:** gate the reference-clip build on items 3, 5 and 8, the A-21 spec and the D-085 finalisation.
- **P2 closeout:**
  - a label-free QC table of `loudnorm_mode`, `source_color_untagged`, BT.2020-SDR, `hdr_source` and `gain_capped` counts;
  - the demotion entry for S-07 and S-08.
