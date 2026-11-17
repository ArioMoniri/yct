# Phase 0 — Neuroscientist review (fresh context)

Reviewed at b83e6c2 (smoke run, metrics, latency CSVs). I did not read `data/sealed/`.

**Vote: GO for P0.** The measurements are valid. Fix the six defects below before P4b lock; none invalidates P0.

## Interpretation
- **Lag 0 TR in output time.** Output t corresponds to BOLD at t + 5 s. On the control-subtracted visual course:
  - The rise starts at output 11 (BOLD +1 s), plateaus over 13–18 (BOLD +3…+8 s) and has decayed by 22 (+12 s). A broadened canonical HRF.
  - The "peak at 15" is the maximum of a flat plateau (0.092 vs 0.085 at 18). The half-max centroid is about +1.5 TR, so L is uncertain by ±2 TR.
- **The pre-onset rise is *not* from the 4 s video context**, which looks backward and explains only the post-onset plateau. It comes from the bidirectional transformer plus the 5 s offset: the expected early HRF limb, not "non-causal leakage" (tribe_requirements:88/163).
- **The auditory ROI responds to the flash more than to speech** (0.20–0.29 vs 0.25). Both clips are silent, so this is global or cross-modal:
  an out-of-distribution black→white step, or learned audiovisual co-occurrence. The speech spike also appears in V1 (+0.08). This threatens P4b(b) selectivity.
- **Single-TR speech spike, followed by an undershoot (26–30).** It is consistent with the summed Word features, which exist only in bins 25–26. Per-chunk audio z-scoring over silence (known issue #2) confounds it further; it is not a usable auditory IR.

## Defects
**P1. The P4b IR is mis-specified** (v2.md:371, "shifted by L and convolved with the P0 IR").
- The IR already contains the timing, so the shift double-counts it if L ≠ 0.
- The auditory IR is text-driven and measured in non-P4b ROIs.
- **Required:**
  - Use one kernel per ROI: the control-subtracted course over output −4…+8, peak-normalised, with no separate shift.
  - Re-derive it on CPU from the pod `.npy` files in the exact P4b ROIs (V1–V3 = 1,148 vertices, A4∪A5 = 223, FFC = 104).
  - For AUD, add a 4–6 s speech clip on a noise bed: audio-only, text-only, and both.

**P2. The localiser read-out time is ambiguous** (v2.md:381, "t = 5 s").
- In our output clock, onset + 5 gives about half the visual peak and roughly 0 auditory.
- **Required:** pre-specify the mean over output onset + [−1, +3]; check paper §5.9's clock.

**P3. The W tail is too short.**
- The raw courses show a stimulus-independent end-of-clip rise over the last ~4 TRs (auditory −0.12 → +0.36 over TRs 36–39).
- Start TR 5 stays correct.
- **Required:** change `window.min_tail_s` from 2 to 5, recorded in DECISIONS.

**P4. The Destrieux latency ROIs are adequate for timing, not for P4b.**
- Visual (655 vertices) = 56% V1, 18% V2, 12% ProS.
- Auditory (130 vertices) = only 25% A1; the rest is belt.
- **Required:**
  - Repeat the latency on the HCP P4b ROIs (P1).
  - Ticket the ROI id lists in config; they are still missing.

**P5. Extend the ENH-002 dry run.**
- Evaluate the controls on per-TR spatially standardised maps (the form the hypotheses use) as well as raw maps. Check whether the flash response in A4∪A5 survives standardisation.
- The V1 flash amplitude is about ¼ of the prediction SD, which supports the risk that the V1–V3 motion control is weak. Keep the pre-lock MT+ fallback.
- Add a talking-face reference clip; it was skipped in P0.

**P6. The A10 (ENH-004) is acceptable only with conditions.**
- "No numeric differences" is assumed, not measured. Ampere sm_86 fp16 kernels will differ by about 1e-3, the same order as the measured drift (3.6e-3).
- **Required, in DECISIONS:**
  - (a) one GPU type per analysis, never mixed in a way correlated with group or processing order;
  - (b) 3 videos extracted on both the A100 and the A10, with max abs diff ≤ the BUG-006 tolerance and r > 0.9999;
  - (c) a 58 s clip and a >100 s clip run on the A10 with VRAM logged (13.4 GB was measured only on ≤40 s clips);
  - (d) GPU type recorded per video.

## Required before P4b lock
P1–P6, plus reword "non-causal leakage" and report centroid/FWHM in tribe_requirements.
