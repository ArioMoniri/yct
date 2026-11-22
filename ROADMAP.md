# ROADMAP (living; v2)

This roadmap is the spec in `docs/prompts/v2.md`. The status values are TODO, WIP, GATE, GO and BLOCKED. When a result or problem changes the plan, the change is added here with an `R-n` id and recorded in `DECISIONS.md`. An R-n change is never edited out afterwards.

| Phase | Status | Owner (exec) | Gate reviewers |
|---|---|---|---|
| P0 Setup + TRIBE smoke | WIP | PI / Modeling | QA, Neuro, Watchdog |
| P1 Curation | TODO (blocked on `DATA_DECISION.md` for media download) | Curator (separate subagent) | Referee, Biostat, Watchdog |
| P2 Normalisation + P2b transcripts | TODO | Preproc | QA, Neuro, Referee, Watchdog |
| P3 Stimulus + M0b features | TODO | Preproc | Referee, Biostat, Watchdog |
| P4 TRIBE inference + QC | TODO | Modeling | QA, Neuro, Watchdog |
| P4b Controls gate | TODO | Neuro | all 5 |
| P5 Features (blinded) | TODO | Neuro | Neuro, Biostat, Watchdog |
| P5b Pipeline validation (permuted labels + synthetic H4 null; v2.2 B-D2) | TODO | Biostat | Biostat, Referee, QA, Watchdog |
| P6 Prereg lock + human unblind | TODO | PI | all 5, unanimous |
| P7 Group stats | TODO | Biostat | Biostat, Referee, Watchdog |
| P8 Prediction | TODO | Biostat | Biostat, Referee, Watchdog |
| P9 Interpretation | TODO | Neuro | Neuro, Referee, Watchdog |
| P10 Report | TODO | Reporter | all 5 |

## Waves (D-044, owner-approved split-sample design)
- **Wave 1 (discovery, exploratory):** everything collected until the current quota day ends → P2–P5 → P5b validation → owner unblinds wave 1 → exploratory P7/P8 → council roadmap review.
- **Lock:** prereg-lock tag; no protocol changes after it.
- **Wave 2+ (confirmatory/replication):** new videos only (collected after the lock), analysed once each with the locked protocol.

## P0 — Setup
**Tasks**
- Repo skeleton.
- `config.yaml` with schema.
- CI with pytest, ruff, gitleaks, and guards for prereg hash, append-only logs and frozen keys.
- Infra helpers:
  - `infra/pod_exec.sh` (SSM);
  - `infra/lambda_gpu.py` (budget, lifetime and reap guards);
  - heartbeat agent.
- Build the TRIBE environment on a Lambda A100: commit `af58661`, HF revision `f894e783`, `best.ckpt` sha256 checked.
- Smoke test on a 10 s clip.
- Impulse clip to measure latency.
- Determinism run (policy v2.5 C3 / D-038: cached rerun ≤ 1e-4, fresh re-extraction reliability ≥ 0.99).

**Tests**
- `test_infra_guards` ✅.
- `test_config_schema`.
- `test_ci_guards`: tamper the prereg or a log in a fixture, and the check must fail.
- `test_tribe_smoke`: shape (T, 20484); T within ±1 of duration/TR; values finite; peak VRAM logged.

**DoD**
- CI green.
- Smoke run directory exists with peak VRAM, runtime, TR and latency.
- `docs/tribe_requirements.md` UNVERIFIED items resolved, or tickets opened for them.

## P1 — Curation
**Tasks**
- Search and log queries in `data/search_log.csv`.
- Build `data/manifest.csv`. It has no outcome column.
- Write sealed labels.
- Store an evidence snapshot plus sha256 for every label.
- Run `verify_labels.py`.
- Log exclusions.
- Exclude pilot videos by hash.
- Identify within-company pairs.
- Define era strata.
- Record the discovery route r ∈ {OPEN, TARGETED} in `data/sealed/` only; the Curator builds the era × route exchangeability blocks (merged within route on total counts) and gives the analyst opaque block codes (D-040, v2.5 C3).
- Write the curation report.

**Tests**
- Manifest schema.
- No duplicates (perceptual hash and audio fingerprint).
- Every label has an evidence snapshot.
- Quotes match their snapshot verbatim.
- The A-rule is recomputed.
- No outcome column outside `data/sealed/`.

**DoD**
- At least 20 confidence-A videos per group. If there are fewer, the study becomes a descriptive pilot.
- MDE recorded for the achieved N.
- Fresh-agent re-derivation of 15% of labels agrees at κ ≥ 0.9.
- Human has spot-checked 10 rows.

## P2 / P2b — Normalisation and transcripts
**Tasks**
- Trim videos. The T1 clip is the first 58.0 s (ffprobe duration ≤ 58.5 s asserted) (v2.2 N-M1).
- Keep native aspect ratio, short side ≥292 px, CFR 30 fps (v2.2 B-D4).
- ~~Record a crop-coverage covariate.~~ Record crop coverage as descriptive QC (R-11; D-086 amends D-005; never in M0).
- ~~Make 480p quality-floor copies.~~ q480 copies are still produced by the frozen code but have no consumer (R-11; D-086; deviation logged).
- Check A/V sync ≤40 ms (QC flag only).
- Check mono phase (QC flag only).
- Speech-gated loudness normalisation.
- ~~Stratify 9:16 videos separately.~~ Flag 9:16 (descriptive); portrait clips enter the S-QC exclusion sensitivity (R-11; D-086).
- Run pinned WhisperX and write the `.tsv` files in TRIBE format.
- Purge stale caches before runs.
- Record the ffmpeg/x264/zscale/swscale build (version + sha256) in every run dir (`yct.provenance.toolchain_record`); wave 2 uses the pinned build (R-11; D-086).
- The P2/P3-consumed config keys (`normalize.*`, `stimulus.{fps, min_short_side_px, center_crop_px, t1_trim_s, t1_max_probe_s}`, `vad.*`, `confounds.*`, `transcribe.whisperx`, `atlases.*`, `localize.*`) are frozen at the wave-1 run commit (FIX-NORM-0 (R-11; D-086)).

**Tests**
- `test_normalize`: ffprobe assertions.
- `test_loudnorm` (BS.1770 reference value, forced dynamic fallback recorded, sidecar gain invariance) (R-11; D-086).
- `test_frozen_p2_keys` (R-11; D-086).
- `test_no_padding`.
- `test_tsv_format`.
- `test_cache_purged`.

**DoD**
- 100% of videos pass, or each failure is logged as an exclusion.
- WER reported on 5 hand-checked videos.
- Label-free pooled QC count table (loudnorm_mode, untagged, BT.2020-SDR, HDR, gain_capped, upscaled, 9:16) (R-11; D-086). Done for loudnorm_mode: 49 linear / 3 dynamic of 52 (`outputs/qc/p2_loudnorm_count.json`; owner Q2 rule: < 10% → frozen mode kept, S-QC sensitivity).

## P3 — Stimulus features (M0) and generic encoder features (M0b)
**Tasks**
- Audio features: RMS, speech fraction, speech rate, pitch, music.
- M0 assembly rules (v2.4 G-D032; `src/yct/features/m0.py`): W-averaging after W is frozen; no `text_frac`; label-free imputation; exclude no-audio / < 20 words in W (logged). Q(M0) by rule D-037 (`m0.q_m0`, v2.5 C3): all linear M0 + era, forced speech_rate², speech_fraction², speech_rate·speech_fraction, fixed-order quadratics to numerical rank ⌊N/3⌋ (SVD rcond 1e-8, cond ≤ 1e8), label-free merge list only if the linear + forced block exceeds it; no PCA.
- Visual features: cuts, optical flow, luminance, contrast, faces, text. Face regressor and face fraction inside the V-JEPA2 crop (v2.4 G-D032).
- Crop coverage, caption flag, era.
- Per-TR M0b backbone embeddings (W-averaging happens only after W is frozen in P4).
- `speech_frac` is reported as "audio-active fraction" (energy VAD; computation unchanged) (R-11; D-086).
- Disclose: scene cuts on the full frame via PySceneDetect's decode; not recomputed (R-11; D-086).
- M0b (when un-deferred): per-column centring on the training fold → PCA per block (3/2/2) → R-CV scaler; TRIBE layers [0.5, 0.75, 1.0], same group-mean and 256² crop (R-11; D-086).

**Tests**
- Feature values within range.
- Per-TR features aligned to the 1.0 s grid.
- M0b is deterministic.

**DoD**
- `confounds.parquet` and `m0b.parquet` written.
- Only label-free distributions produced.

## P4 / P4b — Inference and controls
**Prerequisites (hard, v2.5 C3)**
- BUG-003 closed: TRIBE checkpoint + the three backbones `snapshot_download`ed at the `tribe_requirements.md` §10 revisions; run_clip sets `HF_HUB_OFFLINE=1`; backbone revisions in the cache key / `_revisions()`; a no-network / revision-mismatch test passes.
- One GPU type for all of P4; the A10 only after the A100-equivalence test (v2.md §3).
- Content-addressed feature cache persisted off-pod with a sha256 manifest (D-038).
- FIX-NORM-P4B closed (R-11; D-086): SpeechProvider span trim + band-limited resample + span-based RMS/length/word times (S-23/S-24); one spatial-standardisation path (`networks.spatial_standardize`, M-12b); Legendre-1 drift in the (a) partial-out (owner Q1, `controls.partial_out_nuisance`); bt709/tv tags on the reference clips with a decoded-stream rebuild check (S-22); T-ENV speech-envelope definition (R-ENV, A-21); control keys frozen (A-19/A-20); toolchain record in the NAT run dir (X-02). Reviewed by Watchdog and Neuro.

**Tasks**
- Run all videos on T1/T2.
- Run ablations (audio, video, text+TTS).
- QC report.
- Set window W from the label-free mean time course: default W = [max(5, 4 + L + 1), that + 40) TRs, L = P0 impulse latency rounded up to whole TRs; videos with trimmed duration < W_end + 5 s are excluded from T1 (logged) and kept in T2 (v2.2 N-M2; `window.min_tail_s` = 5, D-039).
- Positive and negative controls.
- OOD check.
- Reliability mask.
- Tail-invariance check on NAT clips (50 s vs 58 s truncation, W-mean ROI/network reliability ≥ 0.99), in the P4b NAT GPU session inside the D-084 projection; required before P6 (R-11; D-086).
- Repeat the label-free bt709 decode-patch test on the pod's moviepy/imageio-ffmpeg binary; record in tribe_requirements.md (R-11; D-086).
- Record neuralset frame padding before t = 0 in tribe_requirements.md (R-11; D-086).

**Tests**
- `test_tribe_outputs`.
- `test_determinism`: cached rerun ≤ 1e-4 (exact expected); fresh re-extraction reliability ≥ 0.99 on ≥ 3 clips (D-038).
- Events dataframe holds exactly one Audio and one Video chunk per T1 clip (v2.2 N-M1).
- `test_controls`: implements v2.md §5 P4b (v2.2 B-D4, N-M4, N-M5):
  - ROI lists / regressors / kernel / readout in config `controls:` (`tests/test_controls_config.py`, v2.5 C3).
  - (a) within-video partial Pearson r (regressors inside the central 256×256 crop, convolved with the per-ROI measured impulse kernel with NO separate shift by L; luminance-change energy partialled out; nuisance = intercept + Legendre-1 drift (D-086, owner Q1, pre-run amendment of D-071 (a); `yct.controls.partial`); low-SD videos excluded, < 15 remaining → reference clips), Fisher-z one-sample t, mean z > 0.2 and p < .001;
  - (b) selectivity (FFC vs V1–V3 for face; AUD = HCP-MMP A4 ∪ A5 vs FFC for speech on the audio-only run), paired p < .01;
  - (c) between-video r > 0.3 and permutation p < .05 (FFC × face fraction; AUD × mean speech envelope);
  - (d) localiser replication (readout = mean of output lags 0–3 TR): FFC face > place and PH place > face, sign-consistent in both hemispheres.
  - ENH-002 dry run before the P4b lock, including a talking-face reference clip, 5 flashes and 5 speech bursts.
  - Any FAIL means STOP.

**DoD**
- `outputs/qc_report.html`.
- `controls_report.md`.
- GPU ledger reconciled.

## P5 — Features
**Tasks**
- Atlases (Schaefer CBIG annot, Yeo-7 derived from it, HCP-MMP).
- Medial-wall mask.
- Spatially standardised network means.
- Global amplitude G.
- ROIs.
- H2 composite per `features.h2_areas` (hemisphere-explicit, vertex-weighted on the standardised W-averaged map) (R-11; D-086).
- S-CENTRE: centre-only network means beside H1, descriptive, outside Holm (R-11; D-086).
- FIX-NORM-P5 (R-11; D-086), before the first analysis-set W-average or readout (D-063 B2): production CV `src/yct/stats/cv.py` (R-CV: 20 × StratifiedGroupKFold(5) by company, nested C over `stats.cv.c_grid`, in-fold StandardScaler on all columns refitted per permutation); R-SCOPE in `m0.py`; Freedman–Lane nuisance (R-FL); `hdr_source` wired into M0 (A-05); pitch barred from optional product terms (A-04); invariance tests (X-08); then freeze `features.*`, `m0.*`, `stats.cv.*` with Watchdog sign-off.

**Tests**
- Parcel counts.
- Medial wall masked.
- Means not degenerate (guards against the [B1] regression).
- Features reproducible from cache.
- H2 vertex counts (R-11; D-086).
- `d_std` uses M-12 (`tests/test_fixnorm_p4b.py`) (R-11; D-086).
- Affine-invariance tests (M-12 per-TR affine; R invariant to affine M0 rescale; loud/quiet sidecar) (R-11; D-086).

## P5b — Pipeline validation (before P6; section moved above P6 in v2.2 B-D4)
Validate the pipeline as in v2.md §5 P5b. All of these must hold:
- H4 null FPR on synthetic outcomes y* ~ Bernoulli(logit(g(M0))) (pre-specified nonlinear g, AUC(M0) ≈ 0.70, real M1; 500 replicates, B = 500, 5 repeats, full nesting) within 3.1–7.1%, plus the size outside the Q span (~~`yct.features.h4_null_sim`, dropped vs included term~~ `yct.features.h4_null_sim` calling the production `src/yct/stats` CV function: nested C, in-fold scaler on all columns refit per permutation, era dummies in the baseline; R-11). If H4 fails, never reduce Q: before P6 a DECISIONS entry may apply further merge-list steps; otherwise H4 is reported as not interpretable as "beyond M0" (v2.2 B-D2; v2.5 C3).
- H1–H3/H4b false-positive rate within 3.7–6.4% over 1,000 label shuffles.
- Planted effects: empirical power at d = 0.5, 0.8 and 1.06 within ±10 points of `analysis/power/h4sim.py` at the same N (pipeline-correctness check, not a power requirement) (v2.2 B-D3).
- AUC ≈ 0.5.
- Leakage test passes.
- Permutation-geometry variant R* ← (I − H_Q)R*: report FPR for both; keep the current construction unless its FPR leaves 3.1–7.1% (R-11; D-086).

## P6 — Prereg lock
- Fill in `docs/preregistration.md`. It must include (R-11; D-086): an estimation-scope section (R-SCOPE: wave 2 re-estimates values under frozen rules; T3/S-T1SHORT reuse T1; other S-* subsets reuse the primary column definitions and full-set z/medians, drop aliased columns, drop optional quadratics in reverse order down to ⌊N_sub/3⌋, else descriptive); R-CV; R-FL; the S-QC rule (one exclusion sensitivity outside α, run when any of the dynamic-loudnorm, upscaled, 9:16, HDR or BT.2020-SDR flags has a count ≥ 1, descriptive fallback; wave 1: 3 dynamic-loudnorm, 1 upscaled); secondary T3 without the clipped clips is descriptive only; shared vmax for the group-mean maps; group means, like the difference map, exist only after unblinding.
- Toolchain pin (X-02) and the tail-invariance check (X-07) done; M-02 and M-04 records in tribe_requirements.md (R-11; D-086).
- Tag `prereg-lock`.
- Unanimous council GO plus Watchdog PASS.
- CI guard: config + code diff of the P2/P3/P5/m0/stats subtrees against tag `prereg-lock` must be empty (R-11; D-086).
- The human issues `UNBLIND_TOKEN`.

## P7 / P8 — Statistics and prediction
**After unblinding:** run H4 (primary), then H1, H2, H3 and H4b (Holm-corrected family), then the exploratory analyses.

## T3 and localisation (v2.3; rules v2.4 G-D032)
- **P2:** produce photometrically normalised T3 copies (statistics on the V-JEPA2 crop; gain capped at `max_gain`; flagged clips kept and reported).
- **P4:** run TRIBE on T3, which doubles the inference count.
- **P5:** compute T3 features.
- **P7/P8:** H1 and H4 sensitivity analyses on T3, reusing T1 M0/Q/W/exclusions/blocks/seeds; outside Holm, no α; "survives" = same sign and p < .05, else "photometrically fragile"; T3 never turns a T1 null into a claim (v2.4 G-D032).
- **P9:** atlas peak-label tables (Schaefer/Yeo/best-overlap HCP-MMP/Destrieux) and four-view maps for group means and the difference map (group-mean maps shown side by side share one vmax; group means exist only after unblinding; R-11): T1 spatially standardised W-averaged maps only, fixed caption, claim-language lint, company-cluster BCa CIs + stability, BH-FDR q on the difference table, stippled unreliable vertices (v2.4 G-D032).
- Known TRIBE issues: docs/tribe_known_issues.md, reviewed at the P0 gate.
- Report states H1/H2/LOC are compositional (relative to the cortical mean) and gives G alongside; opposite-sign networks are not independent findings (R-11; D-086).

## P9 / P10 — Interpretation and report
- Results are tied to M0, M0b and the ablations.
- Figures show 4 views.
- Every number is generated from results files.
- Verdict for each hypothesis.
- Deviations listed.
- Disclosures (R-11; D-086): S-05, S-06 and S-14 are redundant for TRIBE (they exist for determinism, geometry and WhisperX/rms_db); T3 is computed in the gamma domain (V-JEPA2's input space); SHINE runs without an aperture; no ICC handling on the LOC images; scene cuts on the full frame; P4b (a) drift term added pre-run (D-071 (a) amendment, owner Q1); 3/52 analysis-set clips used dynamic loudnorm (S-QC sensitivity).

## Revisions log (R-n)
- **R-1 (2026-11-17):** v1 to v2 after the council review. See `reviews/prompt_v1/` and DECISIONS D-001 to D-012.
- **R-7 (2026-11-17):** v2.5 C3 after G-D032 cycle 2 and Phase 0 cycle 1 (ticket FIX-C3-SCI; DECISIONS D-037–D-041): Q(M0) rule D-037 implemented (`m0.q_m0`; all linear M0, forced speech quadratics, fixed-order quadratics to numerical rank ⌊N/3⌋, label-free merge list, no PCA) with the P5b dropped-term FPR simulation; determinism policy D-038; latency/timing D-039 (`min_tail_s` 5, no timing claims < 5 s, P4b redesign + `controls:` ROI lists); era × route blocks D-040; pinned revisions + `HF_HUB_OFFLINE` as a hard P4 prerequisite; one GPU type for P4; legible stipple (raster-tested), zeros masked not thresholded, medial-wall shrinkage columns.
- **R-6 (2026-11-17):** v2.4 after gate G-D032 (ticket FIX-D032-2; DECISIONS D-034): union medial wall (Schaefer ∪ HCP `???` ∪ Destrieux), crop-aware face regressor, M0 assembly rules (W-averaging, label-free imputation, no `text_frac`, speech rate + speech fraction forced into K_Q, rank ≤ ⌊N/3⌋, no-audio/<20-words exclusion), T3 crop statistics + `max_gain` cap + T3 analysis rules, localisation firewall (caption, claim lint, company-cluster BCa, stability, BH-FDR q, stippled unreliable vertices, best-overlap HCP). ENH-003 (subcortical) deferred.
- **R-8 (2026-11-17):** split-sample waves (D-044).
- **R-9 (2026-11-17):** v2.6 P1 after the Phase 1 gate (ticket FIX-P1; DECISIONS D-046–D-048): one confirmatory look = wave 2 (≥ 30 conf-A/group one-per-company, companies disjoint from wave 1, H4 underpowered < 50/group), waves 3+ replication; manifest `wave`, `collected_after_lock`, `era_block`, `platform_nonYT`, `upload_lag_days` + `tests/test_manifest_schema.py`; E1 + E2 → E12 (config `era_blocks`); forced M0 covariates platform_nonYT + upload_lag_days, YouTube-only sensitivity, one common re-encode in P2; label QC = re-derivation of ALL wave-1 conf-A rows + owner `scripts/owner_label_qc.sh` (κ, opaque block codes → SSM `/yct/owner/blocks`, 10-row spot-check); `check_blinding.py` URL scan; relative sealed checksums; corrected H4 MDE (0.50 power at N = 56; ~80% only at N ≈ 100).
- **R-5 (2026-11-17):** v2.3: T3 photometric sensitivity track and atlas localisation outputs (owner request; D-032).
- **R-4 (2026-11-17):** v2.1 → v2.2 after round-3 Biostat + Neuro reviews (reviews/prompt_v2/round3_*.md); DECISIONS D-023–D-028.
- **R-3 (2026-11-17):** v2 to v2.1 after the round-2 Watchdog and Referee reviews (`reviews/prompt_v2/`). See DECISIONS D-013 to D-022.
- **R-2 (2026-11-17):** Infrastructure changes.
  - The EC2 pod is a t3.large, because the account vCPU quota is 16 and 14 are in use.
  - All GPU work runs on Lambda.
  - SSM `SendCommand` permission is pending from the human.
- **R-10 (2026-11-17):** v2.7 FR after the final council round (tickets FIX-GD032-COND, FIX-P1-OPEN; DECISIONS D-053): P2/T1 BT.709 colour-matrix conversion + tags (`normalize.color`; wave-1 normalisation unblocked); unreliable-vertex mask = config `localize.reliability_mask` (dropout HCP areas, 732 vertices, hashed; default of tables/maps); `platform_nonYT` forced in M0, `upload_lag_days` sensitivity-only (S-LAG, S-PREDECISION); `upload_lag_days` filled by `fill_upload_lag` and validated; salted `company_key` used by analysis code; Q dimension table for 2 era blocks (N = 53: 17 = 16 required + 1 optional); wave-1 53-row totals and label-free MDE in v2.md §0; T3 H1 maxT-adjusted p; `scripts/verify_labels.py` (BUG-022) wired into the owner script; owner spot-check opt-in to stderr (BUG-021 root cause).
- **R-11 (2026-11-22):** normalisation recheck after the owner's request (council audit `reviews/normalization_audit/`: inventory of 81 transforms, five member reviews, chair synthesis; DECISIONS D-086). 90 verdict rows: keep 53, fix 16, clarify 9, add 8, remove 3 (crop coverage S-07, `stratum_9x16` S-08, q480 S-18 demoted to descriptive QC), n/a 1. Tickets FIX-NORM-0 (freeze the P2/P3-consumed keys at the wave-1 run commit; QC count table; toolchain record), FIX-NORM-P4B (blocking before the P4b reference campaign: speech span/resample/RMS, single M-12 standardisation path, owner Q1 Legendre-1 drift in the (a) partial-out, bt709 tags on the reference clips, R-ENV envelope definition, control-key freeze, NAT toolchain record) and FIX-NORM-P5 (before the first analysis-set W-average: H2 composite, production CV R-CV, R-SCOPE, R-FL, `hdr_source` wiring, pitch-product bar, invariance tests, `features.*`/`m0.*`/`stats.cv.*` freeze). Owner Q2: dynamic-loudnorm 3/52 (5.8%) < 10% → frozen mode kept, S-QC sensitivity. Owner Q3 (D-085): the YuNet gate stays broad.
