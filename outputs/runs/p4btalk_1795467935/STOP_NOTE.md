# TALKFACE session 1 (p4btalk_1795467935): STOP, exit 1, nothing logged

- Launched at 46bda13 (CI green, run 45264007461) as instance ab0945da… (yct-p4b-ref-talk), after the pre-launch checks passed: projection $65.71 ≤ $75, L4 ledger current, no live instance. Terminated by the driver at job end (ledger `job_done`, ~510 s, ≈ $0.28).
- Steps setup_w2l, check_env (box freeze == hashed lock) and push_inputs were ok. In wav2lip, talkface_box exited 30 with `FileNotFoundError: talk/mirror/Wav2Lip-SD-NOGAN.pt`.
- Cause, BUG-049: the box chdirs into the Wav2Lip repo before resolving the relative paths that `wav2lip_cmd` passes. The rehearsal used absolute paths, so it never exercised this.
- Classified per D-090 as a STOP: no face skip, nothing in talkface_skips.jsonl, the face stays rank 499. No Wav2Lip output exists.
- The fix (paths resolved before the chdir, with a test) is committed. A re-launch needs the coordinator's go-ahead.
