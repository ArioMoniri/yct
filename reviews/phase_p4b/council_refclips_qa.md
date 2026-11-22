# Council (QA): p4b_ref/v1 non-NAT build 1 STOP. Verdict: REVISE
Read: refclips_build_v1.md; outputs/runs/refclips_v1_nonnat_build1/*; D-071 (a), D-075, d075_final.md, design_v2 §1.5; the four commits f03961c, 82aa000, 21a2239, 97af7ec; the stimulus_qc and confounds code; the contact sheet. No sealed data, labels or predictions were opened.
## 1. LOC / LOC_SCR QC
- **Was the detector mis-specified relative to T-LIC? No.**
  - Both use the same cascade at the same settings (`confounds.face` 1.1 / 5 / 0.08).
  - Both work at the same scale: the 316-px patch at 292/360 is about 256 px, the size of T-LIC's processed crop.
  - What differs is the input. T-LIC screened images before SHINE and never screened the scrambles. This QC runs after SHINE, on H.264 frames, with a grey surround.
- **a) Scramble hits (344/380 bad TRs) are a QC design defect.** A phase scramble has no face by construction. The zero-tolerance Haar rule was frozen without any a-priori estimate of Haar's false-positive rate on 1/f textures, so the frozen stimuli can never pass it.
  - Proposed D-entry amending D-071 (a), with no threshold and nothing fitted:
    - hard check: `face_area_crop_frac` is identical in LOC and LOC_SCR on every non-event TR, so any false positive cancels in the (d) intact − twin readout;
    - hard check: a constructive test that each scramble has the intact image's amplitude spectrum and the seeded phase;
    - scramble and swap-scramble hits are reported descriptively. A swap hit at a face event biases FFC toward zero, so it is conservative.
  - Rejected as forking paths: new seeds (a search until QC passes); any tolerance (it would be fitted to the observed 0.0309); a detector picked after seeing the result.
- **b) Intact body/place hits (10 TRs, 8 clips) and face_00 missed.** D-075 already pre-specifies this case: "post-SHINE QC failing for an image is a STOP to the owner; no replacement is drawn." The owner decides.
  - QA recommends accepting with disclosure, because the FFC kernel uses face events only (K1).
  - Before the owner decides, run one descriptive check: overlay the Haar boxes on those frames and run the already-frozen YuNet 0.5 (B3/P2) on them. A real face found there is a true failure.
- **c) face_hit_frac is mis-implemented.** There is one face TR per clip, so the per-clip "≥ 90%" check is in fact 100%. The D-071 (a) text reads as pooled over "LOC face-event TRs"; pooled, the result is 19/20 = 0.95, a pass.
  - Forking-path flag: this reading is chosen after seeing the result. It is defensible only because the per-clip reading makes the 90% figure meaningless. Log it as a fix of the code to match the frozen text, and disclose it.
- **d) QC coverage gap (blocking).** `stimulus_qc` checks only the LOC face rule and the MOT ratio. Missing from the built-mp4 QC are these §1.5 checks (included by D-071 (a)): MOT/LOC luminance and contrast within 1%; MOT motion at static level outside events, with no event in the static twin; FLASH `luminance_change` at the events only; and, for every family, "no other regressor moves". They exist only as unit tests on frames before encoding, so the reported MOT, FLASH and GREY passes are partial. Implement these checks before any rebuild.
## 2. Speech corpus (spec, mirroring D-071 (b))
- **Source:** one frozen public-domain text source; QA suggests the IEEE/Harvard sentences. The owner picks it, as with Wikimedia for images.
- **Ordering and filtering:** ascending sha256(text), plus a frozen exclusion lexicon for YC, startup, pitch and finance terms.
- **Synthesis:** espeak-ng pinned, `en-us`, default rate, pitch and amplitude (no free number).
- **Selection:** a measured duration window per family:
  SPK: the first 60 three-word leading spans (two-word if three runs over 1.5 s) in 1.0–1.5 s; BURST: 15 sentences, or two joined, in 4–6 s; TALKFACE: the next 3 in 1–6 s. Items are distinct across families; if the source runs out, STOP.
- **Freeze:** the file's sha goes to `speech_corpus_sha256`, frozen before any synthesis is heard.
- **Also unspecified:** the TALKFACE face generator (it also needs the face QC from item 1).
## 3–5. Council-only
- **3. SHINE:** ratify as built, together with the a-priori 16-px crop-overrun bound (21a2239). SHINE must never be changed to make the QC pass.
- **4. Contact sheet:** place_07 (logo) and body_03 (print) passed the frozen P3 and B5 OCR rules. D-075 replaced human judgement with those rules, so a human veto now would bring the superseded judgement back. Take no action and disclose both. body_17's crop shows mostly torso and legs; B2 passed, so it is noted only.
- **5. BUG-044:** keep the content-sha workaround. Add a read-back check that each uploaded object's sha256 equals the manifest's. Do not rename the frozen names; disclose the query-string suffix. Fix `finalise` with a test.

## Who decides, and in what order
- **Owner:** item 1b (the D-075 STOP clause); the speech text source and the TALKFACE generator; acknowledgement of the post-hoc D-071 (a) QC amendment.
- **Council:** 1a, 1c, 1d, 3, 4 and 5.
- **Order:** commit the D-entry and the full QC code with tests, rebuild once, then run QC. Any failure is a STOP, with no second amendment.
