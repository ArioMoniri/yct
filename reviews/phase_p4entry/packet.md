# Council — Gate P4-entry (wave 1: may full TRIBE inference T1/T3 + ablations start?)
Branch head: see `git log -1`. Protocol docs/prompts/v2.md (v2.6); ROADMAP.md P2/P2b/P3/P4/P4b.
Evidence: DECISIONS D-060 (P2/P3), D-061 (WhisperX pin), D-062 (P2b + P4 prereqs); BUGS BUG-018 status (GPU verified), BUG-027 (orphan instance; sweep + dead-man fix); ENHANCEMENTS ENH-002 status (latency dry run), ENH-008 (caption flag not implemented).
Run dirs: outputs/runs/wave1_p2p3_20261117T202935Z, wave1p2b_20261117T234829Z, wave1p2b_20261118T000623Z (aborted), wave1p2b_20261118T002855Z.
Data (label-free): data/wave1_normalize_qc.csv, data/wave1_confounds_summary.csv, data/wave1_transcripts_summary.csv, data/manifest.csv (analyst view).
Code: src/yct/{normalize,confounds,transcribe,tribe_run}, scripts/gpu_wave1_p2b.py, scripts/wave1_p2b_pod.py, infra/{lambda_gpu.py,gpu_deadman.sh}; tests/.

Decisions requested (label-blind; nothing unblinded):
Q1 GO / FIX / STOP for full wave-1 TRIBE inference (T1 + T3, ablations audio/video/text) on the analysis set.
Q2 yct_0644 (no source file; sealed URL failed): pre-unblinding exclusion (reason source-unavailable) if not obtained before P4 inference starts? N becomes 52 (T1: 51 after yct_0483).
Q3 sub-16 fps sources (yct_0626 12.5 fps, yct_0641 15 fps; CFR-30 upsampled by duplication): keep + `low_fps_source` flag + sensitivity re-run excluding them (proposed D-060), or exclude, or other?
Q4 ENH-002: V1–V3 flash response is weak/flat; MT+/FFC respond more. Pre-lock choice for the P4b visual low-level control: keep V1–V3 (risk STOP at P4b), switch to MT+ fallback, or luminance-only kernel? Must be fixed before P4b lock and before any label is seen.
Q5 WER: hand-checked references pending (human). Blocking for P4 or only for P5/report?
Q6 ENH-008 caption flag not implemented: blocking for P4, P5, or limitation only?
Q7 BUG-027 fix adequate (driver still runs in the session container; dead-man halts box, sweep terminates at next start)?
Q8 Anything else that must be fixed before P4 inference (determinism gate passed 3/3 at ≥0.999; BUG-018 verified; cache archived to S3).
