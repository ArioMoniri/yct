# Gate P4-entry (wave 1) — Strict Referee (fresh, adversarial)

**Subagent id.** The harness did not give me one. Council session session_011NAQ1mksc4Ea1mJcrGfTSd, role Strict Referee.

**Scope.**
- Commit 421c7ef, clean tree. `pytest -q`: 619 passed, 0 failed (209 s).
- What I read:
  - the packet;
  - docs/prompts/v2.md (v2.7);
  - ROADMAP.md;
  - DECISIONS D-047…D-062;
  - BUGS (BUG-013, BUG-018, BUG-021, BUG-027);
  - ENHANCEMENTS (ENH-002, ENH-008);
  - run wave1p2b_20261118T002855Z: report.md, metrics.json, enh002_latency.json, enh002_preds/*.csv, *.events.csv;
  - data/wave1_normalize_qc.csv, data/wave1_confounds_summary.csv, data/wave1_transcripts_summary.csv, and the label-free manifest columns;
  - src/yct/tribe_run/{feature_cache,enh002}.py, src/yct/confounds/core.py, src/yct/normalize/photometric.py, scripts/owner_label_qc.sh, config.yaml `controls:`/`vad:`;
  - my prior reviews: reviews/final_round/{p0_c2,p1_c2,gD032_c3}_strict_referee.md.
- I did not open data/sealed/, decrypt anything, touch AWS, or look for any outcome information.

## Q1 verdict: **GO (conditional)** for full wave-1 TRIBE inference (T1 + T3, audio/video/text+TTS ablations)

Running TRIBE is label-free compute. Nothing that has happened so far makes the predictions invalid:
- Gate 1: the cached rerun is bit-identical, 3/3.
- BUG-018 is fixed and GPU-verified.
- Backbones are pinned and run offline.
- A cache entry whose revision or GPU does not match is refused (feature_cache.py:162–165).

The risk is in what happens **after** the predictions exist. W, L, the P4b kernel, the ROIs and comparators, the treatment of low-fps sources and the M0 definitions are all still open. They would then be chosen with the predictions in view, and the orchestrator who would choose them is already exposed to about 11 wave-1 labels (BUG-013, BUG-021).

The GO therefore depends on **B1–B3** below. All three are documentation only, need no re-run, and must be committed as DECISIONS entries **before the instance is launched**. If they are not committed by then, this vote becomes **FIX**. The MAJOR items do not block inference. Each one blocks the phase named next to it.

## Q2 — yct_0644 (no source file)
**Exclude it, before unblinding, with reason `source_unavailable`, as D-060 proposes.**
- The reason is mechanical: no raw file exists, and the owner's sealed-URL attempt failed.
- The deadline is fixed in advance: P4 launch.
- Exclusion also removes a label-exposed row (BUG-013).

Two conditions:
1. The exclusion is **irrevocable**. The video must not be re-admitted to wave 1 even if the file turns up later. Every agent who would re-admit it knows its label.
2. The bias cannot be checked. "Source unavailable" may be missing-not-at-random: a founder site taken down could correlate with outcome. With n = 1 this is negligible, but it must be listed in the deviations.

Consequences:
- N = 52; T1 N = 51.
- Add N = 51 and N = 52 rows to the Q dimension table. Both give ⌊N/3⌋ = 17, the same as N = 53, so the dimensions are unchanged; but the table must be printed at the final N (v2.md:81).

## Q3 — sources below 16 fps
**Accept the D-060 proposal: keep them, add a `low_fps_source` flag, and run a sensitivity analysis that excludes them.** Conditions:
- **(a)** Only **one** analysis-set video is affected: yct_0626, 12.5 fps, E12. yct_0641 has qc_pass = False, so it is outside the 53. Excluding yct_0626 would remove an era-correlated video from the smallest era block (E12 = 10). That is a worse confound than keeping it with the flag.
- **(b)** v2.md:381 says sources "must be at least 16 fps". Read literally, together with the P2 DoD ("each failure is logged as an exclusion"), that is an eligibility rule. The D-entry must **amend that sentence**, not just note an exception. It must also state that the same rule applies unchanged to wave 2.
- **(c)** The flag is not an M0 term. It would add a 17th required Q column at N ≈ 51. The sensitivity analysis sits outside Holm and uses the T3 survive/fragile rule.
- **(d)** yct_0444 (17.2 fps) passes the threshold and gets no flag. Write that down so that nobody later "tidies" it into the flag set.

## Q4 — ENH-002 visual control
**Make the switch now, a priori: MT+ becomes the gating motion control, and V1–V3 is reported descriptively. Reject the luminance-only kernel.** The evidence:
1. **The dry run did not test the motion control.**
   - Control (a) for V1–V3 uses **motion energy** as its regressor (config.yaml:334).
   - The dry run used full-field **luminance flashes**, which is exactly the quantity (a) partials out (config.yaml:335–340).
   - So the weak V1–V3 response to flashes says little about V1–V3 × motion. It does **not** justify a choice in either direction on its own.
2. **The case for MT+ is a priori.** TRIBE known issue #9 (mean-pooled V-JEPA tokens) was documented before any data. MT+ is the canonical motion ROI. v2.md:414 and config.yaml:328–331 already name MT+ as the only sanctioned fallback. Switching for that documented reason, before any wave-1 control is computed, is defensible. Switching after seeing (a) on wave-1 videos is not.
3. **A luminance-only kernel changes the regressor.** v2.md:432 says regressors "cannot be tuned". It would also make the motion control collinear with the partialled-out luminance-change term. Reject it.
4. **Control (b) as written is uninformative.** Raw response to the flash at lags 0–3: FFC 0.232, MT+ 0.180, V1–V3 0.069. FFC reacts to a black→white flash about as much as to the face (raw face − control: FFC 0.253). Against a comparator that barely responds to anything, "FFC > V1–V3 for faces" (v2.md:423) passes trivially. Keep it, and **add** FFC > PH on the face regressor as an extra requirement. Adding a requirement makes the gate harder to pass, never easier.
5. **The kernel and latency evidence is not yet fit to freeze a kernel.** See M1 and M2 below. The reference clips have to be rebuilt before the P4b lock.

## Q5 — WER
**WER does not block P4 inference. It blocks P5 (feature freeze).**
- If WER later forces a change to a transcript, that clip's cache key changes (feature_cache.py:96–100), so only cost is at risk, not validity.
- Two things must be set **now**, before the hand-check:
  - an **action threshold**: there is none (v2.md:396 asks only for a report). A WER number with no consequence is theatre;
  - the **accent flag** that v2.md:396 requires. It is not implemented: no `accent` anywhere in src/, config.yaml or the data CSVs.
- The sample is not random. The 5 WER clips are the first 5 sorted ids. Draw them by a seeded hash instead, or at least add the clip with the lowest ASR-speech fraction (0.09).
- See M5 for language.

## Q6 — ENH-008 caption flag
**A limitation for P4 and P5. It blocks the Q(M0) freeze (P5b) only as a decision, not as an implementation.**
- On-screen text, slides and demo screens are a plausible label-correlated visual confound that M0 does not cover (`text_frac` is never in M0, config.yaml:222).
- Before P5b, choose one of two options:
  - **(a)** add a label-free proxy as an **S-TEXT sensitivity** outside Holm. Do not put it in the primary Q: Q is saturated at N = 51–52;
  - **(b)** declare it a limitation only.
- Either way, the H4 "beyond M0" sentence (v2.md:18) must name on-screen text as **not controlled**.

## Q7 — BUG-027
**Adequate for validity.** The cost side belongs to the Watchdog.
- An aborted extraction cannot be silently mixed into the results:
  - a half-written entry keeps its marker and has no sidecar, so `ensure()` fails on `mkdir` (feature_cache.py:172–173);
  - a mismatched revision or GPU raises.
- Two additions are required:
  - (i) every P4 video record carries run_id and instance_id;
  - (ii) at archive time, assert that **all** P4 cache entries have an identical `revisions` dict, GPU name included. That is the executable form of "one GPU type for all of P4".
- Wiping a partial entry and extracting it again must be logged. `n_extractions` stays 1 per archived entry, so the log is the only record of it.

## Q8 — other items before P4
See B1–B3 (before launch) and M3 and M4. Also see the carry-overs from my P1 c2 and P0 c2 reviews that are still open (M6, M7).

---

## Defects

### BLOCKERS (pre-launch, documentation only)

**B1. L and the rule that fixes W are undefined, and the evidence now conflicts.**
- v2.md:53 sets W start = max(5, 4 + L + 1), with L = "P0 impulse latency rounded up". D-055 states L ≤ 0. But enh002_latency.json gives:
  - speech-AUD peak 0.0 TR (raw) and 0.4 TR (standardised; t95 up to 1.08);
  - flash-V1–V3 peak 2.8 TR (raw) and 4.0 TR (standardised).
- Neither "onset or peak", nor "which ROI and map", nor "P0 or ENH-002" is pinned down.
- T1 eligibility depends on that choice (wave1_normalize_qc.csv):

  | L | W start | min tail W_end + 5 | Also excluded from T1 |
  |---|---|---|---|
  | 0 or 1 | 5–6 | 50–51 s | none |
  | 2–3 | — | 52–53 s | yct_0528 (51.3 s) |
  | 4 | 9 | 54 s | yct_0528, yct_0186 (53.1 s) |

- The minimum count of words in W (22, yct_0528) also sits next to the < 20-word exclusion.
- "Set from the label-free group-mean time course" (v2.md:54) has no rule attached, and the time course becomes visible only after inference.
- **Fix:** before launch, a DECISIONS entry that sets:
  - L := 0 TR, defined by the speech-AUD raw peak lag (5/5 events at lag 0), consistent with D-055;
  - W = [5, 45) TRs, frozen;
  - a mechanical, pre-written rule for when the group-mean time course may move W (for example: only if the cortex-mean spatial SD at TR 5 is still > X% above its W median). Otherwise the time course is descriptive only.

**B2. There is no firewall on the outputs.**
- After the launch, the predictions for all 57 videos exist. The only agent running P4 knows the labels of yct_0644 and of the 10 BUG-021 rows.
- **Fix:** a DECISIONS entry stating:
  - no W-averaged, ROI, M1 or parcel quantity is computed on wave-1 predictions until the P4b design entry (Q4, M1, M2) is committed;
  - every later label-free choice (Q3/Q6 wording, merge list, kernel) is made from pooled, label-free summaries;
  - nobody inspects predictions per video for the exposed ids;
  - the archive manifest hash (sha256) is committed before the first analysis touches the outputs.

**B3. Record the Q2 and Q3 decisions (exclusion of yct_0644; the low-fps rule) before launch, as answered above.**
- These two rules set the analysis set. Once outputs exist they must already be fixed.

### MAJOR

**M1. The reference-clip design makes the ENH-002 kernels and latency CI invalid.**
- The ref clips are 120 s long, so they span **two** 60 s chunks (ref_flash.events.csv: Audio/Video at 0–60 and 60–120). T1 is one 58 s chunk.
- The event at 55 s spans lags to 63 s, across the boundary of known issue #2. Audio is z-scored per chunk.
- Within a clip, the events are not independent:
  - for flash event 5 (95 s), flash − control is **exactly 0.0** at lags +5…+8 (raw and standardised) and the post-event plateau is absent;
  - events 1–4 show non-zero lag 5–8 values. For speech, events 1–4 undershoot by −0.8 to −1.5 at lags 5–8; event 5 does not undershoot.
- The tail of the "impulse response" therefore seems to come from the **next** event, 12–15 s later. That is long-range backward context, beyond the "up to 4 TR" bound of D-055. Otherwise it is an artefact.
- **Fix:**
  - rebuild the clips at ≤ 58 s, single-chunk, **one event per clip**, 5 clips per event type, with matched controls. Add a luminance-balanced **motion** event (drifting grating or dots) for V1–V3 and MT+;
  - explain the exact zeros;
  - restate D-055's bound if the backward context goes beyond 4 TR (e.g. "no timing claim finer than 15 s");
  - run the new clips in the same P4 GPU session (cost about 1 GPU-hour).

**M2. P4b depends on inputs that do not exist yet.** All three are pre-lock, and all can be decided label-free now:
- **(i) The face reference is a cartoon.**
  - The FFC face kernel needs real face footage: a licensed or consenting talking head, not a YC applicant, inside the DATA_DECISION faces terms.
- **(ii) There are no reference naturalistic clips.** v2.md:421 and v2.md:433 need ≥ 5, for the OOD check and for the < 15-video fallback in (a).
- **(iii) The aspect-ratio negative control is degenerate.**
  - Its "expected detectable" known confound has almost no variance: 56 landscape, 1 square, no 9:16 (wave1_normalize_qc.csv).
  - Replace it pre-lock with a label-free stimulus variable that has variance (for example face_area_crop_frac, median split).

**M3. Gate 2 is still not met as specified, and D-062 overstates it.**
- v2.md:410 requires reliability ≥ 0.99 for **every M1 feature and the parcel values**. My P0 c2 B2 asked for the same.
- metrics.json `drift` gates on backbone tensors (`reliability_min` 0.99903) plus whole-map `pred_reliability`. No M1 or parcel reliability is computed.
- D-062 calls the 0.999 result "per-feature reliability", and a reader will take "feature" to mean M1.
- The effect on validity is probably nil: max |Δpred| ≤ 0.0045 against pred_std ≈ 0.16. But the claim is not supported as worded.
- The deviation from "seeded sha" to the first 3 sorted ids is also not reflected in v2.md:410.
- **Fix:**
  - during P4, keep the fresh-extraction predictions of the 3 gate clips;
  - compute M1 and the 400 parcel values under the frozen W, and express the drift relative to the between-video SD over the 51 T1 videos (label-free);
  - until then, reword D-062 to "per backbone-tensor reliability ≥ 0.999; whole-map prediction r ≥ 0.999994; M1/parcel reliability pending";
  - amend v2.md:410 to the sorted-id rule.
  - Blocks P5.

**M4. The speech-fraction confound does not measure speech.**
- `speech_frac` is an energy VAD (core.py:7, config.yaml:132), which counts music and noise.
- Analysis-set T1: median 0.952 (range 0.67–1.00). The ASR word-covered fraction has median 0.668 (0.09–0.78), and the two correlate at only r = 0.25 (wave1_confounds_summary.csv × wave1_transcripts_summary.csv).
- speech_fraction, its square and speech_rate·speech_fraction are **forced** Q terms (v2.md:68) whose purpose is to absorb the text-path confound (known issue #8). Measured this way, they absorb loudness coverage, not speech amount.
- **Fix (label-free, before W-averaged M0 is computed):**
  - redefine `speech_frac` as the fraction of each TR covered by aligned ASR words, or as a speech-specific VAD;
  - keep the energy VAD only for loudness gating;
  - D-entry plus a test.
  - Blocks P5.

**M5. English-only and video authenticity are unverified, and outcome-revealing content is unscreened.** Blocks the P5 analysis-set freeze.
- WhisperX is forced to `en` (known issue #6: "English-only is a hard constraint"), yet `language` is UNKNOWN for 22/53 analysis rows.
- D-047 and v2.md:370 require every in_primary row to be watched (rubric: submitted cut / re-edit / compilation / **outcome-revealing**). The curation report (curation_report.md:127) says this was not done. All 53 rows still carry `is_original_application_video = true` from metadata.
- Media and transcripts now exist. A re-upload that says or shows "we got into YC" would put the **outcome straight into TRIBE's text and video inputs**: direct leakage into M1 and into M0b.
- **Fix:** a sealed agent (not the orchestrator) runs:
  - automated language ID;
  - the watch rubric;
  - a transcript scan for outcome phrases.
  - It outputs only {keep, exclude, reason-code} per id plus counts. Exclusions are applied label-blind.

**M6. Exchangeability blocks have not been re-issued (carry-over: P0 c2 gate list DECISIONS:88; my P1 c2 B1).**
- scripts/owner_label_qc.sh:185–186 and 266–279 still build blocks over **58 in_primary** rows, from the `discovery_method` fallback (`ROUTE_FALLBACKS`, line 66). It neither uses qc_pass nor maps the method to D-040 OPEN/TARGETED.
- SSM /yct/owner/blocks is stale (BUGS: 4 blocks over 58, sizes 4/4/45/5).
- Inference does not use blocks, so this does not block P4. But it was recorded as a P4 precondition, and the packet does not mention it.
- **Fix:**
  - a D-entry that re-scopes it to "before P5b";
  - the owner re-runs the script on the 52-row set with an explicit method → OPEN/TARGETED map;
  - it prints only block sizes and the N in label-mixed blocks.

**M7. The stop rule and other P1 carry-overs are still open.**
- **(a)** ≥ 20 conf-A per group has **not been verified** for the final set (v2.md:25 assumes the 33/20 worst case). The owner should print a single yes/no for "both groups ≥ 20 at N = 52 and at T1 N = 51". If the answer is no, wave 1 becomes a descriptive pilot (v2.md:375).
- **(b)** My P1 c2 B5 (sealed query class plus a NEUTRAL-only sensitivity) and B6 (record the BUG-021 ids sealed; an **exposed-rows-excluded** sensitivity) have no DECISIONS entry. B6 matters more now that the orchestrator runs P4.
- Both block P5b.

### MINOR

**m1. The latency "CI" wording overstates what 5 events can show.** "boot95 [0, 0]" and "t95 [4.0, 4.0]" come from 5 peak lags quantised to whole TRs. A bootstrap over them gives no interval. Report it as "5/5 events peak at lag 0 (TR resolution)", or estimate latency at sub-TR resolution (e.g. a centroid or onset fit).

**m2. The cache key differs from the spec.**
- The spec (v2.md:408): key = video ‖ transcript ‖ revisions ‖ device class.
- The code (feature_cache.py:100) keys on video + transcript only and refuses a mismatched revision or GPU on reuse.
- The two are functionally equivalent (fail-closed), but the spec text must match the code. Amend v2.md:408 or add a D-note.

**m3. The ENH-002 talking-face numbers mix map scales.** `ref_face_minus_control_mean` is raw; the flash and speech by-ROI numbers are standardised. Label each, or report both, before anyone compares FFC face against FFC flash.

**m4. The T1 N and Q table need one line each.**
- Restate T1 N = 51 and N = 52 in v2.md §0, with the label-free MDE re-run (`pw.py 51`, `h4sim.py … 51`).
- The current text gives 53.

---

**Searched and found clean:**
- T3 audio is stream-copied from T1 (photometric.py:234–235), so T1 and T3 differ only in video.
- T3 reuses the T1 transcripts (114 rows from 57 ASR runs).
- uvx/ASR are guarded (`asr_called` false in all runs).
- Gate 1 is bit-identical 3/3.
- BUG-018 checks pass on long110/long160.
- Trimming is applied only where the video is black **and** the audio is silent; first word ≤ 4.1 s.
- No HDR source and no 9:16 source.
- No blinding-sensitive columns in the data CSVs I read.
