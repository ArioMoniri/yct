# Council QA: D-082 draft (BUG-040) and T-NAT0 session-0 readiness (2026-11-22)

**Verdict: REVISE.** The D-082 approach is approved as drafted. Session 0 is not launch-ready because the real PodBox path has defects that the fakes cannot see.

## 1. D-082 (community-1 PLDA, load-only): acceptable
- The pin is an immutable 40-hex revision, the schema refuses a branch name, the download is limited to `allow_patterns=["plda/*"]`, and the `dir_sha` covers the plda dir. `check_mirror` now requires 4 shas before load. `patched_config` passes the PLDA explicitly and refuses non-Agglomerative clustering and an incomplete mirror. The session-0 gate needs `controls.refclips_d082` plus a set and frozen `pyannote_plda_sha256`. The two-commit freeze plan is correct.
- Pod verify (rc 0, 2 speakers, offline under 4.1.0) is good evidence that the pipeline loads. The `fixture_ok` check that requires exactly 2 speakers is a real tightening.
- The soundfile to `wave` fix is right. T1 sidecar wavs are `pcm_s16le` 16 kHz mono (normalize/core.py), and `read_wav` refuses anything else.
- Non-blocking: `plda_loaded`/`clustering` only shows that the PLDA was loaded. "Never applied" rests on reading the code. Cheap extra evidence: rerun verify with the PLDA files swapped for a different valid PLDA and confirm identical segments. Also disclose "head sha on 2026-11-22" in the report.

## 2. Session 0: blocking items (all in `PodBox`, scripts/gpu_p4b_nat0.py)
- **B1. Code not shipped.** `ship_code` ships `gpu_p0_rerun.SHIP`, and `PodBox.start` adds only `infra/gpu_deadman.sh`. Neither `src/yct/curate/` (`nat0_box.py`, `__init__.py`) nor `outputs/runs/wave1p2b_20261117T234829Z/wx_pip_freeze.txt` reaches the box. As a result, `setup_wx` (`pip install -r {b}/{FREEZE}`) and `nat0` (`python -m yct.curate.nat0_box`) both fail. Add both to SHIP, with a test that the shipped tarball contains them.
- **B2. No uv on a fresh box.** `setup_wx` calls `$HOME/.uvbin/uv`, which only `tribe_run/remote_setup.sh` installs, and session 0 never runs that script. Install uv the way remote_setup.sh lines 18-21 do, or ship and run that block.
- **B3. nat0.json gets truncated.** The results are read with `box.run("cat .../nat0.json")`, which goes through `pod()` (SSM stdout is truncated at 24,000 chars, as the `pod_file` docstring says). 40 wavs × ~100 language probs at `indent=1` comes to about 100 KB, so the read raises JSONDecodeError, the step becomes `box_failed`, and the session exits 75 after the GPU time has been spent, on every retry. Fix: copy the file box→pod over ssh and read it with `pod_file`, or write compact JSON and check its size. Add a test with a >24 kB result.
- **B4. CUDA libs not on the path.** The P2b precedent (gpu_wave1_p2b.py:262) exports `LD_LIBRARY_PATH=$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib` for the pinned WhisperX env. PodBox omits this for both `asr` and `nat0`, and `nat0` runs faster-whisper/ctranslate2 on cuda float16. Add the export to both steps.
- **B5. Readiness doc is stale.** t_nat0_ready.md §2/§3 still says "BUG-040 STOP" and "three pyannote shas". Update it to D-082: 4 shas plus the `refclips_d082` frozen row.

## 3. Minimum extra check before launch (fakes only so far)
1. A test that builds the actual ship tarball and asserts that `src/yct/curate/nat0_box.py` and the FREEZE file are in it (covers B1).
2. A pod CPU rehearsal at the launch commit: run `/work/yct/venv_wx/bin/python -m yct.curate.nat0_box --device cpu --shas <the frozen 4>` on 2 to 3 buffer wavs from `/work/yct/nat_scratch/t1/audio16k`. Then read the output back exactly as the driver does (covers B3 and the mirror and shas). In the same step, check that all 40 `<t1_name>.wav`/`.mp4` exist at those local paths and that each wav sha equals the log's `wav_sha256`.
3. B2 and B4 can only be exercised on a GPU box. They are acceptable in the watched session 0, where a failure gives exit 75 at a cost of about $1-3.

## 4. Tests and state
- `pytest -q tests/test_nat0_d082.py tests/test_nat0.py tests/test_gpu_p4b_nat0.py tests/test_natstim.py`: 55 passed.
- NAT log as committed: 39 CPU passes and 28 rejects. The buffer is not full, so the driver will not launch yet.
