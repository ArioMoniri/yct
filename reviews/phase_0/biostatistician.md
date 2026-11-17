# Phase 0 — Biostatistician (fresh reviewer)

Evidence read:
- the smoke `smoke_report.md` and `metrics.json`;
- BUG-006;
- `src/yct/tribe_run/feature_cache.py`;
- D-035;
- the `manifest.csv` header;
- `curation_report.md`;
- v2.md.

`data/sealed/` was not read.

## Vote: **FIX**

The drift is negligible, and caching is acceptable. The protocol text, the cache key and the D-035 blinding need fixes.

## Drift versus between-video variance

- **Size of the drift.**
  - For two runs: 1 − r = σ_e²/σ_tot² = 5.9e-6, so σ_e ≈ 2.4e-3·σ_tot ≈ 3.4e-4 abs (pred SD 0.14).
  - The max of 3.57e-3 is about 7σ of the difference, a heavy tail in one entry out of 2e5.
- **Worst case for M1.**
  - Assume no averaging: the errors are fully correlated across vertices, because they enter through shared backbone features.
  - Assume a pessimistic between-video SD of 0.05 spatial-z for a W-averaged network mean.
  - Then reliability is ≥ 0.9977. A d of 0.80 becomes 0.799, and ΔAUC shifts by about 3e-4.
  - For comparison, the Nadeau–Bengio CI half-width is about 0.1.
- **Verdict.** The drift is negligible. Without a cache, a permutation p near .05 could still flip between reruns and the result could not be audited.
- **Caching** (extract once, predict only from the cache, drift reported) is an acceptable policy. The analysis then conditions on one draw of negligible extraction noise.

## Defects

**P1 [MAJOR]. The protocol still gates on empty-cache determinism.**
- v2.md l.330, l.364-366 and the stop rule at l.450 ("non-deterministic beyond tolerance with an empty cache") are **literally triggered**: 3.57e-3 > 1e-4.
- l.12 still says "deterministic"; ROADMAP l.33 and l.125 also still require empty-cache determinism.

**P2 [MAJOR]. The drift evidence is weak.**
- It is one synthetic 10-TR clip with 2–3 runs.
- It was measured on raw predictions only, with no M1 or T3 check.
- The cache has not been re-run on the GPU.

**P3 [MAJOR]. Cache key and permanence.**
- The key is the video sha only. The transcript check runs only when both tsv files exist (`if cached is not None`), so a tsv added after a text-less extraction silently reuses features with zero-filled text.
- The cache lives on an ephemeral pod, and nothing archives it.

**P4 [MAJOR]. D-035 discovery_method is a label proxy.**
- The directory sweep finds accepted videos and the rejection hunts find rejected ones.
- `curation_report.md` l.113 already flags `label_confidence` for the same reason.
- `manifest.csv` has no `discovery_method` column.
- Naive blocks would unblind the analyst. Label-pure blocks would also add no permutation variability, and nobody counts this.

**P5 [MINOR].** ENH-004: allowing the A10 changes GPU kernels. Never re-extract on mixed hardware, and record the device in the sidecar.

## Required changes

1. **v2.5 amendment** (l.12, 330, 364-366, 450; ROADMAP P0/P4):
   - Determinism = the cached rerun is bit-identical.
   - Fresh drift is reported, not gated.
   - The stop rule applies only if the cached rerun is not identical, or the drift ratio in item 2 is > 0.05.
2. **P4 drift audit.**
   - Use ≥5 real clips chosen label-blind (seeded sha), on T1 and on T3.
   - Report SD(fresh − cached) / between-video SD for the 7 M1 features and for the parcel values.
   - The threshold is 0.05.
3. **Cache.**
   - Key = sha256(video ‖ tsv-or-"none" ‖ revisions ‖ device class).
   - Keep an immutable off-pod archive.
   - Record the cache-manifest hash in the prereg and in every run's provenance.
4. **Exchangeability blocks.**
   - **Route r ∈ {OPEN, TARGETED}:**
     - OPEN = the video appears in the logged keyword/community search results (`search_log`), whatever route found it first.
     - TARGETED = found only by the directory sweep or a rejection hunt.
     - The Curator records r per video.
   - r is stored in `data/sealed/`, never in the manifest. The analyst gets only an opaque, seeded-hash block code.
   - **Block** = merged era × r.
     - The Curator applies the merge on **total** counts. A cell with fewer than 6 videos merges with its neighbour era **within the same r**, never across r.
   - Every permutation uses these blocks:
     - H1 labels;
     - H4 rows of R;
     - H4b swaps;
     - per-parcel p;
     - Freedman–Lane.
   - Bootstraps are stratified by group × r.
   - r is **not** added to M0 or Q. It would put a label proxy into AUC(M0).
   - **At unblinding**, report:
     - the effective N (videos in label-mixed blocks);
     - the label × block table;
     - block-stratified (inverse-variance) effect sizes next to the pooled ones.

     If the effective N is below 20 per group, the verdicts are "inconclusive".
5. **Same-route sensitivity.**
   - OPEN only, with the same W, M0, Q, seeds and era blocks.
   - It sits outside Holm and follows the T3 survive/fragile rule.
   - Freeze it in the prereg before the Curator sweep finishes.
