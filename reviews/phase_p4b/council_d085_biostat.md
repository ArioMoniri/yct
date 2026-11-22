# Council, D-085 draft (p4b_ref/v1): Biostat
**Verdict: REVISE (minor).** I read d085_draft.md, my prior review, 11507d4 / 9a0623c / 3acc014 and speech_corpus_v1.json, plus a web check of the Wav2Lip README and the Harvard-list copyright position. I read no sealed data, labels, transcripts or predictions. The owner chose "fix the rule", so my R = 10 re-seed proposal falls away, and I accept §1 as drafted. YuNet's false-positive rate on scrambles is unmeasured, so D-085 may STOP again under (h); that is a correct, pre-specified outcome. The pooled face_hit (19/20) is a rule reading, not an estimate. No interval or test is attached to it, and face_00 is disclosed. I support the referee's split freeze: `refclips_d085.qc` (§1–§3) now; the speech and TALKFACE keys in a second commit once (a)–(e) are settled.
## Open choices, one recommendation each
- **(a) Harvard licence: usable, but not as "public domain".** IEEE Std 297-1969 (doi:10.1109/IEEESTD.1969.7405210) is a 1964–77 US publication. Renewal for those years is automatic (1992 Act), so the "renewal not checked" gap is moot. If the standard carried a notice, the compilation is presumed © IEEE to about 2064. The web check (2026-11-22) found no licence or PD statement. The basis we can defend:
  - individual sentences are short phrases, not copyrightable (37 CFR 202.1(a));
  - the use is non-commercial research of a widely re-published test list;
  - at most 93 sentences are synthesised, reordered by sha256.

  Record in LICENSES.md and the report: "copyright of the 1969 compilation not cleared; not asserted PD". Before the freeze, the public corpus file keeps list/item/sha256 plus the raw-page sha. The sentence texts move to the private S3 mirror, verified against `raw_sha256`. The queue order needs only the shas, so determinism is unaffected, and the corpus sha is not frozen yet. 3acc014 already holds all 720 texts in git history; whether to leave that is owner Q1.
- **(b) §7 rate: pick (ii), 3-word SPK leads at the approved 175 wpm.** Drop `spk_words_rule` and disclose why the 2/3 balance went: no readout uses word count.
  - (i) is a foreseeable STOP, not a risk. A failing 2-word slot stays 2-word, and its ~0.69 s nominal span sits far below the 1.0 s floor, so it drains the queue.
  - (iii) breaks BURST: ~16 words at 120 wpm is ~8 s, over the 6 s ceiling.
  - (ii) keeps one synthesis rate across SPK, BURST and TALKFACE, so speaking rate never covaries with family or word count. (The referee's (iv), 96/144 wpm, is my second choice.)
  - Feasibility, from arithmetic only: 3 words ≈ 1.03 s nominal, at the floor, so suppose p ≈ 0.3–0.6. Needed draws ≈ 60/p + 30/p_BURST + 3 ≈ 100–260, against 410 in the queue. Exhaustion needs p ≲ 0.17.
  - Pre-specify no test synthesis before the freeze, not even on excluded sentences. Log the per-family pass rates for the report.
- **(c) T-ENV / envelope.**
  - **Gate (constructive):** the wav is sample-equal to the GREY_CTRL bed outside the logged utterance windows, and each window holds the trimmed selected utterance sample-exact at its onset.
  - **Reported only, fixed now:** per clip, event/non-event mean `speech_envelope` ratio and the point-biserial r with the event boxcar. There is no threshold: matched-RMS replacement makes any threshold a guess.
  - **Order:** T-ENV is implemented, tested and frozen before any speech build (§9.4). It does not block the visual rebuild.
- **(d) Twin identity.** Gate on rendered uint8 equality outside [o−4, o+8), as drafted. Report two quantities per clip after the QC freeze, never gating and with no x264 tolerance:
  - decoded max|Δ| and the fraction of differing pixels outside the windows;
  - decoded-vs-rendered max|Δ| at the event mid-frames (§3). Step-2 sha equality already gates decoder determinism.
- **(e) Wav2Lip.**
  - **Licence:** acceptable. The README restricts use to "personal/research/non-commercial", there is no LICENSE file, and the training data is LRS2.
  - **Distribution:** the code is cited, and only the shas (weights, s3fd, README) go in the public repo. The weights stay in the private S3 mirror.
  - **Clips:** they go to TRIBE only, and only numbers are published. Owner Q2 is whether stills or clips may appear.
  - **Weights:** pin `wav2lip_gan.pth`, the README default. A default is a non-choice and removes a fork. TALKFACE is descriptive, so the sync-accuracy edge of `wav2lip.pth` does not bear on any gate.
  - **Face rule:** accept the 21st face pass: outcome-blind, and disjoint from the 20 LOC faces. Add a priori: if the licence is not adaptation-permitting (CC0/CC-BY/CC-BY-SA, no ND), or s3fd/Wav2Lip misses the face on any frame, take the next pass in log order. Log the reason, with no visual review, and STOP after 5 skips.
## Blocking before the speech/TALKFACE freeze
1. Correct the §7 licence text and LICENSES.md, and move the texts out of the public corpus file, per (a).
2. Put (b)(ii) in config and tests, re-set `speech_corpus_sha256`, and add the pass-rate logging.
3. Write the (c) gate and report rules, and the T-ENV ordering, into `refclips_d085`.
4. Write the (e) weights pin, the face fallback and the TALKFACE non-publication into D-085.
5. The freeze commit re-asserts that no frozen computation reads refclip `face_area_crop_frac`, and that no YuNet output exists on built frames. Rebuild sha equality (§9.2) runs before YuNet QC.
