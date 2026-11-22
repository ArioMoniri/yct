# Council: neuro (TRIBE v2 / encoding models) on the normalisation inventory

Scope: does each transform match what TRIBE v2 expects at input (V-JEPA2 / w2v-BERT / Llama) and in its output space
(fs5, 1 s TR, relative z-units)? Verified against tribe_requirements.md, normalize/core.py, features/networks.py,
tribe_run/enh002.py, controls/kernels.py, refclips58.py, config.yaml, ROADMAP.md. Firewall D-063 B2 respected.
Own check: ffmpeg 6.1 decoding a bt709/tv-tagged clip to rgb24 with no options (moviepy's path) equals an explicit bt709
decode; bt601 differs by up to 26 codes on saturated green. So S-09 tagging is what makes TRIBE's decode correct
(M-02: repeat the test on the pod's imageio-ffmpeg binary).

## Correct and needed (keep)
- S-03/S-04 (58 s): one Audio + one Video chunk keeps each T1 clip in one 100-TR window and one w2v-BERT z-score chunk;
  the single most important input normalisation.
- S-05: CFR 30 fine (V-JEPA2 samples 16 fps by time). Sub-16 fps sources give duplicated frames, i.e. zero motion in
  V-JEPA2's 2-frame tubelets, so the low-fps flag and S-LOWFPS are the right handling.
- S-06: no padding is the essential part (bars enter the 256² crop); upscale to 292 is redundant for TRIBE but harmless.
- S-09/S-10/S-11/S-12/S-16/S-21/M-06: consistent, tagged and pinned; removes TRIBE sidecar and cache hazards.
- S-19 (T3 on gamma-encoded values): not a flaw; V-JEPA2 consumes gamma-encoded RGB. Disclose, don't fix. M-07 keep.
- M-10/11/13/14/15/16/17/21/22 verified in code: the medial wall is predicted, so it must be masked; the z-score runs over
  non-medial vertices only; spatial_sd and G use raw cortex; every non-medial vertex has a Yeo label, so the exact rank-6
  dependency makes Limbic the correct reference.
- M-12 (per-TR spatial z): needed. Each vertex's 0 is its training-session mean. The per-TR cortical mean is mostly
  stimulus-driven global gain, not physiology, so removing it is a modelling choice and G is the right counterweight.
  State that H1/H2/LOC are compositional (where, not how much).

## Fix
- S-14 (major): linear loudnorm is a TRIBE no-op (chunk z-score), but dynamic fallback compresses the within-chunk
  envelope TRIBE sees. Fallback is likely common: gain = −23 − I_speech, and quiet speech over music hits TP −1.
  - Count `loudnorm_mode = dynamic` (a label-free QC count).
  - If > 0, pre-state an S-AUDIOLINEAR sensitivity excluding those clips.
  - Wave 2 keeps the same rule. If the count is large, one DECISIONS entry (capped pure gain + flag, both waves, pre-outcome).
- M-12b (major): enh002.standardise (SD 0 → /1, medial wall not NaN, no finiteness check; enh002.py:87 feeds the K-check).
  Replace it with networks.spatial_standardize, and pin the not-yet-written KernelInputs.d_std producer to M-12, with a test.
- M-20 (blocking for H2 at P6): no key, no code. Add `features.h2_areas` (hemisphere-explicit; 44/45 left only) as a
  vertex-weighted mean on the standardised W-map (as M-15), then freeze it. State why STSda is excluded (paper STSv = va+vp).
- S-07/S-08 (major): D-005 (neuro) promised a crop-coverage covariate and nothing consumes it. In-crop confounds measure
  what V-JEPA2 sees, not the framing that decides what lands in the crop, and aspect tracks platform/route.
  - Add `crop_outside_area_frac` as one linear M0 term (label-free; constant → 0).
  - Drop the separate 9:16 stratum (N too small); keep the D-071(i) aspect negative control.
- S-23/S-24 (major): before placement, the SpeechProvider must:
  - trim to the −40 dBFS span;
  - compute RMS, length checks and uniform word times on that span;
  - resample 22.05 → 48 kHz band-limited (soxr/polyphase), not nearest-sample (S-25).
  The RMS-matching rationale is right: chunk SD is what w2v-BERT normalises.
- A-18 (major): within-W trends (Llama context build-up, onset transients) inflate partial r. Add a Legendre-1 drift
  term to `controls.partial_out` (1 df of 40).
- A-21 (major): TRIBE never sees absolute level. Compute the envelope on the chunk-z-scored 16 kHz waveform
  (|hilbert| → 0.5 s bin mean → 1 Hz), so P4b(c) between-video r is not just post-loudnorm level and speech_frac.

## Clarify
- M-04/M-14 start: W start 5 is exactly the minimum (5 s offset + 4 s V-JEPA2 look-back). Read how neuralset video.py
  pads before t = 0 and record it.
- M-14 end: 50–58 s clips leave 5–13 empty TRs in the bidirectional 100-TR window. Add a tail-invariance check: NAT
  clips truncated at 50 vs 58 s must have W-mean reliability ≥ 0.99. Complements S-T1SHORT.
- A-11 M0b: use TRIBE's layers [0.5, 0.75, 1.0] and the same 256² crop, or "beyond generic encoder" compares different inputs.
- S-13: speech_frac measures sound activity, not speech. Relabel it, or use WhisperX word coverage, before the Q freeze.
- A-01: scene cuts on the full frame are acceptable (cuts are global). Disclose, or recompute in the crop (low priority).

## Remove or demote
- S-18 q480: no consumer, and V-JEPA2 discards > 292 px anyway. Drop it from the P2 DoD. rms_db: keep, low value.
- S-15/S-17: QC-only; v2.md and the ROADMAP should not call them confounds. S-22 (minor): add color_tags() to ref clips.
