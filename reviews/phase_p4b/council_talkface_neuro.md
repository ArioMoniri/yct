# Council (neuro): TALKFACE pre-launch check (talkface_ready.md §2, 6e47278)

Verdict: **REVISE**. All 7 choices are acceptable for a 1-clip, internal-only, descriptive control, with the conditions
below. Launch stays disabled until they are frozen, `--prepare`/finish are wired and the CPU rehearsal passes. Ruled
outcome-blind: no GPU output exists, and nothing sealed, no labels or face pixels and no predictions were read.
Context: speech_build_v2 rc 0, QC pass 27 rows / 25 speech rows, video_identity diffs empty. The SPK/BURST path is sound to reuse.

1. Static frame without SHINE: ACCEPT. SHINE is a joint 60-image operation, so it is undefined for 1 image. Freeze it as
   disclosed. Record the face patch mean/RMS luma against the LOC-set mean (numbers only, descriptive). No re-normalisation after we see the result.
2. Wav2Lip driven by the clip audio (bed + speech, 16 kHz): ACCEPT. The mouth follows what TRIBE hears, and the mel-NaN
   failure on silence is avoided. Freeze the 16 kHz resampler and filter, and the sha of the derived wav.
3. Only in-window frames from Wav2Lip: ACCEPT, with one condition. The pasted mouth box is a Wav2Lip reconstruction, so
   it differs from the static frame even with no articulation. Each window onset and offset is then a step change in
   the box that coincides with speech onset (an audiovisual onset transient). Add a descriptive record of
   |first in-window frame - static| and |last - static| inside face_box. Freeze this choice now, and do not switch
   to full-length Wav2Lip later.
4. Lossless grey npz: ACCEPT. The box inlines a BT.709 formula and does not call locimg.grey709. Require a test
   that box frames equal static bit for bit outside face_box (grey-replicated PNG input). The final encode is the frozen SPK/BURST encode.
5. QC: ACCEPT the gates, but `lip_motion` (>= 1 frame != static) passes from reconstruction alone (see 3). Rename it
   `w2l_rendered` and keep it gating. Add descriptive, non-gating within-window articulation: mean |f_t - f_{t-1}|
   inside face_box. No YuNet: agreed.
6. Box env (py3.11, torch 2.8.0, librosa 0.9.2, ...): ACCEPT as a disclosed deviation from upstream. Freeze the
   pin list. The rehearsal pip freeze becomes the reference, and the GPU box freeze must match it apart from the CUDA
   build tag (mismatch = exit 75, not a skip). CPU and GPU numeric differences are not compared: descriptive role.
7. Skip mapping: ACCEPT. "Face not detected" maps to s3fd_no_face, any other Wav2Lip error maps to wav2lip_error, max 5,
   then STOP. Setup or transfer errors exit 75. Add: a NaN mel on the real clip maps to wav2lip_error (it does now) and must be
   logged, never retried with altered audio.

Freeze before launch: items 1-7 above as config keys (including the resampler, pin list, QC names, transient and articulation
descriptives), the rehearsal pip-freeze sha, and the mirror weights paths (§5 last bullet).
Minimum $0 pod-CPU rehearsal: the exact pins and `talkface_box --fixture-box` on a synthetic image with 3 s of bed + speech
audio. It must assert n_mel_chunks = n_frames_total, kept frames = window frames, outside-box bit identity, the loader strict
load, and the pip freeze written. Then `--prepare` on a synthetic face, followed by compose, QC, encode, a private upload
to a scratch mirror prefix, and the result JSON with numbers and shas only. No real face before the freeze.
Missing wiring (blocking): `--prepare` (main refuses), the post-session finish (compose/encode/QC/private upload),
and the committed talkface_inputs.json.

## Re-sign-off (talkface_v2.md, 7d640ab..132bdbe, config controls.refclips_d090): APPROVE
Items 1-7 are frozen as keys: no-SHINE static with luma_vs_loc reported; resample_bandlimited at 928000 pcm16; in-window only, with no switch to full length and edge_step descriptive; box grey709 with outside_face_box_static gating; w2l_rendered renamed; hashed lock 258c44ec.. matches the file, and freeze be658920.. matches the rehearsal record. Rehearsal attempt 3 passed all checks, including 1736 = 1736 chunks, kept 213, outside-box identity 213/213 and flat-grey s3fd -> exit 10.
On the departures from my positions, I accept both:
- (a) Mel NaN -> STOP instead of wav2lip_error. This is stricter. The clip audio includes the bed, so the case should not arise, and a STOP makes an audio-altering retry impossible.
- (b) Pip mismatch -> STOP instead of 75. This is also stricter, and the owner ruled it.
inbox_articulation as a gate: I accept it. The bar is low (at least 1 consecutive-frame diff per window). A fail is a final STOP, never the next face, so it cannot select on the outcome. Its only cost is a possible false "control failed", which is acceptable for a descriptive control.
Owner rulings R1 and R2 are implemented as disclosed.
Non-blocking (Commit A): fix the stale shas in §5 (14d34302.. / 3578d20d..) and the attempt commit in §8; confirm that decoded_vs_composed fills on the real clip.
Outcome-blind: I read nothing sealed, no labels, no faces and no predictions.
