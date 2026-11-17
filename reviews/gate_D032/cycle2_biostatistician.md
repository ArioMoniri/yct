# G-D032 cycle 2 — Biostatistician (fresh reviewer)

HEAD b83e6c2 (fixes at b140dd6). Targeted tests: 42 passed. Scratch scripts are in `/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/c2b/`.

## Vote: **FIX**

All cycle-1 biostatistics defects are fixed. D-036 is not acceptable as written.

## Cycle-1 items: verified fixed

- **D1.**
  - `text_frac` is banned.
  - `m0_window_features` exists.
  - Imputation: no face → 0; unvoiced → median plus `voiced_any`; a missing tsv fails.
  - The finite assert and the rank ≤ ⌊N/3⌋ assert are in place, and aliased columns are logged.
  - Tests cover silent and faceless videos.
  - Checked: the N = 40 default Q raises (rank 23 > 13), a constant `voiced_any` is logged as aliased, and NaN raises.
- **D2.**
  - Companies are resampled with replacement **within group**. Synthetic check: the per-group draw counts are integers that sum to n_g, and videos of one company share one weight in every replicate.
  - BCa uses a leave-one-company-out jackknife.
  - The stability column and the selection caption are present.
  - `bh_fdr` matches `statsmodels fdr_bh` on 200 random p-vectors (ties included), is monotone, and passes NaN through.
- **D3.** The T3 rules are in v2.md l.107-113.
- **D4.** `spatial_standardize` raises on a non-finite cortical value and tolerates NaN on the medial wall.
- **D5.** The gain cap is in place and capped clips are flagged and kept.
- **D6.** The ddof keys are separate.

## Defects

**B1 [MAJOR]. D-036 contradicts the protocol and is ambiguous.**
- v2.md l.69 still says Q = [1, M0, M0², VIF-chosen K_Q products], with era dummies, and "**no PCA**".
- D-036 leaves out the era dummies and `voiced_any`.

Q size under the D-036 rule, by reading:

| N (limit) | I1: as written | I2: + era (2) + voiced_any |
|---|---|---|
| 40 (13) | j = 5, K_Q ≤ 1 | j = 3, K_Q = 2 |
| 60 (20) | j = 7, K_Q = 3 | j = 7, K_Q = 1 |
| 80 (26) | j = 7, K_Q = 4 | j = 7, K_Q = 4 |

**B2 [MAJOR]. At N = 40, D-036 drops terms the protocol promises.**
- PCs 4–7 (I2) or PCs 6–7 (I1) are not in Q even **linearly**.
- sr², sf² and sr·sf, which D-034 forced in for known issue #8, are dropped at every N.
- The l.12 claim "beyond the linear + quadratic span" becomes false.

**B3 [MAJOR]. H4 null simulation.**
- Setup:
  - 9 correlated M0 features plus `voiced_any`, and 3 era blocks.
  - ΔAUC = out-of-fold AUC difference from L2-logistic, 5-fold × 2.
  - R rows permuted within era, B = 99.
- **Diffuse nonlinear null** (300 reps, MC SE 0.013): FPR is 0.053, 0.047 and 0.043 at N = 40, 60 and 80 with the D-036 (I2) Q. This is valid.
- **Adversarial null** (200 reps): the square of the **lowest-variance** PC drives both M1 and y.
  - D-036: FPR **0.285** at N = 40, where that PC is dropped. At N = 60 and 80, where it is included, FPR is 0.025 and 0.020.
  - A linear-first alternative fails the same way wherever the term is not in Q: 0.29 at N = 40 and 0.36 at N = 60.
- **Conclusion.** The conditional permutation is valid only up to the span that Q actually contains.

**B4 [MINOR]. Rank uses numpy's default tolerance.**
- Setting `rms_db = speech_frac + 1e-9·noise` passes with rank 23, no aliased columns and cond(Q) = 4.9e9.

**B5 [MINOR]. Unfinished pieces.**
- FIX-D032-3 is not implemented.
- The permutation blocks are era-only, and D-035 is not wired in.
- BCa coverage in a skewed two-sample case at n = 12/30 was 0.87, and the percentile interval was 0.90. This is a small-sample limitation, not a bug.

## Required changes

1. **v2.5 H4 row**, with one unambiguous Q:
   - Q = [1, all M0 linear (z), `voiced_any`, era dummies], then a quadratic budget in this fixed order: sr², sf², sr·sf, then PC1², PC2², …, then products of the leading PCs, until rank = ⌊N/3⌋.
   - The PCs are label-free, of the z-scored non-speech continuous M0.
   - If the linear block alone exceeds the limit, shorten the M0 list by a pre-registered order.
   - Change "no PCA" to "no PCA of the linear block".
2. **Implement FIX-D032-3.**
   - Freeze the dimension table for N = 40, 60 and 80 in tests and in the prereg.
   - Fix the PC sign convention.
3. **P5 FPR check (l.394).** Use the final Q at the final N, with g including:
   - diffuse squares and products;
   - the square of the last included PC;
   - the square of an excluded PC, reported as the size outside the span.

   The report must name the exact Q span as the meaning of "beyond M0".
4. **Rank tolerance.** Set rank and aliasing with rcond = 1e-8·σ_max, and raise if cond(Q) > 1e8.
5. Add era × route blocks (see the Phase 0 review) to every permutation routine.
6. Label the BCa CIs "approximate (small n)".
