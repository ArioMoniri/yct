# G-D032 cycle 3: Biostatistician (fresh reviewer)

Reviewed at HEAD 2a4ef09 (= 31235e6 plus two DECISIONS lines). 88 targeted tests pass. Scratch scripts are in `/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/c3b/`. I did not read `data/sealed/`.

## Verdict: **GO (conditional)**

D-037 Q and the P5b machinery are correct. The items below must be done before the P6 lock. None of them affects P2–P5.

## Prior required changes (cycle 2)

1. **Unambiguous Q, all linear terms, no PCA: FIXED.**
   - Evidence: `m0.py:313-400`, `v2.md:64-72`.
   - Synthetic data at N = 53: rank 17 = ⌊53/3⌋, cond 18–31, no merges, 1–2 optional squares.
2. **Dimension table frozen: FIXED but STALE.**
   - `tests/test_m0_q_rule.py:69` and `v2.md:71` assume 3 eras. D-047 gives 2, so N = 53 has 15 required and 2 optional terms.
   - The table also leaves out the D-047 covariates (p1_c2 N1).
3. **P5b size inside and outside the span: PARTLY FIXED.**
   - `h4_null_sim` at N = 53 (200 reps, B = 49): `dropped_term` FPR **0.330** (MCSE 0.033); `included_term` **0.010** (MCSE 0.007).
   - The diffuse squares + products scenario is not implemented.
4. **rcond and cond assert: FIXED.** My B4 near-duplicate case now aliases `rms_db` and `rms_db^2` (cond 36). Evidence: `m0.py:198-209`, `m0.py:390`.
5. **Era × route blocks in every permutation: DEFERRED-OK.**
   - `src/yct/stats/` is empty, so no production routine exists yet.
   - `h4_null_sim.py:168-174` hard-codes era-only blocks.
6. **BCa labelled "approximate (small n)": NOT FIXED.**
   - The caption at `config.yaml:237-243` lacks it.
   - Re-check on a lognormal difference at 30/23 (300 reps): BCa covers **0.853**, the percentile interval 0.903.

## New defects

**N1 [MAJOR]. The optional-term order is set by outliers, and one outlier gets leverage 1.**
- `optional_term_order` (`m0.py:281-293`) ranks squares by var(z²), which equals kurtosis − 1. Only 1–2 squares fit at N = 53.
- One video 4 SD out on `scene_cuts` moves `scene_cuts^2` to first place. That video's hat value becomes **1.000**, so its R row is identically 0.
- Even without outliers, the maximum leverage is 0.79.

**N2 [MAJOR]. The P5b band rejects a conservative result.**
- `v2.md:430` requires `included_term` to fall in 3.1–7.1%. At N = 53 I get 0.010, which fails.
- The stated remedy (more merges) does not address conservatism.
- The main P5b g (squares, products and a cubic) lies mostly outside a Q with 2 optional slots. A FAIL ("not beyond M0") is therefore predictable and should be pre-stated.

**N3 [MINOR]. `NullSimResult.term` reports only the last replicate's term** (`h4_null_sim.py:154`). The order is data-dependent, so the term varies across replicates.

**N4 [MINOR]. The simulation's H4 baseline differs from the protocol.**
- The simulation uses linear M0 without era terms, fixed λ and no group-KFold (`h4_null_sim.py:164`).
- `v2.md:81` specifies a nested C.
- The PASS band must come from the production pipeline only.

## Required changes (before P6)

1. **Robustify continuous M0 before z-scoring** (pre-registered, label-free): winsorise at ±3 SD, or apply a rank-inverse-normal transform.
   - Take the optional-term order from a fixed config list, not from kurtosis.
   - Assert max h_ii ≤ 0.9 and log the leverages.
2. **Regenerate `q_dimension_table`** for 2 eras plus the D-047 covariates. Freeze N = 50/53/56 in the tests and in `v2.md:71`.
3. **Make the P5b `included_term` band one-sided** (≤ 7.1%), report conservatism separately, and pre-state the expected diffuse-g outcome.
4. **`simulate_h4_null`:** add a `blocks=` argument, the diffuse scenario, and a per-replicate list of terms.
5. **Caption:** add "approximate (small n)" to the BCa wording, via a DECISIONS entry because the config is frozen.
