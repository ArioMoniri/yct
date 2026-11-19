# D-071 v2: QA sign-off pass

Reviewer: QA. This is a sign-off pass on `reviews/phase_p4b/d071_v2.md` (HEAD 8a755c8), not a full cycle.

Inputs:
- the five cycle-2 reviews (`cycle2_{watchdog,referee,biostat,neuro,qa}.md`);
- `config.yaml` (`controls:`, `seeds:`, `p4:`, `frozen:`);
- `src/yct/config_schema.py`;
- `scripts/check_frozen_config.py`;
- `tests/test_guards_frozen_config.py`, `tests/test_config_schema.py`, `tests/test_controls_config.py`, `tests/test_p4_config.py`;
- `scripts/gpu_wave1_p4.py` (`_no_capacity`, `_finish`), `infra/lambda_gpu.py` (ledger records);
- design_v2 §8 ticket table.

Scope: read-only. I used git, grep and pytest only. I used no AWS, decrypted nothing, read nothing in data/sealed/ or data/wave2_pool/, read no labels or prediction arrays, and made no commit.

`pytest tests/test_guards_frozen_config.py tests/test_config_schema.py tests/test_controls_config.py tests/test_p4_config.py tests/test_gpu_wave1_p4.py`: 140 passed at 8a755c8.

The owner decisions are binding, and v2 records them correctly:
- the $75 cap (`campaign_cap_usd: 75`);
- Wikimedia CC0/PD/CC-BY photographs (b);
- MT+ demotion only on a genuine (valid) K-rule FAIL (g).

## Verdict: **REVISE**

The science text is now consistent, and every scientific blocking item is resolved. What remains is a set of mechanical defects in how the freeze would be committed and tested:
- **the YAML cannot pass `check_frozen_config` as specified** (C1, C2);
- the schema, the frozen-list test and duplicated keys are not in any ticket (C3–C5);
- three of the four enforced rules have no named tests (T1, T2, T4);
- a few cycle-2 residuals are still open (R1–R6).

All of these are text, config and ticket edits. No council cycle is needed. QA re-checks the corrected entry and the commit pair by grep and pytest.

## 1. Blocking items for "commit D-071": status

| reviewer item | status | evidence (d071_v2.md unless noted) |
|---|---|---|
| WD B8 / Ref B13 / Bio B9 / Neuro B7a / QA B11: Q6 contradiction | **RESOLVED** | (j) Q6 = "pre-registered demotion for MT_plus only, per (g); FFC and both AUD kernels are hard STOP". The void clause covers design_v2 §3.2, §3.4 and §10. Bio B9's "(a)/(c)" wording is fixed: (g) demotes the (a) pair only, and (c) has no motion arm. |
| QA B11 (second half): fold the owner decisions into the design_v2 body | **RESOLVED (void clause accepted) with R5** | The intro states that D-071 is the only frozen text and that conflicting design_v2 text is void. I accept that in place of a rewrite. But the design_v2 §8 ticket cells are still the TDD source, and they carry superseded values (R5). |
| WD B9 / Ref B15 / Neuro B7b / QA B12: D-072 collision | **RESOLVED, with R1** | (j) reserves D-073. The intro adds the "appended after D-072" note. design_v2 §4(b) l.259 and §9 l.362 still say D-072, and the enumerated void list does not name them (R1). |
| WD B10 / Bio B11 / Neuro B9c / QA N17: object category | **RESOLVED** | (b) "objects: not curated in v1"; config `loc_categories: [face, body, place]`. |
| WD B11 / Ref B16 / QA B13: launcher limit | **RESOLVED (text); C1 applies** | (k) uses `--max-hours ≤ p4.launcher_max_hours` (1.75, frozen, tested at limit + 0.01). The estimate is restated for 1.75 h: 14 sessions, ≈ $61. 120 × 0.45 + 4 + 3 = 61 ✓. Code: gpu_wave1_p4.py:389 reads the key. |
| Ref B16 (second half) / QA N14: T-DRV debris and ledger-delta tests | **PARTIAL (R4)** | T-DRV adds "no run dir left behind". But `_no_capacity` → `_finish` (gpu_wave1_p4.py:557–559) always writes `runs/<id>/child_metrics.json`, so that test cannot pass without deleting the audit record (WD N18). The design_v2 §8 T-DRV row still says 1.4 and `LAUNCHER_LIMIT_H` (R5). |
| Ref B17 / WD B12 / QA B15 / Bio N18: cap scope and enforcement | **PARTIAL (T1)** | Resolved in (k): the scope (what counts and what does not, v2 has its own cap), the ledger prefix `yct-p4b-ref`, the write-once baseline, exit 1, the $60 `--ack-cap-80` and the config keys. The ledger stores `name` on each launch record (lambda_gpu.py:166), so a prefix filter is feasible. Open: "campaign spend" has two definitions, a baseline delta and a prefix sum (T1), and the tests are not named (T1). |
| Ref B14 (i)–(v) / Neuro B8a–e / QA B14 / WD B13: demotion mechanics | **RESOLVED (spec); tests PARTIAL (T2)** | Resolved: the trigger (valid K-rule FAIL with QC passed); STOP_INVALID and a cap-truncated motion run give STOP; the kernel-only rule (MT_plus PASS + (a)-motion FAIL = STOP); the scope; finality (v2 carries MOT over by sha); `on_fail`, `on_stop_invalid` and `demotion_final` in config; `regressors.motion` not edited; the frozen limitation sentence. QA B14 asked for "STOP_INVALID same as FAIL"; v2 makes it a STOP instead (Ref, WD and Neuro). I accept that as stricter. |
| Ref B14 (vi): v2.md bump to v2.8 | **PARTIAL (R3)** | The intro lists the v2.8 amendments. The "committed together with" sentence names only config keys, not the docs/prompts/v2.md edit itself. Precedent: c616a9d carried the v2.7 P4E text together with the config. |
| Ref B18a / Bio B11 / Neuro B9a–b, f: candidate universe, snapshot, ordered log | **RESOLVED (spec); tests NOT named (T4)** | (b) and (c) freeze the queries, `srnamespace=6`, filetype, the 2,000/1,000 limits, a single recorded UTC date, a candidate sha committed before filtering, sha256(title) order, and a reason-coded log of every inspected candidate. |
| Ref B18b / Neuro B9e / Ref N20: licence set, attribution, personality rights | **RESOLVED** | (b) licence list, exclusions, LICENSES.md fields. Small text gap: config `image_licences` lists `PD` while the prose says `PD-*` (C6). |
| Ref B18c / Neuro B9c: operational content filters | **PARTIAL (R2)** | The face, body and place filters are operational, with the cascade checked on the processed image. Ref B18c also asked for §1.5 QC "face ≈ 0 on body, place **and scrambled** frames". (a) checks only "no LOC body or place TR". |
| Ref B18e / Neuro B9d: frozen processing | **PARTIAL (R2)** | The crop, the ≈316 px resize, joint SHINE across all 60 images and mean luma 128 are frozen. Not frozen: the greyscale formula, the SHINE options (which steps, iterations), and the scramble and MOT-pattern seeds. "Frozen scramble seeds" has no value, key or derivation, and the builder-code sha is not in `refclips_manifest.json`, so the "hashed builder code" alternative is not met either. |
| Ref B18f / Neuro B7e / WD N13: design §1.2 "sorted file name" | **RESOLVED** | The void clause names §1.2. |
| Bio B6: power package B′ | **RESOLVED** | K1 α = .01; FFC ≥ 80% sign check; SPK 20 (60 utterances); MOT 16 + 16 MOT-STAT, 48 distinct (pattern, direction) pairs. |
| Bio B7: single peak, peak ≤ 0, K2 crossing, K6 | **RESOLVED** | One definition, peak := m_full(p*); peak ≤ 0 → FAIL; the crossing is defined on the integer grid. K6 uses Neuro B8d's like-for-like form, mean 0–3 (MOT − MOT-STAT) > mean 0–3 (FLASH − GREY-CTRL), not Bio's m_MOT(p*). That is the stricter of the two and removes Bio's unit mismatch. Biostat should confirm in its own sign-off, because Bio B6–B11 said "any other resolution returns to the council". |
| Bio B8: K3′ | **RESOLVED** | Magnitude AND two-sided p < .01. Spans [o_e + 12, o_{e+1} − 5] give TRs 21–24 and 41–44, 8 per clip ✓. |
| Bio B10 / QA N15 / Neuro N15: half aliasing | **RESOLVED** | s = 0 iff (i // 2) mod 2 = 0. Checked: 5/5 per half for 20 clips, 4/4 for 16. Latin-square row (i // 2) mod 3 splits 4/3/3 in both halves. The T-REF58 test is named. New non-blocking finding N1 below. |
| Neuro B5 residual: K2 plateau | **RESOLVED** | K2 clause: max over [−1, +4] ≥ 0.9 × global max. |
| Neuro B7c: 8 vs 10 directions | **RESOLVED** | 8 directions, (3i + k) mod 8. |
| Neuro B7d: per-hemisphere counts **and `mw_removed_frac`** | **PARTIAL (R6)** | The counts are in (i) and in `controls.rois_per_hemi`. Each sums to the frozen or existing `controls.rois.*.n_vertices` (104/113/223/139/1148 ✓). `mw_removed_frac` is missing from both. |
| Bio N17 / Ref N17: bootstrap seed | **RESOLVED** | `seeds.controls_boot: 20261120`, frozen. |
| QA B16: ablation run path | **RESOLVED** | T-ABL (G) has the six tests from my cycle-2 list. |
| Ref verdict 1 / WD checklist 1 / QA launch item 1: atomic commit with keys in `frozen:` and check_frozen_config green | **NOT RESOLVED (C1–C5)** | See §2. As specified, the commit fails `check_frozen_config`, the schema, and `test_repo_config_has_v22_defaults_and_only_the_d063_freeze`. |
| Bio N20 / WD N21: stale config corrected in the T-D071 commit (Bio: launch condition) | **NOT RESOLVED (C5)** | `controls.kernel.min_reference_clips: 5`, `controls.dry_run.reference_clips_min: 5`, and the `pass.min_videos` comment ("≥ 5 reference naturalistic clips") and `low_sd_percentile` comment ("reference clips") are untouched. Whether `pass:` replaces or extends the existing `pass` is unstated. |

## 2. Config keys vs config_schema.py and the `frozen:` mechanism

How `frozen:` is enforced:
- `scripts/check_frozen_config.py` runs in `make guards` (Makefile:10, CI ci.yml:51) and in `tests/test_guards_frozen_config.py::test_repo_config_passes_guard`.
- It requires that every `frozen_at` (a) is an ancestor of HEAD, (b) whose config.yaml **already contains the key**, and (c) that the value at HEAD equals the value at `frozen_at`. Freezing a mapping freezes its whole subtree.
- Rows can never be removed or re-pointed.
- `Frozen.frozen_at` must be a 40-hex `Sha1` (schema l.620–622).

| # | defect | evidence | required |
|---|---|---|---|
| **C1** | "added to `frozen:` in the same commit … `frozen_at` = the D-071 commit sha" cannot work. | A commit cannot contain its own sha. The precedent is two commits: c616a9d added the values, then 11bc34d added the rows (`frozen_at c616a9d`). | Commit pair, pushed together and CI-green, before any clip is built: **(1)** D-071 + v2.md v2.8 + the config values + schema; **(2)** the `frozen:` rows with `frozen_at = <sha of (1)>`. `p4.launcher_max_hours` may instead use `frozen_at: ca63a9d57857b68cf5c0f9dc7a51ce6d53882db2`: the key already holds 1.75 there (config l.412). Reword the intro bullet and the YAML comment to say this. |
| **C2** | `controls.refclips.manifest_sha256: null` sits inside the frozen subtree `controls.refclips`. | Setting the sha later, as (d) and T-STIM require, changes a frozen value, so check (c) fails. | Move it out of the subtree, e.g. `controls.refclips_manifest_sha256` (`Sha256 | None`). Freeze it with its own row once it is set. Do the same for the image and NAT snapshot/manifest shas if they get config keys. |
| **C3** | The schema rejects every new key. | `M` is `extra="forbid", strict=True` (schema l.23–24). `Seeds` has only `company_pick_salt`. `Controls` has no `refclips` and no `rois_per_hemi`. `Kernel` has no `acceptance`. `Pass` requires `within_video`, `selectivity`, `between_video`, `min_videos` and `low_sd_percentile`, and forbids `a` through `d`. | T-D071 must list `src/yct/config_schema.py` and `tests/test_config_schema.py`. Add typed models for `Seeds.controls_perm` and `Seeds.controls_boot` (PosInt), `RefClips`, `Acceptance` (with `on_fail` and `on_stop_invalid` as `Literal["stop", "descriptive"]` and `demotion_final: bool`), `rois_per_hemi` and the new `Pass`. Also: `job_order` needs `list[str | list[str]]`; make `image_queries.*` uniformly `list[str]` (face and body are str, place is a list); `manifest_sha256` is `Sha256 | None`. |
| **C4** | An existing test pins the frozen list exactly. | `tests/test_guards_frozen_config.py:106` asserts `cfg["frozen"] == [D063_FROZEN rows]`, so adding rows fails it. | Name this test in T-D071. Update `D063_FROZEN`, or add a `D071_FROZEN` list with its sha. Replace the equality with one at least as strict (one line for one line, so `check_test_weakening` passes). |
| **C5** | Duplicated and stale values in one config. Two sources of truth for one rule are a silent-drift path. | `acceptance.lags` vs `kernel.window_tr` ([−4, 8]). `pass.d.readout_lags` vs `controls.readout_lag_tr` ([0, 3]). `pass.c.era_merge_min` vs top-level `era_merge_min_videos` (6). New `pass.a` vs existing `pass.within_video`, `min_videos` and `low_sd_percentile`. `rois_per_hemi` vs `rois.*.n_vertices`. Stale: `kernel.min_reference_clips: 5`, `dry_run.reference_clips_min: 5`, and the `pass` comments. | D-071 states that `controls.pass` is **replaced** by `{a, b, c, d}`; no code reads the old fields (grep). Then either drop each duplicate and reference the existing key, or add an equality test for each pair in `tests/test_controls_config.py`. Add a test that L + R = `n_vertices` per ROI. Update the stale values and comments in commit (1). The `test_controls_config.py:28` assertion `min_reference_clips >= 5` stays valid. |
| **C6** | Small value mismatches between the prose and the YAML. | `image_licences: [.., PD, ..]` vs the prose "PD-*". The (b) reason-code list is "fixed" but not in config. design_v2 §8 T-NAT says licence ∈ {CC0, CC-BY}, while (c) says the same set as (b). | Use `PD-*` (or `PD_any`) and state that matching is by template prefix. Add `controls.refclips.reject_reasons: [licence, personality_rights, …, duplicate]` so the T-LIC test can check the codes against config. |

## 3. Does the ticket list name a test for every enforced rule?

| rule | status | named now | missing (add to the ticket text) |
|---|---|---|---|
| **T1 cap guard** | **NOT** | T-REFRUN: "add the campaign-cap guard and its tests" | First, fix the formula: campaign spend = the sum of cost over ledger launch records whose `name` starts with `controls.refclips.ledger_name_prefix`. The baseline (line count + sha) proves that the ledger is append-only and that no ref instance predates session 1. As written, (k) also allows "spent_usd() − baseline", which would charge D-073 spend in the same period to the cap, contrary to "does not count". Then name the T-REFRUN tests, all against a fixture ledger: (a) the baseline is written once, and a second write is refused; (b) spend + price × max_hours = 75.00 launches, and 75.01 is refused with **exit 1, not 75**, and no launch; (c) at ≥ $60 without `--ack-cap-80` the launch is refused, and with it the launch proceeds; (d) non-prefixed ledger lines are excluded, and prefixed orphan lines (no terminate) are included up to now or the deadline; (e) the cap is read only from the frozen key, with no CLI override; (f) a ledger whose first N lines differ from the baseline sha is refused. |
| **T2 demotion key** | **PARTIAL** | T-KERNEL: an `on_fail`/`on_stop_invalid` matrix; the demotion is decided only from kernels_v1.json before `p4_open` | T-KERNEL: (a) MOT/MOT-STAT/FLASH incomplete, or truncated by the cap, gives STOP_INVALID, never `demoted`; (b) failed §1.5 QC gives no demotion; (c) FLASH STOP_INVALID makes MT_plus STOP_INVALID; (d) the motion kernel is never taken from FLASH (QA B14); (e) with `demotion_final` set, a v2 kernels file cannot set MT_plus back to gating, and v2 MOT/MOT-STAT manifest shas equal v1's. T-CTRL (L): (f) when demoted, the (a) motion pair is computed with the failed kernel, labelled with the rule, non-gating, and `motion` stays in `partial_out`; (g) MT_plus PASS + (a)-motion FAIL gives STOP; (h) `regressors.motion.gating` is read together with `on_fail`. T-REPORT (L): (i) the frozen limitation sentence appears verbatim, with Kx filled in. |
| **T3 launcher limit** | **RESOLVED** | T-REFRUN "launcher-limit test" plus (k) "tested at limit + 0.01"; the freeze is checked by `check_frozen_config` | Only the stale design_v2 §8 T-DRV cell needs editing (R5). |
| **T4 curation snapshots** | **NOT** | T-LIC/T-NAT: the process order only; the NAT disjointness test is hash-only (named) | Name the tests: (a) the snapshot file's sha appears in a commit that is a **strict ancestor** of the commit adding the reject log or manifest (git-order test); (b) the snapshot header (query, `srnamespace`, filetype, limit, UTC date) equals the config values; (c) the log order is ascending sha256(title), and every snapshot entry before the 20th (or 15th) pass is logged, with no gaps; (d) every reason code is in `reject_reasons` (C6); (e) every pass has a licence template in `image_licences` and no personality-rights template; (f) exactly 20 per category (15 NAT), or the build refuses; (g) LICENSES.md has every required field for each manifest file. |

## 4. Remaining residuals (R) and non-blocking findings (N)

- **R1.** Add "§4(b), §9 (D-072 → D-073)" to the enumerated void list in the intro.
- **R2.** (a) QC: the face cascade must also be negative on every LOC-SCR TR and every between-event scramble TR (Ref B18c). (b) Processing: name the greyscale formula (e.g. BT.709 luma, the P2 matrix), the SHINE steps and iteration count, and the seed rule for scrambles and MOT patterns (e.g. `seeds.refclips: <int>` with seed = hash(family, i, k)). Add `seeds.refclips` to `frozen:`, and add the builder-code sha to `refclips_manifest.json` (Ref B18e, Neuro B9d, QA N18).
- **R3.** The intro's commit bullet must list the docs/prompts/v2.md §5 P4b v2.8 edit as part of commit (1).
- **R4.** T-DRV: replace "no run dir left behind" with "only the `runs/<id>/child_metrics.json` record (status `no_capacity`); no instance; no ledger line; `spent_usd()` unchanged; store `manifest.jsonl` bytes unchanged" (WD N18, QA N14).
- **R5.** Add to the "Tickets added or changed" list the design_v2 §8 cells that are superseded:
  - T-DRV: drop "1.4 / `LAUNCHER_LIMIT_H` / default 1.4";
  - T-STIM: "98 clips" becomes 120;
  - T-REFRUN: "all 98" becomes 120;
  - T-NAT: the licence set is as in (b);
  - T-LIC: replace "licence sha256 matches stored text" with the (b) record;
  - T-D071: add `seeds.controls_boot`, `controls.rois_per_hemi`, `p4.launcher_max_hours`, the schema/test files from C3/C4, and the C1 commit pair.
- **R6.** Add per-ROI `mw_removed_frac` to (i) and to config, next to `rois_per_hemi` (Neuro B7d). It is an atlas fact and label-free.
- **N1 (new).** MOT pattern type and onset shift use the same index, (i // 2) mod 2. Every dot field has s = 0 and every grating has s = −1, so pattern type is fully confounded with shift. Both are balanced per half, so this does not block. A pattern rule of (i // 4) mod 2 keeps 8/8, per-half 4/4 and per-shift 4/4 balance. Change it now, or disclose it.
- **N2.** Nothing prevents the next DECISIONS append from taking D-073. Consider a check in T-D071: any `- D-073` line must be the audio-only ablation entry.
- **N3.** These are still open from my cycle 2 and belong in T-REFRUN, not in this commit: N19/WD N19 (`pending[:3]` = GREY-CTRL s0, SPK_00, MOT_00), N21 (GREY-CTRL as a D-038 clip can latch a vacuous STOP when `rmin` is None), N12/N13 (named in T-DRV/T-REFRUN ✓).

## 5. Exact edits for SIGN-OFF

1. Intro bullet and YAML comment: the C1 commit pair; `p4.launcher_max_hours` uses `frozen_at` ca63a9d57857b68cf5c0f9dc7a51ce6d53882db2; commit (1) also carries the v2.md v2.8 text (R3).
2. YAML: move `manifest_sha256` out of `controls.refclips` (C2). Use `PD-*`. Add `reject_reasons`. Make `image_queries` uniformly lists (C3, C6). Add `seeds.refclips` and `mw_removed_frac` (R2, R6). State "`controls.pass` replaced", and drop or equality-test each duplicate in C5. Fix the stale `min_reference_clips`, `reference_clips_min` and `pass` comments (C5).
3. The text edits R1, R2(a/b) and R4.
4. Tickets: T-D071 per C3, C4 and R5; T1 (with the single spend formula), T2 and T4 tests as listed in §3; the other R5 cells.

After these edits, QA signs off on the diff: grep for each item, plus `make guards` and pytest green on the commit pair. No council cycle is needed.
