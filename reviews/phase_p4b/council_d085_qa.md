# Council (QA): D-085 draft. Verdict: REVISE (small; no redesign)
Read: d085_draft.md, my council_refclips_qa.md, 11507d4 / 9a0623c / 3acc014, speech_corpus_v1.json (sha e62b38e5… matches config), refclips_qc85.py, speech_corpus.py. No sealed data, labels, transcripts or predictions opened.
Checks: `pytest -k "d085 or speech or refclips"` 62 passed; `make guards` exit 0 (all 7 guards OK). R1b grep: `face_area_crop_frac` appears only in yct.confounds, refclips58/qc85 and the diag script, with no frozen-analysis reader.
My earlier items are covered: 1a (YuNet gate plus twin identity; Haar becomes descriptive), 1c (pooled face_hit, disclosed as post hoc), 1d (§1.5 checks), BUG-044 read-back, the order rule (freeze before YuNet), and the rebuild-equals-build1-sha STOP.
## Open choices (QA recommendation for each)
- **(a) Harvard licence.** The draft frames this wrongly: the test is not "was it renewed".
  - US works published 1964–1977 were renewed automatically (Copyright Renewal Act 1992). IEEE Std 297-1969 carried notice, so assume it is in copyright to 2064 as a compilation.
  - The individual sentences (about 8 words each) are not separately protectable. Our use (non-commercial research, under 100 of 720 used, no market substitute) is a strong fair-use case, and the list is widely redistributed (Columbia page, many speech datasets).
  - Usable. Record in LICENSES.md: "IEEE 1969, in copyright (compilation); used under fair use; not public domain", and correct the owner's "public domain" premise in D-085.
  - Republishing all 720 texts in the public repo is the one real exposure. That is an owner question (Q1). QA's default is to keep the file as is, since sha-of-text reproducibility needs the text.
- **(b) §7 speech rate: adopt (ii), 3-word SPK leads only, at 175 wpm, fixed a priori.**
  - 175 wpm is espeak-ng's default, so it is not a free number, and it is inside the owner-approved spec. Changing it is (iii), which is the owner's call.
  - (iii) at 120 wpm puts 2 words at about 1.00 s and 3 words at about 1.50 s, both on a gate edge. It is no safer.
  - (i) is a near-certain STOP. With about 5% of 2-word slots passing, 30 such slots × about 20 pops exceeds the 410-item queue.
  - (ii) needs about 60/p pops. Even at p = 0.25 that is 240 + 33 ≤ 410.
  - Disclose the dropped 2/3 balance as a deviation from design_v2, forced by the pre-registered rate.
  - Gate-adaptive word counts are rejected: they choose each item's word count from its measured duration.
  - Exhaustion remains a STOP. No calibration synthesis before the freeze.
- **(c) T-ENV.** Do not make the SPK/BURST gate wait on T-ENV. Speech at matched local RMS is meant to leave a broadband envelope nearly flat, so "envelope follows events" is the wrong pass criterion.
  - Gate constructively instead: (1) wav samples outside the event windows equal GREY_CTRL bit for bit; (2) the −40 dBFS span onset and offset of each inserted item equal the tsv onsets (±1 sample); (3) the video identity check, already in the draft.
  - `speech_envelope` is reported descriptively once T-ENV exists, and never gates.
- **(d) Twin identity.** Gate on the rendered uint8 frames, as drafted. That is constructive and correct.
  - Report the decoded max |Δ| outside the windows, and decoded vs rendered at event mid-frames, descriptively only.
  - No x264 tolerance: any tolerance would be fitted to build-1 decodes.
- **(e) Wav2Lip licence.** The README wording was verified 2026-11-22. There is no LICENSE file, only "personal/research/non-commercial", and LRS2 bars commercial use. That covers this study and a public academic report.
  - Conditions:
    - never commit or publicly mirror the weights (private S3 only);
    - publish the TALKFACE mp4 only as a hash in the repo, never the file;
    - label it as synthetic in the report;
    - cite the paper.
  - Weights: pick `wav2lip.pth` a priori (the README says it has the more accurate sync, and mouth motion is what TALKFACE probes).
  - Weight provenance: the official links are Google Drive, so record the URL, date and sha, and disclose that no author-published hash exists.
- **(e′) TALKFACE face rule.** The 21st pass is outcome-blind and disjoint from the 20 LOC exemplars. Accept it, and add two a-priori rules before the face-log continuation runs:
  - if s3fd or Wav2Lip finds no face, or fails, take the next pass (logged), at most 5 passes, then STOP;
  - Wav2Lip makes an identifiable person say words they never said. CC-BY covers copyright, not personality or publicity rights. Owner question (Q2): restrict to deceased or PD-only subjects, a rule set before the continuation runs?
## Blocking before the freeze
1. Amend the D-085 text and LICENSES.md for (a), and config `speech.spk_words_rule` for (b), with tests: 60/60 three-word leads; exhaustion raises CorpusStopError. Recompute the corpus sha only if the file changes (the rules block holds `spk_words_rule`, so it will).
2. Replace the open SPK/BURST envelope row in §2 with the constructive gate (c). Add unit tests.
3. Freeze `talkface.weights_choice: wav2lip` and the face-fallback rule (e′) in the D-085 freeze commit.
4. Add the decoded-diff descriptive outputs (d) to run_qc, marked non-gating.
