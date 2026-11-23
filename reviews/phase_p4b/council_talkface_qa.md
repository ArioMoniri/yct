# Council QA: TALKFACE pre-launch check (talkface_ready.md, 6e47278)

Verdict: **REVISE**. No launch until items B1-B5 are done. All rulings are made outcome-blind: no GPU output
exists, and no face image, sealed data or predictions were read. Checks: `pytest -k talkface` 11 passed; `tests/test_gpu_p4b_talk.py` 33 passed;
`make guards` OK. Speech build v2 record (numbers only): rc 0, QC pass, 27 rows, 25 speech rows.

## Rulings on the seven §2 choices (freeze as written unless noted)
1. Static frame without SHINE: ACCEPT. Disclose it. As descriptive numbers, record the frame's mean luma and RMS contrast next to the LOC set's.
2. Wav2Lip driven by the clip audio: ACCEPT. Freeze the 48k->16k resampler and its filter in `--prepare` and record its sha.
3. Wav2Lip frames only inside the windows: ACCEPT. Freeze the convention that frame i is at time i/fps and the window is half-open [a, b).
   Disclose that the face crop switches on and off at each window edge. Add a descriptive boundary-jump number for those frames.
4. Lossless grey npz: ACCEPT. The final encode must be the frozen SPK/BURST encoder, with no extra step.
5. QC: REVISE. As written, `lip_motion` is vacuous: Wav2Lip pastes a regenerated crop, so every in-window frame differs from the static frame.
   Gate instead on (a) every pixel outside the recorded `face_box` equals the static frame in every frame, and (b) inside the box,
   each window has at least one consecutive-frame difference > 0. Keep the mean |diff| descriptive. Freeze it before the GPU run.
6. Box env (torch 2.8.0 and others): ACCEPT, on two conditions: the CPU rehearsal with these exact pins passes, and a freeze diff that does not match the pin list is a STOP.
7. Skip mapping: REVISE. `run_session` maps any exception in the `wav2lip` step to a face skip. That includes box.wait timeout,
   ssh failures and the pod copy of frames.npz, so an infrastructure fault would use up a face. Only a non-zero exit of the
   `talkface_box` process may be classified: "Face not detected" -> s3fd_no_face; everything else -> exit 75.
   "Mel contains nan" is an audio fault, not a face fault, so it is a STOP and not a skip.

## Blocking items
- B1 Wire `--prepare`: 48k audio, 16k audio, static.png (3-channel), windows, private upload, and the committed shas-only `talkface_inputs.json`, with tests.
- B2 Wire `finish` on the pod: fetch npz -> to_grey/compose -> revised QC -> frozen encode -> private upload -> numbers-only result, with tests.
- B3 Fix the skip mapping (ruling 7). Revise the QC (ruling 5). Add tests for both.
- B4 Freeze in config: rulings 1-7, the pin list, the resampler, the frame-time convention and the QC definition (commit before launch).
- B5 Run the $0 pod-CPU rehearsal (T-NAT0) with the exact pins and a synthetic image, never the real face:
  (i) `--fixture-box` on 3 s of audio runs end to end; (ii) without `--box`, s3fd loads the real
  `619a3168` weights under torch 2.8 (weights_only) and raises "Face not detected", which is classified as s3fd_no_face;
  (iii) the rehearsal output goes through compose, QC and encode; (iv) the record holds numbers only. Also confirm the `mirror_s3/weights/` path.

## Owner questions
- Q1: Do you accept the window-edge crop switch as a disclosed descriptive artefact rather than a reason for redesign?
- Q2: Do you confirm that a TALKFACE QC fail is a final STOP with no re-run, and that the cap of 5 skips stands?

## Re-sign-off (TALKFACE v2 / D-090 draft, 7d640ab..132bdbe)
Verdict: **APPROVE**. I re-checked this outcome-blind: I read no face image, sealed data or predictions; the rehearsal record is synthetic only. Tests: `tests/test_talkface_v2.py` + `tests/test_gpu_p4b_talk.py` 71 passed; `make guards` OK.
- B1/B2 done: `prepare_main`/`finish_main` are wired and refuse to run until `refclips_d090` is frozen; fixture tests use real ffmpeg.
- B3 done: only `BoxExit(10)` ("Face not detected") skips; `BoxExit(other)`, `EnvMismatch` -> STOP; timeout/ssh/`fetch_frames` -> 75. The vacuous lip_motion gate is replaced by the outside-face-box gate, `w2l_rendered` and `inbox_articulation`.
- B4 done: rulings 1-7 sit in `controls.refclips_d090` (edge switch disclosed per R1, max_skips 5, on_fail final STOP per R2); the lock sha matches the config.
- B5 done: attempt 3 passed. Env freeze == lock; fixture box gives 1736 chunks / 213 frames kept; real s3fd ran under torch 2.8; flat grey -> rc 10 s3fd_no_face.
- Departures: I endorse both. A pip mismatch -> STOP matches my ruling 6 and R2. Mel NaN -> STOP matches ruling 7. Gating articulation in the box is my ruling 5(b): a frozen mouth means the control failed.
- Non-blocking nit: the box matches the "Face not detected" substring on any exception type. It could be narrowed to the pinned ValueError.
- Before launch: freeze `refclips_d090` (commit) before running `--prepare`.
