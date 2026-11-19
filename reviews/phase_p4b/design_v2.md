# P4b design proposal v2 (for council cycle 2)

Status: DRAFT. It resolves every blocking item from cycle 1:
- Watchdog B1–B7;
- Referee B1–B12;
- Biostat B1–B5;
- Neuro B1–B6;
- QA B1–B10.

Where reviewers disagreed, v2 takes the stricter option, and §10 lists those choices.

The pre-run freeze is the proposed entry D-071 (`d071_draft.md`). It must be committed, with its config keys in `frozen:` and its tests green in CI, BEFORE the reference job is built.

Firewall (D-063 B2) is unchanged. No analysis-set prediction array has been read. No analysis-set statistic is computed until the post-run P4b design entry is committed and p4_index carries the guard in §7.

## 0. Ordering (Watchdog B1, Referee B8, QA B6)
1. Commit D-071 (pre-run). It holds the stimulus spec, the clip-manifest scheme, the kernel acceptance formulas and thresholds, the STOP/descriptive split, the (d) rule, the redesign cap, the S3 root, the cost cap, and Q1–Q6. Its values go in config `controls.refclips`, `controls.kernel.acceptance` and `controls.pass`, all listed in `frozen:` (enforced by check_frozen_config).
2. Build tickets T-DRV, T-STIM, T-REF58, T-REFRUN, T-KERNEL and T-ENV with TDD. CI must be green and the council must give GO (cycle 2) on the diff.
3. Build the clips ONCE on the pod with a pinned toolchain. Freeze the sha256 manifest in config (one more `frozen:` key) and upload it to the reference root.
4. Reconcile the ledger (L4, agent side) and record the `spent` value and `budget_cap()`.
5. Reference GPU job.
   - Session 1 is watched and capped: `--limit 3`, the 3 D-038 reference clips, then a human check.
   - Later sessions run with `--max-hours ≤ 1.4` and `--usd-limit 8`.
   - The campaign has a hard cap (§2).
6. Derive kernels on CPU from the reference root only. A K-rule failure is a STOP (§3.4).
7. Write the post-run P4b design entry. It records only:
   - the kernels sha256;
   - the K results;
   - the dry-run results;
   - the ablation entry id;
   - the lock items L1–L4.
8. The first analysis-set read goes through `p4_open` (§7).

**No-revision rule (Watchdog N11).** After step 8, no kernel, ROI, regressor, threshold, exclusion or fallback may change. Any (a)–(d) FAIL is a STOP routed to the owner and the council.

**Redesign cap (Watchdog B1).** At most one versioned redesign of the reference set is allowed:
- it is named `p4b_ref/v2`;
- it requires a new DECISIONS entry;
- the v1 results are reported in full;
- there are no silent re-runs.

A second failure is a STOP that goes to the owner.

## 1. Reference-clip set (label-free, synthetic + licensed images + public naturalistic)

Common rules:
- **Clip format.** Every clip is 58.0 s, so there is one Audio chunk and one Video chunk and T = 58 at TR 1.
- **Background.** A persistent mid-grey background (Neuro N3, Watchdog B2), not black. Mean luma 128 (8-bit full range) in the 256² V-JEPA2 view: the short edge resized to 292, then the central 256 crop. Stimuli sit inside the central ≈316×316 source px of the 640×360 frame (Neuro B4).
- **Events.** 3 events per clip at base onsets [9, 29, 49] s with a per-clip shift s ∈ {0, −1} (alternating by clip index), so spacing is 20 s (Neuro B1, Referee B4).
  - First window start: onset − 4 ≥ 4 s, which also clears the encoder warm-up (Referee N3).
  - Last window end: 49 + 8 = 57 ≤ T − 1, checked against each clip's own segments.csv (QA N6).
  - The shift breaks periodicity only (Neuro N7).
- **Impulse events.** Visual events are 1 s. Speech kernel events are short 1.0–1.5 s utterances of 2–3 words (Referee B5, Neuro N1). 4–6 s bursts appear only in a validation family.
- **Exemplars (Biostat B1).**
  - Every event in a gating family uses a distinct exemplar, with no repeats across the family.
  - Unit of replication = the clip. Each clip contributes the mean of its events for that family. For the localiser, each clip holds one event per category.
- **Audio (Neuro B2).**
  - The seeded white-noise bed (SEED 20261117) is set so that the 58 s waveform's integrated loudness is −23 LUFS. This equals the P2 target, so P2 normalisation is a no-op (§1.4).
  - Speech REPLACES the bed at matched local RMS (a crossfade over 10 ms). The chunk SD of every clip therefore equals the control's within 1%. Tested.
  - Visual-only clips carry the control's audio bit for bit; the extracted wav sha equals the control's.
- **Text.** The .tsv word onsets are uniform splits within each utterance. This is disclosed (Referee N1). Sentences are generic and balanced across clips (Referee N2).

### 1.1 Families

Each family names its baseline: every kernel is (family clip − its matched control clip) at the same TR. The segment start times are asserted equal before subtraction (QA N7).

| family | n clips | event (1 s unless stated) | matched control | kernel ROI | role |
|---|---|---|---|---|---|
| LOC (localiser) | 20 | the 3 events are face, place, body in Latin-square order; an intact greyscale photograph replaces its own phase-scrambled version, which is otherwise shown continuously; luma, RMS contrast and amplitude spectrum matched (SHINE-style) | LOC-SCR twin (20): the same scrambled images; at each onset the scramble swaps to a second scramble of the same exemplar | FFC (face events); PH, body: descriptive | FFC kernel gating; (d) gating (§4) |
| MOT (motion) | 10 | coherent drift for 1 s of a pattern that is present and static for the whole clip; 5 random-dot fields + 5 gratings; directions 0/45/…/315° (10 distinct); temporal frequency ≤ 4 Hz; low CRF | MOT-STAT twin (10): the same pattern, never moving | MT_plus | gating |
| SPK (speech) | 10 | 1.0–1.5 s espeak-ng utterance (30 distinct, 2–3 words), RMS-matched on the bed, grey frame | GREY-CTRL (2, one per shift): bed + grey only | AUD (full model; audio-only for (b)) | gating |
| BURST (validation) | 5 | 4–6 s utterances (as ENH-002), RMS-matched | GREY-CTRL | AUD | descriptive: tests kernel ⊗ envelope (r ≥ 0.8 reported) |
| FLASH | 5 | 1 s full-frame white flash on grey | GREY-CTRL | V1_V3 (+ MT_plus for K6) | descriptive; supplies the K6 comparison |
| TALKFACE | 1 | 58 s synthetic talking cartoon face + speech | GREY-CTRL | none | descriptive (latency); mouth drives MT+ (Neuro N9), disclosed |
| NAT (naturalistic) | 15 | public, openly licensed, non-YC talking-head videos (§1.3) | none | none | P10 low-SD rule, (a) fallback, K1′ scale, OOD reference |

- Totals: 20 + 20 + 10 + 10 + 10 + 2 + 5 + 5 + 1 + 15 = **98 clips**.
- Gating units: FFC 20 clips, MT_plus 10 clips, AUD 10 clips. Each is ≥ 8 (Biostat B1).
- (d): 20 exemplars per category (Biostat Q2).
- Line drawings and the cartoon face are dropped as (d) stimuli. They may appear only as a labelled descriptive sensitivity. That sensitivity is not run in v1.

### 1.2 Licensed localiser images (Q2, Watchdog Q2, Neuro B4)
- Requirements:
  - CC0, public domain, or CC-BY covering derivatives (greyscaling, scrambling and re-encoding into video), verified from the licence text.
  - Record the licence URL, the version or DOI, and the sha256 of the licence text.
  - Freeze the image sha256 manifest.
  - No YC, founder or analysis-company imagery.
- Selection rule (mechanical): within each category, the first 20 images by sorted file name that pass the licence and content filters (single upright subject; frontal faces only for the face category).
- Candidates. **None is verified yet**; ticket T-LIC verifies them and blocks the build:
  - VPNL fLoc stimuli (github.com/VPNL/fLoc). No licence file was found. The pyfLoc README says the stimuli carry separate terms from the code and need acknowledgement. Treat as NOT usable unless an explicit open licence is found.
  - Face Research Lab London Set, figshare DOI 10.6084/m9.figshare.5047666 (faces). The licence field on figshare must be checked per version. The consent covers "original or altered forms".
  - THINGSplus public-domain images, osf.io/jum2f (objects, places, bodies). The dataset is CC0. Confirm that the image subset is public domain.
  - Wikimedia Commons CC0 / public-domain categories (places, bodies), with the per-file licence recorded.
- If no verified set covers face, place and body, (d) and the FFC kernel cannot run. That is an owner decision before the build; there is no synthetic substitute (stricter option; see §10).

### 1.3 Naturalistic reference clips (Q3)
- Use ≥ 15 public, openly licensed (CC-BY or CC0) English talking-head videos with no YC link. Never non-primary wave-1 rows. Never `data/wave2_pool/`.
- The selection rule is pre-written in D-071:
  - source: Wikimedia Commons video search "lecture OR interview OR talk", restricted to CC-BY/CC0 files;
  - single speaker, mostly frontal;
  - ≥ 58 s;
  - the first 15 in order of sha256(file title) that pass.
- The curator is a fresh agent with no label exposure. It records URL, licence and sha256 only.
- Processing: P1/P2/P2b/P3 identically to the analysis T1 clips (58 s trim, normalisation, pinned WhisperX). Their regressors and predictions are read only for the uses listed in §1.1.
- Ticket T-NAT. This is not curated yet.

### 1.4 Input path (Referee B6, QA N11)
- Every clip goes through the same P2 T1 normalisation and the same run_clip flags as the analysis T1 clips:
  - `--qc-gate t1`;
  - word fix and clamp on;
  - offline;
  - pinned transcript sha. Synthetic clips use their generator .tsv; NAT clips use P2b.
- Synthetic clips are built at the P2 output spec, so P2 is close to a no-op.
- Test: the P2 log shows gain change ≤ 0.1 dB, the ffprobe fields (fps, sample rate, crop geometry) equal the T1 spec, and the bed is unchanged after P2.
- controls_report states that (a)–(c) test the pipeline's internal consistency (ROI mapping, alignment, regressors). They cannot detect a timing error shared by the kernels and the analysis path, and the result is not neural validity (Referee B6/N7).

### 1.5 Stimulus QC with the real regressor code (Neuro B6, B3)
T-REF58 runs `yct.confounds` and the T-ENV speech_envelope on the built clips:
- LOC face events: `face_area_crop_frac` > 0 on ≥ 90% of event TRs.
- MOT:
  - `luminance_crop` and `contrast_crop` constant within 1% over the whole clip;
  - `motion_energy_crop` ≥ 10× the static level during events, and at static level elsewhere;
  - the static twin shows no event.
- SPK and BURST: `speech_envelope` follows the events; no visual regressor moves.
- FLASH: `luminance_change` at the events only.
- LOC: luminance and contrast constant within 1% across intact and scrambled frames.
- Each family moves its own regressor and no other beyond tolerance.

### 1.6 Build and provenance (Watchdog B5, QA B4)
- The clips are built ONCE on the pod. The ffmpeg, x264 and espeak-ng versions are recorded, with bit-exact flags (`-fflags +bitexact -flags +bitexact -map_metadata -1`, `-threads 1`).
- They are uploaded with `refclips_manifest.json` (per-file sha256 of mp4, wav and tsv, toolchain, source-image sha256, licence sha256). Its sha256 is frozen in config.
- The GPU box only stages manifest objects and gates `input_sha256` and `transcript_sha256` against the manifest. It never rebuilds a clip.
- Tests:
  - wav and tsv rebuild bit-identically in CI (stdlib, seeded);
  - mp4 rebuild is toolchain-gated (espeak-ng installed in CI, or the test recorded as a build artifact);
  - the wrapper refuses a clip whose sha differs from the manifest.

## 2. GPU job
- **S3 root (Watchdog B4, QA N2):** `s3://yct-research-235229001983/wave1/derived/p4b_ref/v1/`. This is a SIBLING of `.../p4/`, never inside it. It has its own manifest.jsonl, rows/, stops/ and entries/.
  - Prediction prefixes: `full/`, `audioonly/`, `textonly/`.
  - The wrapper never writes under the P4 root.
  - The P4 root `manifest.jsonl` sha256 is recorded before and after every reference session and must be unchanged (test plus a runtime check).
- **Driver:** `scripts/gpu_p4b_ref.py` is a thin wrapper over the hardened driver functions. It passes the S3 root and prefixes as constructor arguments (no monkeypatching) and uses track `ref`, which applies the T1 gate. Its job list comes from `refclips_manifest.json`.
  - D-038 Gate 1/2 runs on 3 reference clips: GREY-CTRL s0, SPK_00 and MOT_00. A STOP latches under the ref root's `stops/`.
  - Revisions and GPU are seeded from the P4 root manifest (QA B3). The wrapper refuses to launch if the P4 revisions hash is None or mixed. Job 1 must match it.
- **Ablations (Watchdog B6, Referee B7):**
  - The full-model, audio-only and text-only predictions for all audio-bearing reference clips (SPK, BURST, GREY-CTRL, TALKFACE, NAT) come from the SAME D-038 cache entry, through `config_update={"data.features_to_use": [...]}`. There is no new cache key and no re-extraction.
  - The cache key is asserted unchanged across conditions (QA B10).
  - Gate 1 cached-rerun bit identity runs on ≥ 3 clips per condition.
  - Visual families need full-model predictions only.
- **Guards:**
  - external terminator at deadline + 15–60 min;
  - dead-man switch first;
  - `--max-hours ≤ 1.4`, enforced by the T-DRV guard;
  - exit 75 means re-run, exit 1 means a human;
  - capacity miss or HTTP 400 gives exit 75 (T-DRV);
  - sweep on a dead driver;
  - launch only from a pushed commit with CI green (the wrapper checks `gh run list --commit`, QA N9).
- **Cost (Watchdog B7, QA N1; replaces v1's $6–7):**
  - 98 extractions at about 6.5 min each ≈ 10.6 h of job time.
  - Ablation predictions from cache: 33 clips × 2 conditions at about 1 min ≈ 1.1 h.
  - D-038 reruns at about 0.2 h.
  - With 1.4 h sessions holding about 7 jobs, that is about 15 sessions ≈ 21 billed h ≈ **$42**.
  - NAT alone is 15 clips ≈ $7 of this. The LOC twins are 20 clips ≈ $9.
  - **Proposed hard campaign cap: $50** (owner decision). Reaching the cap means STOP and report.
  - Current P4 spend is $51.86 against a $43 projection (+$8.9, reconciled in L4 before launch).

## 3. Kernel derivation (CPU, reference root only)
- **Reader guard (Watchdog B4 v):** the kernel module reads only the ref root. It refuses `pred_clampv1/` keys and does not import p4_index (import and AST test).
- **Construction:**
  - d(t) = ROI mean of (clip − matched control)(t).
  - Clip course c_j(lag) = the mean over that clip's events of the family at output lags −4…+8 (nearest TR, must exist).
  - Any NaN, a truncated window, or an exactly-zero-filled TR inside a window → STOP (Referee N4).
- **Kernel:** k = mean_j c_j / max(mean_j c_j). This is the signed max, not max|·|.
- **Maps:**
  - The gating map is `spatially_standardised`.
  - `raw` is computed and enters K5 only.
- **Halves:** even and odd clip index. The selection half is the even clips; the test half is the odd clips.
- **Peak lag:** p* = the signed argmax of the selection-half mean course over lags −4…+8.

### 3.1 Acceptance rules (all frozen in D-071 and config; fail closed)
Notation:
- n_t is the number of test-half clips.
- σ_nat(ROI) is the median over NAT clips of the ROI-mean temporal SD over W on the standardised map.

| rule | formula | threshold |
|---|---|---|
| K1 sign/significance | one-sided one-sample t over the n_t test-half clip means at p*; **and** every test-half clip mean at p* > 0 | p < .001 (FFC n_t = 10: t(9) > 4.30; MOT/AUD n_t = 5: t(4) > 7.17) |
| K1′ magnitude | full-data mean course at p* ≥ 0.25 · σ_nat **and** ≥ 0.2 (standardised units) | both |
| K2 timing | p* ∈ [−1, +4] **and** the full-data signed argmax ∈ [−1, +4]; the first rising-flank crossing of 50% of the peak ∈ [−4, +2]; mean over lags 0–3 ≥ 0.5 · peak | all |
| K3 precision | peak / √( mean_{lag ∈ −4…−2} Var_j(c_j(lag)) / n ) ≥ 3, where Var is the across-clip variance and n is all clips | ≥ 3 |
| K3′ baseline | \|mean of d over event-free spans (≥ +12 TR after an event and ≥ 5 TR before the next)\| ≤ 0.10 · peak | ≤ 0.10 |
| K4a held-out | median over leave-one-clip-out folds of r(kernel from the training clips, the held-out clip course) | ≥ 0.5 |
| K4b split-half | r(even-clip mean course, odd-clip mean course) | ≥ 0.7 |
| K5 map agreement | sign(standardised) = sign(raw) at every lag 0–3, **and** \|p*_std − p*_raw\| ≤ 1 TR | both |
| K6 specificity (MT_plus only) | MT_plus MOT kernel peak (moving − static) > MT_plus FLASH response mean over lags 0–3, standardised | > |

- **Fail-closed rules:**
  - zero, NaN or inf in any denominator, SD = 0, an all-zero course, or any truncated window → STOP;
  - each rule returns PASS, FAIL or STOP_INVALID;
  - only PASS counts.
- **Disclosed in D-071 (Watchdog N3, Biostat B4, QA Q5):**
  - The K2 window was chosen with knowledge of ENH-002.
  - Clips differ by exemplar, but TRIBE is deterministic. The K1 p-value measures consistency across exemplars, not sampling error.
- **Known-data check (Referee B3):** the frozen K-code is run on the ENH-002 summary courses before launch, and the outcome is disclosed in the cycle-2 packet. The expected result is that the ENH-002 flash fails K2 and K5; it is descriptive, so this is no STOP.
- **Operating characteristics (Biostat):** the T-KERNEL tests simulate seeded synthetic courses:
  - null pass rate < 0.05 for each of K1, K3, K4a and K4b;
  - planted d = 1 recovers the kernel at r > 0.99;
  - a −3 TR pre-rise is handled as specified (QA N8).

### 3.2 Gating vs descriptive (Biostat N6, Watchdog Q6)
- Gating kernels:
  - FFC (LOC face, intact − scrambled);
  - MT_plus (MOT, moving − static, incl. K6);
  - AUD full-model (SPK);
  - AUD audio-only (SPK on the audio-only condition, for (b)).
- Descriptive: PH and body (LOC), V1_V3 (FLASH, MOT), BURST, TALKFACE. All K rules are reported for them; they never STOP.

### 3.3 Output
`outputs/p4b/kernels_v1.json` holds kernels, clip courses, K results, clip hashes and code sha. It uses canonical float formatting (repr, sorted keys) and is byte-reproducible from the stored arrays (QA B6e). Its sha256 goes in the post-run entry.

### 3.4 Failure consequence (Q6, stricter option)
- Any gating K FAIL or STOP_INVALID is a P4b **STOP**. There is no pre-registered demotion path.
- One versioned redesign is allowed, by a new DECISIONS entry; a second failure goes to the owner.
- A failed motion kernel may never be replaced by a flash kernel.

## 4. P4b controls (a)–(d)
**Gating set (Referee B9, Biostat N1):** T1, 51 videos, standardised maps. T3 (52) and raw maps are reported and non-gating. Every test is one-sided in the predicted direction (Biostat N2).

### (a) Within-video partial r
- Gating pairs:
  - FFC × face_area_crop_frac;
  - AUD × speech_envelope (full model);
  - MT_plus × motion_energy_crop.
- Descriptive pairs: V1_V3 × motion and V1_V3 × luminance_change.
- Model: ŷ(t) = Σ_{l=−4..8} k(l) x(t − l), with x zero-padded for t < 0 (Biostat N5).
- Partialling:
  - The partial-out regressors are convolved with the target ROI kernel.
  - Luminance_change is always partialled.
  - The target regressor is removed from the partial-out list.
  - An intercept is included.
  - OLS residualisation over W = [5, 45).
- Inference:
  - z = atanh(r), clipped at |r| ≤ 0.999999;
  - one-sample one-sided t across videos;
  - PASS = mean z > 0.2 and p < .001.
- Low-SD exclusion (Referee B11, Biostat B5 iii, Neuro N5):
  - Drop a video if its regressor SD over W is below P10 of that regressor over the 15 NAT clips (numpy `percentile`, linear, ddof 1).
  - If fewer than 15 videos remain, the test runs on the 15 NAT clips instead (n = 15, same thresholds).
  - The exclusion COUNT is computed only after the post-run entry (Watchdog N7).
- Dry run on reference clips is a feasibility check only, with pre-declared actions, not a fifth gate (Biostat N11). It runs on held-out test-half clips and TALKFACE, never the selection half (Watchdog N6). (a)-face on TALKFACE is undefined because face SD is 0; this is stated.

### (b) Selectivity (paired, one-sided, p < .01)
- **Face:** z(FFC, face) > z(V1_V3, face) on the full model.
- **Speech:** z(AUD, speech) > z(FFC, speech) on the **audio-only** condition of the T1 51 videos.
- Both arms of each comparison use the gating ROI's kernel (FFC; AUD audio-only). The own-kernel version is reported as a sensitivity (Biostat N3).
- FFC vs PH (face) is a descriptive contrast (Referee N6).
- The two arms use the same video set, the union of exclusions.
- **Analysis-set audio-only run:** its own ablation entry (proposed D-072):
  - estimand: speech selectivity without the text pathway;
  - label: "audio-only (inference-time ablation, not a retrained unimodal model)" (Neuro Q1);
  - predicted from the existing P4 cache (same key, prefix `pred_audioonly_v1/`), with a cached-rerun Gate 1;
  - the gate verifies that the text and video extractors were not called;
  - the loader is keyed by (track, condition, video) (T-AUDIO).
  - Cost: about 51 predictions at about 1–2 min each ≈ 1–2 h ≈ $3–4. It runs after the reference job, on its own GPU test.

### (c) Between-video
- Tests:
  - r(W-averaged FFC, W-averaged face fraction) > 0.3;
  - r(W-averaged AUD, mean speech envelope) > 0.3;
  - both on T1 51, standardised.
- Inference: one-sided permutation p = (1 + #{r* ≥ r_obs}) / (1 + B), with B = 10,000 and seed `seeds.controls_perm`.
- **Gate (stricter: conjunction):** r > 0.3 **and** unrestricted p < .05 **and** p < .05 permuting within `era_block`, which is label-free in data/manifest.csv.
- Era-block merge rule, fixed now before any count is seen: any era_block with < 6 gating videos is merged into the adjacent later block (the last block into the previous one).
- **Never route blocks:** route is sealed and outcome-associated (D-040). This follows Referee B12, Watchdog Q4 and Neuro Q4, overriding Biostat Q4.
- No per-block statistic is reported before unblinding (Biostat N8).

### (d) Localiser replication (evaluated on LOC; it IS the reference run, Referee B8)
- Readout: the mean of output lags 0–3 of (intact − scrambled twin) per category and hemisphere.
- Contrasts:
  - FFC: face − mean(place, body) > 0 **and** face − place > 0;
  - PH: place − mean(face, body) > 0 **and** place − face > 0.
- The left and right hemispheres are evaluated separately; the per-hemisphere vertex counts are listed in D-071.
- PASS requires both of:
  - sign-consistent in both hemispheres;
  - the seeded clip-bootstrap 95% CI (B = 10,000) excluding 0 in each hemisphere. This is the stricter amendment from Biostat N7.
- Frozen pre-run, in D-071.

### Negative controls, OOD, reliability (Referee B10, QA N10)
- **Upload-date parity.** An even or odd day-of-month from manifest `upload_date`, run through the full pipeline blind. Expected null; any "effect" at p < .05 is reported as a flag.
- **Aspect ratio.** The source aspect ratio (pre-normalisation ffprobe, label-free) is used if at least 2 levels have ≥ 10 T1 videos each. Otherwise D-071 records it as untestable, since D-060 found 9:16 = 0. This is decided by a metadata count that involves no prediction.
- **OOD.** Per-video predicted-variance distribution (W, standardised) vs the 15 NAT clips. The flag is > P99 of NAT, reported only.
- **Reliability mask.** From the D-038 fresh-re-extraction pairs (3 clips): vertices with reliability r ≥ 0.99 across pairs. Specified in T-LOCK; computed only after the post-run entry.

## 5. Speech envelope (T-ENV, unchanged from v1 apart from N9)
- Computation: mono 16 kHz → DC removed → |hilbert| → 0.5 s bin means → TR means aligned to segment starts. Read from the exact wav TRIBE ingests.
- No transcript is opened (tested).
- Output: appended to P3 tables append-only, with originals kept as `*.pre_p4b.*` and provenance (run id, git sha) (Watchdog N9).

## 6. Lock items
- **L1.** `p4.superseded_run_ids` (4 ids) goes into `frozen:`. An AST allowlist test asserts that only p4_index (read) and the driver (write) reference `PRED_PREFIX` or `pred_key`.
- **L2.** Archive manifest (key, size, sha256, run_id) of the P4 root only:
  - it lists the superseded run ids explicitly (Referee N10);
  - the ref root has its own manifest;
  - completeness is tested against a dry-run listing.
- **L3.** `qc_report.html` is built from an **allowlist** of manifest-row, gate and ledger fields (QA B9b):
  - per-job gate, T, n_words vs tsv, chunks, D-038, revisions, GPU, run_id;
  - sessions and aborts (BUG-027/028/031/033);
  - it builds from the 103-job dry store;
  - its sha256 is pinned.
- **L4.** Ledger reconciliation:
  - PASS = |Σ(terminate − launch) × usd_per_hour − `spent_usd()`| ≤ max($0.50, 1%), with orphan minutes per BUG-027/028 event;
  - the owner signs off the invoice separately;
  - reference-job and audio-only spend are reconciled again at P5 entry (QA B9c,d);
  - the agent-side part runs BEFORE the reference launch (Watchdog B7).
- **controls_report.md** (ticket T-REPORT) covers:
  - the K tables;
  - (a)–(d) per gating and reported set;
  - negative controls, OOD and reliability;
  - the circularity statement (§1.4);
  - the TRIBE caveats (Neuro N4, N9).

## 7. p4_index hardening (QA B8)
`p4_open(ref)`:
- refuses until the post-run P4b design entry id exists in DECISIONS, its kernels sha256 equals the file on disk, and its commit precedes HEAD (Watchdog N10);
- verifies the sha256 of the downloaded bytes equals `pred_sha256`;
- refuses while any D-038 STOP is uncleared (`latched_stops` semantics).

Also:
- PRED_PREFIX comes from `qc.WORD_END_CLAMP`, with a test pinning it equal to the driver's;
- the store root is asserted to equal `p4.s3_prefix`;
- rows of track `ref` or of non-run-set videos are ignored, which is tested;
- the QA N3 tests (missing or empty manifest, track case, a real-config 103-row smoke test).

## 8. Tickets

Blocks: **G** = reference GPU launch, **L** = P4b lock.

| ticket | files | TDD tests (first) | blocks |
|---|---|---|---|
| T-D071 | DECISIONS (D-071), config `controls.refclips`, `controls.kernel.acceptance`, `controls.pass`, `seeds.controls_perm`, `frozen:` | check_frozen_config sees every key; the K-code reads thresholds from config only | G |
| T-DRV (BUG-033, BUG-028) | scripts/gpu_wave1_p4.py, infra/lambda_gpu.py | FakeLG without the type, or HTTP 400 on launch → exit 75, nothing billed, no run-dir debris, empty ledger delta; `--max-hours > 1.4` refused (constant `LAUNCHER_LIMIT_H`); default lowered to 1.4 | G |
| T-LIC | docs/stimuli/LICENSES.md, data/stimuli/loc_manifest.json | the licence sha256 matches the stored text; the builder refuses any image not in the manifest; ≥ 20 per category | G |
| T-NAT | data/refnat/manifest.csv (url, licence, sha256), via a label-free curator | 15 rows, licence ∈ {CC0, CC-BY}, no YC-related token, sha256 present; disjoint from data/manifest.csv and the wave-2 pool | G |
| T-STIM / T-REF58 | src/yct/tribe_run/make_reference_clips58.py | 98 clips; 58.0 s; 1 A + 1 V chunk; onset rules; RMS / chunk-SD ±1%; visual-only wav sha = control's; luma/contrast constancy (MOT, LOC); §1.5 regressor QC with real yct.confounds; P2 no-op test; wav/tsv bit-identical rebuild; bit-exact flags present | G |
| T-REFRUN | scripts/gpu_p4b_ref.py | every key under the ref root; P4 manifest sha unchanged; revisions and GPU seeded from P4 (mismatch → gate fail on job 1; None or mixed → refuse); track `ref` uses the T1 gate (all 98 pass in dry run); input/transcript sha gate vs manifest; D-038 on 3 ref clips with STOP latch under the ref root; ablation conditions share one cache key; the D-063 B2 import firewall; `--limit 3` first session; CI-green check | G |
| T-KERNEL | src/yct/tribe_run/kernels.py (generalises enh002) | planted-kernel recovery r > 0.99; null pass rate < 0.05 per rule (seeded); fail-closed cases (NaN, zero SD, all-zero, truncated, zero-filled TR); split halves honoured; K6; gating vs descriptive (V1_V3 never STOPs); byte-reproducible json; refuses `pred_clampv1/`, no p4_index import; known-data run on ENH-002 summaries | G |
| T-ENV | src/yct/confounds/speech_envelope.py | AM tone recovers the envelope; silence ≈ 0; TR alignment; deterministic; no transcript opened; append-only write with provenance | G (ref QC), L |
| T-AUDIO | driver + p4_index (track, condition) | cache key identical apart from features_to_use; separate prefix; same revisions and GPU; extractor-not-called gate; loader keyed by condition | L |
| T-CTRL | src/yct/stats/controls.py | planted effects PASS and nulls FAIL; partialling removes a planted luminance confound; low-SD rule over NAT; < 15 fallback; permutation within era_block with the merge rule; seed reproducible; reads only via p4_open; end-to-end gate pass probability reported (Biostat N6) | L |
| T-NEG | src/yct/stats/negative_controls.py | parity null in simulation; aspect-ratio testability rule | L |
| T-OOD-REL | src/yct/stats/ood.py, reliability.py | P99 flag on synthetic data; reliability-mask threshold from D-038 pairs | L |
| T-INDEX | src/yct/predict/p4_index.py | §7 guards; QA N3 cases; AST allowlist | L |
| T-LOCK | outputs/p4_archive_manifest.csv, outputs/qc_report.html, outputs/p4_ledger_reconciliation.md | L2 completeness; qc allowlist + dry-store build + sha; L4 tolerance with an orphan, a miss and a double-terminate fixture | L (L4 agent part: G) |
| T-REPORT | outputs/controls_report.md generator | sections present; no prediction value outside the (a)–(d) summaries; circularity statement present | L |

## 9. What the post-run P4b design entry records
The pre-run items are already frozen in D-071. The post-run entry records:
- kernels_v1.json sha256;
- the K tables;
- the dry-run outcomes;
- the D-072 run ids;
- the NAT manifest sha;
- the archive / qc_report / reconciliation sha256s;
- the per-hemisphere vertex counts;
- the freeze of every remaining `controls.*` key.

The order is: entry committed → `p4_open` unlocks → the first analysis-set read.

## 10. Disagreements resolved to the stricter option
- **Spacing and events:** Neuro asked for 20 s spacing and 7 clips; Biostat asked for 8–10 distinct clips. v2 uses 20 s spacing, 3 events per clip, and 10–20 distinct clips per gating family.
- **Face/place stimulus:** Referee wanted an intact-vs-scrambled swap; Neuro wanted luminance-matched photographs on grey. v2 does both, with a scrambled twin control per clip.
- **K rules:** v2 takes the union of Biostat's formulas, Neuro's K1′/K2′/K3′/K6 and Referee's effect floor and K5 sign rule.
- **Q4 (c) blocks:** Biostat wanted era × route; three members said never route. v2 drops route and gates on the conjunction of unrestricted and era-blocked permutation.
- **Q6 motion failure:** Neuro offered a pre-registered demotion path; v2 makes it a hard STOP with no demotion.
- **(d) rule:** v2 adds the bootstrap CI requirement in both hemispheres (Biostat N7), on top of the v2.md sign rule.
- **No verified licensed images:** v2 does not fall back to synthetic stimuli; it stops for an owner decision.

## Owner decisions (2026-11-19, after drafting; these override the text above where they conflict)
- **Campaign cap:** a hard cap of $75 for the reference-clip campaign (it replaces the proposed $50 in §cost). Reaching the cap means STOP and report.
- **Localiser images (Q2):** Wikimedia Commons CC0 / public domain / CC-BY photographs for faces, bodies, places and objects. Each file's licence is verified on its file page. A label-free curator selects 20 per category by sha256 of the file title and records only the URL, licence and sha256. fLoc, the London Set and THINGSplus are not used.
- **MT+ failure (Q6):** pre-registered demotion, as the Neuroscientist proposed. If MT_plus fails K1–K6, the motion control becomes descriptive (reported, limitation disclosed, not gating). This is fixed before any reference output exists, and a motion kernel is never replaced by a flash kernel. This replaces the "no demotion path" text above for MT_plus only. FFC and AUD stay hard STOP.
