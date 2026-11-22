# Council, D-085 draft (p4b_ref/v1): Watchdog review
Verdict: **REVISE (minor).** I checked the anti-forking order. The pre-step was done first: 11507d4 holds the build-1 sha256s, committed before any D-085 text in 9a0623c/3acc014. Stimuli, seeds, detectors and thresholds are unchanged, and the §9 step-2 sha-equality STOP makes "byte-identical" testable. Read: d085_draft.md, my prior review, those 3 commits and speech_corpus_v1.json. I read no sealed data, labels, transcripts or predictions.
## What is right, and three conditions
- The amendment is post hoc but blind to the reference outcome, and it is disclosed (`post_hoc: true`). It adds a gate it did not tune (YuNet at its frozen 0.5 / 640 / B3-P2 settings) and leaves no tolerance knob. I accept it. YuNet's false-positive rate on scrambles is also unmeasured, so this may STOP again. That is the correct, pre-specified outcome. A second amendment is barred.
- C1. In the freeze commit, assert that YuNet has never run on any built frame: no YuNet output exists under outputs/, and diag.json holds Haar only.
- C2. The D-085 text must say that the owner ruled the family-pooled face_hit reading. Under it, 19/20 passes and only pooled; per clip it fails. face_00 is disclosed.
- C3. The rebuild sha check (§9.2) runs before YuNet QC, in the same command, and any mismatch is a STOP.
## Open choices: one recommendation each
- **(a) Harvard licence.** Usable, but the "public domain" premise is wrong as stated, so re-document it.
  - IEEE Std 297-1969 appeared in 1969. US works from 1964–77 renewed automatically (1992 Renewal Act), so the "renewal not checked" route does not apply. If the standard carried a notice, the compilation is likely in copyright to about 2064. (I web-searched and found no authoritative statement either way.)
  - Individual short sentences are not copyrightable. Our use is non-commercial research of a widely re-published test list, so it is low risk as fair use.
  - Record it as: "copyright status of the 1969 compilation not cleared; not asserted public domain; used for non-commercial research; origin Harvard PAL (Egan 1948)". Put this in LICENSES.md and the report. Keep the raw-page sha. The full 720-sentence text is in the corpus file at 3acc014. Whether it may be redistributed in a public repo is the owner's call (owner question 1). Determinism does not need it: list/item ids plus text sha256 and the raw-page sha are enough.
- **(b) §7 rate.** Adopt **(ii): SPK uses 3-word leads only, at 175 wpm.** Fix it before the corpus freeze.
  - Option (i) is close to a certain STOP. A failing 2-word slot stays a 2-word slot, and about 0.69 s is far below the 1.0 s floor, so that slot drains the 410-item queue. That is a foreseeable defect, not a risk.
  - Option (iii) breaks BURST. Two Harvard sentences are about 16 words, which at 120 wpm is about 8 s, above the 6 s ceiling. It would also re-open an owner-approved parameter.
  - Option (ii) stays inside the approved rate and the duration gate. Drop `spk_words_rule` and disclose that the design_v2 2/3 balance is dropped, along with the reason.
  - No synthesis or "test" timing before the freeze, not even on excluded sentences: that would be tuning.
- **(c) T-ENV.** It blocks SPK/BURST only, not the visual rebuild.
  - Gate constructively: the wav equals the bed outside the events, and the trimmed corpus utterance sits sample-exact at the logged onsets. Video identity to GREY_CTRL stays as drafted.
  - Report the `speech_envelope` event/non-event contrast descriptively, with no threshold. Bed replacement at matched RMS makes any a-priori threshold a guess, and a threshold fitted later is tuning. T-ENV code is frozen before any speech clip is built.
- **(d) Twin identity.** Gate on the rendered uint8 frames, as drafted.
  - Report decoded max|Δ| outside the windows, and decoded-vs-rendered at event mid-frames (§3), descriptively only.
  - Compute them after the QC freeze. They never gate and no x264 tolerance is ever set.
- **(e) Wav2Lip.** Acceptable for this non-commercial study, on these conditions:
  - Pin `wav2lip_gan.pth` (the README default, so there is no choice to make).
  - The weights and s3fd mirror stay in the private S3 bucket and are never committed or made public. Commit only the shas and the README sha.
  - The TALKFACE clip is sent to TRIBE only. Disclose the research-only licence and the LRS2 provenance in the report.
- **(e2) Face rule.** Accept the 21st face pass: outcome-blind, and disjoint from the 20 LOC faces. Add two rules a priori. If s3fd or Wav2Lip finds no face, or the D-071 (b) licence fails, take the next pass in log order. Log the reason, with no visual review, and STOP after 5 skips. The clip makes a real, identifiable person appear to say words they never said. CC licences do not grant personality rights, so the clip is never published, and no stills appear in the public report (owner question 2).
## Blocking before the freeze
1. Re-document the licence, (a).
2. Adopt (b)(ii) in config and tests, and re-set the corpus sha.
3. Write the (c) constructive gate and the T-ENV ordering into D-085.
4. Write the (e2) fallback and the non-publication of TALKFACE into D-085.
5. C1–C3.
6. If TALKFACE runs as its own session, raise `main_campaign_plan_usd` by $3.48 before the next NAT projection.

## Re-sign-off (2026-11-22): D-085 v2 + addendum fd020e7, and D-086. Verdict: **APPROVE**
Read: d085_v2.md + response matrix, d1fc0d1 2374d77 fd020e7 2e3fe52 0f8e19a 1a3cff7 0efb08d, DECISIONS D-086, ROADMAP R-11, synthesis.md. I read no sealed data, labels, transcripts or predictions. `pytest tests/test_guards_frozen_config.py tests/test_fixnorm_p4b.py tests/test_d085_council.py`: 50 passed.
- **My cycle-1 items are all closed.** (a) The licence is re-documented and the corpus is hashes-only after the history rewrite. (b)(ii) SPK is 3-word only and `spk_words_rule` is gone. (c) The constructive gate is in place and T-ENV runs before any speech build. (e)/(e2) TALKFACE is internal only, with the pinned weights, a private mirror and the face fallback (5-skip STOP). C1, C2 and C3 are done. TALKFACE is in the projection. Owner Q3 "keep it broad" closes Neuro B1, and the gate is not narrowed.
- **The S-22 decoded-fingerprint rebuild check is accepted.**
  - It does not weaken C3. wav/tsv must still match byte for byte. An mp4 passes only on byte equality or on decoded yuv420p+s16le equality against a record taken from the verified build-1 files (0 byte mismatches). A missing record fails closed, and the check still runs before YuNet.
  - All reference frames are grey with neutral chroma, so bt601 and bt709 give the same RGB. Equal decoded YUV therefore means equal TRIBE input.
  - Any decoder difference across ffmpeg builds can only cause a false STOP, never a false pass.
  - Non-blocking: rebuild on the recorded pod ffmpeg (6.1.1-3ubuntu5) and log that version beside the result. Also log the ffprobe nb_frames, r_frame_rate and colour tags descriptively, because the decoded sha does not cover timing metadata.
- **D-086 is accepted.**
  - I checked FIX-NORM-0 key by key. Every key equals its value at b24fc1c, 4db5895 or 976e8ab, so the freeze is genuine and not a re-write. The two new keys are frozen one commit after the commit that set them.
  - The 10% loudnorm rule was written in synthesis (585cfd1) before the count. 3/52 = 5.8% is a pooled, label-free stimulus count, and sensitivity-only is the correct pre-set consequence.
  - The span trim, the polyphase resample and the single M-12b path are test-first and pass.
- **Drift term:** my dissent stands but does not block, since it is the owner's pre-run ruling.
  - Non-blocking: correct "only makes PASS harder" in D-086 and in the report. An added nuisance column can raise a partial r as well as lower it. The real safeguard is "fixed pre-run, never extended after a FAIL".
  - Non-blocking: pre-declare now that the intercept-only partial r will be reported descriptively.
- **No blocking items.** Part 1 may be frozen, including `build1_decoded_sha_record`. Part 2 stays gated on T-ENV and S-23/S-24.
