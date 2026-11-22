# Normalisation audit: chair synthesis

**Inputs.** This synthesis draws on `inventory.md` (S-01–S-33, M-01–M-22 including M-12b, and A-01–A-25) and on the five member reviews: `council_watchdog.md`, `council_referee.md`, `council_biostat.md`, `council_neuro.md` and `council_qa.md`.

**What the chair did not read.** Firewall D-063 B2 applies. The chair read nothing under `data/sealed/`, no labels and no transcripts, no analysis-set prediction array, and no analysis-set P2/P3 record. The only label-free facts cited are the pooled counts already in DECISIONS: D-060 records 0 HDR, 0 9:16, 1 upscaled, 1 untagged, 12 T3-clipped and 2 sources under 16 fps.

**Outcome-blind status today.**
- No analysis-set W-average, ROI, network or cross-video statistic exists.
- The P4b reference campaign has not run, and no reference output exists.
- So every change below is outcome-blind if it lands before those two events (column **OB = yes**).
- **OB = owner** means one of two things. Either the change amends frozen decision text (D-071 is frozen), or it changes the TRIBE inputs of wave-1 predictions that already exist, which needs a P2/P4 rerun and GPU spend. Either way it needs an owner decision.

Verdict labels: **keep**, **fix**, **remove** (demote to descriptive or QC, with no analytic consumer), **add**, **clarify** (keep the transform and disclose or re-label it). **(u)** marks a row that no member challenged. Votes are listed as W / R / B / N / Q (Watchdog, Referee, Biostat, Neuro, QA). A dash means the member did not address the row.

## 1. Per-normalisation verdicts

### 1a. Stimulus side

| ID | Consensus | Sev. | Votes W/R/B/N/Q | Required action | OB |
|---|---|---|---|---|---|
| S-01 SAR/rotation | keep (u) | — | –/–/–/–/– | none | yes |
| S-02 edge trim (both-dead) | keep (u) | — | –/–/–/–/– | none | yes |
| S-03 58 s T1 cap | keep | minor | –/–/–/keep/– | none. This is the key input normalisation: one chunk and one 100-TR window per clip. | yes |
| S-04 ≥ 50 s eligibility | keep (u) | — | –/–/–/–/– | none | yes |
| S-05 CFR 30 | keep | minor | keep/keep/–/keep/– | The methods must say it exists for determinism and is redundant for TRIBE. S-LOWFPS stays as frozen. | yes |
| S-06 short side ≥ 292, no bars | keep | minor | keep/keep/–/keep/– | The methods must say it is redundant for V-JEPA2's resize but fixes the geometry for the confounds and T3. | yes |
| S-07 crop coverage | **remove** (descriptive QC) | minor | clarify/remove/clarify/**fix**/remove | DECISIONS entry amending D-005: crop coverage becomes descriptive QC, and an optional P10 descriptive negative control (Biostat). It is never added to M0, because Q is at 16/17 of its rank budget at N = 51–53. Fix the v2.md P2 "confound" wording. **Dissent: Neuro** (add `crop_outside_area_frac` to M0 linearly). | yes |
| S-08 `stratum_9x16` | **remove** (descriptive) | minor | clarify/remove/clarify/remove/remove | Demote it by a DECISIONS entry. The portrait flag joins the S-QC flag set (X-04). The A-24 aspect negative control is kept. Wave 1 has 0 such videos (D-060). | yes |
| S-09 → BT.709/tv | keep | minor | keep/keep/–/keep/(add X-03) | Neuro's local test showed that the tag is what makes TRIBE's own decode correct. The BT.2020-SDR flag is handled under X-03. | yes |
| S-10 HDR tone-map | keep | minor | keep/fix(=A-05)/–/–/keep | The only gap is A-05. | yes |
| S-11 x264 encode | keep (u) | — | –/–/–/–/– | The build is pinned under X-02. | yes |
| S-12 audio resample/AAC | keep (u) | — | –/–/–/–/– | none | yes |
| S-13 energy VAD | clarify | minor | –/–/–/clarify/– | Rename `speech_frac` to "audio-active fraction" in the report and prereg before the Q freeze. The computation does not change (D-037 forces it into Q). Swapping in WhisperX coverage is rejected, because speech rate already carries the word information. | yes |
| S-14 speech-gated loudnorm | clarify | major | clarify/fix/keep/fix/keep | Keep the transform: it is correct, and needed for WhisperX and rms_db. (1) Take a label-free pooled count of `loudnorm_mode` (X-03; this follows the D-060 precedent for pooled flag counts). (2) A dynamic-mode count above 0 sends those clips into the S-QC exclusion sensitivity, outside α. (3) Add tests: a forced dynamic fallback must be recorded, and a loud and a quiet copy of the same signal must give equal sidecars up to gain (QA). (4) **Never change wave 2 alone** (Watchdog). A capped-pure-gain replacement applies to both waves or to neither: owner Q2. | yes for (1)–(3); **owner** for a changed mode |
| S-15 mono-phase | keep (QC only) | minor | –/keep/–/keep/– | Label it QC-only in v2.md and the ROADMAP. | yes |
| S-16 16 kHz sidecar | keep (u) | — | –/–/–/–/– | none | yes |
| S-17 A/V offset | keep (QC only) | minor | –/keep/–/keep/– | Label it QC-only. | yes |
| S-18 q480 copy | **remove** | minor | remove/remove/–/remove/remove | Drop it from the ROADMAP P2 tasks and DoD and log the deviation. The frozen code keeps producing it, so `normalize.*` stays identical for wave 2. The files stay as an unconsumed QC artefact. | yes |
| S-19 T3 gray-world/gain | keep (disclose) | minor | clarify/clarify/keep/keep/keep | Disclose that it works in the gamma domain, which is V-JEPA2's input space (Neuro). Pre-declare the secondary T3 analysis without the 12 clipped clips as descriptive only (W). | yes |
| S-20 T3 pooled report | keep (u) | — | –/–/–/–/– | none | yes |
| S-21 WhisperX | keep (u) | — | –/–/–/–/– | Freeze `transcribe.whisperx` under X-01. | yes |
| S-22 reference-clip tags | fix | minor | fix/clarify/–/fix/– | Apply `color_tags()` (bt709/tv) **before the D-085 part-1 freeze and rebuild sha record**. Doing it after would break the rebuild sha check. If it misses that window, disclose instead. It is numerically a no-op for grey content. | yes (if done before the part-1 freeze) |
| S-23 reference-audio RMS match | fix | major | (S-24)/fix/–/fix/fix | Compute the RMS match, length check and uniform word times on the −40 dBFS span. Add a BS.1770 reference-value test (997 Hz full-scale sine gives −3.01 LUFS). | yes |
| S-24 SpeechProvider | fix | major | fix/fix/–/fix/fix | Test-first: trim to the −40 dBFS span **before** placement. Resample 22.05 → 48 kHz band-limited (soxr or polyphase), never nearest-sample. Add a test that duration equals the span. This is a precondition of the D-085 part-2 freeze. | yes |
| S-25 ENH-002 clips | n/a (superseded) | — | – | Already not usable (D-063 Q4). Disclose that ENH-002 used the M-12b duplicate (L = 0 only). | — |
| S-26 LOC images, no ICC | clarify (disclose) | minor | –/clarify/keep/–/clarify | Disclose. | yes |
| S-27 SHINE without aperture | clarify (disclose) | minor | –/clarify/keep/–/clarify | Disclose. | yes |
| S-28 LOC twins | keep (u) | — | – | none | yes |
| S-29 MOT | keep (u) | — | – | none | yes |
| S-30 FLASH | keep (u) | — | – | none | yes |
| S-31 TALKFACE | keep (u) | — | – | Owned by D-085. | yes |
| S-32 NAT through P2 | keep (u) | — | – | Record the toolchain build (X-02) in the NAT normalisation run dir. | yes |
| S-33 stimulus QC | keep (u) | — | – | Owned by D-085. | yes |

### 1b. Model side

| ID | Consensus | Sev. | Votes W/R/B/N/Q | Required action | OB |
|---|---|---|---|---|---|
| M-01 per-chunk audio z | keep (u) | — | – | This is the reason S-14 is a no-op for TRIBE. | yes |
| M-02 TRIBE video decode | clarify | minor | –/–/–/clarify/– | Repeat the label-free tagged-patch vs bt709 decode test on the pod's actual moviepy/imageio-ffmpeg binary. Record the result in `tribe_requirements.md`. | yes |
| M-03 text summed per bin | keep (u) | — | – | none | yes |
| M-04 TR/offset | clarify | minor | –/–/–/clarify/– | Read how neuralset pads frames before t = 0 and record it in `tribe_requirements.md`. W start = 5 is exactly the minimum. | yes |
| M-05 relative units | keep (u) | — | – | none | yes |
| M-06 word events | keep (u) | — | – | none | yes |
| M-07 zero-fill ablation | keep | minor | –/–/–/keep/– | It is in-distribution, and the estimand difference is already disclosed. | yes |
| M-08 per-clip QC | keep (u) | — | – | none | yes |
| M-09 determinism | keep (u) | — | – | none | yes |
| M-10 fs5 vertices | keep (u) | — | – | none | yes |
| M-11 union medial wall | keep (u) | — | – | none | yes |
| M-12 per-TR spatial z | keep | minor–major | –/keep/keep/keep/keep | Add a per-TR affine-invariance test (QA). The report says H1, H2 and LOC are compositional, and reports G beside them (N, B). Add the **S-CENTRE** descriptive companion (X-05). | yes |
| M-12b `enh002.standardise` | fix | major | fix/fix/fix/fix/fix | Route it through `networks.spatial_standardize` or delete it. Add an import/AST test so that the `KernelInputs.d_std` producer can only call M-12. Disclose ENH-002's use of the duplicate: QA found it bit-identical on cortex, so there is no numerical effect. | yes |
| M-13 per-vertex-z ban | keep (u) | — | – | none | yes |
| M-14 W = [5, 45) mean | keep | minor | –/–/keep/clarify/– | Freeze the order "z per TR, then W-mean" as implemented (B). Add the **tail-invariance** check (X-07, N). | yes |
| M-15 network means, Limbic reference | keep | minor | –/keep/clarify/keep/keep | Wording: "relative to the cortical mean". Opposite-sign networks are not counted as independent findings (B). | yes |
| M-16 raw spatial SD | keep | minor | –/keep/keep/–/– | Its raw units are why A-10 scaling matters. | yes |
| M-17 G | keep | minor | –/–/keep/–/– | It is a mediator and never a covariate. | yes |
| M-18 parcel means | keep (u) | — | – | none | yes |
| M-19 control ROIs | keep (u) | — | – | The area lists are frozen under A-20. | yes |
| M-20 H2 composite | **fix** | **blocking** | fix-B/fix-maj/fix-B/fix-B/fix-B | Add `features.h2_areas` with hemisphere-explicit lists: 44 and 45 left only, TGd excluded, and why STSda is excluded (STSv = STSva + STSvp). Compute a **vertex-weighted** mean on the standardised W-averaged map, as in M-15. Add code, a vertex-count test, and a freeze before any analysis-set readout. | yes |
| M-21 unreliable mask | keep | minor | –/–/–/keep/– | none | yes |
| M-22 MW-shrink flag | keep (u) | — | – | none | yes |

### 1c. Analysis side

| ID | Consensus | Sev. | Votes W/R/B/N/Q | Required action | OB |
|---|---|---|---|---|---|
| A-01 confounds (full-frame scene cuts) | clarify (disclose) | minor | keep/clarify/keep/clarify/clarify | Disclose that scene cuts come from the full frame through PySceneDetect's own decode. Do not recompute: P3 has run, and a rerun would be a second fork. | yes |
| A-02 W-average | keep (u) | — | – | Code freeze under X-01. | yes |
| A-03 exclusions | keep | minor | –/–/keep/–/– | Give the label × exclusion table at unblinding. | yes |
| A-04 imputation | clarify | minor | –/–/clarify/–/– | Bar pitch from optional **product** terms when `voiced_any` is non-constant. The median choice is not neutral for I·x products. Fix this in a DECISIONS entry before the m0 freeze. | yes |
| A-05 `hdr_source` unwired | fix | minor–major | fix/fix(S-10)/fix/–/fix | Wire the D-056b conditional into `m0.py`. A constant column is omitted. Add a test. There is no wave-1 effect (0 HDR), but wave 2 may have HDR sources. | yes |
| A-06 M0 z-score | keep | minor | –/keep/keep/–/keep | Disclose it as transductive and label-free. Add an R-invariance-to-affine-M0 test when no merge fires (QA). | yes |
| A-07 merge list | keep | minor | keep/–/–/–/– | none | yes |
| A-08 Q(M0) | keep | minor | –/keep/–/–/– | none | yes |
| A-09 residualise once | keep | minor–major | –/keep/clarify/–/– | Add the P5b variant R* ← (I − H_Q)R* and report FPR for both (X-06). Keep the current construction unless its FPR falls outside 3.1–7.1 %. | yes |
| A-10 CV scaling / C grid | **fix** | **blocking** | fix-B/fix-B/fix-B/–/fix-B | See §2 rule R-CV. Write production code in `src/yct/stats` and have P5b call it. | yes |
| A-11 M0b | clarify | major | –/–/clarify/clarify/– | Prereg text (deferred by D-065): per-column centring on the training fold, then PCA per block (3/2/2), then the A-10 scaler. Use TRIBE's layers [0.5, 0.75, 1.0], the same group-mean and the same 256² crop. | yes |
| A-12 era blocks | keep (u) | — | – | none | yes |
| A-13 exchangeability | keep (u) | — | – | none | yes |
| A-14 multiplicity | keep (u) | — | – | none | yes |
| A-15 Freedman–Lane PCs | fix | major | fix/clarify/fix/–/fix | Nuisance = [1, era dummy, `platform_nonYT`] entered directly, plus the first min(5, ⌊N/15⌋) PCs of the **A-06 z-scored continuous linear M0**: centred, binaries and dummies excluded, computed once and label-free. | yes |
| A-16 effect sizes | keep (u) | — | – | none | yes |
| A-17 estimation scope | **fix** | **blocking** | fix-B/clarify/fix/–/fix-B | See §2 rule R-SCOPE. This is a chair ruling. Dissent is recorded there. | yes |
| A-18 P4b(a) nuisance (drift) | fix | major | **keep-frozen**/fix/fix/fix/fix | Add a Legendre order-1 drift term to `controls.partial_out` (1 df of 40). It only tightens the gate. Frozen D-071(a) text says "plus an intercept", so this is a **pre-run amendment** of the D-074 kind: owner Q1. **Dissent: Watchdog** keeps intercept-only as frozen and reports drift only as a disclosed sensitivity. Either way, drift is never added after a FAIL. The p for (a) is already specified as the across-video Fisher-z one-sample t (QA's request is satisfied by D-071). | **owner** (frozen text; OB in substance) |
| A-19 kernel keys | fix | major | fix/fix/fix/fix/fix | Freeze `controls.kernel.{window_tr, type, shift_by_L}`. | yes |
| A-20 readout and ROI lists | fix | major | fix/fix/fix/fix/fix | Freeze `controls.readout_lag_tr` and the FFC/PH/AUD/V1_V3 area lists. | yes |
| A-21 speech envelope | fix | major | fix/fix/fix/fix/fix | Fold it into the D-085 **T-ENV** precondition. The chair's definition: \|hilbert\| of the 16 kHz sidecar after per-clip z-scoring (one chunk = one clip; TRIBE's input space, per N), low-pass 10 Hz (R), mean per 0.5 s bin, then mean to the 1 s TR grid of A-01. Freeze it with `controls.refclips_d085.tenv` and `controls.regressors.speech_envelope`. **Dissent: Referee** wanted the broadband envelope without the z-step. The chair chose the z-step because TRIBE never sees absolute level, so a level-tracking (c) would not test the model. | yes |
| A-22 map scales / group means | fix | minor | fix/clarify/fix/–/– | Show group-mean maps side by side on one shared vmax. Single maps keep their own scale. Fix v2.md l.153: group means also need labels, so they exist only after unblinding. | yes |
| A-23 T3 reuse rules | keep (u) | — | – | Consistent with R-SCOPE. | yes |
| A-24 negative controls | keep (u) | — | – | none | yes |
| A-25 P5b validates a re-implementation | fix | major | –/add/–/–/fix | P5b must call the production A-10 function: nested C, StratifiedGroupKFold × 20, in-fold scaler, and era dummies in the baseline. | yes |

### 1d. Cross-cutting and added items

| ID | Consensus | Sev. | Votes W/R/B/N/Q | Required action | OB |
|---|---|---|---|---|---|
| X-01 freeze coverage (N1) | **fix** | **blocking** | fix-B/fix-B/add/–/fix | Two-commit freeze with a guard test. **Now:** the P2/P3-consumed keys `normalize.*`, `stimulus.{fps, min_short_side_px, center_crop_px, t1_trim_s, t1_max_probe_s}`, `vad.*`, `confounds.*`, `transcribe.whisperx`, `atlases.*` and `localize.*`, all byte-identical to b24fc1c. **Before the P4b campaign:** the A-19/A-20/A-18/A-21 control keys. **Before the first analysis-set W-average** (D-063 B2, the strictest reading, per W): `features.*`, including `h2_areas`, and `m0.*`, after the A-04/A-05/A-17 edits. | yes |
| X-02 toolchain pin | add | major (B for the lock) | add-B/–/–/–/– | Record the ffmpeg/x264/zscale/swscale version string and binary sha256 in every P2/P3 run dir, as `refclips_build` already does. Pin it for wave 2. Recover the wave-1 build from provenance (exec task; the chair did not touch the pod). | yes |
| X-03 P2 QC count table | add | major | (S-14)/(S-14)/add/add/add | Pooled and label-free (D-060 precedent): `loudnorm_mode` linear/dynamic, silent/ungated, `source_color_untagged`, BT.2020-SDR (new flag, QA), `hdr_source`, `gain_capped`, `upscaled`, 9:16. No group split before unblinding. | yes |
| X-04 S-QC sensitivity and source metadata | add | major | clarify/add-maj/–/(S-14)/– | Source bitrate, codec, fps and resolution are descriptive only; amend v2.md P2. Add **one** pre-declared S-QC exclusion sensitivity, outside α: drop every video flagged dynamic-loudnorm, upscaled, 9:16, HDR or BT.2020-SDR. It runs if any flag has a count ≥ 1, following the S-LOWFPS precedent, and is subject to the R-SCOPE descriptive fallback. This replaces the separate S-QUALITY, S-AUDIOLINEAR and portrait-drop proposals with one fork. | yes |
| X-05 S-CENTRE | add | major | –/(M-12 raw means)/add/–/– | Centre-only network means (no SD division) beside H1, with Hedges g. Descriptive, outside Holm. Add the raw `spatial_sd` group difference at unblinding. | yes |
| X-06 P5b permutation geometry | add | minor | –/–/add/–/– | See A-09. | yes |
| X-07 tail invariance | add | major | –/–/–/add/– | Label-free GPU check: NAT clips truncated at 50 s vs 58 s must give W-mean ROI and network reliability ≥ 0.99. Run it in the P4b NAT session inside the D-084 projection. It is required before P6, not before P4b. | yes |
| X-08 invariance tests | add | major | –/–/–/–/add | M-12 per-TR affine; A-06/A-09 M0 rescale; S-14 loud/quiet sidecar plus dynamic-mode recording; S-23 BS.1770 reference value. | yes |
| X-09 crop sharpness | add (optional) | minor | –/add/–/–/– | Optional descriptive covariate for T3 and S-QC. Never in M0. It can be deferred to P10 without loss. | yes |

**Counts (90 rows):** keep 53 (33 of them unchallenged), fix 16, clarify 9, add 8, remove 3, n/a 1.

## 2. Chair rulings on the open specification points

**R-CV (A-10, A-25; unanimous where addressed).**
- The H3, H4 and H4b L2-logistic runs inside 20 × StratifiedGroupKFold(5), with groups = company.
- C comes from a nested inner CV over a C grid set in a new config key `stats.cv.c_grid`, which is frozen.
- In every outer training fold, a `StandardScaler` is fitted on the training rows only. It is applied to **all** design columns, binaries included (B, Q). It is refitted inside the nested C loop and in every permutation.
- **H4 design matrices.** AUC(M0) uses the linear M0 columns as they enter Q (after any merges), plus `platform_nonYT` and the era dummies, without Q's quadratic terms (R, Q). AUC(M0 + R) uses those columns plus the 7 R columns.
- **H3** uses M1.
- The P5b `h4_null_sim` must import this function. QA found that it currently uses a fixed λ, StratifiedKFold and no era dummies.

**R-SCOPE (A-17).**
- *Wave 2:* the rules are frozen and the values are re-estimated within wave 2. That covers the z-scores, imputation medians, Q term selection, merges, ⌊N/3⌋, and any era dummy that aliases (dropped by the numerical-rank rule). This position was unanimous among the members who addressed it.
- *T3 and S-T1SHORT:* reuse the T1 values unchanged, as already specified.
- *Other S-\* subsets* (S-LOWFPS, S-LAG, S-PREDECISION, YouTube-only, OPEN, S-QC):
  1. Reuse the primary analysis's Q **column definitions** (term list and merges) and its full-set z-scores and medians. These are affine-neutral, per B.
  2. Drop columns that alias on the subset rows by the existing rank rule.
  3. If the rank still exceeds ⌊N_sub/3⌋, drop optional quadratics in reverse primary order. Forced terms are never dropped.
  4. If the linear + forced block alone exceeds ⌊N_sub/3⌋, report the subset descriptively, with effect and CI and no p.
  5. S-LAG = primary Q plus its 2 forced lag columns, under the same step 3.
  6. Tests: S-LAG at N = 51 and a subset at N = 25. QA showed that re-running the full rule crashes at N ≤ 38.
- *Dissent:* Referee and Biostat preferred a full rebuild per subset. The ruling keeps their ⌊N_sub/3⌋ budget and drops only the re-selection that QA showed to be unstable.

**R-FL (A-15)** and **R-ENV (A-21)** are as stated in the table rows.

## 3. Blocking items

**Before the P4b reference campaign.** Every item is outcome-blind, because no reference output exists yet.
1. **S-24/S-23:** SpeechProvider span trim, band-limited resampling, and RMS, length and word times computed on the span, with tests. This is a precondition of the D-085 part-2 freeze.
2. **M-12b:** the `d_std` producer is pinned to `networks.spatial_standardize`, with an AST/import test.
3. **A-19, A-20:** freeze rows for `controls.kernel.{window_tr, type, shift_by_L}`, `controls.readout_lag_tr` and the four ROI area lists.
4. **A-18:** owner ruling (Q1), then freeze `controls.partial_out` and `controls.regressors.{face, luminance_change}`.
5. **A-21:** the envelope definition is written into T-ENV and frozen with `regressors.speech_envelope`.
6. Sequencing, not blocking: **S-22** tags must land before the D-085 part-1 freeze, or be disclosed instead. **X-02** build record in the NAT P2 run dir.

**Before P5** (before the first analysis-set W-average or readout, D-063 B2):
1. **X-01:** freeze the P2/P3-consumed keys. Do this now.
2. **M-20:** H2 composite key, code, test and freeze.
3. **A-10/A-25:** production CV code (R-CV) plus the `stats.cv.c_grid` key, which P5b calls.
4. **A-17:** R-SCOPE written as a DECISIONS entry, with tests.
5. **A-15:** Freedman–Lane specification.
6. **A-05:** `hdr_source` wiring with a test. **A-04:** pitch-product bar.
7. **X-01 (second part):** freeze `features.*` and `m0.*` after items 2–6.
8. **X-03:** label-free QC count table. It decides whether S-QC runs, and feeds owner Q2.

**Before the P6 lock:**
- X-02 toolchain pin.
- X-07 tail invariance.
- M-02 and M-04 records.
- CI diff guard: the P2/P3/P5/m0 subtrees must be empty against `prereg-lock`.

## 4. Owner questions

Only these are the owner's:

- **Q1 (frozen text).** D-071(a) specifies "plus an intercept". Should the council amend it before the run, adding one Legendre-1 drift term to the P4b(a) partial-out? This is outcome-blind: no reference output exists, and the change only makes PASS harder. The alternative keeps intercept-only, with drift as a disclosed non-gating sensitivity.
  - Votes: amend 4 (R, B, N, Q); keep 1 (W).
  - The chair recommends amending.
- **Q2 (rerun cost).** If the X-03 count shows many dynamic-loudnorm clips, should a capped pure-gain mode be adopted for **both** waves? That means re-running P2 → P4 for wave 1, with GPU spend under the D-084 projection rule. The alternative keeps the frozen mode and uses the S-QC exclusion sensitivity only.
  - The council's position: no change for wave 2 alone.
  - The chair recommends sensitivity-only unless the dynamic count is ≥ 10 % of the analysis set.

The chair resolved the other contested points on the members' recommendations: S-07, A-17, A-21 and the S-QC merge. They are methodology decisions and are listed with their dissent for the FIX-NORM gate review.
