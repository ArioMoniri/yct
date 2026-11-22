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

## Re-sign-off (D-085 v2 + addendum fd020e7; D-086). Verdict: APPROVE
Read: d085_v2.md, d085_v2_response.md, git show d1fc0d1 2374d77 fd020e7 2e3fe52 0f8e19a 1a3cff7 0efb08d, normalization_audit/synthesis.md. No sealed data, labels, transcripts or predictions were opened.
Checks: `pytest -k "d085 or speech or refclips or d086 or norm or kernel"` gives 194 passed. `make guards` exits 0 (76 frozen keys unchanged).
- **Cycle-1 blocking items 1–4: closed.**
  - (1) Licence wording and `spk_words: 3` are in place. Hashes-only corpus with the history rewrite, per the owner.
  - (2) `speech_gate` is constructive on the rendered 48 kHz audio.
  - (3) `wav2lip.pth` and the face-fallback rule are in the part-2 keys. TALKFACE has `publish: false`, enforced by the schema.
  - (4) `twin_decoded` and `decoded_vs_rendered` are reported with `gating: false`.
  - The owner's Q3 ruling (keep the YuNet gate broad) closes Neuro B1.
- **S-22 decoded-stream rebuild check: sound.**
  - `decoded_sha` hashes the raw yuv420p and s16le streams, so no RGB matrix is involved.
  - The frames are `gray` with neutral chroma, so the bt709/tv tags cannot change what a tag-aware reader such as TRIBE decodes.
  - Local test with ffmpeg 6.1.1: adding the tags changed the mp4 sha but left the decoded sha identical.
  - The 2e3fe52 record covers all 79 mp4 files. Its equal-sha groups (flash 0/1/4, flash 2/3, grey_ctrl 0/1) are the same as the byte-sha groups in build1_sha256.json. A missing record fails closed (tested). wav and tsv are still compared byte for byte.
  - The check is weaker than byte equality only in the container metadata, which the tags change by design.
- **D-086: sound.**
  - FIX-NORM-0 freezes are pinned in tests and the guard reports them unchanged.
  - The drift term is pre-run, only tightens the gate, and fails closed on rank deficiency or non-finite input.
  - S-23/S-24 span trim is tested, including duration equals span and the BS.1770 reference value.
  - M-12b is held to a single standardisation path by AST tests.
  - The loudnorm count of 3/52 = 5.8% is under 10%, so it is a sensitivity analysis only.
- **Non-blocking:**
  - (a) Pin the sha256 of `build1_decoded_sha256.json` in the part-1 freeze commit. Freezing the key fixes only the path, not the file content; the same applies to build1_sha256.json.
  - (b) `rebuild_mismatches` silently skips a rebuilt clip that has no build-1 entry. Add a STOP for that case.
  - (c) Add a real-ffmpeg test that the tags leave `decoded_sha` unchanged.
  - (d) List the 3 dynamic-loudnorm clip ids for the S-QC sensitivity (pod-side). Disclose that the Q2 rule and the count landed in one commit.
  - (e) Pre-existing ruff I001 (import order) in scripts/refclips_build.py:31-36. Fix it with `ruff --fix` in a separate commit.
