# QA / software engineering — Gate P4-entry

Reviewer: QA. Scope: `git log 0a65e75..HEAD` (4db5895 … 421c7ef). Read-only: git, grep, pytest, guards, `gh run`. No AWS/Lambda calls, nothing decrypted, nothing edited except this file.

## Verdict

**Q1: FIX.** The evidence the gates rest on holds up:
- D-038 Gate 1 passed 3/3: cached reruns gave identical `pred_sha256` with `cache_reused` true.
- D-038 Gate 2 passed 3/3: fresh-extraction reliability was ≥ 0.99903.
- BUG-018 is verified on the GPU (160 s and 110 s clips: n_words equals the .tsv row count, 0 duplicates, T within 1).
- The WhisperX pin was enforced at run time and recorded.

The code path for full wave-1 inference, however, does not exist yet:
- there is no batch driver;
- there are no ablations;
- runs cannot be resumed;
- cached features cannot be restored onto a new box.

CI has also been red on every commit in the range. Nothing found invalidates the P2b/P4-prerequisite results, so this is not a STOP. GPU inference should start only after the blockers below are fixed (D1, D2, D3, D5, D8/D9).

## What was checked

| Check | Result |
|---|---|
| `python -m pytest -q` (local, py3.13) | **619 passed**, 0 skipped, 8 warnings (enh002 empty-mask RuntimeWarnings), 213 s |
| `scripts/check_*.py` (all 7, base EMPTY) | all rc 0; `check_test_weakening --base 0a65e75` rc 0 |
| Test diffs in range | additions only; no assert, test or tolerance removed or loosened |
| `ruff check .` | **6 errors**, so CI fails (D2) |
| CI (`gh run list`) | **failure on all 7 pushes since 0a65e75** (Lint step); last green run was 44169384072 (D-059) |
| Run-dir provenance | `cmd`, `git_sha`, `config_sha`, `exit_code`, `metrics.json` (dirty False, diff sha, pip_freeze sha, lock sha), `pip_freeze.txt`, `stdout.log`; aborted run has an ABORTED_NOTE and no exit_code (correct) |
| WhisperX pin | config 3.8.6. Enforced by the box `assert v == "3.8.6"` (wxsetup) and `check_whisperx_pin`. Recorded in `whisperx_run.json` (3.8.6, faster-whisper snapshot edaa852e…) |
| Sweep / terminate scope | `list_ours()` filters names starting `yct-`, and `terminate()` re-reads the name and refuses anything else. The new test covers non-yct, terminated and kept instances. A non-yct instance cannot be terminated. |
| Spend (ledger, local read) | $9.23 of $200 |

## Q7 — Is the BUG-027 fix adequate?

**Partly. It stops the compute, not the billing.** It is acceptable for P4 only with D3 fixed, or with the residual risk explicitly accepted by the owner.

What works:
- The dead-man logic is correct. A missing touch file reads as age 0, which triggers shutdown (fails safe). The grace period is 1200 s against a 60 s touch interval. The hard cap is `max_hours`.
- The dead-man test is genuine: one case halts on a stale touch, the other halts on the hard cap.
- Sweep at driver start, followed by "refuse if anything is still live", is correct, and it cannot touch non-yct instances.

What remains:
1. **Billing continues after the halt.** Lambda bills a halted instance until it is terminated. Termination can only come from (a) `watch`, which runs in the same container and dies with it, or (b) the sweep at the *next* driver start. If no session starts again, an orphan bills without limit.
2. **There is no dead-man during the first ~5–30 min after launch.** That window covers boot, the ssh wait, `ship_code` and the heartbeat start, and no reaper survives a container death in it.
3. **Sweep kills any live yct-\* instance, including a legitimate concurrent run** (D4).

For P4, which needs about 4 sessions (see D1), this exposure recurs every session.

## Q8 — What else must be fixed before P4 inference

D1, D2, D3, D5, D8 and D9 must be fixed. D6 and D7 should land with the P4 driver. The rest are Low or carry-overs.

## Defects

**D1 — Blocker (P4 start). There is no P4 inference code path.**
- `run_clip.py` handles one clip, with no ablation option.
- `gpu_wave1_p2b.py` is P2b-specific.
- `grep -i ablat` matches only a comment in `feature_cache.py`.

Missing pieces:
- (a) A batch driver over the analysis set × {T1, T3} × {full, audio, video, text+TTS}, via `config_update={"data.features_to_use": [...]}` (v2.md P4).
- (b) **Resumability**:
  - a job manifest whose rows record the pred sha256, so finished jobs are skipped;
  - per-job copy-back to the pod. Today results are copied only at the end, so a crash loses the whole session, as in BUG-027.
- (c) **Cache reuse across sessions.** Restore entries from pod `/work/yct/cache` or S3 to the box, verified against the manifest (see D9).
- (d) **Session planning and a cost guard.** Extraction measured about 300 s per 58 s clip, so 106 T1+T3 extractions take about 8.8 GPU-h. Text+TTS adds new extractions if its input differs. In total this is about 9–13 GPU-h, roughly $20–30. That needs at least 3–4 sessions under the 4 h cap, with a pre-flight projected-cost check against the remaining budget.
- (e) QC (finite values, shape, T, outliers), `test_tribe_outputs`, and the ROADMAP test "exactly one Audio and one Video chunk per T1 clip".
- (f) ROADMAP P4 says "T1/T2", while the packet and v2.md §3 say T1, T3 (v2.md also includes T2). The scope needs one decision.

Fix: write `scripts/gpu_wave1_p4.py` on the `gpu_wave1_p2b` pattern, with a pure-CPU job planner, skip and resume logic, and ablation `config_update`. Test it with mocks (planner, resume skip, ablation config, QC failure → exit 1).

**D2 — High. CI has been red since 0a65e75.**
`ruff check .` fails with:
- `tests/test_infra_guards.py:296` E501 (new in 2d9f4fc);
- `outputs/runs/wave1_p2p3_20261117T202935Z/wave1_p2p3.py:8` F401;
- four E501 errors in `wave1_summ.py` in the same directory.

Lint runs first, so pytest, guards and gitleaks have **not run in CI on any commit in the range**, and both GPU runs were launched from red commits.

Fix:
- wrap the docstring at line 296;
- add `"outputs"` to `[tool.ruff] extend-exclude`, because run-dir script snapshots are provenance and must not be edited;
- add "CI green for HEAD" as a driver pre-flight or checklist item.

**D3 — High (cost). Nothing outside the container terminates an orphan (Q7 items 1–2).**

Fix:
- put the deadline in the instance name (e.g. `yct-p4-<runid>-dl<epoch>`);
- add `lambda_gpu.py reap --name-deadline`, which needs no ledger. Today `reap` treats an instance missing from its ledger as past deadline, so a pod-side reaper without the ledger would kill live runs.
- run that reaper outside the session container, either from a pod cron or from a one-shot scheduled task at deadline + 15 min that runs the sweep.
- start the dead-man before `ship_code` (as the first ssh command) to shrink the unguarded window.
- add a test for name-deadline parsing and reaping.

**D4 — Medium. Sweep has no ownership or liveness check.**
Every live `yct-*` instance not in `keep` is terminated, which includes a concurrent legitimate driver from another session.

Fix: add a run lock (pod lockfile with run_id and driver touch time), or before sweeping, check that the box touch file is older than `DEADMAN_GRACE_S`. Require `--force` for the CLI `sweep`. Add a test where a fresh lock or touch is kept.

**D5 — Medium. The driver's exit code ignores the gates.**
`bad` checks only the step return codes. The run still exits 0 when any of these happen:
- `gates[bug018_*].pass` is False;
- `d038_*.cached_rerun_bit_identical` is False;
- `fresh_gate_pass` is False;
- a gate is missing, for example because the real step was skipped or the sha check failed.

This run passed every gate, so the results stand, but the P4 driver must fail closed on gates and QC.

Fix: `exit 1` if any gate is False or any expected gate is missing. Add a CPU test of `post()` with a failing gate.

**D6 — Medium. No tests cover the new driver and pod scripts.**
None of these are exercised by `tests/`:
- `sanitize_run`: privacy, since feature-file names of real clips contain transcript text;
- `short_extractor`;
- the gate logic in `post()`;
- `persist_cache` manifest parsing;
- `wave1_p2b_pod.ingest`: T3-stem copy, flags;
- `confounds()`: idempotence through the `.pre_p2b` backup;
- `wer_score`: the P2 DoD metric;
- `make_reference_clips`: whether onsets agree with the `.tsv` and `enh002.json`.

Fix: add CPU unit tests, for example:
- `wer_score("a b c", "a x c") == 1/3`, empty hyp → 1.0, case and punctuation folding;
- `sanitize_run` output has no key or value from `feature_sha256` or `events`;
- `ingest` on a fake JSON dir writes both the T1 and the T3 tsv;
- running `confounds` twice gives identical output.

Use mocks or monkeypatching, not skips.

**D7 — Medium. The WhisperX pin is enforced in practice but weakly tested and not reproducible.**
- (a) `transcribe_whisperx_batch` skips `check_whisperx_pin` whenever a `runner` is injected, so the pinned path has only the "not installed → raise" test. Fix: call `check_whisperx_pin` unconditionally, and add tests that monkeypatch `_installed_whisperx_version` to "3.8.6" (passes) and "3.8.5" (raises).
- (b) Only whisperx is pinned. The other wxvenv packages are resolved at install time (`uv pip install whisperx==3.8.6 pyyaml pydantic`), and `wx_pip_freeze.txt` is recorded but not installed from. The faster-whisper snapshot revision is recorded but not checked. Fix: commit the freeze as a lock and install with it, then put `model_revision` in config and assert it against `hf_snapshot_revisions`.

**D8 — Medium (P4 provenance). The S3 cache manifest is overwritten on every persist.**
`persist_cache` uploads `TAR_SHA256SUMS` and `FILES_SHA256SUMS` to the same `feature_cache/` root on each run. After P4 sessions 2–4, `files_manifest_sha256` describes only the last session, while v2.md requires one manifest hash in the prereg and in every run's provenance.

Fix:
- write per-run manifests under `feature_cache/manifests/<run_id>/`;
- keep a cumulative append-only index;
- refuse to overwrite an existing `<key>.tar` whose sha256 differs.

**D9 — Medium. Restoring the cache is not implemented or round-trip tested.**
The tars exclude media, but `FeatureStore.verify` hashes all of `input/`, including the clip copy. A restored entry therefore fails `FeatureCacheError` unless the media is re-inserted from `/work/yct/norm`.

Fix: add a `restore_entry(tar, media_src, manifest)` that checks `FILES_SHA256SUMS`, plus a CPU test: tar → restore → `verify` → `predict_cached` identical.

**D10 — Low. Provenance gaps.**
- The transcripts and refreshed confounds used downstream come from `wave1p2b_20261117T234829Z`, which has **exit_code 1**. Its ASR steps returned 0 and the crash came later (sha-check parse). D-062 documents this, but nothing machine-readable in the run marks the artifacts valid.
- `pytest: None` in every run report.

Fix: record `artifacts_valid` per step in `child_metrics.json`. Let the driver refuse to start unless CI is green for HEAD, or run a short pytest pre-flight.

**D11 — Low. The BUG-018 word-fix flag is outside the cache key and revisions.**
Real clips ran without `--bug018-word-fix`; the synthetic clips ran with it. If the fix changes text features for clips ≤ 60 s, entries extracted with and without it share one key.

Fix: add `bug018_fix` to `_revisions()`, or add a test showing it is a no-op at ≤ 60 s. Use one setting (on) for all of P4.

**D12 — Low. Dead-man details.**
- The hard cap counts from dead-man start, not from launch, so it ends a few minutes after the ledger deadline.
- The test depends on timing (grace 3 s, 1 s sleeps) and could flake on a loaded runner. Use a grace of 5 s or more.

**D13 — Low. `enh002.analyse` edge cases.**
- `np.nanargmax` raises on an all-NaN event row (an event whose window runs past the clip end). Guard against it and report the event as missing.
- The synthetic test masks for FFC, PH and MT_plus are empty, which causes the 8 RuntimeWarnings. Give them vertices so the off-target path is actually exercised.

**D14 — Medium (carry-over). The QA required changes from gD032_c3 are still open and have no ticket.**
- `tests/test_gitleaks_allowlist.py` still has no secret-*after*-cache_key case.
- `check_test_weakening.py` still does not flag `assert True`, appended `or True`, `pytest.raises(Exception)`, or newly added `approx(abs=…)`.
- BUGS.md still has duplicate BUG-012, BUG-013 and BUG-014 lines.

This matters more now because P4 will add many tests. Fix: open a ticket and implement the three changes from that review.

## Not defects (verified)
- The sweep cannot terminate non-yct instances (prefix filter plus a server-side name re-check on terminate; tested).
- The new tests make real claims:
  - `apply_transcript` is compared against an independent with-tsv `extract_confounds` run, and the other columns are checked unchanged.
  - The ENH-002 test recovers known lags of -2, 0 and +3 in both maps.
  - The sweep test shows `reap()` would *keep* the orphan and `sweep` kills it.
- Privacy: `sanitize_run` keeps only numbers and hashes for real clips. events.csv files are written to the run dir only for synthetic clips. Transcripts stay on the pod and in S3.
- The GPU name is in `_revisions`, so a cache from a different device class is refused.
