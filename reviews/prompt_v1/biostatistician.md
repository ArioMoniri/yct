# Biostatistician review: prompt v1 (sections 1, 5 P6–P8, 5b B1–B13)

**Verdict: FIX.** The design can be rescued, but as written it has an undefined primary family, one degenerate primary feature, two invalid tests (time-course block permutation, DeLong/bootstrap for nested ΔAUC), a mixed model that barely has a variance component to estimate, and a holdout that leaves the main analysis without the power it needs.

## Power reference (two-sample, α=.05, 80% power)

| n/group | MDE d (2-sided) | d (1-sided) | d (Bonf. /7) | d at 2:1 imbalance, same total | Univariate AUC MDE vs .5 (Hanley–McNeil) | ΔAUC MDE, oracle* |
|---|---|---|---|---|---|---|
| 20 | 0.91 | 0.80 | 1.17 | 0.98 | 0.75 | 0.21 |
| 30 | 0.74 | 0.65 | 0.94 | 0.78 | 0.70 | 0.18 |
| 50 | 0.57 | 0.50 | 0.72 | 0.60 | 0.66 | 0.13 |

*The ΔAUC column uses a paired DeLong test on oracle (true-coefficient) scores, with M0 AUC=.65 and an independent brain signal. It is a **lower bound**. Cross-validated fitting makes it worse. With N≤50/group, H4 can detect only a large brain increment.

## Required changes

**1 [CRITICAL] The primary feature is degenerate.** If a vertex time course is z-scored over time, its mean is exactly 0, so "per-video per-vertex z-scored" mean features are identically zero. The raw signed mean is in turn dominated by global gain (the pilot's "12% higher"). *Replace P5 primary feature with:* "Primary feature = for each video, the time-averaged predicted response after edge trimming, **spatially standardised** (subtract the cortex-wide mean and divide by the cortex-wide SD at each TR, then average over TRs), then averaged within each Yeo-7 network. The global mean amplitude is a separate secondary feature (G). SD, peak, time-to-peak and thirds are secondary."

**2 [CRITICAL] The primary family is undefined.** H1 as written ("parcel/network features differ") covers about 400 parcels × 8 features × 2 tracks × 2 scalings. *Replace section 1 with* the SAP v2 hypothesis table below: one test per hypothesis, H4 as the sole primary, and H1–H3 as key secondaries under Holm.

**3 [CRITICAL] The ΔAUC inference is invalid.** A bootstrap over CV folds treats fold AUCs as independent, which they are not. DeLong on out-of-fold predictions ignores training variance and is invalid for nested models (Demler et al., 2012). *Replace H4/P8 with:* "Estimator: the mean over R=20 repeats of [pooled out-of-fold AUC(M2) − AUC(M0)], using StratifiedGroupKFold(5) by company. **Test:** a conditional permutation test with 2,000 permutations. Inside each training fold, brain features are residualised on M0 features. Residual rows are permuted under the exchangeability blocks of change 5, and the full nested pipeline is rerun for each permutation. p is one-sided (ΔAUC>0) and computed as (b+1)/(B+1). **CI:** a Nadeau–Bengio-corrected repeated-CV t-interval (variance inflation 1/(kr)+n_test/n_train), which is descriptive only."

**4 [MAJOR] Drop the company random effect from the primary analysis (B2).** When most companies contribute one video, the random-intercept variance is identified only by the few pairs. It will sit at the boundary (0), and REML estimates are unstable. *Replace B1/B2 with:* "Primary set = all eligible conf-A videos. The unit is the video; companies are clusters. Inference uses restricted permutation (change 5). Adjusted effects use OLS with **CR2 cluster-robust SE** and Satterthwaite df (clubSandwich-equivalent). A mixed model is run only as a sensitivity analysis, and only if ≥15 companies contribute ≥2 videos. The within-company pairs analysis (sign-flip test over pairs) is secondary and descriptive if <10 pairs. It is reported as confounded with application order, learning and era, because in every pair the accepted video comes later. A further sensitivity analysis uses one video per company, with a seeded random choice for pairs (200 draws, report median p)."

**5 [MAJOR] Define the exchangeability blocks (B6, B13).** *Insert:* "Permutation scheme (used for H1–H4 and Freedman–Lane): labels of singleton-company videos are shuffled **within era strata** (≤2016, 2017–19, 2020–22, ≥2023; adjacent strata are merged until each holds ≥3 videos per class). For two-video companies, labels are swapped within the pair (multi-level blocks, Winkler et al. 2015). Era is then handled by design and is not also entered as a covariate. Freedman–Lane: fit feature ~ Z (nuisance), permute the reduced-model residuals under the same blocks, refit the full model, and use the label t-statistic." Report year×outcome as a Fisher exact test.

**6 [MAJOR] Covariate overload (P7 LM, B5).** Nine covariates plus a label with N≈60 overfits, and global_signal is a probable mediator. *Replace with:* "Adjusted estimand: Z = the first k PCs of the standardised confound matrix, with k = min(5, ⌊N/15⌋), fixed before unblinding. Global signal is excluded from the primary adjusted model and reported as feature G. The unadjusted estimand (total difference) and the adjusted estimand (difference beyond low-level stimulus features) are both reported."

**7 [MAJOR] Block permutation and phase randomisation for time courses (B7) is the wrong null.** The hypothesis is between groups, so the exchangeable unit is the video label. Permuting whole time courses already preserves autocorrelation. *Replace with:* "T2 temporal test: label permutation of whole videos (change 5 blocks) with cluster-mass over the 50 bins (cluster-forming |t|>2.0), FWER over bins. Exploratory."

**8 [MAJOR] Spin tests (B8) do not test group differences.** A spin test checks spatial correspondence between two maps. *Replace with:* "Spin tests (Váša parcel-level spin on the Schaefer-400 sphere centroids, medial wall excluded, 10k rotations) are used only to test whether the group-difference g-map is enriched for language/social networks or correlates with reference maps. They are exploratory and are never used as the group-difference test."

**9 [MAJOR] Vertex-level TFCE needs explicit settings.** *Specify:* "Vertex TFCE runs on the fsaverage5 mesh adjacency, per hemisphere with the medial wall masked, with H=2 and E=1 (2-D settings), maxTFCE across both hemispheres, and 5,000 permutations under the change 5 blocks (PALM-equivalent). Exploratory only."

**10 [MAJOR] Locked holdout (B9).** At N=80, a 20% holdout has 8 videos per class, an AUC SE of about 0.13 and an AUC MDE of 0.87, against 0.68 with full-N CV. *Replace with:* "**Decision rule:** create a stratified locked holdout only if N_total(conf-A) ≥ 200 with ≥80 per class. At that size it has 20 per class and an AUC MDE of 0.75. Otherwise there is no holdout. Integrity comes from blinding, the hash-locked pipeline and permutation. Videos found after the prereg lock form a temporal replication set that is analysed once."

**11 [MAJOR] Model and feature multiplicity in P8.** *Replace with:* "Primary: L2 logistic regression with C tuned on an inner grouped 5-fold over a log-grid of 13 values. Standardisation and PCA are fitted inside folds. M0 = the prespecified ≤10 confound features. M1 = the 7 primary network features. M2 = M0 ∪ M1. The linear SVM and LOYO are sensitivity analyses. Under LOYO, pool OOF scores, because single-year folds can contain one class. Report AUC, balanced accuracy and Brier score. No PPV (B10)."

**12 [MAJOR] SESOI/TOST (B4).** *Replace with:* "SESOI: |d|=0.5 per network, univariate AUC ≈.64. SESOI for ΔAUC is 0.05. Run TOST (α=.05) at ±0.5. Its power with true d=0 is 0.21, 0.60 and 0.82 at n=30, 50 and 70/group. A non-significant result without equivalence is reported as **inconclusive**, not null. Equivalence for ΔAUC at ±0.05 is unattainable at this N, so ΔAUC nulls are always inconclusive."

**13 [MAJOR] Pre-specified stop and futility rules (section 7 and P1).** *Add:* "(a) After curation and **before unblinding**: if conf-A < 20/group (MDE d>0.9), confirmatory testing is cancelled and the study reports as a descriptive pilot. 15–19/group = STOP as in v1. (b) Positive control on blinded data: predicted FFA/OFA response must correlate with face fraction, and STG with speech fraction (Spearman ρ>.3, p<.01). Failure = STOP, because the features are not stimulus-sensitive. (c) If M0 AUC ≥ .85, label-confound entanglement is too strong for H4 to be interpretable. Report it and downgrade H4 to exploratory. (d) No optional stopping: collection ends before unblinding, and later videos go only to the replication set."

**14 [MINOR] Label noise (B11, B12).** *Specify:* "Flip simulation: 1,000 replicates each of symmetric flips at 5% and 10%, plus an asymmetric rejected→accepted flip at 10% (the likelier error). Report the distributions of estimates and p. Two blind coders label every row; Cohen's κ≥0.7 is required, and disagreements become C. For A vs A+B, fit label×confidence; robustness = same sign, and the A+B estimate lies within the A-only 95% CI."

**15 [MINOR] Validation of the null FPR.** For 1,000 null simulations, the acceptance band is 3.7–6.4% (binomial 95%), not "≤5%". Planted effects use d=0.5 and 0.8 in one network, and recovery power is reported.

**16 [MINOR] Bootstrap CIs for g.** Use a cluster bootstrap (company), stratified by label, with BCa and 10k resamples. Sensitivity analyses report estimates and CIs only.

**17 [MINOR] Variable duration.** T1 windows range from 30 to 60 s, so SD and peak features depend on T. Compute primary features over a common window of 6–30 s, with full-length features as a sensitivity analysis.

## Statistical Analysis Plan v2 (paste-ready)

**Analysis set.** All conf-A videos passing QC. Unit = video; companies are clusters. Blinded until P6 GO. Collection ends before unblinding.

**Primary features.** Seven Yeo-7 network means of the spatially standardised, time-averaged TRIBE v2 prediction (track T1, common window 6–30 s after edge trimming). Global amplitude G and the five functional ROIs (pSTS, TP, L IFG, TPJ, V1–V3 control) are secondary.

**Exchangeability.** Singleton-company labels are permuted within prespecified era strata. Two-video companies swap labels within the pair. All p-values are (b+1)/(B+1).

**Hypotheses and tests.**

| | Estimand | Statistic / test | Correction | α |
|---|---|---|---|---|
| **H4 (primary)** | ΔAUC = AUC(M2)−AUC(M0), mean of 20× repeated StratifiedGroupKFold(5) pooled OOF, L2-logistic, nested C | Conditional permutation (brain features residualised on M0 in-fold, permuted under blocks), B=2,000, one-sided | none (sole primary) | .05 |
| H1 (key sec.) | Any network differs | maxT over 7 Welch t (Westfall–Young), B=10,000, two-sided | Holm across H1–H3 | .05 FWER |
| H2 (key sec.) | Accepted > rejected in the language/social composite (mean of the pSTS, TP, L IFG, TPJ Schaefer parcels, listed in prereg) | Welch t, permutation B=10,000, one-sided | Holm across H1–H3 | .05 |
| H3 (key sec.) | AUC(M1) > .5 | Label permutation of the full nested pipeline, B=2,000, one-sided | Holm across H1–H3 | .05 |

H1–H3 are reported as a separate family and are not gated on H4.

**Effect sizes.** Hedges g per network, with a company-cluster BCa bootstrap CI (10k). ΔAUC uses a Nadeau–Bengio-corrected CI. AUC, balanced accuracy and Brier score are reported, with no PPV.

**Adjusted estimand.** Freedman–Lane under the same blocks, with nuisance Z = first min(5, ⌊N/15⌋) PCs of the confounds. OLS with CR2 SE is reported alongside. Unadjusted and adjusted results are both reported, and the adjusted result is the interpretive headline for "beyond stimulus features".

**SESOI.** |d|=0.5 per network and ΔAUC=0.05. TOST at ±0.5 is run for nulls. A result that is non-significant and not equivalent is labelled *inconclusive*.

**Power (prespecified).** At 30/group, the MDE is d=0.74 (two-sided) and the univariate AUC MDE is .70. The oracle ΔAUC MDE is ≥.18, which is a lower bound. Final N and MDE are recorded at the P1 gate.

**Holdout.** Only if N ≥ 200 with ≥80 per class. Otherwise there is none, and a post-lock temporal replication set is analysed once.

**Secondary/exploratory.** Parcels (BH-FDR q=.05 within feature type), vertex TFCE (H=2, E=1, mesh adjacency, maxTFCE), the T2 bin cluster-mass test, spin-test enrichment, modality ablations, SVM and LOYO. Pairs use a sign-flip test and are descriptive if <10 pairs. A mixed model is run only if ≥15 multi-video companies.

**Sensitivity.** A+B (label×confidence), the matched subset, one-video-per-company (200 draws), label flips at 5/10% symmetric and 10% asymmetric, raw vs standardised features, and full-length windows. Estimates and CIs only.

**Validation.** Null FPR from 1,000 shuffles within 3.7–6.4%. Planted d=0.5 and 0.8 recovery reported. Shuffled-label AUC ≈ .5.

**Stop/futility.** Fewer than 20 conf-A per group: descriptive pilot only. Positive-control failure: STOP. M0 AUC ≥ .85: H4 is exploratory. No optional stopping. Deviations are logged in DECISIONS.md with reasons.
