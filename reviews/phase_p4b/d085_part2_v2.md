# D-085 part 2 v2 (speech + TALKFACE): council items applied, for re-sign-off

Status: council cycle 1 (wf_de28150c-be9, `council_d085p2_*.md`) REVISE ×5, no owner questions. Everything
below is implemented and tested. **Nothing new is frozen and there is no DECISIONS part-2 entry yet**: per
the D-084 note, the freeze waits until every member who asked for revisions has re-signed. No synthesis, no
selection, no face continuation and no Wav2Lip run on a real face has happened.

## 1. T-ENV (ruling 1) — disclosure, no amendment

`controls.refclips_d085.tenv` (module `src/yct/confounds/envelope.py`, blob c81eae2b…) was frozen at 62c3806
**before** the council ratified it. The filter is an author-filled detail of the frozen D-086 R-ENV op:
Butterworth order 4 low-pass at 10 Hz, applied forward-backward (`sosfiltfilt`), so the effective order is 8,
zero phase, with a squared magnitude response (−6 dB at 10 Hz, not −3 dB). A silent clip (SD 0) gives an
all-zero envelope. The envelope never gates. The council ratifies it now; any later change, above all after
an envelope has been seen, needs a new decision. This text goes into the DECISIONS part-2 entry.

## 2. espeak-ng engine pin (ruling 2, B1 of watchdog/QA/biostat)

- `speech.engine_pin` is now **required** by the schema (it was `Optional`), and `speech.engine_paths`
  names the binary, library and data dir.
- `src/yct/tribe_run/espeak_engine.py`: `EspeakSynth` re-hashes the binary, library and data tree against
  the pin **before any synthesis**; a mismatch is `SystemExit … STOP to the owner (no reinstall, no
  synthesis)`. Tested with a fake tree: binary, library and one data-file change each stop; nothing is
  called before the pin passes.
- `scripts/espeak_pin.py`: the data-tree hash, committed and tested. It reproduces the recorded pod method
  `cd DATA && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`. Re-checked on the pod
  (2026-11-23): binary 34191438…, library a18be542…, data tree f35962c8… (488 files), all equal to the pin.
- Resample (neuro): selection synthesises at the native 22050 Hz, then resamples with the same band-limited
  path as the build (`refclips58.resample_bandlimited`, polyphase Kaiser FIR, R-11 S-23/S-24) to
  `speech.selection_sr` = 48 kHz, where the −40 dBFS span is measured. So the selection span and the build's
  span are the same quantity. The 16 kHz sidecar is the build's existing S-23 path, unchanged.

## 3. Wav2Lip weights (ruling 3) — option (b) does not exist, so the pre-fixed fallback (a) applies

The council voted (b) 3–2 (watchdog, referee, biostat; QA and neuro preferred (a)), with (a) as the fixed
fallback "if the upstream commit cannot load NOGAN on the synthetic fixture". Checked before any real-face
run:

- `git ls-remote` of Rudrabha/Wav2Lip: the only branch is `master` = **bac9a81e…**, our pinned revision.
- Its 113 commits contain no SD loader: `git log --all -S` for `jit.load`, `SD-NOGAN` and `Wav2Lip-SD` all
  return nothing. So no upstream commit "whose own loader reads Wav2Lip-SD-NOGAN.pt" exists (QA had flagged
  this as unverified).
- The README and licence are therefore unchanged (README sha 8019ca16… at the pinned revision), and the
  s3fd link and sha are unchanged (619a3168…). No STOP condition fired.

Path (a), decided on a synthetic fixture only (`outputs/runs/d085p2_loader_check/loader_check.json`, script
`scripts/wav2lip_loader_check.py`, pod CPU, torch 2.8.0+cpu): the archive (sha 7ab92491…8999, 145,837,271
bytes) loads with `torch.jit.load`; its state_dict has 352 keys, equal by name and shape to the pinned
`models.Wav2Lip` (bac9a81, `models/wav2lip.py` sha a02b5428…); `load_state_dict(strict=True)` succeeds; on
random mel (2,1,80,16) and face (2,6,96,96) the output is (2,3,96,96), finite, in [0, 1], and equal to the
TorchScript forward (max |diff| 0.0). This is QA/neuro's strongest form of (a): the pinned forward pass and
preprocessing stay byte-unchanged and no jit wrapper is used.

`src/yct/tribe_run/wav2lip_loader.py` (`load_nogan`): checks the sha (mismatch = STOP), refuses any GAN file,
loads strict, and has **no jit fallback** (a strict failure is a STOP; the path is fixed). Config:
`weights_file: Wav2Lip-SD-NOGAN.pt`, `weights_sha256: 7ab92491…8999`, `weights_option: {council: b,
applied: a, reason: no_upstream_sd_loader, decided_before_real_face: true}`, `loader: {path:
strict_state_dict, jit_fallback: false, gan_allowed: false}`. The change of literal from `wav2lip.pth` is a
disclosed amendment of D-085 (e). Disclose: the file is dated May 2023 in the README-linked official folder;
trained on LRS2; non-commercial; internal only.

## 4. TALKFACE face continuation (ruling 4) — named in part 2, separate from D-087

`talkface.face_continuation`: v4 face log; `refstim_auto_run.py run … --purpose talkface --target face=21`;
one more pass per technical skip (`face_rule.skip_on`), at most 5 skips (target ≤ 26); at most 20 extra
passes; first pass after rank 492; the same frozen rules; no YuNet replacement; append-only with existing
rows byte-identical (now checked by `assert_byte_prefix` after every category of every run); appended rows
committed before any Wav2Lip run; cap or snapshot exhaustion is a STOP to the owner. The runner refuses the
`talkface` purpose until `controls.refclips_d085.talkface` is frozen, allows it for face only, and keeps the
D-087 path (`purpose loc`) unchanged. The chosen face sha goes into a talkface artifact key, frozen in the
next commit.

## 5. Freeze order (ruling 5, amended)

1. Part-2 commit: `speech` (with the required `engine_pin`, `engine_paths`, `selection_sr`), `talkface`
   (revision, weights file and sha, `weights_option`, `loader`, `face_continuation`) and
   `refclips_artifacts.speech_corpus_sha256` (252c83ac…), together, after the DECISIONS part-2 entry.
2. Fetch the private texts, verify the raw sha and each item sha, run `select`; commit the public kept ids,
   shas and `pass_rates` (k/n per family, Wilson 95% interval, descriptive only); freeze the selection-record
   sha in the next commit. Queue exhaustion (fewer than 60 SPK kept in 410) is a STOP to the owner; the span
   gate is never relaxed after it is seen.
3. TALKFACE face continuation (append-only, committed), then freeze the face sha.
4. SPK, BURST and TALKFACE build, then the frozen QC (the TALKFACE GPU step inside the $75 v2 cap).
5. Clip manifest sha.

No synthesis before step 1 and no listening at any step.

## 6. Draft DECISIONS part-2 text (to be appended after re-sign-off; not written yet)

> D-085 part 2 (speech + TALKFACE; amends D-085 (e)). Council cycle 1 REVISE ×5 → v2 → re-sign-off (4
> APPROVE, neuro REVISE → v2 addendum §7 → neuro re-sign-off).
>
> - **T-ENV disclosure.** `controls.refclips_d085.tenv` (module `src/yct/confounds/envelope.py`, blob
>   c81eae2b…) was frozen at 62c3806 **before** the council ratified it. The filter is an author-filled
>   detail of the frozen D-086 R-ENV op: Butterworth order 4 low-pass at 10 Hz, applied forward-backward
>   (`sosfiltfilt`), so the effective order is 8, zero phase, with a squared magnitude response (−6 dB at
>   10 Hz, not −3 dB). A silent clip (SD 0) gives an all-zero envelope. The envelope never gates. The
>   council ratifies it now; any later change, above all after an envelope has been seen, needs a new
>   decision.
> - **Engine pin.** espeak-ng 1.51+dfsg-12build1 (binary 34191438…, library a18be542…, data tree f35962c8…,
>   488 files), verified at synthesis before any call, fail closed; `select` refuses an unverified synth.
>   Selection span measured on the build's band-limited 48 kHz path.
> - **Wav2Lip weights (amends D-085 (e)).** The literal changes from `wav2lip.pth` to `Wav2Lip-SD-NOGAN.pt`
>   for two reasons: (1) `wav2lip.pth` is no longer in the README-linked official folder at bac9a81, which
>   now holds only the two May 2023 TorchScript archives; (2) option (b) was ruled, but no upstream commit
>   with an SD loader exists (master = bac9a81, 113 commits), so the pre-fixed fallback (a) applies. NOGAN
>   (7ab92491…8999) loads strict into the pinned class, decided on a synthetic fixture only (352/352 keys,
>   max |diff| 0.0; record sha d4e7d038…, loader blob 43f805e8…, both frozen in the part-2 commit). GAN is
>   never used; no jit fallback.
> - **TALKFACE face continuation** (authority here, separate from D-087): v4 face log, target 21, +1 per
>   logged s3fd/Wav2Lip skip (`data/refstim/talkface_skips.jsonl`, committed; each pass above 21 needs one
>   skip_on entry), at most 5 skips, at most 20 extra passes, append-only with byte-identical rows,
>   committed before any Wav2Lip run; exhaustion is a STOP to the owner.
> - **Freeze order** as §5.

## 7. Re-sign-off addendum (wf_77475312-b35)

- Neuro: `talkface.loader.blob_sha1` (43f805e8e1a3066ca138251a47aea814639fdc3b, the loader module) and
  `talkface.loader.check_record_sha256` (d4e7d038…898a, the fixture record) are now part-2 keys, frozen in
  the part-2 commit; the full §1 T-ENV text is in §6.
- Watchdog: `speech_corpus.select` refuses a synth with no `.verified` (only `EspeakSynth`, which verifies
  the pin in its constructor, has it). A face target above 21 needs exactly one committed skip entry per
  extra pass, each with a `face_rule.skip_on` reason (`talkface.face_continuation.skips_log`); the runner
  prints the skip list into the run log. The second reason for the D-085 (e) literal change is in §6.
