# Council D-085 part 2: watchdog
Reviewed: d085_part2.md; 986b773 ba50c76 8754ba5 62c3806 5b34a1c 17c07d1. Not read: sealed data, labels, transcripts, Harvard texts, outputs/ predictions.
Verdict: REVISE. Nothing blocks on design. The items below are fixes to the record and the code, to land in the part-2 freeze commit.

## Rulings
1. **T-ENV filter (Butterworth 4, zero-phase sosfiltfilt): acceptable. Disclose it; no amendment.** R-ENV left the filter family and order open, and this choice fills that gap without contradicting R-ENV. It is outcome-blind: no corpus audio exists before the corpus freeze, and the envelope is descriptive only (refclips_qc85 never gates on it). However, the module was frozen (62c3806) before the council ratified it. The DECISIONS entry must name it as an author-filled detail, frozen before ratification and ratified now. The council may not change the filter after it has seen any envelope.
2. **espeak-ng 1.51 pin: ratified, with one fix (B1).** The binary, lib and data-tree shas, the 22050 Hz rate and the determinism check are sound. But `engine_pin` is only read by the schema and a config test. Synthesis does not check it.
3. **Wav2Lip weights: (b) plus Wav2Lip-SD-NOGAN.pt. (c) is rejected.** The non-GAN choice follows the 3-2 council vote; I dissented at D-085 and accept it. I prefer the authors' own code and weights pair to a loader we write ourselves. Conditions:
   - Pin the upstream commit by sha. Re-hash its README and licence; they must still say non-commercial and research use.
   - Record the `inference.py` diff from bac9a81 in the private log, and confirm the s3fd sha is unchanged.
   - Fallback to (a) is allowed only if that commit cannot load the archive on the synthetic fixture. Decide this before any real-face run, and record which path was used.
   - Freeze `weights_sha256` (7ab92491…8999) in the part-2 commit itself. It is already known, so there is no reason to defer it.
   - The change of the `weights_file` schema literal is a disclosed amendment of D-085 (e).
4. **TALKFACE face: part 2 must name it.** D-087 authorises the continuation only for a LOC category short of passes in the screen. TALKFACE is a different consumer, so it needs its own authority, which the part-2 entry should state:
   - `--target face=21`, then +1 per s3fd/Wav2Lip skip, with at most 5 skips and then a STOP (the existing rule);
   - the same frozen v4 rules; appended rows committed with existing rows byte-identical before any Wav2Lip run;
   - this budget is separate from D-087's 20 per category;
   - snapshot exhaustion is a STOP to the owner.
5. **Freeze order: accepted, with two changes.**
   - The corpus sha is a part-2 key, so freeze it in the same commit.
   - The weights choice and sha, plus the face-continuation rule, are also frozen in that commit.
   - The order is then: freeze commit → texts and sha check → selection, with the kept-id list committed before any build → face continuation committed → build plus frozen QC → clip manifest sha.

## Blocking (before the part-2 freeze or before synthesis)
- B1: `speech_corpus` synthesis must verify the binary, lib and data-tree shas against `engine_pin` and fail closed, with a test. Freeze `engine_pin` with `speech`.
- B2: The DECISIONS part-2 entry must carry the T-ENV disclosure (ruling 1), the weights amendment (ruling 3) and the named TALKFACE continuation (ruling 4).
- B3: The (b)/(a) loader is checked on the synthetic fixture only, before the frozen build.

## Owner questions
None. The licence and use questions are already covered by the owner's rulings (non-commercial, internal only).
