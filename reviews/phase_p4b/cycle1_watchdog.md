# P4b design v1: Watchdog review, council cycle 1

Reviewer: Watchdog (process integrity). Read-only review of `reviews/phase_p4b/design_v1.md` (bb3b1c6) against
v2.md §5 P4/P4b, ROADMAP P4/P4b, DECISIONS D-038/D-039/D-055/D-063/D-065/D-066/D-067/D-068, config
`controls:`/`p4:`/`budget:`, and the cited code: `src/yct/tribe_run/{make_reference_clips,enh002,qc,feature_cache}.py`,
`src/yct/predict/p4_index.py`, `scripts/gpu_wave1_p4.py`, `infra/lambda_gpu.py`.
I read no labels, no `data/sealed/`, no `data/wave2_pool/` and no prediction arrays. I used no AWS.
`pytest tests/test_p4_index.py tests/test_gpu_wave1_p4.py tests/test_controls_config.py`: 52 passed.

## Verdict: GO-with-conditions

- **Building may start now.** That covers the generator, the wrapper, the kernel code, speech_envelope and their
  tests, all CPU and dry-run work.
- **Launching the reference-clip GPU job is NO-GO** until B1–B7 below are closed.
- **Firewall status:** I found no breach of D-063 B2.
  - `p4_index` returns keys and hashes only.
  - Nothing in `src/` or `scripts/` other than the driver and `p4_index` references `pred_clampv1/`.
  - `outputs/` is empty.
  - The design's own claims (103 refs, 1 revisions hash) are manifest metadata only.
- **Process risk:** the design freezes the reference-clip spec, the K1–K5 rules and the STOP consequences only
  in the post-run design entry. The stimulus and the pass/fail rules of a STOP gate would then still be open
  after the gate's own outputs are seen. That ordering is the blocking issue.

## Blocking items

**B1. Stimulus spec, K1–K5 and failure consequences must be in a DECISIONS entry BEFORE the GPU launch, not
only in the post-run design entry (§8).**

Evidence:
- v2.md §5 P4b: "Any control change only via a DECISIONS entry before the lock."
- config `controls.dry_run` comment: "changes only via a DECISIONS entry before the lock".
- D-063 Q4 says the kernels are "re-derive[d] from 58 s single-chunk reference clips". It does not fix families,
  onsets, event counts or thresholds.

The design changes the spec in several places:
- 20 events per family where config has `n_flashes`/`n_speech_bursts` = 5.
- New motion, face and place families.
- Talking face excluded as a kernel source, where v2.md lists "flashes, speech bursts on a noise bed, a talking
  face".

Freezing all of this only after kernels exist (§3 output → §8 items 1–2) lets the stimulus or the thresholds be
revised after the gate's own outputs have been seen.

Required: a pre-run entry (next free id, D-071) that freezes:
- the full §1 spec, including the sha256 manifest of the built clips;
- K1–K5 as exact formulas;
- the consequence of a K failure;
- a cap on redesign. My proposal: at most one versioned redesign (`p4b_refclips_v2`), only by a new DECISIONS
  entry, with v1 results reported in full. No silent re-runs.

The post-run design entry then adds only `kernels_v1.json` sha256 and the K results.

**B2. The motion stimulus spec contradicts itself and cannot be built as written.**

Evidence:
- §1 asks for a "high-contrast grating / random-dot field ... mean luminance matched to the frame (Δ mean luma
  ≈ 0)".
- The base frame is black (`make_reference_clips.py`: `color=c=black`).
- A high-contrast pattern on black has a mean luma above black by construction.
- The planned test "Δ mean luma within 1% of the bed" therefore fails, or forces a near-zero-contrast stimulus.
- The alternative of a grey base for that family breaks "the bed is identical across clips" and the
  ref_control58 subtraction.

Whichever fix is chosen is a stimulus change and belongs in the B1 entry before building. Options include:
- a grey base for every clip;
- a static-grating companion control for the motion family.

The fix must be chosen on stimulus grounds before any motion-kernel output exists. It must not be chosen after
K1 is seen.

**B3. Localiser (d) drops the body category without a DECISIONS entry.**

Evidence:
- v2.md (d) says: "1 s face/place/body image flashes; readout ... minus the other categories".
- The design has face and place families only (§1, §4 d). It plans no body stimuli.

To close: add a body family to the same GPU job, or record the deviation (and the changed "other categories"
contrast) in the B1 entry.

This is linked to Q2: the stimulus source for (d) has to be settled before the job is built. Otherwise (d) needs
a second GPU job, and a second job is exactly where a post-hoc stimulus swap could happen after a synthetic
(d) failure.

**B4. Reference-run isolation is weaker than the design claims and needs explicit guards.**

Evidence:
- §2 says "p4_index refuses any key outside pred_clampv1/, so reference clips can never enter the analysis set".
  In fact `p4_index` drops every row not in the frozen (track, video_id) set before it checks the prefix
  (p4_index.py lines 41–44). The real guard is the run-set filter, not the prefix.
- The P4 driver is hard-wired to the analysis store:
  - `plan_jobs` reads `p4.run_set_*`;
  - `PRED_PREFIX`/`ENTRY_PREFIX` are module constants;
  - `RealBackend.s3root = p4.s3_prefix`;
  - `load_state` lists `s3_list("")` of the whole P4 root;
  - `clip_gate` accepts only `TRACKS = ("t1", "t3")`.
- The proposed `<p4 s3_prefix>/p4b_refclips_v1/` sits inside the P4 root. L2 (the archive of "every object
  under the P4 S3 root") and every P4 driver `load_state` would then see reference objects.

Required, each with a test:
- (i) The reference store is a sibling root outside `wave1/derived/p4/`, for example `wave1/derived/p4b_ref/v1/`.
  It has its own `manifest.jsonl`, `rows/` and `stops/`, and the wrapper never writes under the P4 root.
- (ii) The P4 root `manifest.jsonl` sha256 is recorded before and after each reference session and must be
  unchanged.
- (iii) The P4 driver's analysis-store code path is unchanged, or every existing `test_gpu_wave1_p4` assertion
  still passes unweakened (`check_test_weakening`).
- (iv) A `ref` track gate with T == 58 and n_words == .tsv rows, in place of a relaxed t1/t3 gate.
- (v) The kernel module reads only the reference root. It refuses any `pred_clampv1/` key, and it does not
  import `p4_index`. This is a grep/import test like the driver firewall test.

The design has a T-REFRUN prefix test but no reader-side guard for T-KERNEL.

**B5. What enters TRIBE must be exactly the frozen stimulus.**

Evidence:
- T-REF58 plans a "bit-identical rebuild" test.
- CI has no espeak-ng (no hit in `.github/`).
- libx264, AAC and espeak-ng output depend on version. A clip rebuilt on the GPU box need not match one built
  in CI or on the pod.

Required:
- Build once, record per-file sha256 in the B1 entry, and upload to the reference root.
- The GPU job verifies `input_sha256` and `transcript_sha256` against that frozen manifest. This mirrors the P4
  check "clip/transcript sha256 == the pod's" (D-064 c).
- The job refuses on a mismatch. It never regenerates the clips on the box.

**B6. Q1 option B1 as written conflicts with D-038, D-063 and D-065(d). Audio-only conditions for the reference
clips must also be decided before this job.**

Evidence:
- D-038 / v2.md P4: features are "extracted once into a content-addressed feature cache ... every analysis (T1,
  T3, ablations, M0b) reads from it".
- `feature_cache.py` line 14: "every prediction (reruns, ablations, controls) reads only the cache".
- The design's B1 instead specifies "a new cache key", that is, re-extraction. Re-extraction is not bitwise
  reproducible (D-068).
- D-063 and D-065(d): ablations "wait for their own spec + GPU test".
- config `controls.dry_run.n_speech_bursts` comment: "audio-only, text-only, both". So the dry run expects
  ablation conditions on the reference speech clips. The design runs them only as full-model predictions, plus
  audio-only under B1/B2.

Required:
- The ablation spec is its own DECISIONS entry. It covers the estimand, the label ("audio-only"; text path =
  "text+TTS"), prediction from the existing P4 feature cache (same key, a new prediction prefix such as
  `pred_audioonly_v1/`), a loader keyed by (track, condition, video) with the same firewall, and a GPU test.
- The audio-only and text-only reference conditions (ref_speech58 ×5, ref_control58, ref_talkface58) run in this
  reference job. Alternatively, dropping them is recorded in the B1 entry.

**B7. Cost: the estimate is wrong, and P4 overran its own estimate. Both must be on record before the next
launch.**

Evidence:
- §2: 27 jobs ≈ 3.0 h ≈ 2 sessions ≈ $6–7.
- By the design's own figure (s16–s18: 7–9 jobs per 1.4 h session, including boot and the ~30 min
  `SETUP_EST_S`), 27 jobs take 3–4 sessions, about 4.2–5.6 billed h, about $8.4–11.1. Adding the B6 ablation
  conditions makes it more.
- D-067(e) projected the P4 total at ≈ $43. The design reports `lambda_gpu.py spent` = $51.86 at P4 end, about
  $9 over. That gap is unexplained, and BUG-027 orphan minutes are known.
- The ledger reconciliation (L4) is scheduled only for the lock.

Required in the B1 entry:
- the corrected estimate and a hard campaign cap for the reference job (my proposal: $15). Exceeding the cap
  means STOP and report;
- the agent-side part of L4 (Σ launch→terminate × rate vs `spent`, orphan minutes per BUG-027 event), done
  before the first reference launch;
- the current spent value and the owner-verified cap from `budget_cap()`.

`--usd-limit 8` and `--max-hours ≤ 1.4` per session stand.

The D-066 conditions apply in full:
- an external terminator armed at deadline + 15–60 min;
- the dead-man switch first;
- exit 75 means re-run, exit 1 means a human;
- launch from a pushed commit with CI green.

One more is needed, because the wrapper is new code: session 1 runs capped (`--limit 3`: ref_control58 plus two
clips) and gets a human check before uncapped sessions. This is the D-066 and D-067(d) V1 pattern.

## Non-blocking items

**N1. K1 is ambiguous.** It says "one-sample t across the 20 events", but the test half (k = 1, 3) holds
8 events. At df = 7, p < .001 needs t > 5.4. Also, the events within a clip come from one deterministic forward
pass, so the "p" measures variability across onset positions, not sampling. Write the n and the meaning of the
statistic into B1. Biostat should own the formula.

**N2. K3's baseline window overlaps a known pre-onset rise.** It uses the SD of lags −4…−1. ENH-002 and D-055
record a rise ≈ 3 TR before onset (bidirectional context). K3 could pass or fail for reasons unrelated to kernel
quality. Fix the baseline definition before the run, for example the residual SD of ref_control58, and not
after it.

**N3. K2's window [−1, +4] was chosen knowing the ENH-002 result** (peak 0 for flash and speech). This is
label-free and non-analysis, so it is acceptable, but the B1 entry should disclose it.

**N4. Within-clip events are very close together.** At 13 s spacing with a 13-TR window and ≈ 3 TR of backward
leakage, the next event's pre-rise falls into lags +5…+8 of the previous one. This is Neuro's call, but it must
be decided pre-run (for example, wider spacing or fewer events).

**N5. The FFC kernel source is luminance-confounded.** The face family flashes a face onto black. In ENH-002 the
FFC response to a plain flash (1.25, standardised) was 20× V1–V3's response (0.06). An FFC kernel can therefore
pass K1 with no face specificity. This is not a firewall issue, but a K1 pass for FFC should not be read as
validating the face control. Consider a luminance-matched scrambled-face companion, decided pre-run.

**N6. The (a)/(b) dry run on reference clips is circular.** It is evaluated on the same clips that produce the
kernels. Use held-out clips (the split-half test clips, or ref_talkface58 only) and say so.

**N7. The low-SD exclusion is underspecified.** It reads "P10 of the reference clips", but which ones? The
synthetic families have degenerate regressor SDs (face fraction is 0 in flash clips). The reference set and the
rule must be frozen before anyone tabulates analysis-set regressor SDs against the threshold. P3 confounds of
the analysis set exist and are not under the firewall, but knowing how many videos a threshold excludes is
analysis-set data feeding a design choice. The count of excluded videos is computed only after the design entry.

**N8. Ref clips skip P2 normalisation.** They are 640×360, 30 fps, 16 kHz AAC, while analysis clips go through
P2 (loudness −23 LUFS, 48 kHz). Normalising would break the shared bed, so skipping it is defensible, but the B1
entry should say so and give the reason.

**N9. speech_envelope modifies the analysis-set P3 confounds tables.** Writing it there must be append-only
(originals kept, like `*.pre_p2b.*`) with provenance (run id, git sha). It must read only the P2 audio16k files,
never transcript text. The design's T-ENV test covers the transcript part.

**N10. The T-CTRL guard is weak as written.** "Refuses to run until DECISIONS holds the P4b design entry id"
should also require that the entry's `kernels_v1.json` sha256 equals the file on disk, and that the entry is
committed (`git log`) in a commit that precedes the controls run commit.

**N11. Add a no-revision rule to the design entry.** After the first analysis-set read, no kernel, ROI,
regressor, threshold, exclusion or fallback change is allowed. Any (a)–(d) FAIL is a STOP routed to owner and
council, never a re-specification.

## Answers to the open questions

**Q1. (b) audio-only: B1, B2 or B3?**
- Choose **B1**, as amended by B6:
  - its own ablation DECISIONS entry;
  - prediction from the existing P4 feature cache (no new cache key, no re-extraction; D-038);
  - a separate prediction prefix and loader condition;
  - the same firewall.
- The reference audio-only conditions run in this reference job.
- **B2** narrows a v2.5 C3 control to synthetic speech after P4 has finished. It reads as weakening a gate for
  cost, and the cost saving is small once prediction runs from the cache.
- **B3** is rejected. It contradicts v2.5 C3 and lets the text path carry the speech effect.

**Q2. (d) stimuli: synthetic line drawings, or a licensed public localiser set?**
- A public localiser set is acceptable from a process view only if all of the following hold:
  - the licence is verified and recorded (source URL, commit or version, sha256 of the licence text);
  - the images are frozen by sha256;
  - the per-category selection rule is mechanical (for example, the first N in sorted filename order);
  - no image is linked to YC or to any analysis company;
  - face, place and body categories are included (B3);
  - all of it sits in the B1 entry before the job is built.
- I have not verified the fLoc licence. If no verifiable open licence exists, use synthetic stimuli.
- Whichever source is used, declare now that a (d) FAIL is a STOP. Swapping to "better" stimuli after a
  synthetic failure would be post-hoc tuning of a gate.

**Q3. Reference naturalistic clips: public non-YC talking heads, or non-primary wave-1 rows?**
- Use **public, openly licensed, non-YC talking-head videos.** Requirements:
  - chosen by a pre-declared mechanical search and selection rule;
  - selected by an agent with no label exposure;
  - URL and sha256 frozen in DECISIONS before any TRIBE run on them;
  - processed through P1/P2/P3 like the analysis videos.
- **Not the non-primary wave-1 rows.** They are YC application videos from the same companies as analysis rows
  (one is picked per company), and their labels sit in the sealed file. Their predictions would set the P10
  low-SD threshold and the OOD reference. That makes analysis-adjacent, label-linked data a design input.
- **Not `data/wave2_pool/`.** D-069 says no pool row is analysed.
- If the clips can be fixed before launch, add them to this GPU job to save a session.

**Q4. (c) permutation: unrestricted, or within D-040 era × route blocks?**
- Use **unrestricted** permutation, with n = 10,000 and the seed in config, frozen in the design entry.
- Route (OPEN/TARGETED) is sealed (D-040), and route blocks are coded owner-side (`scripts/owner_label_qc.sh`).
  A label-free control gate must not depend on sealed information or an owner-side step.
- If the council wants exchangeability, use `era_block` only. It is in `data/manifest.csv` and visible to
  analysts. Decide it in the design entry, before any (c) statistic.

**Q5. K1–K5 thresholds: accept as fixed, or tighten?**
- Accept the values. Fix them in the B1 entry before the run, after resolving the N1 and N2 definition issues.
  After the run, neither tighten nor loosen them.
- The consequence must be pre-declared: a gating-kernel K failure is a P4b STOP. The only way forward is one
  versioned redesign by a new DECISIONS entry, with full disclosure of v1 (B1).

**Q6. Is the motion stimulus adequate for an MT+ kernel? If K1 fails for MT_plus, is that a STOP or a disclosed
limitation?**
- The stimulus as written cannot be built (B2). Adequacy is Neuro's call.
- On failure: **a STOP.** `controls.regressors.motion` (gating: true, roi MT_plus) is a frozen key (D-063 Q4).
  A "disclosed limitation" chosen after K1 is seen would turn a gating control into a descriptive one after the
  outcome is known.
- The council may pre-register a downgrade path now. If it does, the path goes in the B1 entry through the
  frozen-key change procedure, before the GPU run. Otherwise a failure is a STOP and goes to the owner.
