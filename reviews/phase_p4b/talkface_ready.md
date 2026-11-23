# TALKFACE session: plan and cost for the council pre-launch check (D-085 part 2 step 4)

Status: driver written and dry-run tested (`scripts/gpu_p4b_talk.py`, `tests/test_gpu_p4b_talk.py`, 33 tests);
**launch is disabled in code** (`main` refuses) until this check signs off. Nothing has run on a GPU.

## 1. What is fixed (frozen) and reused

- Face: v4 face-log row 499 (the 21st face pass after rank 492), licence CC-BY-4.0, source sha
  `fe734910…` = frozen `talkface_face_sha256`; `talkface.face_row` refuses any other row, a LOC rank (<= 492)
  or a non-adaptable licence (no ND; CC-BY-SA is outside `image_licences`).
- Audio: the frozen D-089 TALKFACE selection (3 items, 175 wpm), placed by `refclips58.clip_audio` exactly as
  SPK / BURST (one bed, speech replaces the bed at matched RMS). Engine: the pinned espeak-ng (pin verified).
- Wav2Lip: repo revision bac9a81 (README, `models/wav2lip.py`, `inference.py` sha-checked on the box against
  the loader check record), `Wav2Lip-SD-NOGAN.pt` sha `7ab92491…` loaded only by the frozen
  `wav2lip_loader.load_nogan` (strict state_dict, no GAN, no jit fallback; blob sha checked before launch),
  s3fd sha `619a3168…` placed where the pinned `SFDDetector` reads it (no download), `--static`, fps 30.
- Internal only: frames and the clip stay in the private mirror (`talkface.mirror_s3`); git gets numbers and
  shas (`talkface.public_numbers`, `data/refstim/talkface_result.json`). `publish: false` is checked.

## 2. Proposals the council must ratify (not frozen anywhere yet)

1. **Static frame** = the LOC processing of the face image without SHINE: frozen crop_box, BT.709 luma,
   INTER_AREA to 316 px, centred in the 640x360 mid-grey frame (`talkface.static_frame`). SHINE is a joint
   60-image operation and is not applied to a single image (disclosed).
2. **Wav2Lip is driven by the clip audio itself** (bed + speech, band-limited to 16 kHz), so the mouth follows
   what TRIBE hears; this also avoids the pinned "mel contains nan" failure on digital silence.
3. **Composition**: only frames inside the utterance windows `[onset, onset + span)` come from Wav2Lip; every
   other frame is the static frame bit for bit (no mouth motion driven by the noise bed).
4. **Lossless frames**: `talkface_box` uses the pinned inference functions unchanged (audio, mel chunking line
   for line, `datagen` with s3fd, the pinned forward) but keeps the in-window frames as grey uint8 (npz)
   instead of the pinned DIVX `.avi` + ffmpeg mux, so no extra lossy step precedes our encode.
5. **TALKFACE QC (gating)**: 1740 frames; every out-of-window frame equals the static frame; each of the 3
   windows shows lip motion (>= 1 frame differs from the static frame); the constructive speech gate on the
   rendered audio. Descriptive: mean |frame - static| per window; YuNet is not run on TALKFACE.
6. **Box env** (upstream `requirements.txt` pins torch 1.1 / librosa 0.7, which cannot load the TorchScript
   archive): python 3.11, `torch==2.8.0` (the version the loader check used), numpy 1.26.4, scipy 1.11.4,
   librosa 0.9.2 (still accepts the pinned `audio.py` positional `filters.mel` call), numba 0.59.1,
   llvmlite 0.42.0, resampy 0.4.3, soundfile 0.12.1, opencv-python-headless 4.11.0.86, tqdm 4.66.5. The box
   writes its `pip freeze` next to the result.
7. **Skips** (`face_rule.skip_on`): "Face not detected" from the pinned inference -> `s3fd_no_face`; any
   other error inside the Wav2Lip step -> `wav2lip_error`; each is logged to `data/refstim/talkface_skips.jsonl`
   (exit 1), and the next face needs the frozen face continuation (+1 target per skip, max 5, then STOP).
   Errors in setup / transfer are infrastructure (exit 75, re-run, nothing logged).

## 3. Launch rules (all checked before the launch, exit 1 on any)

TALKFACE dependencies frozen (speech, talkface, tenv, qc, D-089, selection sha, face sha, corpus sha);
publish false; loader blob + check record shas; inputs record present and matching the frozen face and
selection shas; no earlier TALKFACE result; `--max-hours <= 1.75`; `--usd-limit <= 8`; price x hours <= limit;
external terminator between deadline + 900 s and + 3600 s more (never a reused fire time); HEAD = the CI-green
commit and pushed; the L4 ledger record current; no live yct-* instance; the campaign baseline written once;
`ref_campaign.guard_launch` (v2 cap $75, $0.39 carried). Instance name prefix `yct-p4b-ref-talk`; the instance
is always terminated (finally) and the box carries the dead-man switch.

## 4. Cost

One `gpu_1x_a100_sxm4` (1.99 $/h). Setup (venv + clone) ~10 min, transfer ~2 min, Wav2Lip on a 58 s static
input at 30 fps (1740 frames, batch 128) ~2 min: expected **~0.5 h ≈ $1.0**; worst case 1.75 h = **$3.48**
(already in the D-084 projection as `session_worst_usd`). Projection before launch: campaign spend
(~$0.74 after NAT sessions 0-1) + main plan $61 + $3.48 = **~$65.2 <= $75**.

## 5. Not done yet (must precede the launch)

- `--prepare` (pod CPU) is not wired: it must build the TALKFACE audio (48 kHz rendered + 16 kHz Wav2Lip
  input), the static frame from the sha-verified face source, the windows, upload them to the private mirror,
  and commit `data/refstim/talkface_inputs.json` (shas only).
- The post-session `finish` (pod CPU: compose + encode + QC + private upload) is only tested as pure helpers
  (`talkface.compose`, `talkface.qc`); the real pod wiring is not written.
- No real-path rehearsal yet. Proposed (as T-NAT0): a $0 pod CPU rehearsal of the exact box env pins and
  `talkface_box --fixture-box` on a synthetic image (s3fd bypassed via the pinned `--box`), a 3 s audio,
  numbers only; no real face before the freeze of §2.
- The weights + s3fd must be in `mirror_s3/weights/` (they were mirrored at D-085 part 2; path to confirm).

## 6. Speech build result (step 4, done, for context)

SPK 20/20 and BURST 5/5 built and passed the frozen QC (GREY_CTRL rebuild = build 1; video identity; speech
gate; SPK integer span QC), run on the pod at 070c663: `outputs/runs/speech_build_v2/`.
