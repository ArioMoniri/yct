# P4b design v2: Watchdog review, council cycle 2

Reviewer: Watchdog (process integrity). This is a read-only review of:
- `reviews/phase_p4b/design_v2.md`, including its closing "Owner decisions (2026-11-19)" section;
- `reviews/phase_p4b/d071_draft.md` at HEAD cb641da;
- commit ca63a9d (BUG-033 and BUG-028 driver fixes: `scripts/gpu_wave1_p4.py`, `config.yaml`, `src/yct/config_schema.py`,
  `tests/test_gpu_wave1_p4.py`).

I checked these against my cycle-1 review (`cycle1_watchdog.md`), DECISIONS.md, the config `controls:`/`p4:`/`budget:`/`frozen:`
sections, and `infra/lambda_gpu.py`.

Scope limits:
- I read no labels, nothing in `data/sealed/` or `data/wave2_pool/`, and no prediction arrays.
- I used no AWS and decrypted nothing. I made no commit.

Test runs:
- `pytest tests/test_gpu_wave1_p4.py tests/test_p4_index.py tests/test_controls_config.py`: 58 passed (52 in cycle 1, plus the 6 new BUG-033/028 tests). Full suite: 741 passed.
- I did not check the CI status of ca63a9d or cb641da myself. My allowed tools were git, grep and pytest only.

The three owner decisions are binding inputs and I do not re-open them:
- the $75 campaign cap;
- Wikimedia CC0/CC-BY localiser photographs;
- pre-registered demotion of MT+ to descriptive if it fails.

The items below are about whether D-071 records and enforces those decisions consistently. They do not question the decisions.

## Verdicts

**(1) Commit D-071 as written: NO-GO.** Four small text defects make the frozen entry self-contradictory or false
(new items B8–B11). Each is a one-line edit. None needs new design work or another council cycle. After the edits, D-071 may be committed
with its config keys in `frozen:` and CI green, without a further Watchdog review. I will check the diff only.

**(2) Build the tickets, then launch the reference GPU job once the G tickets are closed with green CI: GO-with-conditions.**
- **Building may start** as soon as D-071 is committed in corrected form.
- **The launch** additionally needs:
  - B12 (the $75 campaign cap enforced in code, with a test);
  - B13 (a defined MT+ demotion trigger);
  - B7's pre-launch execution items (L4 reconciliation, recorded spend and `budget_cap()`);
  - the ENH-002 known-data K-run committed;
  - all G tickets green, including T-REFRUN's isolation tests.

**Firewall (D-063 B2): no breach found.**
- `pred_clampv1/` is still referenced only in `src/yct/predict/p4_index.py` and `scripts/gpu_wave1_p4.py`.
- No tracked file exists under `outputs/` except `outputs/runs/`.
- ca63a9d touches only the launch path. Its changes are the price lookup, `lg.launch` exception handling, and the `--max-hours` guard.
- The existing firewall tests (`test_firewall_*`) are unchanged and pass.
- The `SMALL` fixture gained `launcher_max_hours: 4`. That only lets existing tests keep their earlier `max_hours`. It is not a weakened assertion.

**Freeze-before-output: holds.** No reference clip, reference prediction or kernel exists, and D-071 is ordered first (§0, step 1).

**Blinding: holds.** Every new input is label-free: the synthetic families, Wikimedia images and Wikimedia NAT video. Both curators are specified as label-free.

## Cycle-1 blocking items

| id | status | evidence |
|---|---|---|
| B1 pre-run freeze of spec, K-rules, consequences, redesign cap | **PARTIAL** | D-071 (a)–(h) freezes the stimulus spec, the exact K1–K6 formulas, fail-closed rules, the STOP/descriptive split and the redesign cap (`p4b_ref/v2`, one only, v1 reported in full). The clip-manifest sha is to be frozen before upload (D-071 d). Not closed because the entry contradicts itself (B8) and points at an id that is already taken (B9). It closes when B8–B11 are fixed and T-D071's `check_frozen_config` test is green. |
| B2 motion stimulus not buildable | **CLOSED** | Persistent mid-grey background for every clip (luma 128). MOT is the 1 s drift of an always-present pattern, with the MOT-STAT twin (same pattern, never moving) as control. Luma and contrast constancy within 1% is tested with the real `yct.confounds` (§1.5). This was fixed on stimulus grounds before any output exists. |
| B3 body category dropped | **CLOSED** | LOC has face, place and body events in Latin-square order, 20 exemplars each. The (d) contrasts are face − mean(place, body) and place − mean(face, body) (D-071 i). A new inconsistency about the "object" category is raised as B10. |
| B4 reference-run isolation | **CLOSED (spec); implementation gated by T-REFRUN/T-KERNEL** | Sibling root `wave1/derived/p4b_ref/v1/` with its own manifest, rows, stops and entries. The P4 root `manifest.jsonl` sha must be unchanged before and after each session (test + runtime). Track `ref` uses the T1 gate. The kernel reader refuses `pred_clampv1/` and does not import `p4_index` (AST test). All five of my cycle-1 sub-items (i)–(v) are in the T-REFRUN and T-KERNEL test lists. Sub-item (iii) still applies to the refactor: replacing module constants with constructor arguments changes the analysis-store code path, so every existing `test_gpu_wave1_p4` assertion must pass unweakened (`check_test_weakening`). See N16. |
| B5 frozen stimulus enters TRIBE | **CLOSED (spec)** | The clips are built once on the pod with a pinned toolchain and bit-exact flags. `refclips_manifest.json` holds per-file sha256 and its own sha is frozen. The box only stages manifest objects and gates `input_sha256`/`transcript_sha256`; it never rebuilds. Tests are in T-STIM and T-REFRUN. |
| B6 ablations from the cache; audio-only reference conditions | **CLOSED (spec)** | Full, audio-only and text-only predictions come from the same D-038 cache entry via `features_to_use`, with the cache key asserted unchanged and Gate 1 run on ≥ 3 clips per condition. An extractor-not-called gate is required, the prefixes are separate, and the conditions run in this campaign. The analysis-set audio-only run gets its own entry later. That entry is mis-numbered (B9). |
| B7 cost estimate, cap, L4, launch conditions | **PARTIAL** | Closed parts: the estimate is corrected to about 15 sessions, about 21 billed h, about $42. The cap is $75 (owner). L4 runs agent-side before launch with tolerance max($0.50, 1%). Session 1 is `--limit 3` with a human check. The D-066 terminator conditions are restated. Open parts: (i) the $75 cap is not enforced by any code or ticket test (B12); (ii) D-071 (k) says `--max-hours ≤ 1.4 (enforced in code)`, but ca63a9d enforces 1.75 (B11); (iii) the L4 reconciliation and the recorded spend/`budget_cap()` are pre-launch actions and are not done yet. That is correct ordering, and they stay launch preconditions. |

## New blocking items

### Block committing D-071 as written

**B8. D-071 contradicts itself on the MT+ failure consequence.**
- (g) carries the owner's pre-registered MT+ demotion correctly.
- (j) still reads "Q6 = hard STOP".
- design_v2 also still says "There is no pre-registered demotion path" (§3.4) and "v2 makes it a hard STOP with no demotion" (§10). The owner section overrides both, but D-071 is the binding text.

Fix: change (j) Q6 to "pre-registered demotion for MT_plus (see g); FFC and AUD: hard STOP".

**B9. The D-072 id collision.**
- D-071 (j) and design_v2 §4(b) name the analysis-set audio-only ablation entry "D-072".
- D-072 is already in DECISIONS.md: Curator round 4, commit a7e4990.

Fix: write "a separate ablation DECISIONS entry (next free id at the time)". A frozen entry must not cite an id that points to an unrelated decision.

**B10. The "object" category has no defined use.**
- The owner decision and D-071 (b) select 20 images per category for face, body, place **and object**.
- The LOC family in (a), the (d) contrasts in (i) and the 98-clip total all use face, place and body only.

A frozen spec must be single-valued before the build. Write one of these:
- (i) object images are curated but not used in v1 and are not shown to TRIBE. The coverage rule stays "face, place, body".
- (ii) object is a 4th LOC event. That changes the event count, the Latin square, the onsets, the (d) "other categories" mean and the cost.

Option (i) keeps the reviewed design unchanged. Choosing between (i) and (ii) is not re-opening the owner's image-source decision.

**B11. D-071 (k) states a launcher limit the code does not enforce.**
- D-071 (k) and the T-DRV ticket say `--max-hours ≤ 1.4 (enforced in code)`, with a constant `LAUNCHER_LIMIT_H` and a default of 1.4.
- ca63a9d instead adds `p4.launcher_max_hours: 1.75` (not in `frozen:`), sets the CLI default to 1.75, and tests `< 2.0`.
- The §2 cost arithmetic assumes 1.4 h sessions.

Fix, either:
- (a) D-071 says "≤ `p4.launcher_max_hours` (1.75 h), enforced in code", and the estimate is recomputed or noted as conservative; or
- (b) the reference wrapper refuses `--max-hours > 1.4`, with a test.

Either is acceptable, but the frozen text must match the code. If the wrapper reads `p4.launcher_max_hours`, add that key to `frozen:` with D-071. That way the session-length terminator cannot be raised silently during the campaign.

### Block the GPU launch

**B12. The $75 campaign cap must be enforced in code, with a test, before launch.** This concerns enforcement only, not the amount.
- The only automatic spending guards today are:
  - the global `budget_cap()`: min(`infra/BUDGET_USD` = 200, the SSM owner value), checked against the cumulative `spent_usd()` across all phases;
  - the per-session `--usd-limit`.
- Neither enforces a campaign total. A run of 15–20 sessions at ≤ $8 each could pass $75 with every per-session check green.

Required, in T-REFRUN, with tests:
- The baseline `spent_usd()` is recorded once in the ref root (`entries/campaign_baseline.json`, with the ledger line count and sha) before session 1.
- The wrapper refuses to launch when (spent − baseline) + price × max_hours > 75. The refusal is exit 1 (human), not 75.
- At ≥ 80% of the cap ($60), it warns and requires a human acknowledgement.
- The cap value comes from a frozen config key (`controls.refclips.campaign_cap_usd: 75`).

D-071 (k) should also say what the cap covers:
- the reference campaign `p4b_ref/v1` only, including D-038 reruns and the reference ablation conditions;
- not the later analysis-set audio-only run, which carries its own cost in its own entry;
- not a `p4b_ref/v2` redesign, which needs its own cap in its own entry.

The cap must not be re-used silently by a redesign.

**B13. The MT+ demotion trigger must be defined, and placed in config, before any reference output.** The owner has decided the demotion. Its edges are still open, and each edge left open becomes a post-hoc choice.

D-071 (g) must state:
- (i) **Trigger.** Demotion happens on a K FAIL of any MT+ rule (K1, K1′, K2, K3, K3′, K4a, K4b, K5, K6). STOP_INVALID is a pipeline fault (NaN, zero-filled TR, truncated window, zero SD, including a FLASH input that K6 needs). It is a P4b STOP that is fixed and re-run, **not** a demotion. Otherwise a pipeline bug would quietly turn a gate into a description.
- (ii) **Finality.** Once MT+ is demoted in v1, it stays descriptive for the whole study. A `p4b_ref/v2` redesign triggered by an FFC or AUD failure may not re-attempt MT+ to restore it as a gate. Alternatively, D-071 may state the opposite now. Either way, it is fixed before output.
- (iii) **Mechanism.** The frozen key `controls.regressors.motion` (`gating: true`, frozen at c616a9d) stays unchanged. The demotion rule is a new frozen key, for example `controls.kernel.acceptance.on_fail.MT_plus: descriptive`. T-CTRL reads the gating status from that key plus the K results in `kernels_v1.json`, and a test covers the demoted path. The text "motion (a)/(c) controls do not gate" should read "the MT_plus × motion_energy_crop (a) pair does not gate". (c) has no motion pair. `motion` stays in `partial_out` either way, because partialling uses the target ROI's kernel.

## Non-blocking items

**N12. The ENH-002 known-data K-run must be committed before launch, not after.** design_v2 §3.1 promised it "in the cycle-2 packet". It is not there, and it cannot be until T-KERNEL exists. D-071 (f) says "before launch", which is acceptable. Record its output (pass/fail per rule) in a commit that precedes the session-1 launch commit, and make it a checklist item next to L4.

**N13. Snapshot the candidate pools before applying the mechanical selection rules.**
- The Wikimedia category and search results change over time, and the content filters (single subject, frontal, no text or logos) involve judgement.
- For LOC (T-LIC) and NAT (T-NAT), the curator must record:
  - the exact query or category list and its UTC timestamp;
  - the full candidate list, sorted by sha256(title), with its sha;
  - a reject log with one reason code per skipped file.
- Without these, "the first 20 / first 15 that pass" cannot be audited.
- design_v2 §1.2 still says "sorted file name". D-071 (owner) says sha256 of title. D-071 governs, but fix the design text.

**N14. Frontal-face filter.** design_v2 §1.2 requires frontal faces only. D-071 (b) lists "single subject, photograph, no text or logos" and omits it. Add it back, or state that it was dropped.

**N15. The T-NAT disjointness test reads `data/wave2_pool/`.** T-NAT asserts that NAT rows are disjoint from the wave-2 pool. The test should compare only URL or video-id columns, or hashes of them, never any other pool field. The alternative is to run it owner-side. Under D-069 the pool is not analysed, so this restriction keeps the test from becoming a reason to read the pool.

**N16. Keep the analysis-path refactor reviewable.**
- T-REFRUN turns the driver's module constants (`PRED_PREFIX`, `ENTRY_PREFIX`, `s3root`, `TRACKS`) into constructor arguments.
- Land it as its own commit, before the wrapper. Its only test change should be additions.
- Keep the default arguments byte-equal to the current constants, with a test that pins `PRED_PREFIX == "pred_clampv1/"` against `p4_index`.
- Run `check_test_weakening` against ca63a9d.

**N17. Termination for the exit-75 retry loop.**
- ca63a9d maps *every* HTTP 400 from `lg.launch` to no_capacity / exit 75. It also logs the body (good).
- A non-capacity 400 would make the re-run loop retry forever. Examples: a bad ssh-key name, an invalid instance name, an account or quota problem.
- No money is spent, but no human is called either.
- Required, in the wrapper or runner: a maximum number of consecutive exit-75 misses, or a wall-clock limit, after which the loop exits 1 for a human. Alternatively, return exit 75 only when the 400 body matches capacity wording.

**N18. Debris on a miss.** T-DRV requires "no run-dir debris, empty ledger delta". `_no_capacity` → `_finish` writes `child_metrics.json` locally and to `runs/<id>/` in the store. That is a useful audit record, but it does not match the ticket text.
- Either change the ticket wording to "a run record only, no instance, no ledger line", or delete the record.
- Add the assertions the ticket lists but the tests lack: no ledger line, and `spent_usd()` unchanged across the launch-time miss paths. Today only the price-lookup test checks `launched == []`.

**N19. Session-1 job order.** `--limit 3` takes `pending[:3]`. T-REFRUN must test that the wrapper's job order puts GREY-CTRL s0, SPK_00 and MOT_00 first. Session 1 then runs exactly the D-038 clips named in D-071 (k).

**N20. Personality rights.** Wikimedia face photographs of identifiable people can carry the Commons "personality rights" warning. Copyright (CC0/CC-BY) is verified per file. Record the presence of that template in the T-LIC manifest and exclude flagged files, or note why research use is unaffected. Images are internal stimuli only and are never published.

**N21. The config comments on `controls.pass` are stale.**
- `min_videos` says "fewer -> evaluated on the >= 5 reference naturalistic clips".
- `low_sd_percentile` says "of the reference clips".
- D-071 changes both to the 15 NAT clips.
- Update the comments, and the values if needed, in the same commit that adds `controls.pass` to `frozen:`. The frozen subtree then says what D-071 says.

## Launch checklist (Watchdog view)

1. D-071 committed with B8–B11 fixed. `controls.refclips`, `controls.kernel.acceptance` (including the B13 key), `controls.pass`, `seeds.controls_perm` and the cap key are in `frozen:`. CI is green.
2. The G tickets are merged with CI green: T-D071, T-DRV, T-LIC, T-NAT, T-STIM/T-REF58, T-REFRUN (including B12 and N19), T-KERNEL and T-ENV. The LOC, NAT and clip manifests are frozen, with candidate snapshots per N13.
3. The ENH-002 known-data K-run is committed (N12).
4. L4 agent-side reconciliation is PASS. `spent_usd()`, `budget_cap()` and the campaign baseline are recorded.
5. Session 1 runs `--limit 3` from a pushed CI-green commit with the external terminator and dead-man switch armed. A human check follows before any further session.
