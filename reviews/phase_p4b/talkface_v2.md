# TALKFACE v2 (D-090 draft): council talkface rulings applied

Context: the council cycle on `talkface_ready.md` (wf_f194ca9f-6a0, `council_talkface_*.md`) returned REVISE ×5.
The owner ruled on 2026-11-23 (in-session AskUserQuestion):

- "Accept both":
  - the still frame is not SHINE-matched; its luma and contrast are reported against the LOC set;
  - the mouth box switches between the static frame and the Wav2Lip frames at each window edge. This is
    measured and disclosed.
- "As reviewers propose":
  - only the pinned "Face not detected" moves to the next face, with at most 5 skips;
  - loader, sha, mel-NaN, import, OOM and our own code errors are a STOP (exit 1, nothing logged);
  - transfer, timeout and ssh errors exit 75;
  - a TALKFACE QC fail is a final STOP, and the control is reported failed.

Status: implemented test-first and rehearsed on the pod CPU (synthetic only). **Nothing is frozen, there is no
DECISIONS entry, and no GPU has run.**
- The rules live in `controls.refclips_d090`, which is not frozen. It is layered over the frozen
  `refclips_d085.talkface` without editing it.
- The council re-signs before the two-commit freeze.
- `--prepare` and `--finish` refuse to run until D-090 is frozen.

## 1. The seven §2 choices, as ruled

| # | Choice | Ruling | Where |
|---|---|---|---|
| 1 | Static frame without SHINE | Accepted (owner). Recipe: `locimg.patch` with no SHINE, centred 640×360, written as a 3-channel grey png. Patch mean and RMS are reported against SHINE 128 / 32 (descriptive). | `d090.static_frame`, `talkface.static_luma` |
| 2 | Wav2Lip driven by the clip audio | Accepted. The 48→16 kHz path is `refclips58.resample_bandlimited` then pcm16, exactly 928000 samples, so the pinned `load_wav` does not resample again. | `d090.driving_audio`, `prepare_inputs` |
| 3 | Wav2Lip frames only inside the windows | Accepted (owner). Frame i is at i/fps; windows are half-open. The edge switch is reported as `edge_step` (descriptive). There is no later switch to full length. | `d090.frame_time`, `d090.composition` |
| 4 | Lossless grey npz | Accepted. The box now calls `locimg.grey709` itself (`talkface_box.box_grey`); a test checks it bit for bit. The final encode is the frozen SPK/BURST `refclips58.encode`. | `d090.frames`, `d090.encode` |
| 5 | QC | Revised; the gates are listed below in §2. `lip_motion` is renamed `w2l_rendered` and is a sanity gate only. | `d090.qc`, `talkface.qc` |
| 6 | Box env (torch 2.8.0) | Accepted as a disclosed deviation. The pin list moved into config as a **hashed lock**; the launch is gated on the box freeze matching it. | `d090.env`, `infra/talkface_lock.txt` |
| 7 | Skip mapping | Narrowed (owner): only box exit 10 ("Face not detected") is a face skip. | `d090.skips`, `talkface.classify_box_exit` |

## 2. QC (gating unless marked)

Every gate below is checked, and any fail is a final STOP to the owner with the control reported failed.

- **Counts:**
  - `n_frames`: 1740.
  - `n_mel_chunks`: the box record shows n_mel_chunks = n_frames_total = 1736.
  - `kept_frames`: the box kept exactly the in-window frames below 1736.
- **Static-frame checks:**
  - `outside_window_static`: every out-of-window frame equals the static frame. This is true by
    construction of compose; it stays as a guard.
  - `outside_face_box_static`: in **every** frame, the pixels outside the box record's `face_box` equal the
    static frame. This is new and meaningful, because inside the windows only the face box may change.
- **Motion checks:**
  - `w2l_rendered`: each window has at least one frame that differs from static inside the box. This is a
    sanity check only: it shows that Wav2Lip ran.
  - `inbox_articulation`: each window has at least one consecutive-frame difference inside the box, so the
    mouth moves.
- **Encode and audio checks:**
  - `decode_identity`: a second encode with the same frozen encoder gives the same mp4 sha and the same
    decoded sha (tolerance 0, like the SPK video identity).
  - `speech_gate`: the constructive SPK/BURST gate on the rendered 48 kHz audio, against the GREY_CTRL
    rendering.

Descriptive only, never gating:
- `window_mean_abs_diff`;
- `edge_step` (onset and offset frame against static inside the box);
- `mouth_vs_upper_mad` (lower half against upper half of the box);
- `decoded_vs_composed` (max and mean |diff| at the mid-event frames; no x264 tolerance is ever set);
- `static_luma_vs_loc`.

YuNet is not run on TALKFACE.

## 3. Frame count (watchdog B, a defect in the draft)

The pinned mel chunking on 58 s at 16 kHz gives **1736** frames, not 1740:
- librosa with center=True gives 1 + 928000 // 200 = 4641 mel frames;
- at 80/30 per frame with a 16-frame step, that makes 1736 chunks.

`talkface.expected_n_chunks` reproduces the pinned loop line for line, with a test. `--prepare` refuses any
window ending after (1736 − 1)/30 = 57.833 s. The TALKFACE windows end by 49 + 6 = 55 s at most.

Frames 1736–1739 are never in a window, so they are the static frame.

## 4. Failure mapping (owner "As reviewers propose")

- **Exit codes:** `talkface_box` exits 0 on success, 10 on the pinned "Face not detected", and 30 on any
  other failure. The other failures are an input, weights or s3fd sha mismatch, a loader error, a NaN mel, an
  import error, OOM or any traceback.
- **What the driver classifies:** only that process exit (`BoxExit`):
  - 10 → `s3fd_no_face` skip, logged, exit 1 (the next face needs the frozen continuation; at most 5);
  - anything else → STOP, exit 1, nothing logged.
- **Environment mismatch:** `EnvMismatch`, meaning the box freeze differs from the lock or the
  torch/CUDA/python probe is wrong, → STOP.
- **Everything else is infrastructure** (`box.wait` timeout, ssh, the S3 copy, the frame copy-back) → exit 75,
  nothing logged.
- **Frame copy-back:** it is now its own step, `fetch_frames`, outside the classified block.
- **Steps:** `setup_w2l → check_env → push_inputs → wav2lip → fetch_frames`.
- **NaN mel:** a STOP, never a face skip (watchdog, referee and QA). Neuro and biostat had proposed
  `wav2lip_error`, and the owner sided with STOP. Since `wav2lip_error` is no longer a skip, `skip_record`
  refuses it.

## 5. Box env (TALK_PIP → hashed lock)

- **The lock:** `infra/talkface_requirements.in` holds the 10 pins. They are compiled on the pod with
  `uv pip compile --generate-hashes --python-version 3.11 --python-platform x86_64-manylinux_2_28 --index-url
  https://pypi.org/simple` into `infra/talkface_lock.txt` (51 packages, sha `14d34302…`).
- **Torch:** 2.8.0 from the PyPI default index, which is the CUDA 12.8 build (`2.8.0+cu128`; wheel tag
  `cp311-cp311-manylinux_2_28_x86_64`).
- **Box install:** `uv pip install --require-hashes --no-deps -r infra/talkface_lock.txt` (the lock is
  shipped), then a `pip freeze` and an env probe.
- **The gate (`check_env`):**
  - the box freeze must equal the lock pins exactly;
  - the probe must report torch `2.8.0+cu128`, CUDA `12.8` and python 3.11;
  - otherwise STOP. This is QA's position; neuro had proposed exit 75.
- **Reference freeze:** the rehearsal freeze (`outputs/runs/talkface_rehearsal/w2l_pip_freeze.txt`, sha
  `3578d20d…`) is the reference, and it equals the lock.

## 6. Council factual questions (answered)

- **crop_box source for face row 499:** the v4 face-log row 499 `crop_box` [409, 1113, 3038], the T-LIC crop.
  `--prepare` copies it into `data/refstim/talkface_inputs.json`, which holds shas and numbers only.
- **Encode settings:** the frozen SPK/BURST encoder `refclips58.encode`:
  - `normalize.video` and `normalize.audio`, bit-exact flags, with the P2 bt709/tv tags;
  - a 16 kHz sidecar wav and a tsv.
- **Mirror paths:** confirmed on S3 on 2026-11-23. The files sit at the **mirror root**
  (`…/refstim/talkface/private/Wav2Lip-SD-NOGAN.pt` and `…/s3fd-619a316812.pth`), not under `weights/`.
  - `push_cmd` copies exactly these two files; the GAN archive is never fetched.
  - The prepared inputs go to `…/private/inputs/` and the clip to `…/private/clip/`.
- **Torch wheel index:** `https://pypi.org/simple`, the PyPI default, which carries the cu128 build.

## 7. Wiring

- **`--prepare`** (pod CPU, after the D-090 freeze):
  - texts from the private page, every sha checked;
  - the pin-verified espeak-ng at the D-089 TALKFACE rate of 175 wpm;
  - the face from the frozen rank-499 row (licence check; source matched by content sha in the pod scratch).
  - Then `talkface.prepare_inputs` writes the private files: `static.png`, `rendered48k.wav`,
    `clip16k.wav`, `utterances.npz` and `rows.json`.
  - It uploads them to the private mirror, writes the numbers-only `talkface_inputs.json`, and calls
    `assert_no_text` on it.
- **`--finish`** (pod CPU, after the session): `talkface.finish_local` runs these steps:
  1. checks the frames.npz sha against the box record;
  2. composes the frames;
  3. encodes twice;
  4. runs the QC and speech gate;
  5. uploads the clip to the private mirror and returns numbers only.
- **Tests:** a fixture test with real ffmpeg, plus one that refuses a sha mismatch.

## 8. Rehearsal ($0, pod CPU, synthetic only)

`scripts/talkface_rehearsal.py` ran at ecf4830; the record is `outputs/runs/talkface_rehearsal/rehearsal.json`
and the results are in the response matrix. The inputs were:
- a synthetic 640×360 grey image with no face;
- a 58 s noise bed with no speech and no corpus text;
- windows at the TALKFACE onsets.

What it ran:
- the env lock check;
- `talkface_box --fixture-box` on CPU, with a strict NOGAN load: exit, chunk and kept counts, and
  outside-box luma identity;
- the real mirrored s3fd on the same image, which must load under torch 2.8 and end in exit 10 →
  `s3fd_no_face`;
- `finish_local` end to end.

## 9. Freeze plan (after the council re-signs)

The freeze goes in this order:

1. **Commit A:** the DECISIONS D-090 entry, citing this file, the council files and the owner rulings.
2. **Commit B:** the freeze row for `controls.refclips_d090` and its expected row in
   `tests/test_guards_frozen_config.py`.
3. **Then:**
   - `--prepare` on the pod;
   - commit `talkface_inputs.json`;
   - the pre-launch check (`talkface_ready.md` §3);
   - a CI-green HEAD and the external terminator;
   - the session;
   - `--finish`.

## 10. Rehearsal results (pod CPU, synthetic only)

| Attempt | Commit | Result |
|---|---|---|
| 1 | ecf4830 | Both box runs STOPped (exit 30) on `ModuleNotFoundError: pkg_resources`. This is BUG-046, fixed by pinning setuptools 70.3.0 and re-compiling the hashed lock. The classification was correct: a STOP, not a skip. |
| 2 | 287e75f | The fixture box and finish passed. The real s3fd loaded and ran under torch 2.8 but found a box on the textured synthetic image, so the no-face path was not exercised. A flat-grey run was added. |
| 3 | 6fb82b8 | **All pass** (`outputs/runs/talkface_rehearsal/rehearsal.json`), see below. |

Attempt 3 in detail:
- **Env:** freeze == lock; probe torch 2.8.0+cu128, CUDA 12.8, python 3.11.18.
- **Fixture box:** exit 0, strict NOGAN load, n_mel_chunks = n_frames_total = 1736, kept = 213 window frames.
- **Luma:** outside-box luma identity holds over 213/213 frames.
- **s3fd:** runs under torch 2.8. A flat-grey image ends in "Face not detected" → exit 10 → `s3fd_no_face`.
- **Finish:** every gate passes, including decode identity (second encode, same decoded sha) and the speech gate.
