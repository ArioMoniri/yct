# P4b design v2 + D-071 draft: QA review (council cycle 2)

Reviewer: QA (test and engineering quality). Read-only: git, grep, pytest. No AWS, no decryption, nothing read from data/sealed/ or data/wave2_pool/, no labels, no prediction arrays, no commit.

Reviewed:
- reviews/phase_p4b/cycle1_qa.md (my cycle-1 items B1–B10, N1–N11);
- reviews/phase_p4b/design_v2.md, including the closing "Owner decisions (2026-11-19)" section;
- reviews/phase_p4b/d071_draft.md (as amended in cb641da);
- commit ca63a9d: scripts/gpu_wave1_p4.py, tests/test_gpu_wave1_p4.py, config.yaml `p4.launcher_max_hours`, src/yct/config_schema.py, BUGS.md;
- context: infra/lambda_gpu.py (`_req`, `types`, `launch`), src/yct/tribe_run/feature_cache.py (`cache_key`, `reliability`), config.yaml `controls:` and `frozen:`, DECISIONS.md D-070/D-072.

Tests run at HEAD cb641da:
- `pytest tests/test_gpu_wave1_p4.py`: 43 passed in 11 s. This includes the 6 new BUG-033/BUG-028 tests.
- Full suite: **741 passed**, 8 warnings, 241 s. The commit message says 739. The +2 come from later commits (a7e4990 added sealed parts 3–4, which adds parametrised checksum cases).
- I did not check CI status. `gh` is outside the tools I am allowed to use. CI-green is still a launch condition (see the launch list).

## Verdict

1. **Committing D-071 as written: NO-GO. Fix the text, then commit; no new council cycle is needed.** The draft contradicts itself on Q6 and reuses a decision id that is already taken. It also says a 1.4 h limit is "enforced in code" when the code enforces 1.75 h. And it freezes a MT_plus demotion rule that no config key or test can carry. B11–B14 list the edits. They are text and config edits only. QA re-checks them by grep in the D-071 commit.
2. **Building the tickets: GO. Launching the reference-clip GPU job: GO-with-conditions.** The launch can go ahead only once every ticket on the launch-blocking list below is closed, meaning code plus tests on a pushed commit with CI green. The council must also give its GO on that diff (design §0 step 2), and the pre-launch gates at the end of the list must be done.

## Cycle-1 items: status

"Design" means v2/D-071 now specifies the fix and its tests. "Code" means the fix is implemented and tested in the repo.

| item | design | code | status | evidence / residual |
|---|---|---|---|---|
| B1 BUG-033 / BUG-028 | n/a | done | **CLOSED** (a residual threshold issue moves to B13) | see B1 below |
| B2 driver cannot run track `ref` | yes | open | **PARTIAL** | §2 and T-REFRUN cover (i)–(v). The T-REFRUN file list omits the driver refactor it needs (see below). |
| B3 revisions/GPU seeded from P4 | yes | open | **CLOSED (design)** | §2 "seeded from the P4 root manifest; None or mixed → refuse; job 1 must match", plus T-REFRUN tests. Code is ticketed. |
| B4 determinism / provenance | yes | open | **CLOSED (design)** | §1.6: bit-exact flags, `-threads 1`, toolchain recorded, manifest sha frozen, GPU box stages manifest objects only, sha gate. Image-derivation determinism is in N18. |
| B5 motion stimulus vs black frame | yes | open | **CLOSED (design)** | Grey background (luma 128). The pattern is present and static for the whole clip and drifts only during events. MOT-STAT twin. §1.5 checks luminance_crop/contrast_crop within 1% and motion_energy ≥ 10× static. |
| B6 executable, frozen kernel STOP rules | yes | open | **CLOSED (design)** | (a) K1 is now over test-half clip means: n_t = 10 (FFC), n_t = 5 (MOT/AUD), with t thresholds stated. (b) `controls.kernel.acceptance` goes in `frozen:` via T-D071. (c) STOP_INVALID fail-closed list. (d) Tests in T-KERNEL. (e) Byte-reproducible kernels_v1.json. The MT_plus demotion is not yet executable (B14). |
| B7 freeze by test, not prose | yes | open | **CLOSED (design)** | T-D071 (check_frozen_config sees every key). L1 freezes `p4.superseded_run_ids`. §9 freezes the remaining `controls.*` keys. New gap: `p4.launcher_max_hours` is not frozen (B13). |
| B8 p4_index guards | yes | open | **CLOSED (design)** | §7 `p4_open`: entry gate, `pred_sha256` verify, STOP latch, PRED_PREFIX derived from `qc.WORD_END_CLAMP`, store-root assert, `ref`/non-run-set rows ignored, N3 cases. AST allowlist in L1. See N20 for how the entry id is pinned. |
| B9 DoD tickets | yes | open | **CLOSED (design)** | (a) T-REPORT. (b) Allowlist qc_report with a dry-store build and a pinned sha. (c) L4 PASS tolerance max($0.50, 1%). (d) Reconciled again at P5 entry. T-LOCK fixture covers an orphan, a capacity miss and a double-terminate. |
| B10 loader vs audio-only track | partly | open | **PARTIAL** | T-AUDIO keys the loader by (track, condition). But the run side of the ablation is assigned to an L-only ticket, although the reference job needs it to produce a gating kernel, and the cache-key wording contradicts itself (B16). |

### B1 verification (CLOSED)

What the code does:
- **Price lookup** (scripts/gpu_wave1_p4.py:434–437). `avail = lg.types()`. If `itype not in avail`, the driver calls `_no_capacity`, which sets status `no_capacity` and exits 75. This happens before `preflight`, before `inputs` and before `launch`.
- **Launch** (:458–468).
  - `SystemExit` containing "has no capacity" exits 75.
  - `urllib.error.HTTPError` with code 400 exits 75 and logs the first 500 bytes of the body in `capacity_miss`.
  - Any other `SystemExit` re-raises, so the budget cap and "budget unverified" still stop the run.
  - Any other HTTP code also re-raises.
- **Real error path.** `lambda_gpu._req` uses `urlopen` and does not wrap the error. A real HTTP 400 therefore reaches the driver as `HTTPError`, the same as in the test. `lambda_gpu.launch` appends the ledger `launch` record only after the POST succeeds (infra/lambda_gpu.py:167–171). So a miss creates no instance, makes no ledger change and bills nothing.
- **Launcher limit.**
  - `run_session` refuses `--max-hours > p4.launcher_max_hours` (1.75) at :389–391.
  - The CLI default is 1.75.
  - The schema has `launcher_max_hours: gt 0, le 4`.

Tests:
- `test_no_capacity_at_price_lookup_exits_75_without_launch` asserts `launched == []`.
- `..._at_launch_exits_75`.
- `test_http_400_..._logs_body`.
- `test_other_launch_errors_still_fail` (budget cap).
- `test_max_hours_above_launcher_limit_is_refused` checks the boundary: 1.76 is refused and 1.75 runs.
- `test_cli_default_max_hours_within_launcher_limit` checks default ≤ config < 2 h.
- Without the fix, the price-lookup test would hit the old KeyError and the launcher test would not be refused, so these tests discriminate.

Residuals (non-blocking unless noted):
- The threshold is 1.75 h and the key is not in `frozen:`. D-071 says 1.4 h. This is **B13**.
- The tests do not assert `spent_usd()` or `manifest.jsonl` unchanged after a miss (N14).
- A non-capacity HTTP 400 retries forever (N12).
- Each miss writes `runs/<run_id>/child_metrics.json` to S3. `load_state` reads only `manifest.jsonl` and the key list, so this does not affect state. It is a record, not debris (N14).

### B2 residual (PARTIAL)

T-REFRUN lists only `scripts/gpu_p4b_ref.py`, but "a thin wrapper over the hardened driver functions" with constructor-passed roots and prefixes needs changes inside scripts/gpu_wave1_p4.py:
- `PRED_PREFIX`, `ENTRY_PREFIX` and `D038_PREFIX` are module constants (:86–88) used inside `do_job`.
- `plan_jobs` is built from `p4.run_set_*`.
- `PodBackend.inputs` reads P2 t1/t3 rows.
- The S3 root is `cfg["p4"]["s3_prefix"]`.

Required:
- Add the driver to T-REFRUN's file list.
- The refactor keeps all 43 existing driver tests unedited (check_test_weakening).
- Add a P4 dry-run equivalence test: the key set written by `--dry-run --limit 3` is the same before and after the refactor.

## New blocking items

**B11 [D-071 text] Q6 contradicts itself.**
- D-071 (g) carries the owner's pre-registered MT_plus demotion. D-071 (j) still says "Q6 = hard STOP".
- In design_v2, §3.2 lists MT_plus as gating with no condition, and §3.4 and §10 say "no pre-registered demotion path". Only the appendix overrides them.
- A frozen entry must not contain two rules for the same case.
- Fix: (j) Q6 = "pre-registered demotion for MT_plus only, see (g); FFC and AUD hard STOP".
- Fold the owner decisions into the design_v2 body (§2 cap, §1.2 candidates and selection rule, §3.2, §3.4, §10) so the tickets are not built from superseded text.

**B12 [D-071 text] Decision-id collision.**
- D-071 (j) and design §4(b) and §9 name the analysis-set audio-only ablation entry "D-072".
- D-072 is already committed: Curator round 4, DECISIONS.md, a7e4990.
- Fix: refer to "the ablation entry (next free id, assigned at commit)". The id itself is pinned in config when that entry is written.
- Note: D-071 will be appended after D-072. That is allowed by check_append_only, but D-071 should say so in one line, to prevent any later reader from treating the gap as missing history.

**B13 [GPU] The launcher limit has one value in prose and another in code, and it is not frozen.**
- D-071 (k) and design §2 say "`--max-hours ≤ 1.4` (enforced in code)", and T-DRV says "constant `LAUNCHER_LIMIT_H`; default 1.4".
- The code enforces `p4.launcher_max_hours = 1.75` from config, and that key is not in `frozen:`.
- Either value can be defended. 1.75 h ran in sessions s3–s14 under the 2 h harness with no time-limit kill (BUGS.md BUG-028/027). 1.4 h leaves margin for pre-launch work, which the guard does not count. 1.4 h also makes session 1 tight (N16) and adds about 4 sessions of setup overhead to the campaign.
- Fix:
  - D-071 names one number.
  - The reference wrapper enforces it from a frozen key. Either freeze `p4.launcher_max_hours`, or add `controls.refclips.max_hours` and freeze that.
  - T-REFRUN tests that limit + 0.01 is refused.
  - If 1.4 is chosen, the D-071 cost estimate stays as written. If 1.75 is chosen, restate the estimate.

**B14 [GPU] The MT_plus demotion must be executable before the run, not only written in prose.**
- Frozen config `controls.regressors.motion` has `gating: true` (config.yaml:345, frozen at c616a9d).
- D-071 (g) now makes that conditional on the MT_plus kernel passing K1–K6. Nothing in the D-071 key list carries the condition.
- Required:
  - A frozen key, e.g. `controls.kernel.acceptance.on_fail: {FFC: stop, AUD: stop, AUD_audioonly: stop, MT_plus: descriptive}`.
  - D-071 states that `regressors.motion.gating` is read together with this key. The frozen key itself is not edited.
- Tests (T-KERNEL and T-CTRL):
  - an MT_plus K-fail gives status `demoted`, the motion (a) pair is reported and non-gating, and the report flags the limitation;
  - an FFC, AUD or AUD audio-only fail gives a P4b STOP;
  - MT_plus STOP_INVALID is treated the same as FAIL (D-071 must say this; currently it does not);
  - the motion kernel is never taken from FLASH;
  - the demotion decision is written into kernels_v1.json before `p4_open` can unlock.

**B15 [GPU] The $75 campaign cap is enforced by nothing.**
- Code enforces only the per-session `--usd-limit` (price × max_hours) and the global `budget_cap()` (SSM, already partly used by the $51.86 P4 spend). Neither one knows about the campaign.
- Required:
  - At the pre-launch L4 step, record the ledger baseline `spent_usd()` in the reference root, keyed by campaign, written once.
  - The wrapper refuses a launch if (spent − baseline) + price × max_hours > `controls.refclips.campaign_cap_usd` (frozen, 75).
  - Test with a fixture ledger: a launch that would cross the cap is refused and exits 1, not 75.

**B16 [GPU] The ablation run path has no G ticket, and the cache-key wording contradicts itself.**
- The AUD audio-only kernel is gating and comes from the reference job. It needs code that does not exist yet: `features_to_use` appears nowhere in src/ or scripts/. That code is:
  - the `config_update={"data.features_to_use": [...]}` predict path;
  - the extractor-not-called gate;
  - the `audioonly/` and `textonly/` prefixes;
  - a Gate-1 cached rerun per condition.
- T-AUDIO, which builds this, is marked **L** only.
- Separately, `feature_cache.cache_key(video, sha, revisions=...)` does not include `features_to_use`. "The cache key is asserted unchanged across conditions" (§2) is therefore correct. The T-AUDIO line "cache key identical apart from features_to_use" (and my own cycle-1 B10 wording) is wrong.
- Fix:
  - Split T-AUDIO into a run part, T-ABL, marked **G**. Its tests:
    - same cache_key across conditions;
    - same revisions and GPU;
    - an extractor spy shows zero calls;
    - prediction shape equals the full model's;
    - Gate-1 bit identity on ≥ 3 clips per condition;
    - writes only under its own prefix.
  - Keep the loader part of T-AUDIO, marked L.

## New non-blocking items

- **N12** The HTTP 400 handling catches every 400. A misconfiguration 400 (bad ssh-key name, invalid region) then exits 75 forever. Add a stop after N consecutive `no_capacity` results whose body does not mention capacity (exit 1), or match the body. Also add a coupling test: drive the real `lambda_gpu.launch` with a patched `_req`/`types` race so that the literal "has no capacity" is pinned on both sides.
- **N13** Retrying on exit 75 together with a fixed `--external-terminator-at` breaks the D-063 Q7 window, because `planned` moves with every retry. This is the s13 exit-1 precedent in BUGS.md. The reference wrapper's retry loop must re-arm the terminator (or use the pod timer) on each attempt. Test this.
- **N14** In the BUG-033 tests, also assert that `lg.spent_usd()` is unchanged and the store `manifest.jsonl` bytes are unchanged after a miss. L2 must list the `runs/*/child_metrics.json` records of no-capacity attempts.
- **N15** The split halves are confounded with the onset shift: even clips have s = 0 and odd clips have s = −1. K1/K2 selection and testing, and K4b, therefore always compare shift groups. Disclose this in D-071 (f), or assign the shift by `clip_index // 2`.
  - Also specify how MOT families map to clip index (5 dots + 5 gratings; with an i % 2 split the halves are 3/2 vs 2/3).
  - Also specify how the LOC Latin-square order is balanced across the halves (20 clips is not a multiple of 6).
  - Test the assignment.
- **N16** Session 1 at 1.4 h: 3 D-038 jobs at an estimated 2×360 + 120 s, plus 1800 s setup and 600 s teardown, come to 4920 s of the 5040 s available. That leaves 2 minutes, so the third D-038 clip is skipped whenever setup runs long. Resolve this together with B13.
- **N17** D-071 (b) curates an "object" category that no clip family uses. Drop it or state its use. Also, design §1.2 says "sorted file name" while D-071 and the owner decision say "sha256 of the file title". Keep one rule, and make it the one the T-LIC test checks.
- **N18** T-REF58's bit-identical rebuild covers only wav/tsv. Phase scrambles, SHINE matching, and the dot/grating generators must also be seeded, with their frame arrays (or per-frame sha) bit-identical in CI, because they sit upstream of the mp4.
- **N19** NAT goes through P2b (WhisperX). Where it runs (device, pinned config) and its cost are not stated. The NAT transcript sha must exist before the manifest is frozen.
- **N20** `p4_open` must refuse until the post-run entry exists. The entry id should be a config key written in that commit, not a literal, so the guard can be tested now with a fixture DECISIONS file.
- **N21** Make sure GREY-CTRL as a D-038 clip cannot pass or fail vacuously. `feature_reliability` drops `None` arrays (constant-and-unequal arrays) from `rmin`, and an all-None result gives `rmin None`, which fails the gate and latches a STOP. Add unit tests on an event-free synthetic clip's feature shapes (constant text arrays, low-variance video arrays). Alternatively, pick TALKFACE as the third D-038 clip.
- **N22** D-071 (f): "Before launch the frozen code is run on the ENH-002 summary courses and the result is disclosed". Design §3.1 says "in the cycle-2 packet". It is not in this packet, because the K-code does not exist yet. Make it an explicit pre-launch gate (listed below).
- Cycle-1 N1–N11: N1 (cost), N2 (sibling root), N4 (`--limit 3`), N5 (ablations in the same campaign), N6, N7, N9 (CI check in the wrapper), N10 (T-OOD-REL) and N11 (§1.4 P2 path) are all addressed in the design. N3 is in T-INDEX. N8 is covered by T-KERNEL's −3 TR pre-rise test. K3's baseline is now lags −4…−2 and uses across-clip variance, not the mean, so the pre-rise affects K3 only through its variance. The ENH-002 known-data run (N22) will show the effect.

## Launch-blocking list (reference-clip GPU job)

Tickets: each one closed means code plus tests, pushed, with CI green.
1. **T-D071**: D-071 text fixed per B11, B12 and B13. Config `controls.refclips` (including campaign_cap_usd and max_hours), `controls.kernel.acceptance` (including the B14 on_fail key), `controls.pass` and `seeds.controls_perm` are all in `frozen:`, and check_frozen_config passes.
2. **T-DRV**: BUG-033 and BUG-028 are done (ca63a9d). What remains is the B13 limit value and its freeze, plus N12/N13 if they are taken up in the wrapper.
3. **T-LIC**: Wikimedia per-file licences, loc_manifest, ≥ 20 per category.
4. **T-NAT**: 15 rows, plus the NAT P2b stage (N19).
5. **T-STIM / T-REF58**: including N18 and the §1.5 regressor QC.
6. **T-ENV**: the speech_envelope needed for reference-clip QC.
7. **T-REFRUN**: including the B2 driver refactor and equivalence test, B3, the B15 campaign cap, the CI-green check and `--limit 3`.
8. **T-ABL** (new, split from T-AUDIO, B16).
9. **T-KERNEL**: including B14, the fail-closed cases, the null and planted operating characteristics, and N15.

Pre-launch gates (not tickets):

10. The council gives GO on the ticket diff (design §0 step 2).
11. The clips are built once on the pod. `refclips_manifest.json` sha256 is added to `frozen:` and uploaded to `wave1/derived/p4b_ref/v1/`.
12. The L4 agent-side ledger reconciliation passes. The baseline spend and `budget_cap()` are recorded (this is the T-LOCK L4 part).
13. The ENH-002 known-data K run is disclosed (N22).

Not launch-blocking (lock only): T-AUDIO (loader part), T-CTRL, T-NEG, T-OOD-REL, T-INDEX, T-LOCK (except L4), T-REPORT.
