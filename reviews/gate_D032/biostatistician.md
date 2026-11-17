# G-D032 — Biostatistician review

Commit reviewed: 529652d. HEAD aaf6cd3 differs only in a curation CSV. Targeted tests: 26 passed, real atlases loaded.

## Vote: **FIX**

M1 is correct. The defects are:
- NaN confounds that break Q(M0);
- an unspecified resampling unit for the bootstrap CI;
- no inference or reporting rule for T3.

None needs a redesign.

## Verified correct

- **M1 matches §1.**
  - `networks.py:40-50`: per-TR z-score across the non-medial-wall vertices.
  - `:103`: averaging over W happens after standardisation.
  - `:105-108`: 6 non-limbic means, and the code checks that the network list plus the reference partition Yeo-7.
  - `:86-89`: the 7th feature is the time-averaged spatial SD of the raw map.
  - The medial wall is Schaefer label 0 and Yeo-7 is derived from Schaefer (`atlas.py:175-181`), so the sum-to-zero identity is exact.
- **Numerical check.** On 60 random videos:
  - max |Σ n_k m_k| = 2.4e-11;
  - the 7 network means have rank 6;
  - Limbic rebuilt as −Σ(n_k/n_L)m_k has error 8e-15;
  - the M1 7-vector has full rank 7.
- **ENH-001.** `speech_rate_wps` is present (`confounds/core.py:135-140`: word midpoints binned per TR, divided by covered seconds). `speech_frac` is present too (`:124`).
- **TR grid.** TR k covers [k, k+1) s (`core.py:49-55`). This matches the prediction index, because §1 adds no extra HRF shift.

## Defects

**D1 [MAJOR]. NaN confounds will crash Q(M0).**
- `core.py:263`: `text_frac` is entirely NaN.
- `:208`: `face_area_outside_crop_frac` is NaN whenever no face is detected.
- `:145-146`: `pitch_*` is NaN in every TR without voiced speech, so a whole W can be NaN.
- `:140`: `speech_rate_wps` is NaN when there is no tsv.

Reproduced: Q = [1, M0, M0²] with N = 150 and one all-NaN column fails with `LinAlgError: SVD did not converge` (`np.linalg.lstsq`). No code yet averages M0 over W (`:281-284` is a whole-clip `nanmean`), so there is no NaN policy.

*Required changes:*
- (a) Drop `text_frac` from the frozen M0 list until it is implemented. Record this in the prereg. Do not impute it.
- (b) Add `m0_window_features(df, W)` that uses the frozen W.
- (c) Use label-free, pre-specified imputation:
  - no face → `face_area_outside_crop_frac` = 0;
  - no voiced frame in W → pitch = the grand median, plus a binary `voiced_any` that is not squared;
  - no tsv → fail hard.
- (d) The Q builder asserts that every entry is finite and that the **numerical** rank (SVD tolerance) is ≤ ⌊N/3⌋, and it logs aliased columns.
- (e) Add a unit test with silent and faceless synthetic videos.

**D2 [MAJOR]. Peak-table CI** (`localize.py:58-64`).
- It takes arbitrary (B, 20484) maps and computes **percentile** quantiles.
- No generator exists, so nothing enforces company-cluster resampling. Resampling vertices, or resampling without group stratification, would make the CIs invalid.
- §1 uses a company-cluster **BCa** elsewhere, which this does not match.
- The top-20 are selected on the same data, so their CIs are optimistic (winner's curse).

*Required changes:*
- (a) Add `bootstrap_maps(maps, group, company, B=10000, seed)`:
  - resampling unit = company, which is one video in the confirmatory set;
  - stratified by group for the difference map.
- (b) Choose one CI method and state it in the table header:
  - either BCa, with a company jackknife for the acceleration term;
  - or "percentile, descriptive".
- (c) Add `p_top20`: the bootstrap share of replicates in which the parcel stays in the top 20. Add the footnote "CIs not adjusted for selection".
- (d) Specify which maps the table uses: W-averaged, spatially standardised maps (the H1 scale). Difference maps exist only after unblinding.

**D3 [MAJOR]. T3 inference is undefined** (v2.md §1, "Sensitivity track T3").
- T3 equalises each video's mean luminance and contrast. So an M0 recomputed on T3 has near-constant luminance and contrast columns, aliased with the intercept, and the residualisation span changes.

*Required protocol text:*
- (a) T3 reuses the T1 M0, Q(M0), W, exclusions, era blocks and permutation seeds. Only M1 is recomputed. This makes the T1 and T3 nulls paired.
- (b) The T3 H1 and H4 tests sit **outside** the Holm family and spend no α. Report the estimate, CI and uncorrected p, labelled "sensitivity".
- (c) Reporting rule:
  - A T1 effect "survives" if the T3 estimate has the same sign and the T3 p < .05, with the same sidedness as T1.
  - If not, report "photometrically fragile". The T1 verdict is unchanged.
  - T3 can never turn a T1 null into a claim.
  - For H1, judge survival per network, only for networks significant in T1.
- (d) Clip-flagged videos (`photometric.py:119`) stay in T3. A secondary T3 analysis excludes them.

**D4 [MINOR]. `spatial_standardize` lets NaN through silently** (`networks.py:43-47`).
- One NaN vertex makes the whole TR NaN with no error, because `sd <= 0` is False for NaN. I verified this.

*Change:* raise if `~np.isfinite(ctx).all()`.

**D5 [MINOR]. T3 gain is unbounded** (`photometric.py:94`).
- A near-uniform video gets a huge `a`, which causes heavy clipping.

*Change:* flag (do not exclude) when `a` is outside [0.25, 4], and log `a`.

**D6 [MINOR]. The spatial-SD ddof key also sets the standardisation ddof** (`networks.py:102-103`).
- The effect is a harmless scale factor of 1.00003, but it couples two settings.

*Change:* give standardisation its own key, or hard-code ddof = 0.

## ENH-003

The subcortical model is acceptable only as EXPLORATORY: no Holm membership, and no M1/H4 input. Its results go into the exploratory BH-FDR set.
