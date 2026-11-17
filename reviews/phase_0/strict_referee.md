# Phase 0 — Strict Referee (fresh)

Reviewed b83e6c2; no data/sealed/, no other reviews.

**Vote: GO for P1, conditional.** P0 DoD met (shape, TR, finite, VRAM, offline, latency); items 1–6 gate P4.

## Latency: what it implies

What the control-subtracted CSVs show:
- **Visual:** rises from t = 11–12 s to a plateau of 0.078–0.092 at 13–18 s for a flash at 15 s. That is about 4 TRs of backward leakage.
- **Auditory:** responds 0.20–0.29 to the flash, which is more than its 0.237 response to speech. The speech response is a single TR at 25 s, followed by an undershoot of −0.09 to −0.13. Visual shows +0.079 at 25 s.
- n = 1, no noise estimate; "L = 0" = peak-picking on a plateau.

What follows:
- **Claims.** The outputs are non-causal and smeared by ±4 s. ROIs are not modality-selective in raw units, and the speech response is probably carried by the Word/text features. This bars any timing or onset claim finer than about 5 s, and any reading of the T2 progress bins as event-locked. The W-averaged H1–H4 are unaffected in principle.
- **W.** W = [5, 45) stands. But the exclusion margin "W_end + 2 s" (v2.md:45) is thinner than the measured spread, and the raw auditory course rises at the last TR.
- **P4b (v2.md:369–381):**
  - **(a)** Convolving with the "P0-measured impulse response" (n = 1, OOD black screen, 2-word transcript) gives a text-spike kernel for speech. AUD could then pass through the text features, not acoustics.
  - **(b)** "Speech AUD > FFC" is at risk because AUD tracks luminance transients, and luminance is not among the partial-out regressors.
  - **(d)** "Response at t = 5 s" (v2.md:381) is ambiguous in output time. P0 puts the peak at lag 0–3 TRs. At onset + 5 the visual response has decayed to 0.045.
  - **Untested.** The talking-face clip was skipped, so no face or acoustic latency was measured.

## Determinism by caching

This is acceptable as a reproducibility statement: predictions are bitwise identical from archived, hashed features, and re-extraction drifts by ≤ 3.6e-3 (r = 0.999994, about 2.5% of one SD). It is honest only if three conditions hold:
- the features are archived durably;
- the drift is shown not to move inference;
- one extraction feeds every analysis.

## Defects
D1 BUG-003 open (run_clip.py:46–58; feature_cache.py:118). D2 drift ungated, no GPU re-run, ROADMAP.md:125 vs BUG-006, v2.md:366 open-ended, ENH-004 hardware switch. D3 P4b rests on n = 1 OOD impulse (v2.md:371, 374–377, 381). D4 P0 predictions unarchived outside pod.

## Required changes (v2.4.1, before P4)

1. **Close BUG-003:**
   - pin the three backbones at the §10 revisions;
   - run_clip sets `HF_HUB_OFFLINE=1`;
   - the backbone revisions are in `_revisions()`;
   - a no-network test.
2. **Determinism spec (v2.md:366, ROADMAP:125):**
   - the cached rerun must give max abs = 0;
   - fresh re-extraction of ≥5 videos is gated at ≤ 1e-2 and r ≥ 0.9999;
   - one GPU type for all P4 extraction (T1, T3, ablations), with ENH-004 decided once for the whole study;
   - M0b is read from the same FeatureStore.
3. **Prereg/P10 statement:** "Bitwise reproducible from archived features (sha256 manifest); re-extraction on identical hardware reproduces to ≤ X."
   - Add a sensitivity check: recompute H1/H4 with a second extraction of 10 videos, and show the change is far below the permutation SE.
4. **P4b:**
   - **(a)** Replace the n = 1 kernel with "regressor shifted by L, mean over a centred 5-TR window", or with per-modality kernels from ≥5 reference clips, fixed before P4.
   - **(a)/(b)** Add luminance-change energy as a partial-out regressor.
   - **(a)/(b)** Also pass AUD on the audio-only ablation.
   - **(a)/(b)** Use the spatially standardised maps.
   - **(d)** Define the readout as the mean of output lags 0–3 TRs.
   - Run the ENH-002 dry run with a talking-face clip, 5 flashes and 5 speech bursts, so latency has a CI.
5. **W:** change the exclusion margin to W_end + 5 s (v2.md:45; ROADMAP:117).
6. **v2.md §1, add:** "TRIBE predictions are temporally non-causal (≈4 s backward leakage, P0); no within-video timing claims finer than 5 s."
7. **Archive** the P0 npy files, caches and clips with a sha256 manifest. Record the location in §10.
