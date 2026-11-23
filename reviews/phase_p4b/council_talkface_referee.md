# Council (referee): TALKFACE pre-launch check (talkface_ready.md, 6e47278) — verdict REVISE
Scope read: talkface_ready.md, git show 6e47278 (driver, talkface.py, talkface_box.py, tests), speech_build_v2 numbers only
(rc 0; 27/27 rows pass, 25 speech rows; window RMS ratio 0.999-1.003; SPK spans 1.00-1.48 s; envelope descriptive). Nothing
sealed, no face image, no texts, no GPU output seen. All rulings are fixed outcome-blind, before any Wav2Lip frame exists.

## Rulings on the seven unfrozen choices (TALKFACE = 1 clip, internal, descriptive role)
1. Still frame without SHINE: ACCEPT. SHINE is a 60-image joint op; a single-image analogue would be a new author choice.
   Add descriptive: mean luma + RMS contrast of the static frame vs the LOC face set; disclose "not SHINE-matched".
2. Wav2Lip driven by the clip audio: ACCEPT. Freeze the 48k->16k resampler (function, filter, rounding) and its sha.
3. Speech-window-only composition: ACCEPT, with disclosure: the whole s3fd box is re-rendered, so each window onset is a
   box-shaped visual step synchronous with speech. Add descriptive (non-gating) onset-step |diff| in/outside the mouth half.
4. Lossless grey frames (npz) then our own encode: ACCEPT. The box luma (BGR order) must equal locimg.grey709; add a test.
5. QC: ACCEPT as gating but strengthen: `outside_static` is tautological after compose; ADD gating "in-window pixels
   outside the recorded face_box equal the static frame" and "n_mel_chunks/kept frames = expected (1740 / window count)".
   Freeze the fail action: a QC fail is STOP to the owner, never a face skip/next face.
6. Box env (py3.11, torch 2.8.0, librosa 0.9.2 ...): ACCEPT (upstream torch 1.1 cannot load the archive; 2.8.0 is what
   the loader check used). Freeze the exact wheel incl. CUDA tag, install from a hashed lock (--require-hashes), and
   gate launch on rehearsal `pip freeze` == lock. Note pinned sfd_detector calls torch.load(path): weights_only=True in
   2.8 — must be proven in rehearsal, not discovered on the GPU.
7. Skip mapping: REVISE. "any other error -> wav2lip_error" turns our bugs/OOM/env faults into face selection (a forking
   path), and "Mel contains nan" is audio-only (the next face gets the same audio). Freeze: s3fd_no_face only for the
   pinned "Face not detected"; all other errors (mel nan, CUDA, import, sha, our code) = STOP/infrastructure, not logged.

## Must be frozen (config `controls.refclips_d085.talkface`, then sha in the face/inputs records) before launch
static_frame recipe; driving audio + resampler; composition rule; frame format + luma formula; QC gating list + STOP action;
env lock file sha; narrowed skip_on table; expected frame/mel-chunk counts; descriptive metrics list (1, 3, 5).

## Minimum $0 pod-CPU rehearsal (T-NAT0) and missing wiring, all before launch
- Wire `--prepare` (audio 48k + 16k, static frame from sha-verified source, windows, private upload, commit inputs json)
  and post-session `finish` (compose -> QC -> encode -> speech gate -> private upload -> public_numbers); CI-green, pushed.
- Rehearse with the exact lock: pinned repo shas, load_nogan on the real NOGAN blob, s3fd.pth load + one forward on a
  synthetic image (detection result ignored), talkface_box --fixture-box on a synthetic image with a FULL 58 s synthetic
  (non-corpus) audio -> frame count, then finish end-to-end on that output to a rehearsal mirror prefix; numbers only.
- Confirm mirror_s3/weights/ paths + shas. No real face, no real TALKFACE audio until the freeze above is committed.
