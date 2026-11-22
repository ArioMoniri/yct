# Council, p4b_ref/v1 non-NAT build STOP: Referee

**Verdict on build-as-is: REVISE.** The STOP was correct: no rule was changed, nothing was substituted, no clip was uploaded and no TRIBE output exists. MOT, MOT_STAT, GREY_CTRL and FLASH stand unchanged. Every fix below is outcome-blind with respect to the reference predictions. The one thing we have seen is the Haar QC outcome, so no fix may be tuned to it. That rules out a tolerance, new seeds and exemplar changes.

## 1. LOC/LOC_SCR face QC: the rule is mis-specified (my own E9 / B18c)
- **Diagnosis.** B18c asked for no face *content* in body, place and scramble frames. D-071 (a) put that into practice as "regressor `face_area_crop_frac` = 0". That is the Haar FFC regressor, and nobody had measured its false-positive rate on noise. Phase scrambles are face-free by construction (random phase), so the 344 scramble hit TRs measure the detector, not the stimuli. The parameters are not the cause. T-LIC used the same `confounds.face` Haar settings at about the same scale (256-px crop; the video patch is about 256 px of 292). The real gap is structural. B3 and P2 were run pre-SHINE, because joint SHINE cannot run during sequential filtering, while the QC runs post-SHINE and post-x264. Conclusion: a QC rule that the frozen, correctly built stimuli cannot pass is a design defect of the rule. It is not a stimulus failure, and it is not an (h) redesign.
- **R1a, face_hit_frac.** D-071 (a) says "≥ 90% of LOC face-event TRs". Each clip has exactly 1 face TR, so a per-clip 0.9 threshold is vacuous; only a family-level reading gives the 90% a meaning. `stimulus_qc` applies it per clip. Pooled, the family scores 19/20 = 0.95 and passes. This is a code-to-text conformance fix. Because it was found after the outcome, put it in the owner D-entry below rather than fixing it silently.
- **R1b, amendment to D-071 (a) QC only; stimuli unchanged, (h) not consumed.** **Content check:** "no face" on every non-face LOC TR and every LOC_SCR TR, tested with the already-frozen T-LIC content detector, YuNet (frozen sha, score ≥ 0.5 as in B3/P2), on the decoded 316-px patch at the `face_fps` sample frames. **Haar result:** `face_area_crop_frac` on those TRs is reported descriptively, with the false-positive rate per family. It is disclosed as a specificity limit of the FFC regressor, which also bears on NAT and T1. **Haar sensitivity:** unchanged on face events (R1a). **Ordering:** freeze the rule before YuNet is run on any built frame. diag.json holds Haar only; keep it that way. **If YuNet fires on any TR:** STOP to the owner and go to D-071 (h). No further change to the QC rule. **QA must assert** that no frozen computation reads refclip `face_area_crop_frac`. A grep finds it only in confounds and refclips58.
- **Rejected:** new scramble seeds (seed shopping), a QC tolerance (a threshold chosen after seeing the data), dropping exemplars (barred by "no substitution"), and changing the Haar parameters (they are frozen for the analysis).

## 2. SPK/BURST/TALKFACE speech corpus
- **Status:** D-071 leaves it unspecified. SPK gates AUD (hard STOP), so the corpus is a stimulus definition. It needs an owner-approved D-entry; the council drafts it.
- **Content:** one corpus file: 60 SPK phrases of 2–3 words, 15 BURST sentences and 3 TALKFACE sentences; each set in a fixed primary order, followed by an ordered reserve list; common everyday English; excluded: proper nouns, numbers, and YC, startup, business, finance or tech words; also excluded: face, body, place and motion words, because the text path could otherwise drive FFC, PH or MT+ and contaminate (b) AUD > FFC.
- **Synthesis settings:** espeak-ng version recorded, voice `en-us`, rate 175 wpm, pitch 50, amplitude 100, no SSML.
- **Duration check:** speech span = first to last sample above −40 dBFS (a priori). It must fall within the family range (SPK 1.0–1.5 s, BURST 4–6 s, TALKFACE 1–6 s). An item that fails is replaced by the next reserve item, in order. Nobody listens to the output to choose items.
- **Balance:** 2-word and 3-word phrases are split equally across the even and odd halves, by a fixed assignment.
- **Freeze:** the file sha goes in `speech_corpus_sha256` before any synthesis. The builder guard already enforces this.
- **Open:** the TALKFACE cartoon-face generator is not specified either. It is descriptive only, but must be pinned in the same entry.

## 3. SHINE interpretation: council ratifies
Joint specMatch (keeps each image's own phase and DC) followed by lumMatch to 128/32, 2 iterations, rounding to uint8 at each step, is the faithful reading of D-071 (b) and of SHINE. Ratify it. The 16-px crop-overrun bound was written after the 2-px case was seen. It is acceptable only because the criterion is "identical pixels to the T-LIC numpy slice". A test should assert that.

## 4. Contact sheet (place_07 logo, body_03 jacket print): council, no action
D-075 replaced human judgement with frozen automatic rules, and P3 and B5 passed. If we excluded either image on sight, that would be the forking path. Record both as disclosed residuals in the v1 report.

## 5. BUG-044: council ratifies the workaround
The recovery is gated on content sha256 and is tested. Keep the frozen names that carry the URL query string, because renaming changes a frozen sha; it is cosmetic. Add a pre-freeze check that every `s3_key` exists in S3 with a matching sha.

## Owner vs council
- **Owner:** the D-entry for R1a and R1b; the speech-corpus D-entry, including TALKFACE.
- **Council-only:** SHINE ratification and the crop test (3); the contact sheet (4); BUG-044 (5); the QA assertion in R1b.
- **Forking-path risk:** highest in R1, because the Haar outcome is known. It is mitigated by moving to the already-frozen detector, freezing before any YuNet run, and disclosing the v1 Haar QC in full.
