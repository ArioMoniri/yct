# P1 cycle 2 — Neuroscientist (fresh context)

I reviewed at HEAD 2a4ef09; the code is that of cef030e. I did not read `data/sealed/`. All figures are aggregates over the wave-1 analysis set (`in_primary & qc_pass`, n = 53).

**Verdict: FIX (narrow).**
- P2 **downloads** may start now. They are also needed for D-047's `is_original_application_video` check.
- P2 **normalisation** waits for one fix, Q3 below (colour-matrix tagging, the same item as G-D032 G1/N4). Normalising earlier would mean a full re-run with new content hashes.

## Prior required changes for my role
No Neuroscientist review at P1 cycle 1 (none in reviews/phase_1/). Carried-over item touching P2: N4 (G-D032 c2). It is **NOT FIXED** for the P2 path: normalize/core.py:389 and 245-257 add no matrix or tag.

## New defects
**Q1 (major, P2b). Unknown language versus a model hard-coded to English.**
- `language` is `UNKNOWN` for 22/53 rows (en 29, en-US 2).
- WhisperX runs with `--language en` (config.yaml:110; transcribe/core.py:122-123), and TRIBE's text path is English-only.
- A non-English pitch would yield a forced-English transcript. Those garbage Llama features would enter M1 and the H2 language composite.
- There is no label-free language-ID step anywhere in src/.

**Q2 (major, planning). Duration versus BUG-018 and T1 eligibility.**

| Duration | Videos (of 53) | Consequence |
|---|---|---|
| > 70 s | 20 (38%) | T2 is broken until BUG-018 is fixed |
| < 58 s | 7 | Shorter than the T1 trim |
| < 50 s | 1 | Fails the T1 tail rule (W_end + 5 = 50 s) before any silence trim |

- Median 65 s, range 43–160 s.
- After black/silence trimming, T1 N may fall below 53. If W = [7, 47) is adopted as a sensitivity (P0 L1), it needs ≥ 52 s.
- Effective T1 N is needed before D-037 sizing.

**Q3 (major, blocks normalisation). The P2 output inherits or omits the source colour tag.**
- I tested ffmpeg 6.1 with the exact P2 chain:
  - untagged → `unknown`;
  - smpte170m → smpte170m;
  - bt709 → bt709.
- So the decoding matrix TRIBE applies varies by source. That makes it platform-correlated: 46 youtube, 6 linkedin, 1 web, and `platform_nonYT` is an M0 covariate.
- It also mismatches the forced-BT.709 crop statistics and T3.

**Q4 (minor). Burned-in letterbox/pillarbox bars are not detected.**
- tribe_requirements.md:40 notes that bars enter the 256² crop.
- P2 pads nothing (config.yaml:19), but bars already in the source are not detected: no `cropdetect` or bar check in src/.
- Bars lower crop luminance and contrast, and change what V-JEPA2 sees, systematically by recording setup.

## Required changes
1. **Q3, before any normalisation:**
   - P2 encodes `scale=…:out_color_matrix=bt709:out_range=tv` plus `-colorspace/-color_primaries/-color_trc bt709 -color_range tv`.
   - Add a test that untagged and smpte170m sources come out as bt709 under ffprobe.
   - Record `src_color_space` per video in the normalisation log.
2. **Q1, before P2b:**
   - Add a label-free language-ID step (WhisperX/faster-whisper detect on the first 30 s of speech, pinned).
   - Rows with p(en) < 0.8 are excluded from T1 and logged.
   - Add a DECISIONS entry and a test.
3. **Q2, after normalisation and before P4:**
   - Report the T1-eligible N (post-trim) and the N for W = [7, 47).
   - Re-run the D-037 rank plan with that N.
   - Keep T2 marked BLOCKED (BUG-018) for clips over 70 s; do not truncate silently.
4. **Q4:**
   - Add `cropdetect` on the source.
   - Log `bar_frac_in_crop` per video as a label-free QC flag. Pre-specify that a crop bar fraction above 0.1 adds a covariate or exclusion through a DECISIONS entry before P4.
