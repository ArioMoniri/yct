# Gate P4-entry — Neuroscientist / TRIBE v2 (fresh context)

Reviewed at HEAD 421c7ef (packet commit; code = 15a7227). Read-only: git, grep, pytest, plus local reads of the label-free run artifacts. I did not decrypt anything, did not touch AWS, and did not read `data/sealed/`. The ENH-002 prediction `.npy` files are in S3 only, so all re-analysis below uses `outputs/runs/wave1p2b_20261118T002855Z/enh002_latency.json` (event courses per lag) and the `*.events.csv` / `*.segments.csv` files.

Targeted tests: `tests/test_tribe_word_events.py test_enh002_latency.py test_controls_config.py test_tribe_feature_cache.py test_tribe_offline.py` → 63 passed.

## Q1 verdict: **FIX (narrow)**

- **Full-model T1 + T3 inference (feature extraction + full predictions) may start** once C1–C3 below are met. The TRIBE usage is correct for both tracks: 58 s clips give one Audio chunk, one Video chunk and one 100-TR window (verified on 3/3 real clips in D-062: `chunks {Audio: 1, Video: 1}`, T = 58). The stack is pinned and offline. Gate 1 is bit-identical; Gate 2 passes at ≥ 0.999 with only Llama drifting. BUG-018 is irrelevant at 58 s anyway.
- **Ablations may not start yet.** No ablation code exists (`grep features_to_use|config_update` in src/scripts finds nothing), the ablation path was never run on the GPU (tribe_requirements §5 says "run in P0", but no P0 run did it), and the estimand is not specified (D3). Ablations are cheap because they re-predict from the cache in about 3 s per clip, so waiting for the spec costs nothing.
- **P4b controls must not be computed on any analysis-set prediction** until the Q4 specification and the re-derived kernels are fixed in a DECISIONS entry. This holds even though the controls are label-free: a control chosen after seeing it pass on the analysis data is no longer a falsification check.

Conditions before the first analysis-set extraction:
- **C1.** A resumable P4 batch driver exists: per-video skip if the cache entry exists, and per-video sync of the cache entry and predictions to S3 right after each video. About 104 clips × ~305 s ≈ 8.8 h of extraction exceeds `budget.max_hours_per_instance: 4`, and BUG-027's dead-man switch halts the box and loses everything not yet synced. All instances must be the same GPU type (A100-SXM4-40GB, as in D-062).
- **C2.** A hard per-video gate for T1/T3: exactly one Audio and one Video chunk, T == 58 ± 1, n_words == .tsv rows. v2.md:52 and ROADMAP require this as a test. Today run_clip only *records* `chunks` and fails on the word check only with `--bug018-word-fix` (D2).
- **C3.** yct_0644 is handled as in Q2.

## Q2 — yct_0644
Excluding it as source-unavailable is acceptable. It is label-blind, and the reason (source unavailable) is unrelated to content. Extraction is per-video and independent, though, so the cut-off does not need to be "before P4 starts". The cut-off should be **the first label-free cross-video computation**: W from the mean time course, the OOD distribution, M0 z-scores or the Q(M0) rank. Until then the video can still go through P2/P2b/P3/P4 on the same GPU type and stack. After that point it is excluded (N = 52, T1 51). Record the cut-off in DECISIONS now.

## Q3 — sources below 16 fps (yct_0626 12.54 fps, yct_0641 14.99 fps)
**Keep them, flag them, and run a sensitivity analysis that excludes them**, with a refinement and an amendment to the protocol text:
- **What V-JEPA2 actually sees.** It samples 64 frames over 4 s, i.e. 16/s, from the 30 fps CFR file. At 12.54 fps only about 50 of the 64 sampled frames are distinct (≈ 22 % duplicates); at 14.99 fps about 60 of 64 (≈ 6 %). With tubelet size 2, a duplicated pair has zero temporal difference inside the token, so the effect is a mild, content-independent loss of motion signal. It is not a failure mode. Frame interpolation (minterpolate) would be worse, because it synthesises out-of-distribution frames. Keep duplication.
- **The same aliasing affects M0.** `motion_energy_crop` is sampled at 10 fps from the duplicated 30 fps stream, so some frame differences are exactly zero and motion energy is biased low for these two videos. The flag must therefore also be disclosed beside M0, not only beside TRIBE.
- **Flag definition.** Pre-specify `low_fps_source = src_fps < stimulus.min_source_fps (16)`. Log the per-video label-free `vjepa_unique_frame_frac` (distinct source frames per 64-frame sample) for all videos. yct_0444 at 17.15 fps sits just above the threshold, and 23.976/24/25 fps sources also produce a few duplicates in the 30-CFR stream.
- **Sensitivity.** Excluding the flagged videos: same W, M0, Q rule, seeds and blocks; outside Holm; T3 survive/fragile rule; no α spent.
- **Protocol text.** v2.md:381 says sources "must be at least 16 fps". A DECISIONS entry should amend this to "should; sources < 16 fps are kept, flagged, and excluded in a pre-specified sensitivity", or the council must exclude them. Keeping them silently against a "must" is not acceptable.
- **Optional, non-blocking, label-free.** Decimate one non-analysis or reference naturalistic clip to 12.5 fps, re-upsample it to 30 CFR, run TRIBE, and report the prediction reliability against the original. That measures the effect directly, for about 5 GPU-min.

## Q4 — the low-level visual control for P4b

**What the dry run shows** (my reading of enh002_latency.json):

| Course | Raw, lags 0–3 | Standardised, lags 0–3 | Shape |
|---|---|---|---|
| Flash → V1–V3 | 0.069 | 0.060 | rises from −0.045 at lag −4 to a plateau of about 0.07 over lags 0…+4; positive-mass centroid ≈ +2.6 TR |
| Flash → MT+ | 0.18 | 0.46 | — |
| Flash → FFC | 0.23 | 1.25 | — |
| Flash → PH | 0.15 | 0.88 | — |
| Speech → AUD | 0.43 | 2.66 | positive-mass centroid ≈ +0.6 TR, i.e. *before* the centre of the ~4 s burst |

- The V1–V3 plateau is the 4 s V-JEPA2 clip window: a 1 s flash is present in every 0.5 s bin for about 4–5 s. That is why the "peak lag" of 4.0 TR (5/5) is not a latency.
- The flash response is **not retinotopic in TRIBE**: FFC > PH > MT+ ≫ V1–V3. This matches known issue #9 (mean-pooled V-JEPA2 tokens).
- A4 ∪ A5 now responds more to speech than to the flash (2.66 vs 0.15 standardised). The P0 problem, where the Destrieux A1/belt ROI responded more to the flash, is gone with the HCP ROI.

**Three artifacts in the dry run.** They do not change the qualitative conclusion, but they make the kernels unusable as fixed inputs:
1. **The 100-TR window boundary.** For event 5 (onset 95 s), flash − control is exactly 0.000 at lags +5…+8 (t = 100–103), and speech − control ≈ −0.05. TRIBE's second 100-TR window has no access to the first, so this is a hard context reset. Event 5 is therefore truncated.
2. **The 60 s chunk boundary.** Event 3 (onset 55 s) has its window 51–63 straddling the chunk boundary (`ref_flash.events.csv`: Audio/Video [0,60] + [60,60]): audio is z-scored per chunk, and V-JEPA frames are clamped at the chunk start. This is known issue #2, observed inside the dry run itself.
3. **No baseline correction.** Control subtraction leaves a large pre-onset offset, because the transformer head sees every flash in the 100 s window, so all TRs shift. As a result the standardised V1–V3 "peak-normalised" kernel has its largest absolute value at **lag −4 = −1.0**, and its post-onset maximum is only 0.48. `enh002.analyse` normalises by `max |·|`. Convolving a regressor with that kernel would mostly be convolving with a negative pre-onset baseline. `tests/test_enh002_latency.py:38` asserts `max(kernel) == 1`, which the real output violates; the test is synthetic and has no offset.

Also, only V1–V3 (flash) and AUD (speech) kernels were derived at all. There is **no FFC kernel and no MT+ kernel**, yet "one kernel per ROI" is required (v2.md:418). The talking-face clip has continuous speech and no event structure, so it cannot give an FFC kernel. Controls (a)–(d) were not run on any reference clip, and no localiser images or naturalistic reference clips have been sourced.

**Recommendation.** Switch the gating motion control to MT+, keep V1–V3 as a descriptive (non-gating) control, and reject the luminance-only kernel as the gating visual control. The reasons for rejecting luminance-only:
- (i) The model's flash response is dominated by FFC/PH, so a luminance control in V1–V3 tests nothing low-level.
- (ii) Luminance change is already partialled out of every control (D-039); it cannot also be the tested regressor without changing the design.
- (iii) The full-field white-on-black flash is out of distribution.

Keeping V1–V3 as the gate carries a known, mechanism-explained STOP risk (#9) that tests a property of V-JEPA2 pooling, not of our pipeline.

**Concrete pre-lock specification** (one DECISIONS entry plus config `controls:` plus tests, before the P4b lock and before any analysis-set control is computed):
1. **ROIs.**
   - `MT_plus` = HCP MT ∪ MST ∪ FST, bilateral, union medial wall: **139 fs5 vertices** (MT 38, MST 45, FST 56, counted on the cached atlas).
   - **Drop V4t** (29 vertices). It is the paper's EBA proxy (tribe_requirements §4), so in talking-head videos it would let body content pass a motion control. This was raised in G-D032 c3 G3 and is still open.
   - Keep `V1_V3` in config as descriptive only.
2. **Regressors and roles.**
   - (a) **gating** controls: face → FFC; **motion_energy_crop → MT_plus**; speech_envelope → AUD.
   - (a) descriptive: motion → V1_V3; luminance_change → V1_V3.
   - `partial_out` unchanged: face, motion, luminance_change, speech_envelope.
   - Pass thresholds unchanged.
3. **(b) Selectivity for faces: compare FFC with PH, not with V1–V3.** V1–V3 is hypo-responsive to everything in TRIBE, so "FFC > V1–V3" is near-guaranteed and not diagnostic. FFC vs PH is the paper-validated category contrast, and the two ROIs are matched in general visual responsiveness (flash: 1.25 vs 0.88). Report FFC vs V1–V3 alongside. Speech AUD > FFC on the audio-only run is unchanged.
4. **Reference clips v2** (synthetic, label-free; replaces the 120 s design for kernel derivation):
   - **Geometry.** Every clip is 58.0 s, 640×360, CFR 30: the T1 geometry, with one chunk and one window, so it has no boundary artifacts. Two events per clip, at onsets jittered per clip within 14–16 s and 34–36 s. At least 3 clips per event type (≥ 6 events). Seeded noise bed; matched control clip per bed.
   - **Event types:**
     - (i) 1 s full-field flash: luminance_change kernel, descriptive only.
     - (ii) **Motion bursts**: 1 s of coherent drifting texture or random dots on the same static texture, mean luminance and contrast matched frame by frame. This gives the MT+ and V1–V3 kernels.
     - (iii) **Face onsets**: 1 s static face images on a mid-grey background, with place and body images interleaved. This gives the FFC kernel, and the same clips serve as the (d) localiser. (d) uses the fixed lags 0–3 readout, not the kernel, so there is no circularity. Record the stimulus set and its licence; an fLoc-style set is one option.
     - (iv) Speech bursts, as now: AUD kernel.
   - **Kernel per ROI.**
     - Event-locked (clip − matched control) course at lags −4…+8, **minus the mean of that difference over lags −10…−5** (pre-leakage baseline, same clip).
     - Average the events, then normalise by the **maximum over lags 0…+8** (expected-sign peak, not `max |·|`).
     - Derive it on the map type the control uses (spatially standardised; raw reported).
     - Assert in a test that the normalised kernel's maximum lies in 0…+8 and equals 1.
   - **Convolution.**
     - Acausal: `x̂(t) = Σ_{k=−4..8} K(k)·r(t−k)` on the full 58 s regressor.
     - Indices t − k < 0 use edge replication (only t = 5–7 are affected).
     - The result is evaluated over W only.
5. **Naturalistic reference clips.** Source at least 5 label-free, licensed, non-YC naturalistic talking-head clips **before the P4b lock**. They are required for (a)'s < 15-video fallback, for the `low_sd_percentile` rule and for the OOD check. None exist yet.
6. **Order of operations.** DECISIONS entry → reference clips v2 on the same GPU type (about 12 × 58 s ≈ 1 h, roughly $2) → kernels frozen (sha256 into config) → only then compute P4b on the analysis set.

## Q5 — WER
WER does not block the start of P4 inference. It **blocks the P4b/prereg lock**, because the H2 language composite and M1 depend on transcript quality, and a bad WER would force re-transcription, which means new tsv hashes and re-extraction. Pre-specify the action now: if the mean WER on the 5 hand-checked transcripts exceeds 0.15 (or any single one exceeds 0.30), a DECISIONS entry is required before the lock, either re-transcription or a limitation with a sensitivity. The open **language-ID item (P1 c2 Neuro Q1)** belongs to the same block: 22/53 rows have language `UNKNOWN`, WhisperX ran with `--language en`, and no language check exists in src/. A label-free faster-whisper language-probability pass with the pinned 3.8.6 venv costs a few GPU-minutes. Its exclusion rule (p(en) < 0.8) must be fixed before the lock. It needs no re-extraction, because it only excludes rows.

## Q6 — ENH-008 caption flag
Not blocking for P4, because it does not change TRIBE's input. It **should be decided before the P5/prereg lock**. `text_frac` is already in `m0.never`, so M0 is unaffected, but burned-in captions or slides drive V-JEPA2 features and the ventral occipitotemporal (VWFA) region while Llama never sees them. Either implement the label-free OCR-free proxy (edge or text-region density in the 256² crop, as a QC flag plus a pre-specified sensitivity) or record it as a P9 limitation. I prefer the proxy, which costs a few hours of CPU code.

## Q7 — BUG-027
The fix is adequate for the cost exposure: the sweep runs at driver start and the dead-man switch halts the box after 20 min without a touch. It is **not adequate for an 8–9 h P4 run**, because a halt loses every un-synced extraction. This is condition C1: per-video S3 sync plus a resumable driver. Any session that finds the driver gone runs `lambda_gpu.py sweep` (already documented). Running the driver pod-side stays an owner decision.

## Q8 — other items before P4
See defects D1–D4 (D1–D3 are condition-level). Everything else can close before the P4b/prereg lock.

## Defects

| # | Severity | Defect | Fix |
|---|---|---|---|
| D1 | **Major (blocks P4 start)** | There is no P4 batch driver: no resumable per-video loop, no per-video S3 sync, no multi-instance plan. Extraction runs ~8.8 h against a 4 h instance cap. | Write `scripts/gpu_wave1_p4.py` with skip-if-cached, per-video sync of cache entry, predictions and metrics, the same GPU type across instances, and T3 run as a separate pass. |
| D2 | **Major (blocks P4 start)** | The v2.md:52 "exactly one Audio and one Video chunk per T1 clip" test does not exist (no test or gate in src/scripts/tests). run_clip records `chunks` but does not fail on it. The word/T check is enforced only with `--bug018-word-fix`. | In the P4 driver, fail any T1/T3 video unless chunks == {Audio: 1, Video: 1}, T == 58 ± 1, n_words == .tsv rows and finite. Add a CPU test on a synthetic metrics dict. |
| D3 | **Major (blocks ablations)** | Ablations are under-specified and unimplemented. ROADMAP says "audio, video, text+TTS" without saying single-modality or drop-one. "text+TTS" is wrong for our path: with `features_to_use` and injected .tsv no TTS occurs, so that label applies only to `text_path=` input. The `config_update` path was never run on the GPU. | Add a DECISIONS entry. (i) Ablations run on **T1 only**, from the archived cache, never re-extracting (FeatureStore re-hash must be unchanged). (ii) Run all 3 single-modality ([audio], [video], [text]) and all 3 drop-one combinations; the cost is seconds each. The pre-declared exploratory estimand is drop-one, and [audio] is the run that P4b(b) needs. (iii) Label the text run "text-only (pinned-ASR words at ASR timings; speech rate still present, known issue #8)", not "text+TTS". (iv) Before the batch, run a 1-clip GPU smoke: finite output, prediction differs from the full model, the log shows the removed extractor, and the cache hash is unchanged. Add a `--features` flag in run_clip that goes into the output provenance. |
| D4 | Major (P4b lock) | ENH-002 kernels are invalid as fixed inputs: there is no baseline correction, and the standardised V1–V3 kernel has its peak magnitude at lag −4 (−1.0). Event 5 is truncated by the 100-TR window boundary (exact zeros at lags +5…+8) and event 3 straddles the 60 s chunk boundary. There is no FFC or MT+ kernel. Normalisation by `max |·|` is used; the test checks only synthetic data. | Q4 items 4 and 6: 58 s reference clips, baseline over lags −10…−5, expected-sign peak over 0…+8, one kernel per gating ROI, test on the real-shape output. |
| D5 | Major (P4b lock) | V1–V3 is the gating motion ROI despite #9 and the dry run. MT+ includes V4t (body/EBA proxy). Face selectivity against V1–V3 is non-diagnostic. | Q4 items 1–3 (MT ∪ MST ∪ FST = 139 vertices; (b) FFC vs PH). Update `tests/test_controls_config.py` vertex counts. |
| D6 | Major (P4b lock) | No naturalistic reference clips (needed for (a) fallback, `low_sd_percentile` and OOD) and no localiser images for (d). | Source and pin by sha256 before the lock (Q4 item 5). |
| D7 | Major (before lock) | Carry-over P1 c2 Neuro Q1: no language ID despite 22/53 `UNKNOWN` and forced `--language en`. | Q5: label-free language-probability pass plus a pre-fixed exclusion rule plus a DECISIONS entry. |
| D8 | Minor (before lock) | Carry-overs. (a) P1 c2 Q4: burned-in bars are not detected (`bar_frac_in_crop`). (b) P0 c2 L1: the latency centroid sensitivity (W = [7, 47)) was neither adopted nor rejected. The dry run now gives visual centroid ≈ +2.6 TR and auditory ≈ +0.6 TR, so W = [5, 45) is defensible, but record the rejection. | (a) cropdetect flag; (b) a DECISIONS line. |
| D9 | Minor | Q3 protocol conflict: v2.md:381 "must be ≥ 16 fps" vs D-060 "keep". Aliasing of `motion_energy_crop` for the two low-fps videos is undisclosed. | Q3 amendment, plus a `vjepa_unique_frame_frac` log. |
| D10 | Minor | T3 has its own cache key, so its audio and text features are re-extracted although the audio is a stream copy and the transcript is identical. T3 − T1 therefore contains Llama re-extraction drift (≤ Gate-2 level, reliability ≈ 0.99998), not only the photometric change. | Disclose it in the T3 report, using the D-062 Gate-2 figures. |
| D11 | Minor (docs) | tribe_requirements §10:169 still says BUG-018 "GPU verification pending". §6:114-120 still attributes drift to "fp16 backbones" generally, although D-062 shows V-JEPA2 and w2v-BERT are bit-identical and only Llama drifts (P0 c2 L2). §5 says the ablation path was "run in P0"; it was not. The word_events.py docstring still says "GPU verification is PENDING". The config comments for PH (lateral occipitotemporal, not anatomical PPA) and MT_plus (V4t = EBA proxy) are missing (G-D032 c3 G3). | Edit the text. |
| D12 | Minor (T2, not in this gate) | Known issue #2 is unresolved and, per the ENH-002 data, the 100-TR window boundary is a hard reset. v2.md has no T2 boundary rule (known_issues §Implications 1 suggests ±5 TR). | Before any T2 run, add a DECISIONS entry: exclude output TRs within [−5, +5] of every 60 s chunk start and every 100 s window start (or add a boundary covariate). T2 stays out of this gate. |

Blockers for Q1, all narrow:
- **Before analysis-set extraction:** D1, D2 and the yct_0644 cut-off rule.
- **Before ablations:** D3.
- **Before the P4b lock:** D4–D7 and the WER action rule. They do not block extraction.
