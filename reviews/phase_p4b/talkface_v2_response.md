# TALKFACE v2: response matrix (council wf_f194ca9f-6a0, `council_talkface_*.md`)

Owner rulings, 2026-11-23:
- **R1 "Accept both":** no SHINE on the still frame, and the edge switch at each window, both disclosed.
- **R2 "As reviewers propose":** the narrowed failure mapping, and a QC fail is a final STOP.

| Member | Item | Response | Where |
|---|---|---|---|
| Watchdog | Rule 1: luma/contrast reported next to the LOC values | Done, descriptive (`static_luma_vs_loc` in the inputs record) | `talkface.static_luma` |
| Watchdog | Rule 2: freeze the 48→16 kHz resampler | `d090.driving_audio.resampler = refclips58.resample_bandlimited`, pcm16, n = 928000 | config, `prepare_inputs` |
| Watchdog | Rule 3 (blocking): 1736, not 1740 | `expected_n_chunks` (pinned loop, tested); `--prepare` refuses a window ending after 1735/30 s; the record holds n_chunks | `talkface.py`, tests |
| Watchdog | Rule 4: box luma == grey709 bit for bit | The box calls `locimg.grey709` (`box_grey`); there is a test, and the rehearsal checks outside-box identity | `talkface_box.py` |
| Watchdog | Rule 5: outside-face-box gate, decode gate, rename to wav2lip_applied | `outside_face_box_static` and `decode_identity` gate. The rename is **`w2l_rendered`** (neuro's name; same meaning, sanity only) | `talkface.qc` |
| Watchdog | Rule 6: TALK_PIP into frozen config, pip freeze sha, drift = STOP | Hashed lock `infra/talkface_lock.txt` (sha in `d090.env`); reference freeze sha; `check_env` → STOP | config, `gpu_p4b_talk.check_env` |
| Watchdog | Rule 7: narrowed skip mapping, frame copy out of the skip block | Box exit codes 0/10/30. Only 10 is a skip (R2). The copy-back is its own step, `fetch_frames` (→ 75) | `talkface_box`, `run_session` |
| Watchdog | Wire --prepare, finish, rehearsal, mirror confirmation | Done (§7, §8); mirror at the root, confirmed | `talkface_v2.md` |
| Referee | Rule 3: disclose the box-shaped step at onset; descriptive step metric | `edge_step` (onset/offset vs static inside the box), descriptive; disclosed (R1) | `talkface.qc` |
| Referee | Rule 5: outside-face-box gate + chunk/kept counts; QC fail = STOP to owner | `outside_face_box_static`, `n_mel_chunks`, `kept_frames` gate; `d090.qc.on_fail = final_stop_owner_control_failed` | config, `qc` |
| Referee | Rule 6: exact wheel and CUDA tag, hashed lock, launch gated on freeze; s3fd under weights_only proven | Lock with hashes (`--require-hashes --no-deps`); probe torch 2.8.0+cu128 / CUDA 12.8; s3fd proven in rehearsal step 3 | `d090.env`, rehearsal |
| Referee | Rule 7: only "Face not detected" is a skip; mel NaN is STOP | Done (R2) | `classify_box_exit` |
| Referee | Q: crop_box source, encode, mirror paths, wheel index | `talkface_v2.md` §6 | |
| Biostat | (see the journal; same points as watchdog/referee on the counts, the gates and the narrowed skips) | Covered by the rows above | |
| Neuro | Freeze items 1–7 as keys | `controls.refclips_d090` (frozen after re-sign) | config |
| Neuro | Rename lip_motion → w2l_rendered; descriptive articulation | Renamed and gating as a sanity check. **Articulation is gating** (`inbox_articulation`) as QA asked; neuro proposed descriptive. A frozen mouth means the lip-sync failed, so the gate stays | `qc` |
| Neuro | Box frames == static outside face_box, bit for bit (test) | `outside_face_box_static` gate + box_grey test + rehearsal | |
| Neuro | Rehearsal: n_mel_chunks == n_frames_total, kept == window frames, strict NOGAN, pip freeze written | Rehearsal steps 0–2 | `rehearsal.json` |
| Neuro | Rule 6: pip-freeze mismatch = exit 75 | **Not adopted.** A mismatch is a STOP, per QA and R2 ("sha / integrity → STOP"). Dissent noted | `d090.env.on_freeze_mismatch` |
| Neuro | Rule 7: mel NaN = wav2lip_error | **Not adopted.** Mel NaN = STOP (R2; watchdog, referee, QA). Dissent noted | `d090.skips.stop` |
| QA | B1 prepare, B2 finish with tests | Done, fixture tests with real ffmpeg | `tests/test_talkface_v2.py` |
| QA | B3: only a non-zero talkface_box exit may map to a skip; timeout/ssh/copy = 75; mel NaN STOP; replace the vacuous gate | Done | `run_session`, `qc` |
| QA | B4: freeze rulings 1–7 | `refclips_d090` (freeze after re-sign) | |
| QA | B5: rehearsal (fixture box; real s3fd under torch 2.8 → s3fd_no_face; compose, QC, encode; numbers only; mirror path) | Done; attempt 1 found BUG-046 (setuptools / pkg_resources), fixed; attempt 2 results in `talkface_v2.md` §8 | `outputs/runs/talkface_rehearsal/` |

Other changes:
- **Existing tests:** `tests/test_gpu_p4b_talk.py` follows the amended behaviour:
  - the fake box returns the record at `fetch_frames`, and the no-face case raises `BoxExit(10)`;
  - the QC calls use the new signature and key names (`outside_window_static`, `w2l_rendered`);
  - `classify_box_exit` replaces `classify_failure`;
  - the setup script asserts the hashed-lock install.

  The same number of assertions is kept.
- **New tests:** 37 in `tests/test_talkface_v2.py`.
