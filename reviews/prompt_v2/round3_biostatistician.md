# Round 3: biostatistician review (independent context)

Scope: v2.1 §0–§1, §5 P5b–P8, `ROADMAP.md`.

**Vote: FIX.** H4 as written is not guaranteed to hold its size. The main problem is the residualisation step, not the permutation scheme.

## Simulation (scratch `r3/sim.py`)

Setup:
- N = 60 (30/30 case-control); M0 has p = 12 features, N(0, I).
- The outcome depends only on M0, nonlinearly: logit = 1.2(x1² − 1) + 1.0·x2x3 + 0.6·x4.
- M1 (7 columns) = linear(M0) + x1² + x2x3 + noise. So TRIBE adds nothing beyond quadratic M0, and H4's null is true.
- Fitting: 3× repeated 5-fold CV, L2-logistic with C fixed (no nesting, no strata), B = 200, 300 simulated datasets per row (120 for ridge).

| Residualisation basis | Size, spec'd test (permute R) | Size, re-residualise after permuting |
|---|---|---|
| Linear M0 only | 0.79 | 0.79 |
| OLS on the true terms (M0 + x1² + x2x3) | **0.020** | 0.053 |
| OLS on M0 + squares (no products) | 0.057 | 0.14 |
| OLS on M0 + quadratic in the top 5 PCs | 0.24 | 0.28 |
| **Ridge on full Q (90 terms > N), GCV λ** | **0.108** | 0.30 |

What this shows:
1. Permuting the rows of R is a valid but **conservative** test, *only if* the residualisation removes the M0 nonlinearity exactly (size 0.02). (Freedman–Lane does not apply to binary y.)
2. The real risk is **leakage through imperfect residualisation**. Ridge shrinkage leaves quadratic M0 in R, and because M0 enters the outcome model only linearly, that leftover counts as "TRIBE signal" (size ≈ 0.11 at GCV λ). Re-orthogonalising the permuted R makes it worse.

## Defects

**D1 (CRITICAL): §1 H4, Q(M0) is ill-posed and λ is unspecified.**
- P3 implies p ≈ 15–20, so Q has 135–230 terms, which is more than N = 40–60.
- Minimum-norm OLS gives R ≡ 0. With ridge, λ alone sets how much quadratic M0 leaks into R.
- λ is the analyst's choice, a forking path.

Replacement for the H4 estimand cell, from "R = M1 residualised…" up to "…not a leakage path.":
> R = M1 residualised by **unpenalised OLS** on Q(M0) = [1, M0, M0², and pairwise products among the K_Q M0 features named in the prereg], with rank(Q) ≤ ⌊N/3⌋. The K_Q features are the ones with the largest label-free variance-inflation-adjusted variance, chosen before unblinding. Era dummies enter linearly only. No ridge and no PCA. The residualisation is computed once on the full analysis set; it is label-free. The report states that "beyond M0" means beyond this listed span only.

**D2 (CRITICAL): §5 P5b / ROADMAP P5b, the validation cannot detect D1's failure mode.**
- Shuffling labels makes y independent of M0, so leakage through R can never show up in the FPR check.
- Cost is undefined (1,000 × B = 2,000 × nested CV ≈ 10⁸ fits).

Replacement for the first P5b bullet:
> Null FPR for H4 is estimated on **synthetic outcomes y\* ~ Bernoulli(logit(g(M0)))**, where g is a pre-specified nonlinear function of the real M0 (squares, products and one cubic term, scaled so AUC(M0) ≈ 0.70) and M1 is real. Use 500 replicates with B = 500, 5 repeats and the full nesting. The acceptable FPR range is 3.1–7.1% (the binomial 95% range for 500 replicates). H1–H3/H4b FPR uses 1,000 label shuffles as before. If H4 fails, reduce K_Q (D1) and rerun before P6; this must not change after P6.

**D3 (MAJOR): §5 P5b, "recovery of planted effects at d = 0.5 and 0.8" has no pass criterion.**
§0 says H4 needs d ≈ 1.06 for 80% power, so d = 0.8 recovery will fail or be waived.

Replacement:
> Report empirical power at d = 0.5, 0.8 and 1.06. PASS = power within ±10 points of `analysis/power/h4sim.py` at the same N. This is a pipeline-correctness check, not a power requirement.

**D4 (MAJOR): ROADMAP contradicts v2.md.**

| ROADMAP says | v2.md says |
|---|---|
| P2 "short side ≥256" | P2 ≥292 |
| P4b test "face/STG contrast d > 0.8" | P4b (a) mean z > 0.2 and p < .001; (b) selectivity; (c) between-video r > 0.3 |
| P6 is listed before P5b | P5b runs before P6 |

Replacement text:
- ROADMAP P2: "Keep native aspect ratio, short side ≥292 px, CFR 30 fps."
- ROADMAP `test_controls`: "implements v2.md §5 P4b (a) within-video HAC partial-r, mean z > 0.2 and p < .001; (b) selectivity paired p < .01; (c) between-video r > 0.3 and permutation p < .05. Any FAIL means STOP."
- Move the "P5b — Pipeline validation" section above "P6 — Prereg lock".

**D5 (MAJOR): §1, M0's dimension is never fixed.**
P3 says only "as in v1, plus …", so p is not defined. D1 and the Freedman–Lane nuisance count (⌊N/15⌋ PCs) both depend on it.

Add to the §1 Comparator models, after the M0 bullet:
> The M0 feature list and p are frozen in the prereg. Binary and categorical features are not squared.

## Minor (no vote impact)
- H1 tests all 7 Yeo networks while M1 drops limbic. Keep this, but say so in §1.
- I searched the Holm family, the MDE (d = 0.74 ⇔ AUC 0.70), the 3.7–6.4% range, p = (b+1)/(B+1) and the 47 s cutoff. All are consistent.

## Simulation caveats
- Fixed C (no nesting), 3 repeats rather than 20, no strata; B = 200 (re-residualisation column B = 100).
- Monte Carlo SE is about 0.013 at 300 datasets and 0.028 at 120. Directions are robust; exact sizes are approximate.
