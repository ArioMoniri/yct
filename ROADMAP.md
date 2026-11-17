# ROADMAP (living; v2)

This roadmap is the spec in `docs/prompts/v2.md`. The status values are TODO, WIP, GATE, GO and BLOCKED. When a result or problem changes the plan, the change is added here with an `R-n` id and recorded in `DECISIONS.md`. An R-n change is never edited out afterwards.

| Phase | Status | Owner (exec) | Gate reviewers |
|---|---|---|---|
| P0 Setup + TRIBE smoke | WIP | PI / Modeling | QA, Neuro, Watchdog |
| P1 Curation | TODO (blocked on `DATA_DECISION.md` for media download) | Curator | Referee, Biostat, Watchdog |
| P2 Normalisation + P2b transcripts | TODO | Preproc | QA, Neuro, Referee, Watchdog |
| P3 Stimulus + M0b features | TODO | Preproc | Referee, Biostat, Watchdog |
| P4 TRIBE inference + QC | TODO | Modeling | QA, Neuro, Watchdog |
| P4b Controls gate | TODO | Neuro | all 5 |
| P5 Features (blinded) | TODO | Neuro | Neuro, Biostat, Watchdog |
| P6 Prereg lock + human unblind | TODO | PI | all 5, unanimous |
| P7 Group stats | TODO | Biostat | Biostat, Referee, Watchdog |
| P8 Prediction | TODO | Biostat | Biostat, Referee, Watchdog |
| P9 Interpretation | TODO | Neuro | Neuro, Referee, Watchdog |
| P10 Report | TODO | Reporter | all 5 |

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
- Determinism run with an empty cache.

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
- Trim videos.
- Keep native aspect ratio, short side ≥256, CFR 30 fps.
- Record a crop-coverage covariate.
- Make 480p quality-floor copies.
- Check A/V sync ≤40 ms.
- Check mono phase.
- Speech-gated loudness normalisation.
- Stratify 9:16 videos separately.
- Run pinned WhisperX and write the `.tsv` files in TRIBE format.
- Purge stale caches before runs.

**Tests**
- `test_normalize`: ffprobe assertions.
- `test_no_padding`.
- `test_tsv_format`.
- `test_cache_purged`.

**DoD**
- 100% of videos pass, or each failure is logged as an exclusion.
- WER reported on 5 hand-checked videos.

## P3 — Stimulus features (M0) and generic encoder features (M0b)
**Tasks**
- Audio features: RMS, speech fraction, speech rate, pitch, music.
- Visual features: cuts, optical flow, luminance, contrast, faces, text.
- Crop coverage, caption flag, era.
- M0b backbone embeddings, time-averaged over window W.

**Tests**
- Feature values within range.
- Per-TR features aligned to the 1.0 s grid.
- M0b is deterministic.

**DoD**
- `confounds.parquet` and `m0b.parquet` written.
- Only label-free distributions produced.

## P4 / P4b — Inference and controls
**Tasks**
- Run all videos on T1/T2.
- Run ablations (audio, video, text+TTS).
- QC report.
- Set window W from the label-free mean time course.
- Positive and negative controls.
- OOD check.
- Reliability mask.

**Tests**
- `test_tribe_outputs`.
- `test_determinism` (empty cache).
- `test_controls`:
  - fusiform face-contrast d > 0.8;
  - STG speech-contrast d > 0.8.
  - If either fails, STOP.

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

**Tests**
- Parcel counts.
- Medial wall masked.
- Means not degenerate (guards against the [B1] regression).
- Features reproducible from cache.

## P6 — Prereg lock
- Fill in `docs/preregistration.md`.
- Tag `prereg-lock`.
- Unanimous council GO plus Watchdog PASS.
- The human issues `UNBLIND_TOKEN`.

## P7 / P8 — Statistics and prediction
**Before unblinding:** validate the pipeline on permuted labels.
- False-positive rate within 3.7–6.4%.
- Planted effects recovered.
- AUC ≈ 0.5.
- Leakage test passes.

**After unblinding:** run H4 (primary), then H1, H2, H3 and H4b (Holm-corrected family), then the exploratory analyses.

## P9 / P10 — Interpretation and report
- Results are tied to M0, M0b and the ablations.
- Figures show 4 views.
- Every number is generated from results files.
- Verdict for each hypothesis.
- Deviations listed.

## Revisions log (R-n)
- **R-1 (2026-11-17):** v1 to v2 after the council review. See `reviews/prompt_v1/` and DECISIONS D-001 to D-012.
- **R-2 (2026-11-17):** Infrastructure changes.
  - The EC2 pod is a t3.large, because the account vCPU quota is 16 and 14 are in use.
  - All GPU work runs on Lambda.
  - SSM `SendCommand` permission is pending from the human.
