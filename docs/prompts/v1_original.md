# TRIBE v2 × YC Application Videos — Agent Prompts (v1, as supplied by the user)

Three prompts: A (find & classify videos), B (normalise + run TRIBE v2), C (master: roadmap, TDD, DoD, agent council, debug/enhance loops). C is used for the full run.

---

## Prompt A: Find and classify videos

ROLE: Data Curator. Tests whether TRIBE v2 predicted brain responses differ between ACCEPTED and REJECTED YC application videos.

GOAL: labelled, deduplicated, documented set of PUBLIC YC application videos. Target ≥30 per group (stretch ≥50). Class balance and label quality over volume.

RULES: only founder-posted public videos; never private/unlisted; follow platform ToS; data/raw/ research-only, never redistribute. Record every source URL. Never fabricate or guess a label.

STEP 1 SEARCH (log each query + result count in data/search_log.csv): YouTube/Vimeo ("YC application video", "Y Combinator application video", "our YC video accepted", "rejected YC application video", "YC interview video W24/S24…" looping batches W2012→current); X/Twitter, LinkedIn, HN (Ask/Show HN) posts sharing video + outcome; Reddit r/ycombinator, r/startups; founder blogs/Medium/Substack; public playlists (verify each).

STEP 2 LABEL (data/manifest.csv): video_id, url, platform, title, upload_date, claimed_batch, company_name, founders, outcome {accepted,rejected}, label_confidence {A,B,C}, evidence_url, evidence_quote (≤15 words), later_accepted, duration_s, language, n_speakers_on_screen, is_original_application_video, notes.
Confidence: A accepted = in YC directory with matching batch AND ≥1 founder match; A rejected = founder explicitly says THIS video was rejected AND company not listed for that batch. B = founder states outcome, not cross-checked. C = implied; excluded from primary.
Label by application cycle; a company rejected S21 and accepted W22 gets two rows if both videos exist.

STEP 3 INCLUSION/EXCLUSION: include actual application video (~1 min, founders talking), English, audio. Exclude >3 min, post-hoc promos/trailers, re-uploads/duplicates (perceptual video hash + audio fingerprint), interviews, demo-day pitches, no audio. Log exclusions in data/exclusions.csv.

STEP 4 DOWNLOAD: yt-dlp best quality → data/raw/<video_id>.<ext>; sha256; ffprobe metadata → data/raw_probe.csv.

STEP 5 BALANCE/BIAS REPORT (data/curation_report.md): counts outcome×confidence×batch year; duration, n founders, aspect distributions per group; biases (survivorship, YC format drift, accepted founders publicise more); matched subset (batch year ±1, duration ±15 s, n founders).

DoD: manifest schema pytest; every row has url, evidence_url, confidence; no duplicates; ≥30 conf-A per group OR shortfall report proposing B; curation report. Stop if <15 conf-A per group.

---

## Prompt B: Normalise + run TRIBE v2

INPUT manifest + raw; conf A only (B if config says).
STEP 0: read official TRIBE v2 repo/README/config; record in docs/tribe_requirements.md with file/line refs: input formats (fps, res, audio rate, transcript/word events), TR/output rate, output mesh (expected fsaverage5, 20,484 vertices; verify). Don't hardcode from memory. Pin repo commit + weights checksum in config.yaml.
STEP 1 TRIM: leading/trailing black (blackdetect) and silence (silencedetect −50 dB, 0.5 s); log.
STEP 2 FORMAT: mp4, H.264 libx264 veryfast CRF18, yuv420p; CFR 30 fps unless TRIBE needs other; scale-to-fit 1280×720 + pad, never crop; record aspect + padding fraction. Audio −23 LUFS two-pass loudnorm, TP −1 dBTP, AAC 48 kHz, sidecar WAV at TRIBE rate (e.g. 16 kHz mono). Duration: T1 primary first min(dur,60 s), drop <30 s; T2 full length → 50 progress bins.
STEP 2b: quality floor (downscale to e.g. 480p then up to 720p, primary); A/V sync ≤40 ms after CFR; stereo→mono phase cancellation (>3 dB drop); speech-gated loudness, flag music; strip platform intros/outros/end cards/watermarks; flag burned captions/on-screen text; 9:16 separate stratum; float32, fixed batch size.
STEP 3 TRANSCRIPTS: WhisperX word timestamps in TRIBE format; JSON per video; hand-check 5 for WER; same ASR for all; no platform captions; WER + accent flag covariates.
STEP 4 RUN: same commit/weights/device/seed; resumable batches; float32 .npy (T,20484) outputs/preds/<track>/<id>.npy + JSON sidecar (model hash, input hash, TR, T, runtime). Modality ablations audio-only/video-only/text-only if API supports; document.
STEP 5 QC: no NaN/Inf; shape; T = dur/TR ±1; outliers >4 SD investigated; rerun 3 videos max abs diff ≤1e-4; mean time course edge plot → n_drop_start (default 6 s) / n_drop_end (default 3 TRs).
TESTS FIRST: test_normalize.py, test_tribe_outputs.py, test_determinism.py.
DoD: tests green; outputs/qc_report.html; config frozen; no silent drops.

---

## Prompt C: Master

QUESTION: Do TRIBE v2 predicted responses distinguish ACCEPTED from REJECTED YC videos, beyond plain audio/visual features?

0 CONTEXT: pilot 1 vs 1: rejected ~12% higher mean |BOLD|; accepted > rejected in STS & anterior temporal/temporal pole; rejected > accepted occipitotemporal early and scattered frontoparietal; both spike at end. Flaws: N=1, |BOLD|, no per-video normalisation, edge artifacts, arbitrary top-5%, no atlas, no confound control, different lengths.

1 HYPOTHESES (prereg before any group comparison): H1 parcel/network features differ (FDR q<.05). H2 accepted > rejected in language/social networks (STS, TP, IFG, TPJ), directional. H3 brain classifier AUC>.5 (perm p<.05). H4 KEY: ΔAUC(M2−M0) 95% bootstrap CI excludes 0. Nulls are valid.

2 AGENT COUNCIL: PI/Orchestrator, Data Curator, Preprocessing Eng, Modeling Eng, Neuro Analyst, Statistician, Skeptic/Red Team (STOP on leakage/confound), QA (merge blocked on red), Reporter. Gate protocol: packet → per-role GO/FIX/STOP review → GO needs no STOP + majority GO; FIX → ticket + re-gate; Skeptic/Statistician STOP blocks; PI logs DECISIONS.md; max 3 FIX cycles then escalate to human.

3 ENGINEERING: TDD (never weaken a test; QA vote to change); config.yaml, no magic numbers; seeds, requirements.lock, TRIBE commit + weights hash; sha256 in data/hashes.csv; layout src/{curate,normalize,transcribe,tribe_run,features,confounds,stats,predict,interpret,report}, tests, data, outputs, reviews, docs, config.yaml, DECISIONS.md, BUGS.md, CHANGELOG.md; JSON logs; blinding with shuffled labels until Phase 6 GO.

4 DEBUG/ENHANCE LOOP: log BUGS.md/ENHANCEMENTS.md → minimal repro + failing regression test → root cause (hypothesis, evidence, ruled out) → fix + full suite → rerun stale downstream by hash → before/after metrics, re-gate. Enhancements: state expected effect + measure; revert if no gain; post-unblinding only as EXPLORATORY.

5 ROADMAP
P0 Setup: skeleton, env, CI (pytest+ruff), config, TRIBE requirements doc; TRIBE smoke on 10 s clip. Gate QA, Modeling.
P1 Curation (as Prompt A); ≥30 conf-A per group or PI approves B w/ sensitivity; matched subset. Gate Curator, Skeptic, Statistician (MDE at 80% power).
P2 Normalisation (as Prompt B). Gate Preproc, QA, Skeptic.
P3 Transcripts + confounds: audio RMS, speech fraction, rate, pitch mean/var, music; visual cuts (PySceneDetect), optical flow, luminance, contrast, face fraction/count, on-screen text; global duration, n founders, aspect, year. confounds.parquet + confound-only group-difference table. Gate Skeptic, Statistician.
P4 TRIBE inference T1/T2 + ablations; QC; edge handling. Gate Modeling, QA.
P5 Features (blinded): drop edges; signed raw + per-video per-vertex z-scored; Schaefer-400/7 primary, Yeo-7, Destrieux on fsaverage5 (verify; nearest-vertex; coverage test); per parcel/network mean, SD, peak, time-to-peak, AUC above baseline, thirds; global signal covariate. Gate Neuro, Stat.
P6 Prereg lock: hypotheses, primary features/track/version/atlas, tests, corrections, covariates, CV, metrics, exclusions, SESOI; commit hash in DECISIONS.md; unanimous GO; then unblind.
P7 Group stats: per-network/parcel 10k permutations; Hedges g + bootstrap CI; BH-FDR; covariate LM per parcel (duration, speech_rate, cuts, motion, face_fraction, loudness, aspect, batch_year, global_signal); vertex TFCE/cluster; temporal cluster perm on T2 bins; ablations; sensitivity (matched, A only, T2, raw vs z, leave-one-year-out); planted-effect recovery + null FPR ≤5%. Gate Stat, Skeptic.
P8 Prediction: M0 confounds, M1 TRIBE, M2 both; L2 logistic + linear SVM; nested CV outer stratified 5-fold ×10 grouped by company (+LOYO), inner tunes C; everything inside folds; AUC, balanced acc, 1000-perm AUC test, ΔAUC bootstrap; leakage test; shuffled AUC≈.5; deterministic. Gate Stat, Skeptic.
P9 Interpretation: networks + anatomical labels; optional NiMARE/Neurosynth; link to stimulus features; no reverse inference; "predicted response".
P10 Report HTML/PDF, all numbers generated; build fails on missing result; pilot claims confirmed/not.

5b EXPERT ADDITIONS (take precedence)
Engineering E1–E8 (quality-matched copies; A/V sync; mono phase; speech-gated loudness; strip intros/outros, caption covariate; 9:16 stratum; float32 fixed batch, runtime; one ASR, WER + accent).
Biostat B1 within-company pairs (paired test). B2 mixed model, company random effect. B3 primary = 7 Yeo networks + ≤5 ROIs; parcels secondary; gatekeeping; PCA only inside folds. B4 MDE (~d=0.73 for 30/group), SESOI + TOST. B5 two estimands (unadjusted total, adjusted); VIF>5 → PCs. B6 Freedman–Lane. B7 block perm / phase randomisation for time courses. B8 spin tests. B9 20% locked holdout stratified by outcome/year. B10 case-control: no PPV. B11 A vs A+B; label-flip simulation 5/10%. B12 two coders, κ≥0.7. B13 year matching, year×outcome check.
Neuro N1 lateral/medial/ventral/dorsal views. N2 reliability mask (TRIBE accuracy/noise ceiling or dropout mask); recheck TP. N3 subcortical gap limitation; cortical proxies. N4 functional ROIs (FFA/OFA, pSTS, L IFG, L MTG/STG, TPJ, dmPFC, vmPFC, AI/dACC, DAN, V1–V3 control). N5 lateralisation index. N6 content-aligned segments (intro/team, problem, solution/demo, traction, market, ask) LLM draft + human κ. N7 HRF lag 4–6 s, test on known event. N8 OOD check vs reference clips. N9 wording.
Phase 9b behavioural validation (Prolific, 100–200 raters × ~10 videos, ratings + moment slider, IRB; mixed models; ICC≥0.6).
Extra roles: Biostatistician (B1–B13), Neurologist/Cog Neuro (N1–N9, veto on functional claims), Ethics/Data Steward (ToS, IRB, retention; STOP on collection).

6 GLOBAL DoD: all gates GO; CI green; `make all` rebuilds from data/raw + config; prereg hash; deviations listed; H1–H4 each supported / not / inconclusive (with power).
7 STOP: <15 conf-A per group; TRIBE not deterministic or inputs unmet; unaddressable confound; >3 FIX cycles.
