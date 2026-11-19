# Proposed DECISIONS entry D-071 (draft; to be appended to DECISIONS.md only after council cycle 2 GO)

- D-071 P4b pre-run freeze (reference-clip campaign `p4b_ref/v1`; design reviews/phase_p4b/design_v2.md; council cycle 1 reviews/phase_p4b/cycle1_*.md; cycle 2 reviews/phase_p4b/cycle2_*.md). This entry is label-free. It is committed with config `controls.refclips`, `controls.kernel.acceptance`, `controls.pass` and `seeds.controls_perm`, and each of those keys is listed in `frozen:`. Every item below is committed BEFORE any reference clip is built or any reference prediction exists.

  (a) **Stimulus spec**
  - Clips: 58.0 s, 640×360, built at the P2 T1 output spec, persistent mid-grey background (luma 128), stimuli inside the central ≈316×316 px.
  - Events: 3 per clip at onsets [9, 29, 49] s + s, with s = 0 for even clip index and −1 for odd.
  - Audio: seeded white-noise bed (SEED 20261117) at −23 LUFS integrated. Speech replaces the bed at matched local RMS, so chunk SD is within ±1% of control. Visual-only clips carry the control audio bit for bit.
  - Families:
    | family | clips | content | control |
    |---|---|---|---|
    | LOC | 20 | face/place/body in Latin-square order; intact greyscale photo replaces its phase-scrambled version (SHINE-matched) | LOC-SCR twins (20) |
    | MOT | 10 | 1 s coherent drift of an otherwise static pattern; 5 dot fields + 5 gratings; 10 directions; ≤ 4 Hz | MOT-STAT twins (10) |
    | SPK | 10 | 1.0–1.5 s utterances, 30 distinct | GREY-CTRL (2) |
    | BURST | 5 | 4–6 s utterances | GREY-CTRL |
    | FLASH | 5 | 1 s full-frame white | GREY-CTRL |
    | TALKFACE | 1 | synthetic talking face | GREY-CTRL |
    | NAT | 15 | naturalistic clips, see (c) | none |
  - Total: 98 clips.
  - Stimulus QC (design_v2 §1.5) must pass with the real yct.confounds code before upload.

  (b) **Localiser images**
  - Licence: CC0, public domain, or CC-BY that permits derivatives, verified from the licence text. The URL, version/DOI and sha256 of the licence text are recorded in docs/stimuli/LICENSES.md.
  - Source (owner decision, 2026-11-19): Wikimedia Commons, CC0 / public domain / CC-BY only, per-file licence verified from the file page. A label-free curator selects them and records the URL, licence and sha256 only.
  - Selection: the first 20 images per category (face, body, place, object) by sha256 of the Commons file title that pass the licence and content filters (single subject, photograph, no text or logos). The image sha256 manifest is frozen.
  - No YC, founder or analysis-company imagery.
  - If no verified set covers face, place and body, the build does not start. That goes to the owner, with no synthetic substitute.

  (c) **Naturalistic clips (NAT)**
  - Source: Wikimedia Commons video search "lecture OR interview OR talk", with licence ∈ {CC-BY, CC0}.
  - Content: English, single mostly-frontal speaker, ≥ 58 s, no YC link.
  - Selection: the first 15 by sha256(file title).
  - Curator: a label-free curator, recording URL, licence and sha256 only.
  - Processing: P1/P2/P2b/P3 identical to analysis T1.
  - Never wave-1 rows. Never data/wave2_pool/.

  (d) **Clip manifest**
  - Built ONCE on the pod with a pinned ffmpeg/x264/espeak-ng toolchain and bit-exact flags.
  - `refclips_manifest.json` holds the per-file sha256 of mp4/wav/tsv, the toolchain, the source-image sha and the licence sha. Its sha256 is added to `frozen:` before upload.
  - The GPU box stages manifest objects only and gates input_sha256 and transcript_sha256 against the manifest. It never rebuilds.

  (e) **S3 root**
  - `s3://yct-research-235229001983/wave1/derived/p4b_ref/v1/`, a sibling of `.../p4/` and never inside it.
  - Prediction prefixes: full/, audioonly/, textonly/.
  - The P4 root manifest.jsonl sha256 must be unchanged after every reference session.

  (f) **Kernels**
  - Kernel: d = ROI mean of (clip − matched control). The clip course is the event mean at lags −4…+8. The kernel is mean/max (signed).
  - Map: the gating map is spatially standardised. Raw enters K5 only.
  - Halves: selection = even clips, test = odd clips. p* = the signed argmax of the selection-half mean over lags −4…+8.
  - Acceptance rules:
    - **K1:** one-sided one-sample t over test-half clip means at p*, p < .001, AND every test-half clip mean > 0.
    - **K1′:** full mean at p* ≥ 0.25·σ_nat AND ≥ 0.2. σ_nat is the median ROI temporal SD over W in the NAT clips, standardised.
    - **K2:** p* and the full-data signed argmax both lie in [−1, +4]. The first rising 50%-of-peak crossing lies in [−4, +2]. The mean over lags 0–3 is ≥ 0.5·peak.
    - **K3:** peak / √(mean_{lag −4…−2} Var_j c_j(lag) / n) ≥ 3.
    - **K3′:** |mean of d over event-free spans (≥ +12 TR after an event and ≥ 5 TR before the next)| ≤ 0.10·peak.
    - **K4a:** median leave-one-clip-out r(training kernel, held-out course) ≥ 0.5.
    - **K4b:** split-half r(even, odd) ≥ 0.7.
    - **K5:** sign(std) = sign(raw) at lags 0–3, AND |p*_std − p*_raw| ≤ 1.
    - **K6 (MT_plus only):** MOT peak > the FLASH response mean over lags 0–3.
  - Fail closed: NaN, inf, zero SD, an all-zero course, a truncated window or a zero-filled TR gives STOP_INVALID. Only PASS counts.
  - Disclosed: the K2 window was chosen knowing ENH-002. TRIBE is deterministic, so K1's p measures consistency across exemplars, not sampling error.
  - Before launch, the frozen code is run on the ENH-002 summary courses and the result is disclosed.

  (g) **STOP versus descriptive**
  - Gating kernels: FFC (LOC face), AUD full model (SPK), AUD audio-only (SPK, audio-only condition).
  - MT_plus (MOT incl. K6), per owner decision 2026-11-19 (pre-registered demotion, Neuroscientist cycle-1 option): MT_plus gates if its kernel passes K1–K6. If it fails, the motion control is demoted to descriptive before any analysis-set read: it is reported with the failing criterion, the limitation is disclosed in the report, and the motion (a)/(c) controls do not gate. It is never replaced by a flash kernel, and this rule is fixed now and cannot be revisited after reference outputs exist.
  - Descriptive: PH, body, V1_V3, BURST, TALKFACE.
  - Any other gating FAIL or STOP_INVALID is a P4b STOP.

  (h) **Redesign cap**
  - At most one versioned redesign (`p4b_ref/v2`), by a new DECISIONS entry, with v1 reported in full.
  - A second failure is a STOP to the owner. No silent re-runs.

  (i) **Controls**
  - Gating set and map: T1 (51) on standardised maps. T3 and raw are reported. All tests are one-sided.
  - (a) Within-video partial r:
    - pairs FFC×face_area_crop_frac, AUD×speech_envelope and MT_plus×motion_energy_crop;
    - the regressor is convolved with the ROI kernel at lags −4…+8 with zero-padding;
    - partial out the other regressors and luminance_change (convolved with the target kernel), with an intercept, over W [5, 45);
    - inference: z = atanh(r) clipped at 0.999999; PASS = mean z > 0.2 and p < .001;
    - low-SD exclusion: SD below P10 over NAT (linear, ddof 1); if fewer than 15 videos remain, use NAT (n = 15).
  - (b) Selectivity, paired, p < .01:
    - face: FFC > V1_V3 on the full model;
    - speech: AUD > FFC on the audio-only condition of T1 51;
    - both arms use the gating ROI's kernel.
  - (c) Between-video correlation:
    - pairs W-averaged FFC × face fraction, and AUD × mean envelope;
    - B = 10,000 permutations, seed `seeds.controls_perm`;
    - PASS = r > 0.3 AND unrestricted p < .05 AND within-era_block p < .05;
    - era blocks with < 6 gating videos merge into the adjacent later block (the last merges into the previous one);
    - route blocks are never used.
  - (d) Localiser:
    - readout: the mean of lags 0–3 of (intact − scrambled) per category and hemisphere;
    - FFC: face − mean(place, body) > 0 and face − place > 0;
    - PH: place − mean(face, body) > 0 and place − face > 0;
    - PASS = sign-consistent in L and R AND a clip-bootstrap 95% CI (B = 10,000) that excludes 0 in each hemisphere.
  - Negative controls:
    - upload-date parity (expected null);
    - source aspect ratio, only if ≥ 2 levels have ≥ 10 T1 videos each; otherwise recorded as untestable.

  (j) **Q1–Q6**
  - Q1 = B1 amended. Audio-only and text-only predictions come from the existing D-038 cache: same key, new prefix, Gate-1 cached rerun, an extractor-not-called gate. Reference-clip conditions run in this campaign. The analysis-set audio-only run has its own ablation entry (D-072) and runs after it.
  - Q2 = licensed photographs, intact vs scrambled, on grey, ≥ 20 per category including body.
  - Q3 = NAT, as in (c).
  - Q4 = unrestricted AND era_block, never route.
  - Q5 = (f).
  - Q6 = hard STOP.

  (k) **Cost and launch**
  - Estimate: about 15 sessions, about 21 billed h, about $42.
  - Hard campaign cap: $75 (owner decision, 2026-11-19). Reaching the cap means STOP and report.
  - Before launch: the ledger is reconciled agent-side (L4 tolerance max($0.50, 1%)), and the current spend and budget_cap() are recorded.
  - Session 1: `--limit 3` (GREY-CTRL s0, SPK_00, MOT_00, which are also the D-038 clips), watched, with a human check.
  - Every session: `--max-hours ≤ 1.4` (enforced in code), `--usd-limit 8`, external terminator, dead-man switch, exit 75/1 semantics, and launch only from a pushed CI-green commit. Driver fixes BUG-033 and BUG-028 must be merged first.

  (l) **No-revision rule.** After the post-run P4b design entry and the first analysis-set read through `p4_open`, no kernel, ROI, regressor, threshold, exclusion or fallback may change. Any (a)–(d) FAIL is a STOP to the owner and the council.
