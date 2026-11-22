# ROADMAP proposal: normalisation recheck (R-11)

This proposal comes from the chair's synthesis (`synthesis.md`).

**Ground rules**
- The ROADMAP is append-only.
- Struck text uses `~~…~~` plus an "(R-11)" tag, in the same convention as v2.md.
- No frozen decision is changed, with one exception: Q1. D-071(a) gains a drift term only if the owner approves; this is a pre-run amendment of the D-074 kind.
- Every ticket below is outcome-blind as long as it lands before (a) the first analysis-set W-average or readout and (b) the first P4b reference-campaign output.

**DECISIONS entry**
- Proposed entry: **D-08x**, the next free number after D-085.
- It records the ten items below.

| # | What D-08x records |
|---|---|
| 1 | R-CV |
| 2 | R-SCOPE |
| 3 | R-FL |
| 4 | R-ENV, linked to T-ENV |
| 5 | Demotion of crop coverage, `stratum_9x16`, q480 and source metadata to descriptive QC (amends D-005 and v2.md P2) |
| 6 | The S-QC sensitivity rule |
| 7 | The pitch-product bar |
| 8 | The H2 composite definition |
| 9 | The freeze plan |
| 10 | The toolchain pin |

## Ordered edits

### 1. New ticket FIX-NORM-0 (now; CPU only; no GPU, pod, or analysis-set read)

1. **Freeze, first commit pair.** Add `frozen:` rows for these keys, each byte-identical to b24fc1c (D-060 run):

   | Key | Scope |
   |---|---|
   | `normalize.*` | all |
   | `stimulus.*` | `fps`, `min_short_side_px`, `center_crop_px`, `t1_trim_s`, `t1_max_probe_s` |
   | `vad.*` | all |
   | `confounds.*` | all |
   | `transcribe.whisperx` | — |
   | `atlases.*` | all |
   | `localize.*` | all |

   Also extend `tests/test_frozen_keys` (or the existing guard) so that every config key read by `src/yct/{normalize,confounds,media}` must be frozen.
2. **QC count table.** Produce a P2 QC count table, `outputs/qc/p2_counts.md`. It is pooled, label-free and follows the D-060 precedent. Its columns are:
   - `loudnorm_mode` (linear or dynamic)
   - silent/ungated
   - `source_color_untagged`
   - BT.2020-SDR, a new derived flag computed from the P2 probe records
   - `hdr_source`
   - `gain_capped`
   - `upscaled`
   - 9:16
   - `low_fps_source`

   No split by group is allowed.
3. **Toolchain record.**
   - Write the `ffmpeg -version` string, the x264/zscale/swscale library versions and the binary sha256 into every new P2/P3 run dir.
   - Add a provenance field to `run_with_provenance`.
   - The executor recovers the wave-1 build from the existing run dirs. If it cannot be recovered, that is disclosed.

### 2. New ticket FIX-NORM-P4B (before the D-085 freezes and the P4b reference campaign)

Prerequisite for the campaign: these items are closed and reviewed by Watchdog and Neuro.

1. **SpeechProvider (S-24/S-23), test-first.** Write the tests before the implementation.
   - Trim each item to the −40 dBFS span before placement.
   - Resample 22.05 → 48 kHz with a band-limited resampler (soxr or polyphase).
   - Compute the RMS match, the `clip_audio` length gate and the uniform word times on the span.
   - Tests: duration == span; no nearest-sample path; BS.1770 reference value (997 Hz full scale = −3.01 LUFS).
   - This is a precondition of the D-085 part-2 freeze.
2. **Reference-clip colour tags (S-22).** Apply `color_tags()` (bt709/tv) to the reference clips **before** the D-085 part-1 freeze and `build1_sha_record`. If that is no longer possible, disclose it instead.
3. **`d_std` path (M-12b).**
   - Route `enh002.standardise` through `networks.spatial_standardize`, or delete it.
   - Add an AST/import test: the `KernelInputs.d_std` producer calls only M-12.
   - Disclose ENH-002's use of the duplicate (bit-identical on cortex).
4. **Envelope definition (A-21/R-ENV).** Write the definition into the T-ENV module:
   - |hilbert| of the per-clip z-scored 16 kHz sidecar;
   - low-pass at 10 Hz;
   - mean per 0.5 s bin;
   - mean onto the 1 s TR grid of A-01.

   Freeze it with `controls.refclips_d085.tenv` and `controls.regressors.speech_envelope`. The D-085 rule that the envelope "never gates in reference clips" is unchanged.
5. **Drift term (A-18).**
   - **If the owner approves Q1:** a pre-run D-071(a) amendment adds a Legendre-1 drift term to `controls.partial_out`.
   - **Otherwise:** intercept-only stays, and a drift variant is reported as a disclosed, non-gating sensitivity.
   - In both cases, nothing is added to the nuisance set after a FAIL.
6. **Second freeze commit pair.** Freeze these keys:
   - `controls.kernel.{window_tr, type, shift_by_L}`
   - `controls.readout_lag_tr`
   - `controls.partial_out`
   - `controls.regressors.{face, luminance_change, speech_envelope}`
   - the FFC, PH, AUD and V1_V3 area lists
7. **NAT build record.** Record the toolchain (FIX-NORM-0 item 3) in the NAT normalisation run dir.

**ROADMAP P4/P4b "Prerequisites" — add:** "FIX-NORM-P4B closed (R-11)."

### 3. New ticket FIX-NORM-P5 (before the first analysis-set W-average or readout; D-063 B2)

1. **H2 composite (M-20).**
   - Add the key `features.h2_areas`, hemisphere-explicit:
     - STSva, STSvp, STSdp, PGi and TE1a: both hemispheres;
     - 44 and 45: left only;
     - TGd excluded, with the reason it is excluded;
     - the reason STSda is excluded.
   - Pooling is a vertex-weighted mean on the standardised W-averaged map, as in M-15.
   - Add the code and a vertex-count test.
2. **Production CV (A-10/A-25/R-CV).** Put the code in `src/yct/stats/cv.py`:
   - 20 × StratifiedGroupKFold(5) by company;
   - nested C over `stats.cv.c_grid` (new key);
   - an in-fold StandardScaler on all columns, including binaries, refitted inside the nested loop and in every permutation;
   - for H4, AUC(M0) is computed on the linear Q columns plus `platform_nonYT` plus the era dummies.

   `features.h4_null_sim` must import this function.
3. **Estimation scope (A-17/R-SCOPE).** Implement R-SCOPE in `m0.py`:
   - `q_m0(subset_of=primary)` reuses the primary column definitions and the full-set z/median values;
   - aliased columns are dropped;
   - optional quadratics are dropped in reverse order down to ⌊N_sub/3⌋;
   - the descriptive fallback applies.

   Tests: S-LAG at N = 51; a subset at N = 25; YouTube-only (platform aliased).
4. **Freedman–Lane (A-15/R-FL).** The nuisance set is:
   - `[1, era dummy, platform_nonYT]`;
   - plus the first min(5, ⌊N/15⌋) PCs of the A-06 z-scored continuous linear M0, computed once and label-free.

   Add the code and a test.
5. **HDR (A-05).** Wire `hdr_source` (D-056b) into `m0.py`, using the existing `normalize.core.normalisation_covariates`. A constant column is omitted. Add a test.
6. **Pitch products (A-04).** Bar pitch from the optional product terms whenever `voiced_any` is non-constant. Add a test.
7. **Invariance tests (X-08).**
   - M-12 per-TR affine invariance: M1 is unchanged, and `spatial_sd` scales by a_t.
   - R is invariant to affine rescaling of M0 when no merge fires.
   - S-14 loud and quiet copies give equal sidecars up to gain.
   - A forced dynamic fallback is recorded in `loudnorm_mode`.
8. **Third freeze commit pair.** Freeze `features.*` (including `h2_areas`), `m0.*` and `stats.cv.*`. This happens **before** the first analysis-set W-average, with Watchdog sign-off.

**ROADMAP P5 "Tasks" — add:**
- "H2 composite per `features.h2_areas` (R-11)."
- "S-CENTRE: centre-only network means beside H1, descriptive, outside Holm (R-11)."

**ROADMAP P5 "Tests" — add:**
- "H2 vertex counts."
- "`d_std` uses M-12."
- "Affine-invariance tests (R-11)."

### 4. ROADMAP P2/P2b text edits

**Tasks**
- `Record a crop-coverage covariate.` → `~~Record a crop-coverage covariate.~~ Record crop coverage as descriptive QC (R-11; D-08x amends D-005; never in M0).`
- `Make 480p quality-floor copies.` → `~~Make 480p quality-floor copies.~~ q480 copies are still produced by the frozen code but have no consumer (R-11; deviation logged).`
- `Check A/V sync ≤40 ms.` / `Check mono phase.` → append ` (QC flag only)`.
- `Stratify 9:16 videos separately.` → `~~Stratify 9:16 videos separately.~~ Flag 9:16 (descriptive); portrait clips enter the S-QC exclusion sensitivity (R-11).`
- **Add:** `Record the ffmpeg/x264/zscale/swscale build (version + sha256) in every run dir; wave 2 uses the pinned build (R-11).`

**Tests**
- **Add:** `test_loudnorm` (BS.1770 reference value, forced dynamic fallback recorded, sidecar gain invariance).
- **Add:** `test_frozen_p2_keys`.

**DoD**
- **Add:** `Label-free pooled QC count table (loudnorm_mode, untagged, BT.2020-SDR, HDR, gain_capped, upscaled, 9:16) (R-11).`

### 5. ROADMAP P3 text edits
- **Add:** `speech_frac is reported as "audio-active fraction" (energy VAD; computation unchanged) (R-11).`
- **Add:** `Disclose: scene cuts on the full frame via PySceneDetect's decode; not recomputed (R-11).`
- **Add:** `M0b (when un-deferred): per-column centring on the training fold → PCA per block (3/2/2) → R-CV scaler; TRIBE layers [0.5, 0.75, 1.0], same group-mean and 256² crop (R-11).`

### 6. ROADMAP P4 text edits

**Add to Tasks**
- `Tail-invariance check on NAT clips (50 s vs 58 s truncation, W-mean ROI/network reliability ≥ 0.99), in the P4b NAT GPU session inside the D-084 projection; required before P6 (R-11).`
- `Repeat the label-free bt709 decode-patch test on the pod's moviepy/imageio-ffmpeg binary; record in tribe_requirements.md (R-11).`
- `Record neuralset frame padding before t = 0 in tribe_requirements.md (R-11).`

### 7. ROADMAP P5b edits
- Replace `(yct.features.h4_null_sim, dropped vs included term)` with `(yct.features.h4_null_sim calling the production src/yct/stats CV function: nested C, in-fold scaler on all columns refit per permutation, era dummies in the baseline; R-11)`.
- **Add:** `Permutation-geometry variant R* ← (I − H_Q)R*: report FPR for both; keep the current construction unless its FPR leaves 3.1–7.1% (R-11).`

### 8. ROADMAP P6 edits

**Add to the prereg contents**
- An estimation-scope section (R-SCOPE).
- R-CV.
- R-FL.
- The S-QC rule: one exclusion sensitivity outside α, run when any of the dynamic-loudnorm, upscaled, 9:16, HDR or BT.2020-SDR flags has a count ≥ 1, with a descriptive fallback.
- Secondary T3 without the clipped clips is descriptive only.
- Shared vmax for the group-mean maps.
- Group means, like the difference map, exist only after unblinding.

**Add to the gate**
- `CI guard: config + code diff of the P2/P3/P5/m0/stats subtrees against tag prereg-lock must be empty (R-11).`

### 9. ROADMAP T3 and localisation (P9) text edit
- `four-view maps for group means and the difference map` → append `; group-mean maps shown side by side share one vmax; group means exist only after unblinding (R-11)`.
- **Add:** `Report states H1/H2/LOC are compositional (relative to the cortical mean) and gives G alongside; opposite-sign networks are not independent findings (R-11).`

### 10. ROADMAP P9/P10 disclosure list (add)
- S-05, S-06 and S-14 are redundant for TRIBE. They exist for determinism, geometry and WhisperX/rms_db respectively.
- T3 is computed in the gamma domain (V-JEPA2's input space).
- SHINE runs without an aperture.
- There is no ICC handling on the LOC images.
- Scene cuts are computed on the full frame.
- Reference-clip tags, if S-22 missed the freeze.
- The z-scoring and residualisation are transductive and label-free.
- ENH-002 used the duplicate standardise.
- Pitch-imputation handling.
- Raw-map and S-CENTRE companions.
- The label × exclusion table at unblinding.

### 11. ROADMAP Waves edit
- After `**Wave 2+ (confirmatory/replication):** … analysed once each with the locked protocol.`, append: ` Wave 2 reruns P2–P5 with the frozen keys and the pinned toolchain; rules are frozen and values (z, medians, Q selection, merges, ⌊N/3⌋) are re-estimated within wave 2; no normalisation change applies to wave 2 alone (R-11).`

### 12. Revisions log (append)
- `- **R-11 (2026-11-22):** normalisation recheck (reviews/normalization_audit/; DECISIONS D-08x): tickets FIX-NORM-0 (P2/P3 key freeze, label-free QC counts, toolchain record), FIX-NORM-P4B (SpeechProvider span trim + band-limited resample, ref-clip tags, d_std via M-12, T-ENV envelope definition, controls kernel/readout/ROI/partial_out/regressor freeze; D-071(a) drift only on owner approval), FIX-NORM-P5 (H2 composite, production CV + C grid, estimation scope, Freedman–Lane, hdr_source, pitch-product bar, invariance tests, features/m0/stats freeze before any analysis-set W-average); crop coverage, 9:16, q480 and source metadata demoted to descriptive QC (amends D-005); one S-QC exclusion sensitivity; S-CENTRE companion; tail-invariance check; shared-vmax group maps.`

## Explicitly unchanged
The following stay as they are:
- D-071, except Q1;
- the W, S-LOWFPS and P4 run-set freezes;
- D-037's Q rule for the primary analysis;
- the T3 reuse rules (A-23);
- the D-085 two-part freeze order;
- all S-* analyses being outside α.
