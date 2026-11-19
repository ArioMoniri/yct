# D-071 v2 sign-off: STRICT REFEREE

Scope: a sign-off pass, not a full cycle. I checked `reviews/phase_p4b/d071_v2.md` (HEAD 8a755c8), including its YAML block and changelog, against every item that blocks "commit D-071" in the five cycle-2 reviews (`cycle2_{watchdog,referee,biostat,neuro,qa}.md`).

The owner decisions are binding and were not re-opened: the $75 cap, Wikimedia CC0/CC-BY photos, and MT+ demotion on a genuine FAIL.

Method: read-only (git, grep, pytest, and one label-free atlas count).
- No AWS, no decryption, nothing from data/sealed/ or data/wave2_pool/, no labels or prediction arrays, no commit.
- `pytest tests/test_guards_frozen_config.py tests/test_config_schema.py tests/test_controls_config.py`: 89 passed.
- I recomputed the ROI vertex counts from the cached HCP-MMP1 annots with `yct.features.atlas.load_all()` and the union medial wall. FFC 46/58, PH 62/51, AUD 108/115, MT_plus 74/65 and V1_V3 572/576 all match D-071 (i). `mw_removed_frac` = 0.0 for all five.
- I recomputed the MOT direction and pattern balance from the frozen rules in plain Python (see X4).

## Item table

Line numbers refer to d071_v2.md unless stated otherwise.

| review item | status | evidence |
|---|---|---|
| WD B8 (Q6 contradiction) | RESOLVED | l.189: Q6 is now demotion for MT_plus only, with FFC and both AUD kernels hard STOP. l.6 voids design_v2 §3.2, §3.4 and §10. |
| WD B9 (D-072 collision) | RESOLVED | l.184 reserves D-073. A grep finds no other use of D-073 in the repo. l.5 has the append-after-D-072 note. The design_v2 residue is handled under Ref B15. |
| WD B10 (object category) | RESOLVED | l.51 says "objects: not curated in v1", and YAML l.245 agrees. |
| WD B11 (1.4 vs 1.75 h) | RESOLVED, but freezing it hits X1 | l.215 and YAML l.229/l.281 set 1.75 and freeze it. The cost is restated at l.192: 120 jobs × $0.45 + $4 + $3 = $61, and the clip count of 120 checks out. |
| WD B12 (cap enforced) | **NOT** (X5) | Scope, prefix, baseline, the exit-1 guard and the $60 acknowledgement are all present (l.193–199). But "campaign spend" in the guard formula (l.198) is never defined; see X5. |
| WD B13 (demotion trigger) | RESOLVED | The trigger, STOP_INVALID = STOP, finality, the `on_fail` key and the reading of the motion regressor are at l.130–139, with YAML l.271–273. |
| Ref verdict 1 (atomic freeze commit) | **NOT** (X1, X2, X3) | As specified, the freeze commit cannot pass check_frozen_config or the schema. |
| Ref B13 (Q6) | RESOLVED | l.189 and l.6. |
| Ref B14 i (FAIL vs STOP_INVALID) | RESOLVED | l.130–131. |
| Ref B14 ii (K6 needs FLASH) | RESOLVED | l.119 and l.130 (the trigger requires a complete FLASH). |
| Ref B14 iii (what is demoted; no (c)) | RESOLVED | l.133–137. |
| Ref B14 iv (kernel-only trigger) | RESOLVED | l.132. |
| Ref B14 v (config mechanism and test) | RESOLVED | YAML l.271–273. l.139. T-KERNEL l.314. |
| Ref B14 vi (v2.8 bump; frozen sentence) | RESOLVED, but the commit contents must list it (E1) | l.8–13 and l.140. |
| Ref B15 (id collision in design_v2 §4(b)/§9) | **NOT** | design_v2.md l.259 ("proposed D-072") and l.362 ("the D-072 run ids") are unchanged. The explicit void list at l.6 names §1.2, §2, §3.2, §3.4 and §10 only. |
| Ref B16 (launcher limit; T-DRV tests) | **NOT** (X6) | The limit is fixed. But the T-DRV wording at l.302, "no run dir left behind", contradicts the miss record the driver writes on purpose: `_no_capacity` → `_finish` writes `runs/<id>/child_metrics.json` (scripts/gpu_wave1_p4.py l.533–559). |
| Ref B17 (cap scope and enforcement) | **NOT** (X5) | As WD B12. |
| Ref B18 a (candidate universe) | RESOLVED | l.38–46 and l.62–63: queries, namespace, limits, UTC date, snapshot sha before any filter, and the reject log. |
| Ref B18 b (licences, attribution) | RESOLVED, plus trivial E8 | The text at l.36–37 and l.57 is complete. Config l.248 says `PD` while the text says `PD-*`. |
| Ref B18 c (content filters; QC on scrambles) | **NOT** | The filters at l.47–50 are fine. But the QC at l.33 checks only LOC body and place TRs. The required check, `face_area_crop_frac` ≈ 0 on scrambled frames (LOC-SCR, and the LOC scramble periods), is missing. |
| Ref B18 d (objects) | RESOLVED | l.51. |
| Ref B18 e (image processing frozen) | **NOT** | l.52–56 name the steps only. The greyscale formula, the SHINE options and iterations, and the scramble and pattern seed values (or a rule for deriving them) are absent. So is any record of the builder code's sha. |
| Ref B18 f (design_v2 §1.2) | RESOLVED | The void clause at l.6 names §1.2 explicitly. |
| Bio B6 (power) | RESOLVED | K1 α = .01 and FFC ≥ 80% (l.100–102, YAML l.262). SPK 20, MOT 16 + 16. Cost $61 < $75. |
| Bio B7 (peak; ≤ 0; K2 crossing) | RESOLVED | l.96–98 and l.106–109. K6 follows the like-for-like form (l.117). |
| Bio B8 (K3′) | RESOLVED | l.111–113. With onsets 9, 29, 49 the spans are TR 21–24 and 41–44 (8 TR), as I checked. |
| Bio B9 (self-contradiction; (c); estimate) | RESOLVED | l.189, l.136 and l.192. |
| Bio B10 (shift aliasing; Latin rows) | RESOLVED | Shift by (i//2) mod 2 gives 5/5 per half for 20 clips and 4/4 for 16. Latin rows split 4/3/3 in both halves. All verified. |
| Bio B11 (candidate pools) | RESOLVED | As Ref B18 a. |
| Neuro B5 residual (K2 plateau) | RESOLVED | l.107, YAML K2 `plateau_frac: 0.9`. |
| Neuro B7a / B7b | RESOLVED | l.189 and l.184. |
| Neuro B7c (MOT exemplars, balanced across halves) | **NOT** (X4) | All 48 exemplars are distinct, but the direction rule aliases direction class with the halves. |
| Neuro B7d (per-hemisphere counts and `mw_removed_frac`) | **NOT** (E6) | The counts at l.150–155 are correct (verified). `mw_removed_frac` is missing. |
| Neuro B7e (only frozen text) | RESOLVED, but the void list is incomplete (see Ref B15) | l.6. |
| Neuro B8 a–e | RESOLVED | l.130–140 and l.117. |
| Neuro B9 a–f | RESOLVED | l.36–72. Of these, (c) is l.47–50, (d) l.52–56 and (f) l.62–69. |
| QA B11 / B12 | RESOLVED | l.189, l.184 and l.5. |
| QA B13 (one number; frozen; limit + 0.01 test) | RESOLVED, but freezing it hits X1 | l.215 and l.309. |
| QA B14 (demotion executable) | RESOLVED | The `on_fail`/`on_stop_invalid` keys and the test matrix are at l.312–314. QA asked that STOP_INVALID be treated "as FAIL". D-071 instead makes it a STOP, which is stricter and agrees with WD B13(i), Ref B14(i) and Neuro B8a. This is disclosed at l.329, and I accept it. |
| QA B15 (cap guard) | **NOT** (X5) | As WD B12. |
| QA B16 (T-ABL) | RESOLVED | l.291–300 and l.182. |

## Defects found in d071_v2 (new or carried forward)

**X1. The freeze procedure it states cannot work (blocking).**
- l.7 and YAML l.280 say the keys are added to `frozen:` "in the same commit", with `frozen_at` = the D-071 commit sha.
- scripts/check_frozen_config.py requires `frozen_at` to be an ancestor of HEAD whose config.yaml already holds the key. A commit cannot name its own sha.
- The precedent uses two commits: c616a9d (keys), then 11bc34d (frozen rows with `frozen_at` c616a9d, plus tests/test_guards_frozen_config.py and tests/test_p4_config.py asserting the exact list).

**X2. `manifest_sha256: null` sits inside the frozen `controls.refclips` subtree (blocking).**
- Freezing a mapping freezes its whole subtree, compared by value.
- When T-STIM later sets the sha (l.81), check_frozen_config fails.

**X3. The YAML block does not fit the strict schema or the existing `controls.pass` (blocking).**
- src/yct/config_schema.py uses `extra="forbid"`:
  - `Seeds` has only `company_pick_salt`;
  - `Controls` has no `refclips` or `rois_per_hemi`;
  - `Kernel` has no `acceptance`;
  - `Pass` requires `within_video`, `selectivity`, `between_video`, `min_videos` and `low_sd_percentile`. The YAML block's `pass: {a, b, c, d}` would either fail the schema or sit beside the old keys and their stale "≥ 5 reference" comments (WD N21, Bio N20).
- D-071 does not say whether the new keys replace or merge with the old ones, or that the schema changes in the same commit.

**X4. The MOT rules alias stimulus content with the halves and the shift (blocking: this is Neuro B7c, and the same class of defect as Bio B10).**
- Under direction ((3i + k) mod 8), the selection half (even i) shows each cardinal direction (0/90/180/270°) 4 times and each oblique 2 times. The test half (odd i) is the reverse.
- So K1, K4b and K5 compare cardinal-heavy against oblique-heavy halves. Motion processing is anisotropic across directions, so this matters.
- The pattern-type rule ((i//2) mod 2 = 0 → dots) is the shift rule itself: every dot clip has s = 0 and every grating has s = −1.
- Checked: direction ((3·(i//2) + k) mod 8) gives each of the 8 directions exactly 3 times per half, and all 48 (pattern, direction) pairs stay distinct. Pattern type by (i//4) mod 2 gives a 2/2/2/2 pattern × shift cross in each half.

**X5. "Campaign spend" is undefined in the cap guard (blocking: WD B12, Ref B17, QA B15).**
- l.194 counts by instance-name prefix. l.197 records a global `spent_usd()` baseline.
- l.198 uses "(campaign spend)" without saying which of the two it means. Under baseline differencing, D-073 or any other concurrent spend would count. Under the prefix, it would not.

**X6. The T-DRV debris wording contradicts the code and QA's accepted audit record (blocking: Ref B16).** See the table row for Ref B16.

Non-blocking (worth folding in while revising):
- (g) l.141 lists PH as "Descriptive", while (i)(d) l.175–176 makes PH's localiser contrasts part of the (d) PASS rule. State that PH's (d) contrasts gate and that only the PH kernel is descriptive (Bio N17).
- Bio N18: a v2 redesign may change stimuli only, and K rules and thresholds stay as frozen in D-071.

## Verdict: REVISE

These are text and config edits only, with no design change and no GPU. After they are made, a grep-level delta check by Referee + QA is enough. Exact edits:

- **E1 (X1).** Replace l.7 with: "It is committed in two consecutive commits before any reference clip is built: (1) this entry, the config keys of the YAML block, the config_schema.py models for them, and the v2.md §5 P4b v2.8 text; (2) the `frozen:` rows for those keys with `frozen_at` = commit (1), plus tests asserting the exact frozen list (as 11bc34d did for c616a9d)." In YAML l.280, change the comment to "frozen_at = the sha of commit (1)". `p4.launcher_max_hours` may use `frozen_at: ca63a9d`.
- **E2 (X2).** Move `manifest_sha256` out of `controls.refclips` into a sibling key, `controls.refclips_manifest_sha256`. It is set and frozen in its own commit after the build and before upload. Edit l.81 to match.
- **E3 (X3).** Add to l.7: "`controls.pass` is replaced wholesale by the block below (schema `Pass` rewritten). `controls.kernel.min_reference_clips` and `controls.dry_run.{reference_clips_min, n_flashes, n_speech_bursts}` are set to D-071 values or removed, with tests/test_controls_config.py updated without weakening. `Seeds`, `Controls` and `Kernel` gain the new fields."
- **E4 (X4).** In (a) MOT l.27 and in the config:
  - direction = ((3·(i // 2) + k) mod 8) × 45°;
  - pattern type = dot if (i // 4) mod 2 = 0, else grating;
  - add `mot_pattern_rule`, and change `mot_direction_rule` to `"((3 * (i // 2) + k) % 8)"`;
  - add to T-REF58: "each direction 3× per half; pattern × shift 2/2/2/2 per half".
- **E5 (X5).** At l.198, define: "campaign spend := sum of billed cost (launch to terminate, `spent_usd()` semantics) over ledger launch records whose name starts with `yct-p4b-ref`, after the baseline line count". State that the baseline is used for reconciliation only.
- **E6 (Neuro B7d).** After l.155, add: "`mw_removed_frac` = 0.0 for all five (union medial wall removes no ROI vertex)". Add it beside `rois_per_hemi` in the config.
- **E7 (Ref B15).** In l.6, add "§4(b) and §9 (D-072 → D-073), and §4(d) (vertex counts are in (i))" to the list of void design_v2 passages.
- **E8 (Ref B18 b).** In config l.248, change `PD` to `PD-*` (template prefix) so that the config matches l.36.
- **E9 (Ref B18 c).** In l.33, change "on no LOC body or place TR" to "on no LOC body, place or scramble-period TR and no LOC-SCR TR (`face_area_crop_frac` = 0 there)".
- **E10 (Ref B18 e).** In (b) Processing, state: the greyscale formula (for example ITU-R BT.601 luma); the SHINE functions and iteration count; and the seed rule for each phase scramble and MOT pattern (derived from a named seed key in `seeds:`). Also record the builder code's git blob sha in `refclips_manifest.json`.
- **E11 (X6).** In T-DRV l.302, change "no run dir left behind" to "no instance and no ledger line; `spent_usd()` and the store `manifest.jsonl` bytes unchanged; the `runs/<id>/child_metrics.json` miss record is allowed and listed in L2".
