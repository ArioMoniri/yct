# Council (watchdog): TALKFACE pre-launch check, talkface_ready.md §2 at 6e47278. Verdict: REVISE (no launch yet)
Read: talkface_ready.md, 6e47278, config talkface, speech_build_v2 numbers (rc 0; 27 rows pass, SPK 20 + BURST 5). Not
read: sealed data, labels, transcripts, texts, face image, predictions. No GPU output exists: all rulings outcome-blind.
1 Still frame without SHINE: RATIFY, disclosed; commit its mean/sd luma beside the LOC set's (numbers). No retro match.
2 Wav2Lip driven by the clip audio (bed+speech -> 16 kHz): RATIFY. FREEZE the 48->16 kHz resampler (function, filter,
  int16 rounding) in --prepare; record its sha.
3 Only in-window frames from Wav2Lip: RATIFY. Blocking defect: 58 s at 16 kHz gives 4641 mel frames, so the pinned
  chunking gives ~1736 chunks, not 1740. Frames >= ~57.87 s cannot come from Wav2Lip and the tail chunk is
  misaligned. --prepare must refuse if max(window end) > (n_chunks-1)/30, and the record must hold n_chunks.
4 Lossless grey npz instead of the DIVX avi + ffmpeg mux: RATIFY. The box luma is inline; it must equal locimg.grey709
  bit for bit (rehearsal check).
5 QC: REVISE. "Out-of-window == static" holds by construction in compose (tautological), and ">=1 frame differs" is
  true for any Wav2Lip regen, so it shows Wav2Lip ran, not lip motion. Rename it wav2lip_applied. ADD two gating
  checks: (a) in-window pixels outside the recorded face_box == static; (b) the encoded clip decodes to the composed
  frames within the frozen SPK video_identity tolerance, same encoder. Mouth frame-to-frame diff: descriptive.
6 Box env (py3.11, torch 2.8.0 = loader-check version, librosa 0.9.2 ...): RATIFY as a disclosed deviation from
  upstream pins. FREEZE TALK_PIP in config (now a script constant); commit the pip freeze sha; resolver drift = STOP.
7 Skip mapping: REVISE. Every exception in the "wav2lip" step now becomes wav2lip_error and uses up a face. That
  includes the frame scp back to the pod, box.wait timeouts, ssh drops, CUDA OOM, loader sha mismatch and "Mel contains
  nan", none of which depend on the face. Rule: "Face not detected" -> s3fd_no_face (skip). A traceback raised
  inside pinned datagen/forward for this face -> wav2lip_error (skip). Loader/sha/mel-nan/import errors -> STOP
  (exit 1, nothing logged). Transfer/timeout/ssh -> 75. Split the frame copy out of the skip-classified block.
Blocking before launch: (i) freeze rules 2, 3-guard, 5, 6, 7 in config (one commit, council-referenced);
(ii) wire --prepare (48k render, 16k input, static png from the sha-verified source, windows, n_chunks guard, private
upload, talkface_inputs.json shas only); (iii) wire finish (pull frames, compose, encode with the SPK/BURST encoder,
QC incl. 5a/5b + speech gate, private upload, commit numbers only), with a test on fixture frames;
(iv) $0 pod-CPU rehearsal: exact pins, talkface_box --fixture-box on a synthetic image + 3 s audio -> luma identity,
outside-box identity, n_chunks; plus one s3fd run on the synthetic image with the real mirrored s3fd, which must
classify as s3fd_no_face; then finish end to end on those frames (numbers only, no real face);
(v) confirm mirror_s3 weights/ path + NOGAN/s3fd shas from the pod. Then CI-green HEAD; launch per §3-4.
