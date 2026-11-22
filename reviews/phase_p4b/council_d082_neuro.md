# Council D-082 + T-NAT0 readiness: neuro member (2026-11-22)

**Verdict: REVISE.** D-082 itself is acceptable as drafted. Session-0 readiness has two blocking items.

## (1) D-082 (PLDA as a load-only dependency): acceptable
- Option (a) is the smallest departure from D-075. The 3.1 config is unchanged (AgglomerativeClustering, centroid,
  threshold 0.7046, min_cluster_size 12). In 4.1.0, the PLDA reaches the clustering only under VBxClustering, and
  `patched_config` refuses any clustering other than Agglomerative. So the N2 decision uses the same pipeline as before.
- The pin is a 40-hex revision. Only `plda/*` is mirrored, `dir_sha` is checked like the other three, and the plda key
  is in `PYANNOTE_KEYS`, `check_frozen` and `--shas`. Requiring the fixture to return exactly 2 speakers is better
  than the old "non-empty" check.
- `diarize()` uses `speaker_diarization`, the overlapping output, not the exclusive one. That keeps 3.x semantics for
  `main_frac` and `max_other_s`. Good.
- Non-blocking: (i) add a single-voice fixture expecting 1 speaker, which tests N2's pass side (a 2-voice A-B-A
  fixture only tests the split side). (ii) The §5 disclosure should also say that N2 ran 3.1 under 4.1.0, not
  the 3.x release it was published for, and on CUDA, while the verify ran on CPU.

## (2) Session-0 readiness: blocking items
- **B1. The box code does not ship `yct.curate`.** `PodBox.start` ships `gpu_p0_rerun.SHIP` plus
  `infra/gpu_deadman.sh`. SHIP has `src/yct/{__init__,config,media,config_schema}.py`, `tribe_run`, `transcribe` and
  the heartbeat script, but no `src/yct/curate/`. On the box, the `nat0` step
  (`python -m yct.curate.nat0_box`, PYTHONPATH={B}/src) therefore fails with ModuleNotFoundError. The result would
  be a paid launch, `box_failed`, exit 75, and a burned terminator fire time. The fakes cannot see this.
  Fix (test-first): append `src/yct/curate/__init__.py` and `src/yct/curate/nat0_box.py` to SHIP in
  `PodBox.start`. Add a test that builds the real `ship_code` file list and asserts it contains every module a
  box step runs (`yct.curate.nat0_box`, `yct.transcribe`).
- **B2. Launch only on a complete buffer.** `check_buffer` accepts 1–40 passes. If session 0 runs on a partial
  buffer and gets fewer than 15 passes, it logs session-0 rows. Those rows then refuse every later session 0, so
  the rest of the 40-buffer can never be evaluated, which contradicts D-075 §3 ("fewer than 15 in the 40-buffer").
  Fix: refuse unless `len(buf) == cpu_buffer`, or unless the CPU stage has finished with the snapshot exhausted
  (natcpu.rc == 0 plus an exhausted marker in the log). Add a test for each case.
- **B3. Minimum real-path check before launch** (pod CPU, $0, no Lambda launch, done after the D-082 freeze commits):
  1. Build the exact `ship_code` tarball and untar it into a fresh temp dir on the pod.
  2. Run the exact `push_buffer` S3 sync of the mirror. Then run `/work/yct/venv_wx/bin/python -m
     yct.curate.nat0_box --device cpu` with PYTHONPATH=<tmp>/src, the frozen `--shas` JSON, and 2 real buffer wavs
     from `/work/yct/nat_scratch/t1/audio16k`. It must exit 0, which proves `check_mirror` passes with all four
     shas, `read_wav` accepts real T1 PCM16, and N1 and N2 both run.
  3. Feed that JSON, plus `PodBox.n3` on the same 2 T1 mp4s, to `ns.session0_rows` in a dry call that writes no
     log rows.
  4. Assert that the wav and mp4 exist for every buffer `t1_name`, and that each wav's sha equals its logged
     `wav_sha256`.
  5. Commit the output as a pod log. This would have caught B1.
- After that, use the D-071 (k) launch as written: CI-green pushed HEAD, a new terminator, L4 reconciliation, the
  baseline written once, and the cap guard.

## Re-check + pre-launch (2026-11-22, at ed1e842): APPROVE
- B1 fixed: `EXTRA_SHIP` adds `src/yct/curate/{__init__,nat0_box}.py` and the freeze; the import-closure test
  checks the real tarball; rehearsal run 3 ran `nat0_box` from the untarred ship tree (rc 0). B2 fixed:
  `check_buffer` refuses unless 40/40 or a logged `snapshot_exhausted`; the buffer is 40/40, 0 session-0 rows.
  B3 done as runs 1-3 (a-h). Runs 1-2 found BUG-042 (wrong embedding loader, which would have cost a paid
  exit 75) and BUG-043 (OOM). Both fixed test-first. BUG-042's `{checkpoint}` loader is the one the D-082
  verify used, so that 2-speaker evidence stands. L4 record: 2807 lines, no open or live launch, $0 campaign.
  (d7f2c62 is not in this repo. Every other listed commit checked.)
- No frozen value changed after the rehearsal: config.yaml and DECISIONS are unchanged since f4211ea, and the
  NAT log sha is 4d1cd61f (unchanged). Non-blocking: the run-3 reject reasons look like real signal, not a
  pipeline fault. 5c57 has p(en) 0.20 and 0 pyannote turns (no speech in the first 30 s). 192a has 0.69 with 15
  turns. 3e8d has 0.999 but fails N2. N3 is 0.2 on one mp4.
- The rehearsal must NOT change any rule. It is outcome-exposed. It covers 3 of 40 clips on CPU int8, not the
  frozen CUDA fp16 path. It is not a decision. N1 0.9, N2 95%/3 s/zero speech, N3 0.5, nat_n 15 and the
  40-buffer stay as frozen. Changing any of them now would fit the rules to seen outcomes.
- Launch is still the frozen next step. The <15/40 STOP is defined on session-0 output, not on a forecast.
  Session 0 is the only way to reach that decision under the rules. It costs about $1.5 (planned $3.48), against
  a projected $63 of the $75 cap. If it yields fewer than 15 passes, the rows are logged, exit 1 and a STOP to the
  owner, with no relaxation and no second session 0. Telling the owner about the early warning before launch is
  a courtesy, not a gate.
- Verdict: APPROVE. No blocking items. Launch under D-071 (k): CI-green pushed HEAD, a new external terminator,
  the L4 record re-checked at launch, the baseline written once, the cap guard, and a watched run.
