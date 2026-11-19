# P4b design proposal v1 (council cycle 1)

Status: DRAFT for the 5-member council. Nothing here is frozen until the P4b design entry in DECISIONS.
Firewall (D-063 B2) still holds: no analysis-set prediction array has been read, W-averaged, ROI-read or used in any cross-video statistic. The only P4 outputs used so far are QC gate metadata and S3 keys and hashes (src/yct/predict/p4_index.py).

Inputs: v2.md §5 P4b (v2.5 C3, v2.7 P4E), ROADMAP P4/P4b, config `controls:`, D-039, D-063 Q4/B2, D-065 (d), D-066, D-067 (c), ENH-002 dry run (wave1p2b_20261118T002855Z).

## 0. Where we are
- P4 is complete: 103/103 jobs (T3 52, T1 51) on one revisions set and one GPU type (gpu_1x_a100_sxm4), with gate_failures empty in every session (s5–s19).
- Superseded runs are s1–s4 (D-067 c). The single loader (b632d6d) applies them, finds 103 refs and 1 revisions hash, and every key sits under pred_clampv1/.
- The ENH-002 kernels are NOT usable (D-063 Q4). They came from 120 s two-chunk clips with no baseline correction, and there are no FFC or MT+ kernels. They must be re-derived (§1–3).

## 1. ENH-002b reference-clip set (synthetic, label-free)
Common design:
- Every clip is 58.0 s long, so there is one Audio chunk and one Video chunk and T = 58 at TR 1.
- The base is the same black frame plus the seeded white-noise bed as make_reference_clips.py (SEED 20261117, BED_AMP 0.01), cut to 58 s. Every clip therefore shares a bit-identical bed and frame outside its events.
- Each clip is baseline-corrected by subtracting ref_control58 at the same TR (control-subtracted course), as enh002.analyse already does.
- Event window: output lags −4…+8 TR. It must hold onset − 4 ≥ 0 and onset + 8 ≤ 57, and events must be ≥ 13 s apart so windows never overlap.
- Onsets: 4 events per clip at base onsets [6, 19, 32, 45] s, shifted by a per-clip phase φ_k = k s (k = 0..4, clip index), giving [6+k, 19+k, 32+k, 45+k]. The last window ends at 45 + 4 + 8 = 57 ≤ 57, so it fits. The phase decorrelates events from chunk-internal position.
- Event duration: 1 s for visual impulses, and 4–6 s for speech bursts (as ENH-002). Speech windows still start at onset; a 6 s burst at 19+k ends before the next onset.

Clip families (5 clips each, 4 events per clip, so 20 events per kernel):
| family | event | kernel ROI | notes |
|---|---|---|---|
| ref_flash58_k | 1 s full-frame white flash | V1_V3 (descriptive), luminance-change partial | as P0/ENH-002 |
| ref_motion58_k | 1 s drifting high-contrast grating / random-dot field inside the central 256×256 crop, mean luminance matched to the frame (Δ mean luma ≈ 0) | MT_plus (gating) | luminance-matched so the motion kernel is not a luminance kernel (D-063 Q4) |
| ref_speech58_k | 4–6 s espeak-ng burst (SENTENCES), no visual change | AUD (gating) | exact-time .tsv; words come from the .tsv as in P4 |
| ref_face58_k | 1 s synthetic cartoon face (as ref_face) inside the crop, no mouth motion, no audio | FFC (gating) | weak face stimulus by construction (no real face footage label-free) |
| ref_place58_k | 1 s synthetic scene (perspective corridor / house line drawing) inside the crop | PH (localiser d) | weak place stimulus by construction |

Also:
- ref_control58: the bed only, no events, header-only .tsv. It is the baseline for every family.
- ref_talkface58: a 58 s continuous talking cartoon face plus continuous speech (as ref_face, cut to 58 s). This is the required talking-face clip for the dry run (config dry_run.talking_face_clip). It is used for face/acoustic latency and for (a)/(b) on reference clips. It is not a kernel source.

Count: 5 × 5 + 1 + 1 = 27 clips. min_reference_clips 5 is met for each kernel, with 5 clips and 20 events per ROI.
Determinism: make_reference_clips58 is stdlib + ffmpeg + espeak-ng, seeded, and ships its own sha256 manifest. A rebuild must give bit-identical mp4/wav/tsv hashes, which a test checks.

## 2. GPU job
- Driver: reuse scripts/gpu_wave1_p4.py with a job list of 27 ref clips (track "ref"), or a thin wrapper. Same stack and same revisions; the loader-style check must give the same revisions_sha256 as P4. Same gpu_1x_a100_sxm4.
- S3: `<p4 s3_prefix>/p4b_refclips_v1/` (pred/, entries/, manifest.jsonl). This is never under pred_clampv1/. p4_index refuses any key outside pred_clampv1/, so reference clips can never enter the analysis set.
- Estimate: P4 averaged about 7 min per 58 s job (s16–s18: 7–9 jobs per 1.4 h incl. boot). The synthetic clips have the same chunk structure, so about 6–7 min each, about 3.0 h total, which is 2 sessions at --max-hours 1.4. At $1.99/h that is about $6–7. A D-038 cached rerun on 3 clips adds about 5 min.
- Rules (D-063 Q7, D-066, BUG-027/028/033):
  - External terminator armed at deadline + 15–60 min before every launch.
  - Dead-man switch started first.
  - --max-hours ≤ 1.4 under the 2 h harness limit.
  - Exit 75 means re-run; exit 1 means a human.
  - Capacity misses (KeyError / no capacity / HTTP 400) are retried pod-side.
  - Any session that finds a driver dead runs sweep/terminate.
  - --usd-limit 8 per session.
  - Launch only from a pushed commit with CI green.

## 3. Kernel derivation (CPU, reference clips only)
For each family f and its ROI r, and for each map in {spatially_standardised, raw}:
1. d_f(t) = mean over r of (pred_f − pred_control58)(t). Each clip uses its own aligned segments.csv times.
2. Event courses e_{f,i}(lag) for lag in −4…+8, giving 20 events.
3. Kernel k_r = mean_i e_{f,i}, divided by max|·| (peak-normalised). This is enh002.analyse generalised to 5 families.

STOP criteria (any one means STOP, report, and send to the council; no tuning):
- K1 (gating kernels FFC, AUD, MT_plus, and PH for d) PEAK > 0. The value at the peak lag of the mean course must be > 0, with a one-sample t across the 20 events at that lag of p < .001. The peak lag is chosen on half the clips (k = 0, 2, 4) and tested on the other half (k = 1, 3), to avoid peak-picking bias.
- K2 TIMING: the peak lag must lie in [−1, +4] TR. ENH-002 found 0 for both flash and speech, and TRIBE carries the 5 s offset.
- K3 SNR: peak / SD(pre-onset lags −4…−1 across events) ≥ 3.
- K4 STABILITY: leave-one-clip-out kernels must correlate with the full kernel at r ≥ 0.8 for all 5 folds.
- K5 POLARITY / map agreement: the peak lag on standardised and raw maps must differ by ≤ 1 TR.

V1_V3 kernels (flash, motion) are descriptive only (D-063 Q4); K1–K5 are reported for them but never STOP.
Output: outputs/p4b/kernels_v1.json. It holds each kernel, events, K1–K5 and clip hashes, and is frozen by sha256 in the design entry.

## 4. P4b controls (a)–(d), exactly as v2.md §5 / config `controls:`
Applied to the analysis set (T3 52; T1 51 reported) ONLY after the design entry is committed. All reads go through p4_index.

(a) Within-video partial r.
- Pairs: FFC × face_area_crop_frac; AUD × speech_envelope; MT_plus × motion_energy_crop. V1_V3 × motion and V1_V3 × luminance_change are descriptive.
- The regressor is computed in the central 256×256 crop at 2 Hz, mean-pooled to 1 Hz, and convolved with k_r (no shift by L). The partial r is over W = [5, 45), partialling out the other regressors and luminance_change.
- Inference is Fisher-z, one-sample t across videos. PASS = mean z > 0.2 and p < .001.
- Low-SD exclusion: drop videos whose regressor SD over W is < P10 of the reference clips. If fewer than 15 remain, use the reference naturalistic clips (see Q3).
- Needs: P3 confounds (exist), the speech envelope (§5), kernels (§3), and the loader.

(b) Selectivity, paired across videos, p < .01, on standardised maps (raw reported).
- Face: z(FFC, face) > z(V1_V3, face).
- Speech: z(AUD, speech) > z(FFC, speech), on the AUDIO-ONLY TRIBE run.
- **Conflict:** v2.md requires the audio-only run (`data.features_to_use=[audio]`), but D-065 (d) deferred ablations out of the P4 campaign, so no audio-only predictions exist. Options for the council:
  - B1 (recommended): an audio-only TRIBE run on the T3 analysis set (52 jobs) plus the 27 reference clips. It uses the same stack and GPU, a new cache key, and prefix pred_audioonly_v1/, with the loader extended by track. The speech-selectivity part is about 52 × ~5 min ≈ 4.5 h ≈ 3–4 sessions ≈ $10. The face part of (b) needs no new run.
  - B2: (b)-speech on the 5 ref_speech58 clips plus ref_talkface58 (audio-only run of the references only, about 30 min, about $1). This is cheaper but tests selectivity on synthetic speech only. Weaker, and it changes v2.md (needs a DECISIONS entry).
  - B3: run (b)-speech on the full-model run and disclose the text-pathway leak. This contradicts v2.5 C3 and is NOT recommended.
- The firewall is unaffected by any option: these are feature-extraction outputs, read only after the design entry.

(c) Between-video at the analysis level.
- W-averaged FFC × W-averaged face fraction, and W-averaged AUD × mean speech envelope.
- PASS = r > 0.3 and permutation p < .05. Use 10,000 permutations, seed fixed in config, permuting within era × route blocks (D-040) if the council keeps blocks for controls; otherwise unrestricted. This is Q4.

(d) Localiser replication.
- 1 s image flashes; readout = mean of output lags 0–3 TR, minus the other categories.
- PASS = FFC face > place AND PH place > face, sign-consistent in both hemispheres.
- Needs face/place/body images. Synthetic line drawings (ref_face58, ref_place58) are weak by construction and may fail for reasons unrelated to the pipeline. See Q2.

ENH-002 dry run: (a)–(d) on the reference clips, raw and standardised, BEFORE the lock. The (a)/(b) reference-clip evaluation uses ref_talkface58 and the 5-clip families (one face/speech series per clip).

## 5. Speech-envelope regressor (ENH-002 ticket)
- yct.confounds.speech_envelope(audio16k: np.ndarray, seg_starts: np.ndarray) produces a 1 Hz series aligned to TRIBE segment starts.
- Steps:
  1. Mono 16 kHz, DC removed.
  2. |hilbert(x)| (scipy.signal, broadband, no band-pass, per config op hilbert_broadband_envelope_mean).
  3. Mean over each 0.5 s bin (2 Hz), then mean of the two bins in each 1 s TR bin [t, t+1).
- Source: the trimmed 58 s audio actually fed to TRIBE (P2 normalised wav; same sha as the P4 input_sha256 lineage). No transcript text is read.
- Written to the P3 confounds table as speech_envelope (and speech_envelope_crop is not applicable).

## 6. Remaining P4b-lock items
- L1: freeze p4.superseded_run_ids (the 4 runs in D-067 c) with a config test pinning the list and its sha256. p4_index is the only reader (test: no other module opens pred_clampv1/ keys; a grep test).
- L2: archive manifest outputs/p4_archive_manifest.csv (key, size, sha256, run_id) for every object under the P4 S3 root (pred_clampv1/, entries_clampv1/, feature_cache/, rows/, d038_fresh_clampv1/, superseded objects, stops/). Hashes are recorded; arrays are not opened beyond hashing bytes.
- L3: P4 DoD outputs/qc_report.html, built from manifest rows and gate metadata only. It covers per-job gate pass, T, n_words vs .tsv rows, chunk counts, D-038 results, revisions hash, GPU, run_id and sessions/aborts (BUG-027/028/033). No prediction values.
- L4: GPU ledger reconciliation. Sum each launch→terminate × usd_per_hour and compare it with `lambda_gpu.py spent` ($51.86 at P4 end) and with the Lambda invoice when the owner provides it. List orphan minutes per BUG-027 event. The result goes in outputs/p4_ledger_reconciliation.md.
- L5: OOD check spec (predicted-variance distributions vs ≥ 5 reference naturalistic clips). It needs those clips (Q3).

## 7. Tickets (TDD: tests first, CI green, council GO)
- T-REF58 make_reference_clips58.
  - test: 27 clips, 58.0 s, one A and one V chunk;
  - test: onsets and windows inside [0, 57], with spacing ≥ 13;
  - test: bit-identical rebuild hashes;
  - test: the motion clip has Δ mean luma within 1% of the bed;
  - test: the bed is identical across clips.
- T-REFRUN GPU wrapper for ref clips.
  - test: prefix p4b_refclips_v1/ and never pred_clampv1/;
  - test: revisions sha equals the P4 sha, else refuse;
  - test: terminator/dead-man preconditions (reuse test_gpu_wave1_p4 fixtures).
- T-KERNEL enh002 generalised to 5 families.
  - test: synthetic predictions with a planted kernel recover it (r > 0.99);
  - test: K1–K5 STOP on flat, late-peak, negative and unstable synthetic inputs;
  - test: the split-half peak selection is honoured;
  - test: both maps are computed.
- T-ENV speech_envelope.
  - test: an AM tone recovers the envelope;
  - test: silence gives about 0;
  - test: TR-bin alignment to segment starts;
  - test: deterministic output;
  - test: no transcript file is opened.
- T-CTRL controls (a)–(d) module.
  - test: planted-effect simulations PASS and nulls FAIL at the stated thresholds;
  - test: the low-SD exclusion and the <15 fallback;
  - test: partialling removes a luminance confound planted in AUD;
  - test: permutation seed and blocks;
  - test: it reads only via p4_index;
  - test: it refuses to run until DECISIONS holds the P4b design entry id (firewall guard).
- T-AUDIO (if B1/B2): audio-only track in the driver and loader.
  - test: separate cache key and prefix;
  - test: same revisions and GPU;
  - test: the loader keys by (track, video).
- T-LOCK L1–L4.
  - test: frozen superseded list;
  - test: only p4_index reads pred keys;
  - test: archive manifest complete vs an S3 listing (dry backend);
  - test: the qc_report has no numeric prediction fields;
  - test: ledger sums are reproducible.

## 8. The P4b design entry must freeze
1. Reference-clip spec: families, onsets/phases, durations, seed, bed, and clip sha256 manifest.
2. kernels_v1.json sha256, K1–K5 results, and the STOP rules.
3. ROI lists and vertex counts (as config `controls.rois`, unchanged) and the gating/descriptive split.
4. Regressor definitions incl. speech_envelope, crop, the 2 Hz → 1 Hz rule, and partial_out.
5. Control thresholds (a) z > 0.2 & p < .001; (b) p < .01; (c) r > 0.3 & perm p < .05 with n_perm, seed and blocks; (d) sign rule and lags 0–3. Also the low-SD P10 rule and the < 15 fallback set.
6. The (b) audio-only option chosen (B1/B2/B3) and its run ids.
7. The reference naturalistic clip set (Q3) for the fallback and the OOD check.
8. p4.superseded_run_ids, the archive manifest sha256, the qc_report sha256, and the ledger reconciliation.
9. The order: design entry committed, then (and only then) the first analysis-set read through p4_index.

## Open questions for the council
- Q1 (b) audio-only: B1 / B2 / B3? (§4 b)
- Q2 (d) localiser stimuli: synthetic line drawings (weak, may fail by construction), or a public localiser image set with a verified open licence (e.g. fLoc, licence to be checked), shown as 1 s flashes in 58 s clips? Adding images is a stimulus change and needs a DECISIONS entry.
- Q3 Reference naturalistic clips (≥ 5) for the (a) fallback and the OOD check: non-analysis public talking-head videos with no YC link, or non-primary wave-1 rows? The latter carry labels in the sealed file and may be a leakage risk.
- Q4 (c) permutation: unrestricted, or within D-040 era × route blocks?
- Q5 K1–K5 STOP thresholds (p < .001, lag [−1, 4], SNR ≥ 3, LOCO r ≥ 0.8): acceptable as fixed, or tighten?
- Q6 Motion stimulus: is a luminance-matched drifting grating / dot field inside the crop adequate for an MT+ kernel given TRIBE known issue #9 (weak low-level visual predictions)? If K1 fails for MT_plus, is that a STOP or a disclosed-limitation entry?
