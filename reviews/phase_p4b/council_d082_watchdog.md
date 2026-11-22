# Council D-082 + T-NAT0 readiness: watchdog (2026-11-22)

**Verdict: REVISE.** The D-082 substance is sound. There are three blocking items: one procedural item on D-082 and two on the launch path. Inputs read: d082_draft.md, BUGS.md BUG-040, the diffs d30175d/4129e8b/78d09e3/5a9992e, t_nat0_ready.md, scripts/gpu_p4b_nat0.py, tests/test_gpu_p4b_nat0.py, d075_final.md §3, DECISIONS D-071 (k), and the NAT log counts only (67 cpu rows, 39 passes). No sealed data, labels, transcripts or predictions were read. The local tests pass: test_nat0_d082 + test_gpu_p4b_nat0 + test_nat0, 42 passed.

## (1) D-082: community-1 PLDA pinned as a load-only dependency
- **Sound.**
  - The pin is an immutable 40-hex revision, and only `plda/*` is mirrored.
  - It is passed explicitly, so 4.1.0 never falls back to the hub default.
  - `patched_config` refuses a clustering other than AgglomerativeClustering and refuses an incomplete PLDA mirror.
  - `pyannote_plda_sha256` is part of the session-0 freeze gate.
  - The schema has Literal guards.
  - The fixture now needs exactly 2 speakers, a real fix: before, any non-empty output passed.
  - The soundfile to wave fix was found by the real env, which is the right outcome.
  - The pod evidence (`plda_loaded: true`, `clustering: AgglomerativeClustering`) matches the code path.
  - The two-commit set-then-freeze plan matches D-075.
- **BLOCKING W1, token rule deviation.** D-075 §3 says agents "never test gate access with the token". D-082 §1 ("Gate check on the pod: with the owner's token … API returned HTTP 200 … plda.npz … config.yaml all returned 200") records exactly such a test. Before acceptance:
  - log it as a deviation (BUGS entry or a D-082 §1 note);
  - confirm from the pod shell history and logs that the value was never echoed or written outside the shredded umask-077 file;
  - drop the gate-check line as acceptance evidence. The mirror shas plus the offline verify are the evidence.
  - Also: `config.yaml` was fetched but is not mirrored (only `plda/*`). State that it is not used.
- Non-blocking: in the commit-k row for D-082 in DECISIONS, keep the wording "loaded, never applied; any VBx path is refused", and keep the §5 disclosure as written.

## (2) Session-0 pre-launch readiness
- **The preflight is correct, but only against fakes.** It covers the frozen rows (now including refclips_d082 and all four shas), the limits (1.75 h, $8, price × h), the terminator window and re-arm, HEAD == CI-green and pushed, one instance at a time, the baseline written once before the first prefixed launch, the $75 cap guard, and the 75/1 exits with terminate in `finally`. This matches D-071 (k) and D-075 §3.
- **BLOCKING W2, partial-buffer launch.** `check_buffer` accepts any 1..40 CPU passes, and `buffer_ids` returns a short buffer "as is". The CPU stage is at 39 of 40 and still running. A session 0 launched now would permanently fix a 39-candidate buffer, because session-0 rows block re-evaluation, and that deviates from D-075's fixed 40. Required:
  - refuse unless len(buf) == `cpu_buffer`, or the log carries an explicit snapshot-exhausted terminal record from `run_cpu`;
  - add a test for the 39-pass case.
- **BLOCKING W3, real PodBox path untested.** Minimum check before launch, on the pod, no GPU, at the launch commit (record the output in t_nat0_ready.md):
  - (a) For every buffer `t1_name`: `/work/yct/nat_scratch/t1/audio16k/<t1>.wav` and `t1/<t1>.mp4` exist (the paths `push_buffer` and `n3` hard-code); the wav sha equals the logged `wav_sha256`; and `nat0_box.read_wav` accepts it (PCM16, mono, 16 kHz).
  - (b) `aws s3 sync` of `models/pyannote/` into a temp dir, then `check_mirror` against the four shas about to be frozen. This is the exact JSON that `PodBox.step("nat0")` builds.
  - (c) `venv_wx/bin/python -m yct.curate.nat0_box --wavs <2 buffer wavs> --mirror <tmp> --shas '<json>' --out x.json --device cpu` exits 0, with numbers only in x.json.
  - (d) `PodBox.n3` on one buffer mp4 returns a float.
  - The ssh, deadman and setup_wx parts reuse the P2b box pattern that ran for real, so a watched first launch covers them.
- Non-blocking: t_nat0_ready.md is stale (dated 11-21, "BUG-040 STOP", three shas). Update it to D-082 and four shas when W2 and W3 are done.
