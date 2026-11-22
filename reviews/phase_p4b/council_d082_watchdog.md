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

## Re-check + pre-launch (2026-11-22, at ed1e842): APPROVE
- **W1 closed.** BUG-041 logs the deviation, with a counts-only token audit (0 token-shaped strings in pod files, 0 in 72 SSM commands). The D-082 DECISIONS evidence line and d082_draft §7 withdraw the gate check as evidence. config.yaml is stated as not mirrored and never loaded.
- **W2 closed.** `check_buffer` now needs exactly 40 passes, or a logged `snapshot_exhausted` record whose counts match. It also refuses while the CPU stage is alive or the pod log differs from the committed one. Tests cover 39 refused, 39 with the record accepted, a count mismatch refused, and 40 accepted. The CPU stage is done: rc 0, 40/40.
- **W3 closed, and more.** Rehearsal run 3 at 72bd29d (run3_72bd29d.json) did (a) 40/40 files with wav shas, (b) the exact ship tarball with a fresh uv and venv, (c) a mirror sync that reproduces the four frozen shas, and (d) `nat0_box` on CPU on 3 wavs, rc 0. N3 returned a float, plus checks on offline, transcribe and dry rows. Runs 1 and 2 found the real defects BUG-042 and BUG-043, which would have cost a paid exit 75. Both are fixed test-first. L4 record: 2807 lines, no open or live instance, $0 campaign spend. 77 local NAT and freeze tests pass. The stale readiness doc is updated.
- Nit: `d7f2c62` is not a revision in this repo. The tests-first commit is 5582611. Nothing depends on it.
- **The rehearsal outcome changes no rule.** It covered 3 of the 40 buffer candidates on CPU int8: N1 p(en) was 0.20 and 0.69, one failed N2, and N3 was 0.2 on one mp4. That is outcome exposure on candidate data, so it cannot justify any change to N1 ≥ 0.9, N2, N3, the 40-buffer, nat_n 15, or their order. Any later change needs a new D- entry that discloses this exposure, and it is the owner's call. The rehearsal decisions are not session-0 rows (`log_unchanged: true`). Session 0 recomputes all 40 on the A100.
- **Launching is still the frozen next step.** The plan is: session 0, then rows logged, then 15 or more passes to proceed or fewer than 15 as a STOP to the owner. Skipping the launch because of a 3-clip CPU preview would itself be an outcome-driven deviation. About $1.5 against the $75 cap (projected ~$63 after) buys the full 40-row evidence the owner needs to decide.
- Pre-launch gates (orchestrator, none waived): CI green on HEAD and HEAD pushed; reconcile record still matching the ledger; terminator armed in its window; one instance; baseline once; cap guard; watched; terminate in `finally`.
- Expect STOP as a likely outcome. The driver logs the rows and exits 1. There is no in-session relaxation and no re-run of failed candidates.
