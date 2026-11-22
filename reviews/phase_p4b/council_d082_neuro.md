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
