# p4b_ref/v1 D-085 build 2: amended stimulus QC STOP, to the owner (D-071 (h))

- **Run:** pod at f9f71ee (the D-085 part-1 freeze: qc frozen at 0d01a59, freeze rows b4fafdf). The run is CPU
  only, with `scripts/refclips_build.py /work/yct/refclips_v1_d085 --qc d085`; exit 1.
- **Rebuild check (C3, before YuNet):**
  - The clip-name set equals build 1.
  - **0 mismatches** over 79 clips: wav and tsv are byte-equal, and the mp4s are decoded-stream-equal to
    `build1_decoded_sha256.json`.
  - Descriptive (`rebuild_record.json`): pod ffmpeg 6.1.1-3ubuntu5; every mp4 has 1740 frames, 30/1 fps, and
    bt709/tv tags; max |U−128| = max |V−128| = 0.
- **QC by family:**

  | Family | Clips passing |
  |---|---|
  | GREY_CTRL | 2/2 |
  | FLASH | 5/5 |
  | MOT | 16/16 |
  | MOT_STAT | 16/16 |
  | LOC_SCR | 20/20 |
  | LOC | **19/20** |

  The LOC family face_hit_frac is 19/20 = 0.95, which passes.
- **Failure:** `loc_14`, YuNet no-face gate. The frozen T-LIC YuNet (score ≥ 0.5) fires at t = 28.0 and 28.5 s
  (TR 28), score 0.681. This is event k1, the intact **place_14** image (onset 28.0 s). Every other check on
  loc_14 passes: twin identity, luminance, contrast and audio identity.
  - place_14 passed the T-LIC selection detectors (P2 YuNet on the pre-SHINE image). The hit appears only on
    the post-SHINE 316-px decoded patch.
  - place_14 was also one of the 10 intact body/place frames where build 1's Haar fired
    (`refclips_v1_nonnat_build1`).
- **Rule:** under the frozen D-085 / amended D-071 (a), any YuNet hit is a STOP to the owner under D-071 (h), and no
  second amendment is allowed. So nothing was uploaded, no partial visual manifest was written, and nothing
  was substituted or re-run.
- **C1:** qc.json records `code_commit` f9f71ee, which descends from the qc freeze commit 0d01a59.
