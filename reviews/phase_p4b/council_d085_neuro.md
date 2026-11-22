# Council, D-085 draft (p4b_ref/v1): Neuro review
**Verdict: REVISE (minor).** §1 to §6 match my refclips review. No reference output exists, and each rule below is fixed before any YuNet run, synthesis or Wav2Lip run. Read: d085_draft.md, my council_refclips_neuro.md, 11507d4 / 9a0623c / 3acc014, speech_corpus_v1.json (rules and source fields), config `controls.regressors`, design_v2 §1.4–§1.5. Not read: sealed data, labels, transcripts, predictions.

## Blocking
- **B1. YuNet gate scope (§1).** The draft gates YuNet on every non-face LOC TR and every LOC_SCR TR, which is about 95% scramble frames. YuNet's false-positive rate on SHINE 1/f scrambles was never measured, which is the same defect that sank the Haar rule. One false hit would be a STOP with no further change allowed.
  - Fix: gate YuNet only on the intact body and place event TRs (40 per family pair). Report YuNet on scramble TRs, but do not let it gate. Scrambles are face-free by construction, and twin identity (gated) cancels them in the (d) readout. This was my item 1 (ii)–(iii).
- **B2. The SPK/BURST envelope check must not wait on T-ENV, and must not gate on direction (§2).**
  - `speech_envelope` is defined as `hilbert_broadband_envelope_mean`. Speech replaces the bed at matched RMS, and speech has a higher crest factor than the Gaussian bed, whose envelope mean is about 1.25σ. So the mean envelope is expected to *dip* at speech events. "Follows the events" therefore has no a-priori sign.
  - Gate SPK/BURST now on structural checks: outside event windows the wav is byte-equal to the GREY_CTRL wav; event-window chunk RMS is within 1% of the control; the −40 dBFS span lies inside the event TR window; video_features equal GREY_CTRL.
  - Once T-ENV is frozen, report the event-locked `speech_envelope` change descriptively, with any sign allowed. Also disclose that with an RMS-matched design, the partial-out cannot explain SPK AUD.
  - BURST kernel ⊗ envelope (r ≥ 0.8, descriptive) must use each utterance's own pre-mix Hilbert envelope. The broadband mix envelope is near-flat or inverted, so it would make the test degenerate. Pre-specify this in D-085.
- **B3. Harvard list documentation (§7a).** "Public domain" is not established, so it must not be recorded as such. Details below.

## Open choices: recommendations
- **(a) Harvard licence.** A web check found no licence or renewal evidence.
  - US works published 1964–1977 had their renewal made automatic by the 1992 Copyright Renewal Act. So "not renewed" cannot make IEEE Std 297-1969 public domain, if it carried a notice. The sentences go back to Egan 1948 (Harvard PAL), whose status is also unverified.
  - Usable: single sentences are short phrases (37 CFR 202.1(a)). SPK uses only 2–3-word fragments. We use about 93 of 720 items, for non-commercial research. The list is used ubiquitously in speech science.
  - Document in LICENSES.md as "copyright status unverified; used as short phrases / fair use for non-commercial research; not asserted public domain".
  - Do not redistribute the compilation. Pre-freeze, the corpus file should hold (list, item, sha256) plus raw_sha256. Text is fetched and parse-verified at build time, with the raw page mirrored privately to S3. 3acc014 already put the full text in git history (see owner Q2).
- **(b) Speech rate (§7).** Keep 175 wpm. Pre-specify a duration-driven lead length that stays within the approved "2–3 words, 1.0–1.5 s":
  - k = 2 if the 2-word span is ≥ 1.0 s, else k = 3; keep the item iff its span is in [1.0, 1.5] s.
  - This drops the fixed alternation rule `spk_words`. Report the 2/3 counts per half descriptively; assignment by sha order is outcome-blind.
  - Rationale: for an impulse kernel the property that matters is acoustic duration, and word count was only a proxy for it. Function-word leads ("The", "A") make word-count estimates unreliable in both directions. Option (ii) can still fail at about 1.0 s. Option (iii) at 120 wpm moves 3-word leads to the 1.5 s ceiling, and it reopens an owner-approved rate.
  - Exhaustion remains a STOP.
- **(c) T-ENV.** Decouple, as in B2. T-ENV must still be implemented, tested and frozen before any NAT partial-out. It is not a prerequisite for building or gating SPK/BURST.
- **(d) Twin identity.** Gate on rendered uint8 equality outside [o−4, o+8), as drafted. That is constructive and avoids x264 inter-frame artefacts.
  - Report decoded max and mean |Δ| outside the windows, per frame, descriptively. Residuals add variance to intact − twin, not bias, and both arms are encoded with the same bit-exact flags.
  - Also report decoded-vs-rendered PSNR at event mid-frames (§3). No x264 tolerance gates.
- **(e) Wav2Lip.**
  - Weights: pick `wav2lip.pth`, not `wav2lip_gan`. The README rates it "highly accurate lip-sync", whereas the GAN version has "slightly inferior lip-sync". Mouth-motion timing is what drives MT+/STS.
  - Frame rate: run with `--fps 30` on the static face (the mel stepping is fps-parametrised). This avoids 25→30 duplication jitter.
  - Licence: the README restricts use to "personal/research/non-commercial", and the code licence has changed from MIT. Record the sha of the README and LICENSE.
  - Distribution: mirror the weights only to the private S3 bucket. Commit only the shas. Do not commit TALKFACE mp4s to the public repo. Reporting results in a research write-up is within the terms if the study is non-commercial (see owner Q1).
  - Disclose that the mouth is synthesised at 96 px with no head motion or blinks.
  - Face rule: the 21st face pass is approved as outcome-blind and disjoint. Add, pre-specified:
    - its licence must permit derivatives (no ND), and consent must cover altered forms;
    - if Wav2Lip's s3fd finds no face, take the next pass, logged, for at most 5 passes, then STOP. TALKFACE is descriptive, so this is a technical skip, not substitution;
    - disclose if its identity matches a LOC face identity in the source metadata.

## Owner questions
1. Wav2Lip and LRS2 terms are research and non-commercial only. Is this study and its public report free of any commercial use or sponsor? If not, drop TALKFACE, which is descriptive only.
2. The Harvard list is not demonstrably public domain. Should the council's restructure stand (index-only corpus file, documented as unverified), and should the full text added in 3acc014 stay in git history or be rewritten out?

## Re-sign-off (2026-11-22; D-085 v2 + addendum fd020e7, D-086)
**Verdict: APPROVE.** I read d085_v2.md, the response matrix, the §9 addendum, d1fc0d1 / 2374d77 / fd020e7 / 2e3fe52 / 0f8e19a / 1a3cff7 / 0efb08d, DECISIONS D-086, ROADMAP R-11 and the normalisation synthesis. tests/test_fixnorm_p4b.py and tests/test_d085_council.py pass (40). I did not read sealed data, labels, transcripts or predictions.
- **Owner rulings accepted:** hashes-only corpus with the history rewrite, SPK 3-word only, TALKFACE internal only, and the broad YuNet gate. B1 is closed by the owner's ruling. My risk note stands for the record: a YuNet false hit on a SHINE scramble now means a STOP, with no further amendment allowed.
- **S-22 decoded-stream rebuild check: sound.** The frames enter as `gray`, so U = V = 128. Changing the matrix from bt601 to bt709 therefore does not change any RGB value, and tv range is also the untagged default. `decoded_sha` decodes at native yuv420p plus s16le, so it ignores the tags while still covering every pixel and audio sample. The stimulus TRIBE sees is the same as in build 1. wav and tsv are still byte-exact, and a missing record fails closed. Non-blocking: decode the rebuild with the same pod ffmpeg 6.1.1-3ubuntu5 (the toolchain record). A decoder drift would fail closed, which is the safe direction. `rebuild_mismatches` only iterates over rebuilt clips, so a build-1 clip that was never rebuilt is not flagged. Assert that the two name sets are equal.
- **S-23/S-24 span trim:** correct, because the onset and word times now refer to the acoustic span. Non-blocking: at 175 wpm, trimmed 3-word spans near 1.0 s will fail the length gate more often. `pass_rates` logs this and exhaustion is still a STOP.
- **D-086:**
  - The FIX-NORM-0 freeze at b24fc1c (whisperx at 4db5895, control keys at 976e8ab) is right.
  - The Legendre-1 drift is appropriate for 58 s clips. It only makes PASS harder, and it fails closed when the design is rank-deficient.
  - The single M-12b standardisation path is right.
  - R-ENV is right: the z-step only rescales, and the 10 Hz low-pass suits a syllabic-rate envelope.
  - The loudnorm count of 3/52 = 5.8% is below the 10% bar, a rule set before the count, so the frozen mode is kept and those 3 clips go to S-QC sensitivity only. Approved.
- **Blocking items:** none.
