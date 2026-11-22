# Council D-085 part 2: referee (d085_part2.md; 986b773, ba50c76, 8754ba5, 62c3806, 5b34a1c, 17c07d1)

Verdict: **REVISE**. The record is sound and nothing outcome-bearing has run. Three items block the part-2 freeze commit (B1–B3).

1. **T-ENV filter: acceptable, but disclose it.** R-ENV (D-086) fixed the op and left the filter family and order open. The choice (Butterworth 4, `sosfiltfilt`, 10 Hz) is standard for a syllabic envelope. It was pinned before any speech clip existed and is outcome-blind, and it does not contradict the frozen op. No amendment is needed. The part-2 DECISIONS entry must say that `refclips_d085.tenv` was frozen at 62c3806, before council ratification, as an implementation of the frozen R-ENV op. It must also record that zero-phase filtering makes the effective order 8. The council ratifies the freeze retroactively. If it is ever changed, it needs a new decision, never an edit.
2. **espeak-ng 1.51 pin: ratified.** The binary, lib and data-tree shas are recorded, and determinism was checked on a non-corpus string. B3: move `speech.engine_pin` into the frozen `speech` key and commit the data-tree hash script with a test. A pod whose shas differ is a STOP, not a reinstall-and-continue.
3. **Wav2Lip weights: option (b), with NOGAN.** Pin the upstream commit whose own loader reads `Wav2Lip-SD-NOGAN.pt` (sha 7ab92491…8999). The weights and the loader then both come from the authors, with no custom wrapper. NOGAN is the accuracy variant and the closest match to the council's earlier non-GAN `wav2lip.pth`. GAN is excluded now and is never a fallback after looking at frames. (c) is rejected (provenance). B1: re-hash the README and licence at the new commit. If the terms differ from personal, research and non-commercial use, or the s3fd link or sha changes, that is a STOP to the owner. If the new commit cannot load NOGAN natively, the fallback is (a) with the same file. That fallback is fixed now, before any output, and it needs a loader test on a synthetic fixture.
4. **TALKFACE face: part 2 must name it.** D-087's `continuation` exists for LOC screen shortages: it is tied to the re-screen (`committed_before_rescreen`) and to the v2 cap or exhaustion STOP. `talkface_after` sets only the rank rule, not continuation authority. Reading D-087 as covering TALKFACE would stretch a frozen key. B2: `refclips_d085.talkface.face_continuation` = v4 log, `--target face=21` under the same frozen filter, append-only (existing rows byte-identical, appended rows committed before use), ≤ 20 extra passes then STOP to the owner. Take the first pass after rank 492 and run no YuNet replacement on it (an intact face is the purpose). Record its sha in a talkface artifact key, frozen in the next commit.
5. **Freeze order: amended.** The weights sha is known now, so it must not wait until after selection.
   1. Part-2 commit: `speech` (with the engine pin), `talkface` (revision, `weights_file`, `weights_sha256`, loader test, face_continuation rule) and `speech_corpus_sha256`.
   2. Fetch the texts, verify the shas, run `select`, and commit the public ids, shas and `pass_rates`. The selection record sha is frozen in the next commit. Queue exhaustion is a STOP.
   3. Face continuation (append-only), then freeze the face sha.
   4. SPK, BURST and TALKFACE build, then frozen QC.
   5. Clip manifest sha.

   There is no synthesis before step 1 (`require_frozen`), and no listening at any point.

Owner rulings respected: TALKFACE internal only; AI lip-sync; 3-word SPK at 175 wpm; Harvard texts as hashes only. No owner decision is needed now. The licence check in B1 becomes one only if the terms differ.

## Re-sign-off (v2: d085_part2_v2.md, d7692c7, cadb82d, ff0bc9f)

Verdict: **APPROVE**. B1–B3 are met, and nothing outcome-bearing has run.
- Ruling 3: option (b) does not exist (upstream master = bac9a81, 113 commits, no SD loader), so my pre-stated fallback (a) applies as fixed. The fixture check (loader_check.json) passed: 352/352 keys, strict load succeeds, max |diff| 0.0 against the jit forward, decided before any real face. `load_nogan` has no jit fallback and refuses GAN. The README, licence and s3fd are unchanged, so no STOP fired. The literal change from `wav2lip.pth` is disclosed as a D-085 (e) amendment. Accepted.
- B2: `face_continuation` is separate from D-087 and gated on the part-2 freeze. It is face only, append-only (`assert_byte_prefix`), with no YuNet replacement. The skip allowance (+1 per frozen mechanical `skip_on`, ≤5, target ≤26, within 20 extra passes) adds no visual or quality judgement. Accepted.
- B3: `engine_pin` is required and re-hashed before synthesis, fail-closed. The data-tree script is committed and tested. 38 tests pass.
- Ruling 1 and the freeze order match my review. Non-blocking: the DECISIONS entry should carry the full §1 T-ENV sentence (frozen at 62c3806 before ratification, effective order 8, any change needs a new decision), not just "(§1)".
