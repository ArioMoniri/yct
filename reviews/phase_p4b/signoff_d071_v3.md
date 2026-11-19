# D-071 v3: Referee + QA delta sign-off

Scope: a delta check, not a council cycle. I compared the remaining-edit lists in `signoff_d071_referee.md` (E1–E11, X1–X6) and `signoff_d071_qa.md` (C1–C6, T1–T4, R1–R6, N1–N3) with:
- commit 976e8ab (T-D071 1/2) and commit 7a312b4 (T-D071 2/2), read with `git show`;
- `reviews/phase_p4b/d071_v3.md`;
- the D-071 entry in DECISIONS.md.

HEAD is 7a312b4. The worktree is clean, and the branch matches its origin tracking ref.

Method: read-only. I used git, grep and pytest only. I used no AWS, decrypted nothing, read nothing in data/sealed/ or data/wave2_pool/, read no labels or prediction arrays, and made no commit.

## 0. Integrity checks

- **The entry is verbatim.** I diffed the DECISIONS.md lines that 976e8ab adds against d071_v3.md l.5–233. They are identical apart from the dated section header. The DECISIONS diff deletes no lines (0 `-` lines), so the file stays append-only.
- **D-071 follows D-072** (DECISIONS l.152 → l.155), as the entry's numbering note says.
- **The frozen rows match the entry.** 7a312b4 adds exactly the 10 rows listed in d071_v3 §"frozen: rows", in the same order:
  - `p4.launcher_max_hours` @ ca63a9d;
  - `seeds.{controls_perm, controls_boot, refclips}`, `controls.kernel.{acceptance, min_reference_clips}`, `controls.pass`, `controls.rois_per_hemi`, `controls.mw_removed_frac` and `controls.refclips`, each @ 976e8ab.
- **The `frozen_at` shas are valid.** `7a312b4^` = 976e8ab. ca63a9d is an ancestor of 976e8ab and already holds `launcher_max_hours: 1.75` (its config l.412).
- **`controls.refclips_artifacts` is unfrozen and outside every frozen subtree.** That is what the entry says.
- **No test was weakened.** Across c91d6bf..7a312b4, the only lines removed from tests/ are:
  - (a) a docstring line;
  - (b) the `cfg["frozen"] == [D063 rows]` equality, replaced by an equality on D063 rows + D071 rows (one line for one line, strictly stronger);
  - (c) a `raise HTTPError(...)` line in test_gpu_wave1_p4.py, split into two lines with the same behaviour.

  No test file was deleted. No `guards:` or `owner:` change was made. No code reads the old `pass` fields: grep finds only the schema comment.

## 1. Tests

| run | result |
|---|---|
| `pytest -q tests/test_d071_config.py tests/test_ref_campaign_cap.py tests/test_guards_frozen_config.py tests/test_guards_frozen_section.py` | 36 passed |
| full suite, `<scratchpad venv>/bin/python -m pytest -q` | **763 passed**, 8 warnings (numpy divide warnings in test_enh002_latency), 232 s |

`test_repo_config_passes_guard` (it runs `scripts/check_frozen_config.py --base HEAD`) passes, so all 10 new rows satisfy the ancestor, key-present and value-equal checks.

## 2. Referee items (signoff_d071_referee.md)

| item | status | evidence |
|---|---|---|
| E1 / X1: two-commit freeze | RESOLVED | v3 l.9–11 state the commit pair and the ca63a9d exception. 976e8ab holds the keys, schema, tests and v2.8. 7a312b4 holds the rows and the exact-list test. |
| E2 / X2: `manifest_sha256` outside the frozen subtree | RESOLVED | config `controls.refclips_artifacts.*` (5 keys, `Sha256 \| None`). v3 l.13 and l.90. Test `test_curation_snapshot_keys` asserts `"manifest_sha256" not in R`. `test_artifact_sha_must_be_hex`. |
| E3 / X3: `pass` replaced; schema; stale values | RESOLVED | v3 l.12. Schema `Pass{a,b,c,d}`, `Acceptance`, `RefClips`, `RefClipArtifacts`, plus the new `Seeds` and `Controls` fields (`extra=forbid` kept). `min_reference_clips` and `dry_run.reference_clips_min` both 5 → 16. `dry_run.n_flashes` and `n_speech_bursts` = 5, equal to `families.FLASH` and `families.BURST`. Old comments rewritten. |
| E4 / X4: MOT aliasing | RESOLVED | v3 l.33. Config `mot_direction_rule: "((3 * (i // 2) + k) % 8)"` and `mot_pattern_rule: "dot if (i // 4) % 2 == 0 else grating"`. `test_mot_direction_and_pattern_balanced_per_half` checks 8 directions × 3 per half, pattern × shift 2/2/2/2 per half, and 48 distinct pairs. T-REF58 l.292. |
| E5 / X5: campaign spend defined | RESOLVED | v3 l.207–209 give one prefix-sum formula. The baseline is "never subtracted". `ref_campaign.campaign_spend` matches `lambda_gpu.spent_usd()` semantics (terminate, else now), restricted by prefix. |
| E6: `mw_removed_frac` | RESOLVED | v3 l.165. Config `controls.mw_removed_frac` (all five 0.0, frozen). Schema check that its keys match `rois_per_hemi`. |
| E7: void list | RESOLVED | v3 l.8 adds §4(b), §9, §4(d) and the §8 cells. The design_v2.md erratum is appended (l.384–385). The old l.259/l.362 text is left in place and voided, as accepted. |
| E8: `PD-*` | RESOLVED | config `image_licences: [CC0, PD-*, …]`. v3 l.42 says matching is by prefix. |
| E9: face QC on scrambles | RESOLVED | v3 l.39: "no LOC body, place or scramble-period TR and no LOC-SCR TR (`face_area_crop_frac` = 0 there)". |
| E10: processing frozen | RESOLVED | v3 l.62–65. Config `greyscale: bt709_luma`, `shine: {steps: [specMatch, lumMatch], iterations: 2, mean_luma: 128, rms_contrast: 32}`, and `seeds.refclips` with the sha256 seed rule (frozen). Builder blob shas go in `refclips_manifest.json`. |
| E11 / X6: T-DRV miss record | RESOLVED | v3 l.231 and l.267. The `runs/<id>/child_metrics.json` (`no_capacity`) record is allowed. Also asserted: no instance and no ledger line, and the bytes of `spent_usd()` and `manifest.jsonl` are unchanged. |
| Non-blocking (g): Bio N17, PH | RESOLVED | v3 l.150. |
| Non-blocking: Bio N18, stimuli-only redesign | RESOLVED | v3 l.153. |

## 3. QA items (signoff_d071_qa.md)

| item | status | evidence |
|---|---|---|
| C1 + R3: commit pair, v2.8 in commit (1) | RESOLVED | as E1. docs/prompts/v2.md v2.8 header and §5 P4b override bullet are in 976e8ab. |
| C2 | RESOLVED | as E2. |
| C3: schema models | RESOLVED | All named models are present. `on_fail` is `dict[Literal[4 ROIs], Literal["stop", "descriptive"]]`. `on_stop_invalid` is `Literal["stop"]`, stricter than asked. `image_queries` is uniformly `list[str]`. `job_order` is `list[list[str]]`, and config uses a list for every step. |
| C4: exact frozen-list test | RESOLVED | `D071_FROZEN` with its sha, in a strict equality (test_guards_frozen_config.py). |
| C5: duplicates and stale values | RESOLVED | Each rule now has one source: `acceptance` has no `lags` key, `pass.d` no `readout_lags`, `pass.c` no `era_merge_min` (all asserted in `test_acceptance_thresholds` and `test_pass_block_replaced_and_single_sources`). L + R = `n_vertices` is checked by a schema validator and by a test. Stale values and comments are fixed. |
| C6: `PD-*`, `reject_reasons` | RESOLVED | config `reject_reasons` (16 codes, equal to the v3 l.52 list). The T-NAT licence set is "same as (b)" (v3 l.72). |
| T1: cap guard | RESOLVED | The code is in `src/yct/tribe_run/ref_campaign.py`. Coverage in tests/test_ref_campaign_cap.py: prefix-only spend with orphans counted to now; baseline written once; 75.00 allowed and 75.01 refused; `--ack` required at $60 or more; no override parameter; tampered pre-baseline ledger refused; prefixed instance before the baseline refused. Wiring into the launcher is T-REFRUN (open, allowed). |
| T2: demotion tests | RESOLVED (config side); runtime open in T-KERNEL / T-CTRL / T-REPORT (allowed) | `test_demotion_key_mt_plus_only` and `test_demotion_key_rejects_other_values`. The (a)–(i) runtime list is named per ticket in v3 l.286–289. |
| T3: launcher limit | RESOLVED | Frozen at ca63a9d. The ca63a9d tests are in the green suite. |
| T4: curation snapshot tests | RESOLVED (config side); runtime open in T-LIC / T-NAT (allowed) | `test_curation_snapshot_keys`. The (a)–(g) list is in v3 l.291. |
| R1 | RESOLVED | as E7. |
| R2a / R2b | RESOLVED | as E9 / E10. |
| R4 | RESOLVED | as E11. |
| R5: superseded §8 cells | RESOLVED | v3 l.293, plus the design_v2 erratum. |
| R6 | RESOLVED | as E6. |
| N1: pattern/shift confound | RESOLVED | as E4. |
| N2: D-073 reservation | RESOLVED | `test_d073_reserved_for_the_audio_only_ablation`. |
| N3: `pending[:3]`, GREY-CTRL vacuous STOP | Open in T-REFRUN (allowed) | v3 l.216 names the session-1 clips. N21 is left to T-REFRUN, as QA asked. |

## 4. Non-blocking notes (carry into T-REFRUN; no edit to the frozen text)

1. In `test_launch_at_exactly_the_cap_is_allowed_and_above_is_refused_exit_1`, the assertion is `code != 75`. A `SystemExit` with a str code does exit with status 1, so the behaviour is correct. When T-REFRUN wires the guard into the wrapper, add a subprocess test asserting the process exit status == 1.
2. `guard_launch` takes `cfg` as an argument, so "read only from the frozen key" holds only if the wrapper passes `load_config()`. T-REFRUN should test that the wrapper never builds its own `cfg` or applies overrides.
3. The v2.md §5 P4b body still says "≥ 5 reference naturalistic clips" in (a). The v2.8 override bullet governs ("the (a) fallback is the 15 NAT clips"), which is the same accepted pattern as the design_v2 void clause.

## 5. Verdicts

- **Referee: SIGN-OFF.** E1–E11 and X1–X6 are all resolved. The frozen rows equal the entry. No test was weakened. The full suite is green (763 passed).
- **QA: SIGN-OFF.** C1–C6, T1–T4 (config side) and R1–R6 are resolved, and so are N1 and N2. The runtime test lists in T-KERNEL, T-CTRL, T-REPORT, T-LIC, T-NAT and T-REFRUN are open tickets that the entry names explicitly, which the brief accepts.
