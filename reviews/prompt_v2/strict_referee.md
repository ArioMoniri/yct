# Strict Referee review: master prompt v2

Scope: `docs/prompts/v2.md`, `ROADMAP.md`, `docs/tribe_requirements.md`. I did not read `reviews/prompt_v1/*`.

**Vote: FIX.** Two CRITICAL defects (C1, C2) stop the sole primary test from licensing its claim. All are fixable before P6.

## Simulations

Script: `/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/h4sim.py`.

Setup: N = 60, 12 M0 and 7 brain features, brain correlated with the outcome-relevant M0 columns. L2-logistic with C fixed at 0.3 (nested C not simulated), 2 × 5-fold CV, pooled out-of-fold AUC. Brain features residualised on M0 and permuted, B = 99; 250 datasets per row.

| Scenario | Rejection at .05 | Mean p |
|---|---|---|
| Linear null, observed statistic uses raw M1 (as §1 l.47 is written) | 0.052 | 0.355 |
| Linear null, observed statistic uses residualised M1 | 0.040 | 0.573 |
| Null where brain = M0 + M0², and Y depends on M0² | **0.404** | 0.236 |
| Power at residual d = 1.06 beyond M0 | 0.79 | — |

H4b score swap (`h4bsim.py`) with different scale or offset between models: size 0.02–0.07, acceptable. The 7 spatially standardised Yeo-7 means have rank 6; this was confirmed numerically.

## Required changes

**1. [CRITICAL] H4 tests independence given *linear* M0 (§1 l.47; §0 l.12).**

Nonlinear stimulus information that M0 misses passes through the residuals, and H4 then rejects 40% of the time with no brain-specific content.

Two further problems:
- The observed statistic uses raw M1 while the null uses permuted residuals. These are different features under L2, and the null p-values come out skewed (mean 0.355).
- "In-fold" residualisation is ambiguous, and it is unneeded because it uses no labels.

Replace the H4 Test cell with:
> "Residualise M1 on M0 once in the full sample (label-free OLS with intercept). The observed statistic and every null draw use the residuals R: ΔAUC = AUC([M0, R]) − AUC(M0), with identical splits, seeds and C grid. Each null draw permutes the rows of R jointly within blocks, globally across folds. B = 2,000, one-sided."

Add to §0 l.12:
> "H4 tests prediction beyond a *linear* model of the measured stimulus features. Because TRIBE is a nonlinear function of the stimulus, a positive H4 can come from nonlinear stimulus information alone. Report it with H4b and an exploratory nonlinear-M0 sensitivity analysis (M0 + pairwise products of its top-5 PCs)."

**2. [CRITICAL] The within-pair label swap is invalid (§1 l.55; ROADMAP l.54).**

In a reapply-then-accepted pair, the accepted video is always the later one. The label is therefore aliased with order, and with everything that comes with order: practice, newer devices, era and aspect ratio. Swapping labels within a pair counts configurations that cannot occur, so any order effect is read as an acceptance effect, in both H1 and H4.

Replace l.55 with:
> "Confirmatory analyses use one video per company, chosen before unblinding by the seeded label-free rule `random.Random(company_hash)`, and logged. Pairs are EXPLORATORY only, reported as 'accepted-later vs rejected-earlier', with order, year gap and device change listed as aliased explanations."

**3. [MAJOR] The power statement is not about H4 (§0 l.16).**

d ≈ 0.74 is the MDE for a single Welch t. H4 needed a residual d ≈ 1.06 to reach 80% power even in my optimistic setup. Replace "At 30 per group…" with:
> "The H1/H2 MDE (d ≈ 0.74 at 30/group) does not apply to H4. Before P6, simulate the H4 pipeline at the achieved N with the real M0 covariance and put the 80%-power residual d in the prereg. If it is above 1.0, label H4 'powered only for implausibly large effects'."

**4. [MAJOR] Spatial standardisation produces compositional, rank-6 features and removes the spatial-SD signal (§1 l.30–32).**

Schaefer-400/7 labels every non-medial vertex, so Σ nₖmₖ = 0 at every TR. A network difference is then a difference relative to the cortical mean. Scaling by the spatial SD also discards any group difference in how differentiated the maps are; G (l.296) recovers only the mean, not the SD. On top of that, the clip-mean level of a model trained on per-session z-scored, detrended targets (tribe_requirements §3 "Units") is unvalidated.

Add after l.32:
> "The 7 means sum to zero, vertex-weighted; H1 effects are reported 'relative to the cortical mean'. Prediction models use 6 networks (Limbic dropped, prespecified). Standardise after the reliability mask. Report the per-TR spatial SD (S) beside G as a secondary feature."

**5. [MAJOR] The positive-control gate is under-specified, gameable, and checks the wrong quantity (§5 l.285–288; ROADMAP l.124–127).**

- "d > 0.8" over autocorrelated TRs has no meaningful df, and no aggregation across videos is stated.
- Talking-head pitches have few face-absent TRs, and face and speech are collinear.
- Detector thresholds and parcels can be chosen after looking.
- The gate re-tests within-video stimulus tracking, which the paper already shows (§9), and never tests the between-video, W-averaged features that every hypothesis uses.

Replace with:
> "Detectors, thresholds and parcels are frozen in `config.yaml` before P4.
> (a) Per video with ≥10 TRs in each condition: an AR(1) GLM on the standardised prediction, testing selectivity (face: FFC − A1; speech: A4/A5 − V1). Pass = the across-video median d > 0.8, the 95% bootstrap lower bound > 0.5, and ≥70% of videos positive. Ineligible videos are listed.
> (b) The exact H4 feature pipeline must predict the label-free face fraction and speech fraction with out-of-fold R² > 0.3.
> STOP if either fails."

**6. [MAJOR] M0b at PCA k = 7 is a weak comparator (§1 l.39, l.51; §0 l.14).**

Plain PCA on the concatenated 1408-, 1024- and 3072-dimensional embeddings is dominated by the highest-variance block and by nuisance directions. A two-sided non-rejection in H4b cannot show M1 ≥ M0b.

Replace l.39 with:
> "M0b: TRIBE's backbones and layers ([0.5, 0.75, 1.0], group-mean), averaged over W; each block z-scored and divided by √dim; PCA within each fold to k = 7. Ridge on all PCs is an exploratory sensitivity analysis."

Replace §0 l.14 with:
> "No brain-specificity claim is made. At this N, H4b can only show M1 < M0b or be inconclusive."

**7. [MAJOR] W is label-free but not neutral, and M0b depends on W before W exists.**

- ROADMAP l.100 (P3) averages M0b over W, but W is set in P4 (l.116).
- Videos longer than 60 s are chunked (tribe_requirements §2.2 item 2), which puts a discontinuity inside [5, 45). Video length plausibly differs by outcome.
- No rule is given for videos shorter than 45 s, or for how W is chosen.

Replace l.33 with:
> "W = TRs [5, 45). Inputs are trimmed to ≤ 59.0 s before TRIBE, so no chunk boundary occurs. Videos with < 45 TRs are excluded, and the counts are reported by group after unblinding. Any departure from the default follows the rule 'first TR where the group-mean global signal is within 1 SD of its plateau', computed once in P4 and frozen. M0b is extracted per TR in P3 and averaged over W in P5."

**8. [MINOR] Era strata (§1 l.54).**

The ≤2016 stratum may contain zero rejected videos. "Before labels are seen by analysts" is not blinding either, because the Curator sees labels.

Replace with:
> "Era strata are set from upload year by a non-Curator agent. A stratum with < 6 videos is merged with its neighbour by a script run inside the Watchdog-audited unblinding step; only the block IDs are released. Era also enters M0 as a categorical."

**9. [MINOR] §7 l.354 demotes H4 after unblinding.**

Add:
> "H4 is run and reported regardless; only the wording changes."

**10. [MINOR] Overclaiming and loose ends.**

- §0 l.13: replace "useful inductive bias / dimensionality reduction" with "improves out-of-sample prediction over linear M0 in this sample".
- H4b (l.51): rank-normalise scores within each repeat before swapping.
- l.65: state that the Freedman–Lane PCs are computed on all N, label-free.

## Searched; no defect found

HRF handling (no extra shift; P0 impulse clip), fs5 mesh nesting, medial-wall masking, in-distribution ablation (§5), licence wording, GroupKFold by company, the p-value formula, TOST/inconclusive labelling, and the holdout rule.
