# Phase 1 cycle 2: Biostatistician (fresh reviewer)

Evidence:
- `data/manifest.csv`, analysis set in_primary & qc_pass = 53 rows from 53 companies (E3 43, E12 10, non-YouTube 7);
- D-046–D-052;
- `v2.md`, `owner_label_qc.sh`, `analysis/power/`.

I did not read `data/sealed/`.

## Verdict: **GO for P2** (downloads plus wave-1 normalisation)

None of the defects affects downloading or re-encoding. All must close before P5/P6 and the prereg lock.

## Prior required changes (P1 cycle 1)

1. **H4 MDE:**
   - **The text: FIXED** (`v2.md:22`).
   - **The ≥500-dataset rerun: DEFERRED-OK** (before the lock).
   - **The N parameter: NOT FIXED.** `h4sim.py:8` still hard-codes `N=60`.
2. **Single confirmatory look: FIXED** (D-046; `v2.md:364`), with two gaps:
   - No N_target or calendar stop, so the timing of the look is not fixed.
   - `v2.md:363` still says "20–29 per group is confirmatory", which contradicts l.364.
3. **Wave-2 floors, disjoint companies, `wave` and `collected_after_lock`: FIXED** (`manifest.py:37`, `test_manifest_schema.py`).
4. **Block totals reported: FIXED** (BUGS.md:32). **E1 + E2 merge: FIXED** (`config.yaml:32-37`).
5. **Platform:**
   - **The column: FIXED.**
   - **The D-047 "forced M0 covariate": NOT FIXED.** `config.yaml:175-184` has neither `platform_nonYT` nor `upload_lag_days`, and `q_m0` has no forced-covariate path. `upload_lag_days` is empty for all rows.
6. **Counts: FIXED** (D-047). **`curation_report.md:34`** still says "youtube 627": NOT FIXED.
7. **κ on all rows: FIXED** (DECISIONS:79). **ROADMAP:76** still says "15%": NOT FIXED.

## Checks I ran

**κ adequacy: adequate for exploratory wave 1.**
- 2 disagreements in 58 give κ = 0.931–0.933 with CI [0.84, 1.0], which reproduces the reported result.
- The PASS rests on the point estimate; the lower bound is below 0.9.
- Both raters are LLM agents with correlated errors, so κ measures agreement, not accuracy.

**Analysis-set rule (D-050).**
- Dropping disagreements and non-A re-derivations is label-symmetric, and the analyst stays blind. Acceptable.
- The worst case becomes **30/23**.

**MDE at 30/23** (two-sided):

| Test | MDE d |
|---|---|
| Single-network test | 0.79 (AUC 0.71) |
| Holm worst case | 0.955 |
| Bonferroni over 7 | 1.015 |

`v2.md:23` still states the 56-company / 30/26 figures (0.76, 0.92–0.95).

## New defects

**N1 [MAJOR]. Honouring D-047 saturates Q at N = 53.**
- Required columns: 1 + 9 + `voiced_any` + `platform_nonYT` + `upload_lag` + 1 era + 3 forced = 17, which equals ⌊53/3⌋.
- That leaves 0 optional terms. Merges start if N falls below 51.
- T1 already drops 1 video shorter than 50 s, before the audio and word-count exclusions.

**N2 [MAJOR]. The `qc_pass` rule is for wave 1 only** (not in `v2.md`; grep finds no hits). Wave 2 needs the same rule pre-registered.

**N3 [MAJOR]. The blocks were coded on 58 rows, with raw routes, and three are under 6** (p0_c2 N1–N2). They must be recoded on the 53-row set before P5.

**N4 [MINOR]. BUG-021.** Log that the post-exposure choices (D-049, D-050) are label-symmetric. P5b must use the identical code path.

## Required changes

1. **Before P5:** add `platform_nonYT` and `upload_lag_days` to `m0.features` as forced linear terms. For missing upload dates use the label-free median plus an indicator. Regenerate the dimension table at N = 50–53.
2. **`v2.md`:**
   - l.23: set the MDE to 0.79 / 0.955 / 1.015;
   - l.363: delete "20–29 confirmatory";
   - add a label-blind wave-2 N_target (30/group) and a hard calendar stop;
   - add the `qc_pass` rule for every wave.
3. **`h4sim.py`:** take N from argv, pin the seed, rerun ≥500 datasets at N = 53 and N = 100 with the D-037 Q, and commit the outputs.
4. **Housekeeping:** fix ROADMAP:76 and regenerate `curation_report.md`.
5. **Owner:** recode the blocks on the 53-row set (OPEN/TARGETED), report sizes only, and grant pod read access.
