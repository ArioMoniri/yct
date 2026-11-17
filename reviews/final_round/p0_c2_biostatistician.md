# Phase 0 cycle 2: Biostatistician (fresh reviewer)

Evidence: `outputs/runs/p0rel_20261117T163701Z/{report.md,summary.json,cmd}`, `feature_cache.py`, `owner_label_qc.sh`, `v2.md`, BUGS.md. I did not read `data/sealed/`.

## Verdict: **FIX**

This verdict gates P4. P2 is not blocked. Cached determinism is shown. The fresh-drift gate measures the wrong quantity, and the block coding does not follow D-040.

## Prior required changes (P0 cycle 1)

1. **v2.5 determinism amendment: FIXED.**
   - Text: `v2.md:352`, `v2.md:397-398`, `v2.md:486`, ROADMAP:136.
   - Cached reruns are bit-identical for all 3 clips (p0rel report.md).
2. **Drift audit (≥5 real clips chosen label-blind, T1 and T3; ratio for M1 and parcels ≤ 0.05): NOT FIXED.**
   - The clips are synthetic testsrc2 + espeak (`gpu_p0_rerun.py:15-16`).
   - The gate runs on backbone feature arrays. `reliability()` (`feature_cache.py:225-238`) divides by the pooled within-array variance, not by the between-video variance of M1. So 0.9913 says little about M1.
   - The prediction max|diff| (0.0017 at 70 s) suggests the M1 ratio is small, but that has not been shown.
3. **Cache key and archive:**
   - **Transcript in the key: FIXED** (`feature_cache.py:7-8`).
   - **Revisions and device: DEFERRED-OK.** D-038 allows one GPU type, the revisions are in the sidecar, and `instance_type` is in `summary.json`.
   - **Off-pod archive: NOT FIXED.** No code for it exists; the cache is only in `/work/yct/cache/`.
   - **Cache-manifest hash: FIXED** for runs. For the prereg it is DEFERRED-OK.
4. **Blocks = era × {OPEN, TARGETED}, merged within route; bootstrap stratified by group × r:**
   - **Text: FIXED** (`v2.md:96-103`).
   - **Code: NOT FIXED.**
     - `block_codes` (`owner_label_qc.sh:234-246`) uses the raw uppercased routes.
     - With 2 routes and a minimum of 6, the published sizes **4/4/45/5** (BUGS.md:32) are impossible. I reproduced 45/5/4/4 with 4 raw routes (scratch `blk.py`).
     - The bootstrap is stratified by group only (`localize.py:150-200`).
5. **Same-route sensitivity: FIXED** (`v2.md:103`).

## New defects

**N1 [MAJOR]. What the published blocks mean for permutation.**
- The blocks of 4, 4 and 5 are single-route and probably label-homogeneous by design (D-035).
- **H4 (R-row permutation):** blocking is still needed.
  - Synthetic setup: N = 53, blocks 40/4/4/5, route shifts M1, y depends on route only.
  - FPR is **0.347** with global permutation vs **0.06** with block permutation. Power at eff 1.0 is 0.89 vs 0.91.
- **H1 (label permutation):** the pure blocks contribute no variability, so inference rests on the 45-row block. Era stratification is lost if E12 was merged into it.

**N2 [MAJOR]. The blocks were coded on in_primary (58), not on the analysis set (53, `qc_pass`).** Pod read access to `/yct/owner/blocks` is missing from `owner_setup.sh`.

**N3 [MINOR]. BUG-018 blocks T2 for a large share of the set.** 20/53 analysis-set videos are longer than 70 s (max 160 s). T2 stays STOP until the fix is verified at ≥160 s. T1 is unaffected.

**N4 [MINOR]. Misleading report line.** report.md says "A==B False (sha256 None)" for steps that were not run. Print "not run".

## Required changes (before P4)

1. **Redefine the D-038 drift gate** as SD(fresh − cached) / between-video SD, for each of the 7 M1 means over W and for the parcel values.
   - Use the first ≥5 real wave-1 clips (seeded sha), on T1 and on T3.
   - Gate: ≤ 0.05 (reliability ≥ 0.9975).
   - Keep the array-level number as a diagnostic.
2. **Archive the feature cache off-pod** (content-addressed; object lock) and verify its sha256 manifest after each upload.
3. **Owner recodes the blocks on in_primary & qc_pass** with OPEN/TARGETED (`v2.md:98`). Assert inside `block_codes` that each block has ≥ 6 videos or is its route's only group. Print sizes only, and grant pod read access.
4. **Stratify `company_bootstrap`** by group × opaque block.
