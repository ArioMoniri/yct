# D-085 part 2 (speech + TALKFACE): pre-freeze record for the council

Status: draft for council review. Nothing here is frozen. Part 1 (visual QC) is frozen and the v2 visual families pass (D-087, `outputs/runs/refclips_v2_build/`).

Part-2 keys to freeze (`controls.refclips_d085.freeze_plan.part2`):
- `controls.refclips_d085.speech`
- `controls.refclips_d085.talkface`
- `controls.refclips_artifacts.speech_corpus_sha256`

## 1. Done before this draft

- **T-ENV** (`src/yct/confounds/envelope.py`, D-086 R-ENV). It is set at 8754ba5 (module + blob sha1 c81eae2b…) and frozen at 62c3806 (`controls.refclips_d085.tenv`). The steps are:
  - per-clip z-score;
  - |hilbert|;
  - low-pass 10 Hz, Butterworth order 4, zero-phase (`sosfiltfilt`);
  - mean per 0.5 s bin;
  - mean onto the 1 s TR grid of `yct.confounds.tr_grid`.

  R-ENV did not name the filter family or order. They are stated in the module and frozen with its blob sha. A silent clip (SD 0) gives an all-zero envelope. The envelope never gates on reference clips.
- **BUG-045** is fixed. Cache hits now head and upload to `s3_key`, and every LOC build ends with the S3 read-back.
- **CI.** `tests/test_nat_d084.py` had pinned the real NAT log to session 0. It is now pinned to the log prefix it was written for, with a new test for the current log (sessions 0–1).

## 2. Speech (espeak-ng)

**Engine pin**, recorded on the pod. It is set in `speech.engine_pin`, not frozen.

| Item | Value |
|---|---|
| package | espeak-ng 1.51+dfsg-12build1 (espeak-ng-data and libespeak-ng1 at the same version) |
| `/usr/bin/espeak-ng` | 34191438…d076 |
| `libespeak-ng.so.1.1.51` | a18be542…7508 |
| data tree (488 files, `sha256sum` over LC_ALL=C-sorted paths, then sha256) | f35962c8…a439 |
| native sample rate | 22050 Hz |
| determinism | two runs of a non-corpus test string give the same wav sha256 |

Synthesis settings, unchanged: `-v en-us -s 175 -p 50 -a 100`.

**Corpus.** The hash-only `data/refstim/speech/speech_corpus_v1.json` has sha256 252c83ac…40c3. That matches `refclips_artifacts.speech_corpus_sha256`, which is set but not frozen. The texts stay in `speech.private_raw_s3`, and `resolve_texts` checks the raw sha and every item sha (fail closed).

**Selection was NOT run, so no pass rates exist yet.**
- `speech_corpus.require_frozen` refuses synthesis until `speech_corpus_sha256` is frozen. That rule is the council's D-085 design: no synthesis, and so no duration outcome, before the corpus freeze.
- Running the selector now would expose per-item span outcomes before the rule that consumes them is frozen.
- Order after the part-2 freeze:
  1. fetch the private texts and verify their shas;
  2. run `select` (SPK 3-word, −40 dBFS span gate, in-order replacement; `pass_rates` per family);
  3. the private log holds the texts, and the public record holds ids, shas and numbers only;
  4. queue exhaustion is a STOP to the owner.
- Nobody listens to the audio.
- **Feasibility risk, already disclosed** (neuro, re-sign-off): spans are now measured on the −40 dBFS span (D-086 S-23/S-24). That makes more 3-word items at 175 wpm fall under 1.0 s. The queue is 410 items, and SPK needs 60 kept.

## 3. TALKFACE (Wav2Lip)

- **Revision:** bac9a81e63ecc153202353372e5724b83d9e6322. Its README.md sha256 is 8019ca16…cd34, and the README is mirrored privately.
- **Licence**, per the README "License and Citation": personal, research and non-commercial use only; trained on LRS2. The owner confirmed the study is non-commercial, and the clip is internal only.
- **Face detector (s3fd).** Downloaded from the README's primary link, `s3fd-619a316812.pth` (adrianbulat.com). Its sha256 is 619a31681264d3f7…3543, and the 10-hex prefix matches the file name. Mirrored to `talkface.mirror_s3`; set in `face_detector_sha256`, not frozen.
- **Weights: council decision needed (blocking).**
  - The README at the pinned revision links "Wav2Lip, highly accurate lip-sync" to a Google Drive folder. That folder no longer holds `wav2lip.pth` (the original state_dict the council chose). It holds two TorchScript archives dated May 2023:
    - `Wav2Lip-SD-NOGAN.pt`, sha256 7ab92491…8999, 145,837,271 bytes;
    - `Wav2Lip-SD-GAN.pt`, sha256 180cfd49…3b8e, 145,829,145 bytes.

    Both are mirrored privately and nothing is public.
  - The pinned `inference.py` loads with `torch.load` plus a `state_dict`, so it cannot load these archives as they are.
  - Options for the council:
    - (a) Keep the revision. Use `Wav2Lip-SD-NOGAN.pt`, the "accurate lip-sync" variant and the closest match to the council's `wav2lip.pth` choice, with a small `torch.jit.load` wrapper. The wrapper is tested on a synthetic fixture.
    - (b) Move to the upstream revision that ships the SD loader, pinned by commit.
    - (c) Take `wav2lip.pth` from a non-official mirror. This has a provenance risk and is not recommended.

    `weights_file` stays the schema literal `wav2lip.pth` until the council rules; `weights_sha256` stays null.
- **Face rule.** "first face pass after rank 492". The v2 LOC selection consumed face ranks up to 492 (no face slot was replaced or screened out), so `max_consumed_face_rank` = 492. The v4 face log ends at its 20th pass (rank 492), so no TALKFACE candidate exists yet. Taking one needs the frozen refstim continuation on the face log (`--target face=21`, same frozen rules, append-only). Open for the council:
  - whether D-087's continuation key (`refclips_d087`, at most 20 extra passes per category) covers a TALKFACE purpose;
  - or whether the part-2 entry names it.

  The continuation was not run.
- **GPU step.** A short session `yct-p4b-ref-talk` with worst case $3.4825, inside the D-087 $75 v2 cap. `check_projection` already includes `session_worst_usd`. So far $0.74 is spent (NAT sessions 0–1), and the projection before NAT session 1 was $68.35. Nothing was launched.

## 4. Council questions (part-2 freeze)

1. Wav2Lip weights: choose (a), (b) or (c) from §3. With (a), `weights_file` changes from the schema literal `wav2lip.pth` to `Wav2Lip-SD-NOGAN.pt`, plus a tested TorchScript loader.
2. TALKFACE face continuation: is it under D-087 or named in part 2? Either way, run it after the part-2 freeze and log it append-only.
3. Ratify the engine pin (§2) and the T-ENV filter choice (§1).
4. Confirm that synthesis and selection happen only after the part-2 freeze, with pass rates reported then.
5. Freeze order:
   1. part-2 keys;
   2. corpus sha;
   3. selection run;
   4. TALKFACE face continuation;
   5. weights sha;
   6. SPK/BURST/TALKFACE build + frozen QC;
   7. clip manifest sha.
