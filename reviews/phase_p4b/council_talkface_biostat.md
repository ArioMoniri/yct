# Council pre-launch check, TALKFACE (D-085 part 2 step 4): biostat member

Read: talkface_ready.md, 6e47278 (driver, box, helpers, tests), config.yaml talkface block, speech_build_v2 numbers (rc 0; QC pass 27 rows, 25 speech rows; SPK 20/20, BURST 5/5). Sealed data, the face image, labels and texts not read. TALKFACE is 1 clip, internal, descriptive, so no choice below can move an inferential estimate. Every ruling is fixed here, before any GPU output, and none may be revisited after one.
**Verdict: REVISE.** All 7 choices ratified, 2 with amendments. Launch is blocked until the items at the end are met.

## Rulings on the seven choices in §2 (outcome-blind)
1. Still frame without SHINE: RATIFIED. SHINE is a joint operation over 60 images, and applying it to one image would be a new method. Disclose that TALKFACE luminance is not matched to LOC. --prepare records the static frame's mean and SD luminance next to the LOC SHINE targets (descriptive). No TALKFACE-vs-LOC contrast may be reported inferentially. Owner must confirm where the crop_box for row 499 comes from (the T-LIC crop on the v4 log row) and that it is frozen in talkface_inputs.json.
2. Wav2Lip driven by the clip audio (bed + speech): RATIFIED. TRIBE hears the same signal, which avoids an audio/video mismatch confound. Freeze the 48k -> 16k path: refclips58.resample_bandlimited, the same op as selection_sr. Freeze clip16k.wav at exactly 16000 Hz so the pinned audio.load_wav does no second resample. Record the clip16k sha.
3. Wav2Lip frames only inside the windows [onset, onset+span): RATIFIED. Disclose that Wav2Lip regenerates the whole s3fd face box, not only the mouth, so each window edge has a step change over the face box. Add 2 descriptive numbers per window: the face-box |diff| at the first in-window frame, and the mouth (lower-half) vs upper-half MAD. Neither gates.
4. Lossless frames (npz, grey uint8): RATIFIED. It drops one lossy step and changes only the container. Amendment: the box's inline luma must equal locimg.grey709, i.e. talkface.to_grey (add a unit test), or it must call it.
5. QC gates: RATIFIED as a pipeline-sanity gate only. lip_motion (at least 1 differing frame) passes almost trivially because the face box is resynthesised, so state that. Add 2 gates: n_mel_chunks >= the last in-window frame + 1, and n_frames_total == n_mel_chunks. YuNet not run: agreed.
6. Box env (torch 2.8.0, etc.): RATIFIED, because it is the env the loader check passed (352/352 keys, max diff 0.0). Freeze the TALK_PIP list as written, plus the torch wheel index/CUDA tag. Commit the pip freeze and its sha with the result. Torch's transitive dependencies are not pinned, so diff the box freeze against the rehearsal freeze and record it (not gating).
7. Skip mapping: RATIFIED WITH NARROWING. An infrastructure error must never use up a face, because a face changed after a non-face error is an analyst degree of freedom. As written, any exception in the "wav2lip" step becomes wav2lip_error. That covers sha mismatches, box.wait timeouts, CUDA OOM and the ssh copy of frames.npz. Freeze this mapping instead:
   - "Face not detected" -> s3fd_no_face.
   - An exception raised inside the pinned inference, datagen or forward, or "Mel contains nan" -> wav2lip_error.
   - A weights/s3fd/loader sha mismatch -> STOP (exit 1, nothing logged).
   - Timeout, OOM, CUDA error or transfer failure -> infrastructure (exit 75).
   talkface_box must exit with distinct codes for these cases, and the frame pull must move out of the skip-classified block.

## Minimum before launch (blocking)
- B1: Freeze rulings 1-7 in config.yaml (incl. resampler, crop_box source, skip exit-code map, TALK_PIP + wheel index) and commit.
- B2: Wire --prepare: static.png, clip48k + clip16k, windows from the frozen D-089 selection, private upload, talkface_inputs.json with shas only. Test it.
- B3: Wire the post-session finish on pod CPU: load the npz, check its sha against w2l_record, compose, QC including the speech gate, encode to the frozen clip codec, private upload, public_numbers. Test it with the real file I/O.
- B4: $0 CPU rehearsal (T-NAT0) of the exact box env and `talkface_box --fixture-box` on a synthetic image. Use a 58 s synthetic bed, not 3 s, so the 1740-frame/mel-chunk count and the window indices are exercised. Then run finish on that output end to end. Record numbers only.
- B5: Confirm the weights and s3fd are at mirror_s3/weights/ with matching shas (listing + sha, no download into git).
- B6: Implement the narrowed skip mapping (ruling 7) and add tests for each class.
