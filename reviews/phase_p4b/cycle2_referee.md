# P4b design v2 — council cycle 2 — STRICT REFEREE

Reviewer: Referee (hostile journal reviewer). Scope:
- reviews/phase_p4b/design_v2.md, including its closing "Owner decisions (2026-11-19)" section;
- reviews/phase_p4b/d071_draft.md;
- my own reviews/phase_p4b/cycle1_referee.md.

I checked them against DECISIONS.md (D-063, D-070, D-072), docs/prompts/v2.md §5 P4b (l.416–436), config.yaml (`controls:`, `p4.launcher_max_hours`, `frozen:`), BUGS.md (BUG-028, BUG-033), scripts/gpu_wave1_p4.py and tests/test_gpu_wave1_p4.py.

Method: read-only (git, grep, pytest).
- I opened nothing in data/sealed/ or data/wave2_pool/, and no labels or prediction arrays.
- I did not use AWS.
- pytest could not collect tests/test_controls_config.py or tests/test_gpu_wave1_p4.py in this container, because numpy and yaml are not installed (ModuleNotFoundError). I installed nothing. Statements about the BUG-028/033 tests come from reading the test source and from commit ca63a9d ("full suite 739 passed"). They are not my own run.

The owner decisions are binding inputs and I do not re-litigate them:
- the $75 campaign cap;
- Wikimedia Commons CC0 / PD / CC-BY localiser photographs;
- MT+ pre-registered demotion to descriptive.

I judge only whether D-071 discloses and specifies them adequately.

## Verdicts

1. **Committing D-071 as written: NO-GO (minor revision).**
   - The scientific content is sound and closes almost all of cycle 1.
   - But the draft contradicts itself on the one owner decision that changes the inference (Q6 / MT+, B13).
   - It does not specify the demotion branch well enough to run it mechanically (B14).
   - It points its ablation entry at a DECISIONS id that already exists for a different purpose (B15).
   - It claims a launcher limit that the code does not enforce (B16).
   - It leaves the cap's scope and enforcement undefined (B17).
   - It leaves the Wikimedia curation rule not mechanical (B18).

   All six are text or config fixes with no GPU. They need no new council cycle: a delta check by Referee + QA on the amended draft is enough. The commit must be **atomic**: D-071 + `controls.refclips`, `controls.kernel.acceptance`, `controls.pass` and `seeds.controls_perm` in config.yaml + their `frozen:` rows + the check_frozen_config test. None of those keys exists in config.yaml today. Without them, D-071 is prose and not a freeze (cycle-1 B8).

2. **Building the tickets, and launching the reference-clip GPU job once the launch-blocking tickets close with green CI: GO, with conditions.**
   - Ticket building (TDD) may start now for T-DRV, T-REFRUN, T-KERNEL and T-ENV.
   - T-LIC and T-STIM/T-REF58 may start only after the amended D-071 is committed, because B18 changes their specs.
   - The launch is GO only when all of the following hold:
     - (i) the amended D-071 is committed atomically, as above, on a commit that precedes the clip build;
     - (ii) every G ticket in design_v2 §8 is merged and CI is green on the launch commit, **including** the T-DRV items that are still missing (B16);
     - (iii) the T-KERNEL known-data run on the ENH-002 summaries is committed, with the list of evaluable rules (N14), before session 1;
     - (iv) the image (T-LIC) and NAT (T-NAT) manifests and `refclips_manifest.json` are frozen in `frozen:` before upload;
     - (v) the campaign-cap guard (B17) is in the wrapper and tested;
     - (vi) session 1 is `--limit 3`, watched, and followed by a human check, as specified.

## Status of cycle-1 blocking items

| # | Status | Evidence |
|---|---|---|
| B1 motion stimulus | **CLOSED** | §1.1 MOT: the pattern is static for the whole clip and drifts for 1 s. The MOT-STAT twin is the baseline. The background is mid-grey (luma 128 in the 256² view). §1.5 requires `luminance_crop`/`contrast_crop` to stay within 1% over the clip, and the static twin to show no event. |
| B2 face/place category specificity, body | **CLOSED** (residual → B18) | LOC: an intact photo replaces its own phase-scramble. The twin swaps to a second scramble of the same exemplar, which matches the transient. SHINE-matched luma, RMS contrast and spectrum. Body family added. Real licensed photos (owner: Wikimedia). The residual is that body images can contain faces (B18c). |
| B3 STOP criteria | **CLOSED** for the design (residuals N11–N14) | Signed argmax (§3, "not max\|·\|"). The clip is the unit, with disjoint even/odd halves. Effect floor K1′ (≥ 0.2 and ≥ 0.25·σ_nat). The gating map is standardised. K5 has a sign rule. K2 cites the ENH-002 knowledge as disclosed. The known-data run is moved from "disclosed in the design" to "before launch". I accept that only as a launch condition (verdict 2 iii). The design says the outcome is "disclosed in the cycle-2 packet", but no such output is in reviews/phase_p4b/. K5 still *gates* on lag agreement against my request (N11). |
| B4 event isolation | **CLOSED** | 3 events at 20 s spacing ([9, 29, 49] + s). The first window starts at ≥ 4 s. K3′ checks the residual baseline. With a 20 s spacing and a −4…+8 window, no previous response reaches the next window before lag +16. |
| B5 speech impulse | **CLOSED** | SPK: 1.0–1.5 s utterances of 2–3 words, 30 distinct. BURST is kept only for descriptive kernel ⊗ envelope validation. |
| B6 input path / circularity | **CLOSED** | §1.4: the same P2 T1 normalisation and run_clip flags, a P2 no-op test, and the controls_report circularity statement. The text path still gets uniform-split .tsv timings and not WhisperX (disclosed, N1 of cycle 1). |
| B7 ablation runs, cache rule | **CLOSED** | §2: full/audioonly/textonly from the same D-038 cache entry, cache key asserted unchanged, Gate-1 on ≥ 3 clips per condition, a gating audio-only AUD kernel. 33 audio-bearing clips (10 + 5 + 2 + 1 + 15) check out. |
| B8 pre-run freeze | **PARTIAL** | The structure is right. D-071 freezes stimuli, K-code and thresholds, the (d) rule, the STOP/descriptive split, the redesign cap, the S3 root and the cap, all before any reference output. Not closed because: (j) contradicts (g) (B13); the demotion branch is not mechanical (B14); the ablation entry id collides (B15); the frozen config keys do not exist yet (verdict 1). |
| B9 gating set | **CLOSED** | §4 and D-071 (i): T1 51 on standardised maps gates; T3 and raw are reported. The audio-only run is on T1 51. |
| B10 negative controls, OOD, reliability | **CLOSED** (residual N18) | Upload-date parity. An aspect-ratio testability rule fixed now by a label-free metadata count. OOD as > P99 of NAT. Reliability mask from the D-038 pairs. What the mask is *applied to* is unspecified (N18). |
| B11 low-SD rule, fallback | **CLOSED** | P10 over the 15 NAT clips (linear, ddof 1). Fallback n = 15 is feasible: the one-sided critical t(14) at .001 is about 3.79. TALKFACE (a)-face is declared undefined. The v2.md text ("≥5 reference naturalistic clips") still has to be amended (B14 vi). |
| B12 route blocks | **CLOSED** | §4 (c): never route. era_block is a label-free column of data/manifest.csv (header checked). Era blocks with < 6 videos merge, a rule fixed before any count is seen. |

## New blocking items

These block the D-071 commit. B16 and B17 also block the launch.

**B13. D-071 contradicts itself on Q6.**
- D-071 (g) carries the owner's MT+ pre-registered demotion.
- D-071 (j) still says "Q6 = hard STOP".
- design_v2 §3.2 lists MT_plus as gating with no condition. §3.4 says "There is no pre-registered demotion path". §10 says "v2 makes it a hard STOP with no demotion".
- The closing owner section says it "overrides the text above where they conflict", but D-071 is the frozen artefact and must be consistent on its own.
- Required:
  - (j) Q6 = "pre-registered demotion of MT_plus only, per (g); FFC and both AUD kernels hard STOP".
  - D-071 states that it supersedes design_v2 §3.2/§3.4/§10 on this point.

**B14. The MT+ demotion branch is not specified well enough to apply mechanically, and its amendments are not disclosed.**
- (i) **FAIL vs STOP_INVALID.**
  - D-071 (g) demotes "if it fails".
  - STOP_INVALID (NaN, zero SD, a zero-filled or truncated window) signals a pipeline fault, not an absent motion signal. Demoting on it would hide a pipeline fault.
  - Required: only a K-rule FAIL demotes. STOP_INVALID on MT_plus stays a P4b STOP.
- (ii) **K6 depends on a descriptive family.** K6 compares against the FLASH response, and FLASH is descriptive. Fix what happens when FLASH is STOP_INVALID: proposed, MT_plus K6 = STOP_INVALID, which by (i) is a STOP.
- (iii) **What exactly is demoted.** Name it:
  - the (a) MT_plus × motion_energy_crop pair, and the MT_plus kernel's K table, become descriptive;
  - `motion` stays in the (a) partial-out set, convolved with the *target* ROI kernel, so it is unaffected;
  - (c) has no motion pair. D-071 (g) says "motion (a)/(c) controls", which is wrong for (c).
- (iv) **The trigger is kernel-only, not result-contingent.** If the MT_plus kernel PASSes K1–K6, an analysis-set (a)-motion FAIL is a STOP, as for any gating control. State this explicitly. Otherwise the demotion reads as a licence to drop motion after seeing (a).
- (v) **Config mechanism.**
  - `controls.regressors.motion` (`gating: true`) is frozen at c616a9d (config.yaml l.461).
  - The demotion needs a new frozen key, for example `controls.pass.demote_on_kernel_fail: [MT_plus]`, that the controls code reads, with a test. The frozen key must not be edited after the run.
  - The test must show that the demotion is decided only from the K table in kernels_v1.json, before `p4_open`.
- (vi) **Disclosure.**
  - The demotion amends v2.md §5 P4b, which says "FAIL on any of them means STOP" (l.434) and makes motion energy for MT+ an (a) control (l.420).
  - It also amends the D-063 Q4 ruling that made MT+ gating.
  - D-071 must say so and bump v2.md (v2.8, as D-063 did with v2.7 P4E). In the same bump, carry the other v2.md changes D-071 makes:
    - kernel source families (SPK/LOC/MOT, not "flashes, speech bursts, a talking face");
    - NAT fallback n = 15 instead of ≥ 5;
    - the (c) era-block conjunction;
    - the (d) bootstrap CI and the twin-subtracted readout.
  - Fix the controls_report limitation sentence for the demoted branch now, as frozen text.

**B15. The ablation entry id collides.**
- D-071 (j) ("its own ablation entry (D-072)"), design_v2 §4 (b) ("proposed D-072") and §9 ("the D-072 run ids") all refer to D-072.
- D-072 already exists: DECISIONS.md l.152, Curator round 4 (wave-2 pool, commit a7e4990).
- A frozen pre-registration that points at an entry about pool collection is a provenance error. A later reader would follow it into the wave-2 curation record.
- Required:
  - Refer to "the analysis-set audio-only ablation entry (id assigned when written; next free id)", or reserve an explicit free id.
  - Correct §4 (b) and §9.

**B16. D-071 claims a launcher limit that the code does not enforce.**
- D-071 (k) says "`--max-hours ≤ 1.4` (enforced in code)". T-DRV says "constant `LAUNCHER_LIMIT_H`; default lowered to 1.4". The cost model assumes 1.4 h sessions of about 7 jobs.
- The merged fix (ca63a9d) enforces `p4.launcher_max_hours: 1.75` (config.yaml l.412; scripts/gpu_wave1_p4.py l.389, CLI default l.1096). The test pins 1.75 (tests/test_gpu_wave1_p4.py l.487–492).
- The T-DRV acceptance items "no run-dir debris, empty ledger delta" have no test. The capacity-miss tests (l.451–480) assert exit 75 and no launch, but not the debris or the ledger delta.
- Required, either:
  - a reference-campaign limit of 1.4 (config key + wrapper guard + test); or
  - amend D-071 to "≤ `p4.launcher_max_hours` (1.75)" and re-cost the sessions.
- Add the debris and ledger-delta assertions to T-DRV. T-DRV is not closed until both are done.

**B17. The $75 cap is binding but its scope and enforcement are unspecified.**
- The per-session `--usd-limit 8` does not enforce a campaign total.
- D-071 must fix:
  - (a) what counts toward the cap: reference sessions, orphan minutes (BUG-027/028 class), failed launches, the D-038 reruns, and the one permitted `p4b_ref/v2` redesign. Does the redesign share the $75 or get none without a new owner decision? The analysis-set audio-only run is presumably excluded, and that should be stated;
  - (b) the ledger tag or prefix that identifies campaign spend;
  - (c) the guard: the wrapper refuses to launch when `campaign_spent + usd_limit × safety > 75`, so that "reaching the cap" is prevented before launch, not discovered after it;
  - (d) a test.

**B18. Under the owner decision, the Wikimedia localiser curation is not yet mechanical.**
I accept the source; this item is about the specification only.
- (a) **Candidate universe.** "The first 20 by sha256 of the file title that pass" is mechanical only over a fixed candidate list.
  - D-071 must name the Commons categories and/or search strings per category, and a snapshot timestamp.
  - The curator freezes the full candidate list (title + file-page revision id) *before* ordering.
  - The curator logs every rejection with a reason code.
  - Otherwise the curator chooses the pool, and the hash ordering is decoration.
  - The same applies to NAT (c) ("lecture OR interview OR talk": the search namespace, filters and snapshot are not fixed).
- (b) **Licence set and attribution.**
  - List the admissible licence templates exactly: CC0; PD-*; CC-BY 2.0/2.5/3.0/4.0.
  - State whether CC-BY-SA is in or out.
  - Exclude NC, ND and GFDL-only.
  - CC-BY requires attribution, so "records only the URL, licence and sha256" is not enough. Record author/attribution and the file-page revision id in docs/stimuli/LICENSES.md. A per-file "licence text sha256" (D-071 b) needs a defined source for each file.
- (c) **Content filters, defined operationally.**
  - Body images must be headless, or have the face excluded. Otherwise FFC "face − mean(place, body)" in (d) is contaminated by faces in the body images.
  - Places contain no people.
  - Faces are single, frontal and adult.
  - Add to §1.5 QC: `face_area_crop_frac` ≈ 0 on body, place and scrambled frames, beside the existing "> 0 on ≥ 90% of face-event TRs".
- (d) **The object category.**
  - The owner decision and D-071 (b) curate face, body, place *and object*.
  - The LOC family has three event slots (face/place/body), and no (d) contrast or kernel uses object.
  - State its role, for example "curated, not shown in v1" or "descriptive only, never in a contrast". An unassigned frozen category is a forking path.
- (e) **Image processing.** Freeze the processing in D-071 or in the hashed builder code:
  - square crop rule;
  - resize to about 316 px;
  - greyscale formula;
  - SHINE options (histogram and/or spectrum matching, iterations);
  - scramble seed.
- (f) design_v2 §1.2 still says "sorted file name" and lists fLoc, the London Set and THINGSplus as candidates. Correct it to the owner rule, so that the cited design and D-071 agree.

## Non-blocking items

- **N11.** K5 keeps |p*_std − p*_raw| ≤ 1 as a *gate*.
  - The ENH-002 flash already shows a 2 TR std/raw lag split (+4 vs +2), which comes from spatial standardisation and not from signal transfer.
  - A stricter rule does not bias toward a pass, but it can spend the single permitted redesign on an artefact.
  - Recommendation: lag agreement reported only, sign agreement gating, as in cycle-1 Q5. If it is kept, disclose the ENH-002 precedent in D-071 (f).
- **N12.** The K3 denominator can be near zero, which makes K3 close to automatic.
  - The denominator is the across-clip variance at lags −4…−2. MOT and its twin share identical pre-onset frames, and SPK and GREY-CTRL share a bit-identical bed.
  - With deterministic TRIBE, that variance comes only from bidirectional context.
  - Disclose this, or add a floor (for example the denominator ≥ 0.05·σ_nat).
- **N13.** K3′ "event-free spans" leave room for interpretation. Fix the exact TR list. By my reading it is 21–24 and 41–44 (+ s), 8 TRs per clip. Say whether 0–4 (warm-up) is excluded.
- **N14.** On the ENH-002 summary courses, only K2, K5 and a partial K1′ (no σ_nat) are evaluable. K1, K3, K4a, K4b and K3′ need multiple clips and matched controls, and will return STOP_INVALID. The committed known-data disclosure should list which rules were evaluable. Otherwise "the expected result: flash fails K2 and K5" overstates what was checked.
- **N15.** "Latin-square order" over 20 LOC clips is not balanced. 20 is not a multiple of 3 (or of 6 orderings). Freeze the clip-to-order map and report the balance of category × onset position in the odd (test) half, which gates FFC K1.
- **N16.** The halves are confounded with the shift: even clips have s = 0 and odd clips s = −1. This is acceptable as a phase-generalisation test, but disclose it.
- **N17.** The (d) bootstrap seed key is unspecified, and only `seeds.controls_perm` is frozen. Add a `seeds.controls_boot` key, or state the reuse.
- **N18.** The reliability mask (r ≥ 0.99 over 3 D-038 pairs) has no stated use: applied to ROIs? reported only? Specify it before the lock.
- **N19.** design_v2 still has stale text beyond B13/B18f: §2 "proposed hard campaign cap $50". §4 (d) says the per-hemisphere vertex counts "are listed in D-071", but they are not, and §9 puts them in the post-run entry. They are atlas-derived and label-free, so put them in D-071.
- **N20.** Wikimedia face photos show identifiable people. Exclude files carrying a personality-rights warning and photos of minors, and record this in LICENSES.md.
- **N21.** I could not run pytest in this container (numpy and yaml are missing). The launch condition "CI green on the launch commit" therefore carries the whole verification of BUG-028/033 and the new tickets. Do not substitute a local run for it.
- **N22.** The cycle-1 N items I do not repeat are addressed or carried forward (N1 disclosed, N2 balanced sentences, N3 first window ≥ 4 s, N4 fail-closed on zero-filled TRs, N6 FFC vs PH descriptive, N7 circularity, N8 re-costed, N9 one-sided, N10 superseded run ids).

## Summary for the council
v2 is a substantial and honest revision. Ten of my twelve cycle-1 blockers are closed in the design. B3 is closed on the design, but its known-data run is still a launch condition. B8 is partial.

The remaining defects are consistency and specification defects in the freeze document itself:
- the Q6 contradiction;
- the demotion mechanics and disclosure;
- the D-072 collision;
- the 1.4 h vs 1.75 h claim;
- the cap enforcement;
- the Wikimedia candidate universe, attribution and the object category.

Fix B13–B18 in the text and config, have Referee + QA run a delta check, and commit atomically. Then the ticket build and the launch are GO under the conditions above.
