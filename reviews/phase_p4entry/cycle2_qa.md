# QA / software engineering — Gate P4-entry, cycle 2

Reviewer: QA. Scope: `git log 0c8e2bc..HEAD` (c616a9d, 11bc34d, 9c4cb32). The review was read-only:
- I ran git, pytest, ruff, the guards, `gh run list`, the dry run (with its run dir in the scratchpad) and an ad-hoc probe script (also in the scratchpad).
- I made no AWS or Lambda calls and decrypted nothing.
- The only file I edited is this one.

## Verdict: **FIX**, a short fix. Launch once N1 and N2 below are fixed and tested.

All the cycle-1 blockers are closed: D1, D2, D3, D5, D8 and D9. The driver is solid:
- It is resumable.
- It fails closed on the gates.
- It keeps objects immutable.
- It enforces the output firewall.

I found two small defects in the resume path. A real campaign will hit that path, and the dry run does not exercise either defect. Each fix is about 10 lines plus a test. Once both are fixed I would vote GO without another cycle; a diff review is enough.

## Checks

| Check | Result |
|---|---|
| `python -m pytest -q` | **693 passed**, 0 failed, 8 warnings (the enh002 empty-mask RuntimeWarnings, D13), 244 s |
| `ruff check .` | All checks passed |
| `make guards` (7 guards, whole history, 104 commits) | all rc 0; `check_test_weakening --base 0c8e2bc` OK |
| Test diffs in range | `test_tribe_feature_cache.py` changes only mechanically, `cache_key(clip)` → `cache_key(clip, revisions=REV)`. `test_guards_frozen_config` swaps "frozen == []" for the exact D-063 list. Nothing is loosened. |
| CI | c616a9d and 11bc34d are green (44229884476). The 3 later pushes are still in progress. |
| `gpu_wave1_p4.py --dry-run`, 5 invocations on one root | rc 75/75/75/0/0. Done counts: 28 → 59 → 90 → 103/103, and the 5th run is a no-op. Runs never re-extracted a job. |

## Cycle-1 defects

| # | Status | Evidence |
|---|---|---|
| D1 no P4 code path | **CLOSED** | See D1 detail below. Ablations are out of scope (D-063). |
| D2 CI red | **CLOSED** | `outputs/runs` is in `extend-exclude`, ruff is clean and CI is green on the FIX commits. |
| D3 no out-of-container terminator | **CLOSED (residual accepted in D-064)** | See D3 detail below. |
| D4 sweep kills concurrent runs | **CLOSED** | Sweep keeps an instance whose touch is ≤ 1200 s old or that is booting (< 1800 s by its name and no heartbeat). `--force` gives the old kill-all. Tested on the CLI too. |
| D5 exit code ignores gates | **CLOSED** | `_finish` returns 1 on any gate failure, error, STOP or instance alive after teardown. `clip_gate` fails closed when a field is missing. A missing D-038 rerun counts as a fail. Tested. |
| D6 untested driver/pod code | **PARTLY CLOSED** | The P4 driver, qc and cache_archive are well tested. The P2b-era items (`wer_score`, `ingest`, `confounds` idempotence, `sanitize_run`, `make_reference_clips`) are still untested. They do not block P4. |
| D7 WhisperX pin test / lock | **OPEN** (not blocking) | `transcribe_whisperx_batch` still skips `check_whisperx_pin` when a `runner` is injected (core.py:202). There is no wx lock. P4 does no ASR. |
| D8 S3 manifest overwritten | **CLOSED** | `manifest.jsonl` is append-only, plus an immutable `rows/<run>/<job>.json`. Each row records the tar and FILES_SHA256SUMS sha256. Objects with a sha256 sidecar are never overwritten (tested). This rests on S3 reads being reliable: see N2. |
| D9 restore not implemented | **CLOSED on CPU** | See D9 detail below. |
| D10 provenance gaps | **OPEN** (Low) | There is no per-step `artifacts_valid`, and no CI-green or pytest pre-flight in the P4 driver. |
| D11 word-fix flag outside key | **CLOSED** | `bug018_word_fix` is in the revisions and so in the cache key. The driver always passes `--bug018-word-fix`, and the gate requires it. |
| D12 dead-man details | **PARTLY CLOSED** | An absolute launch deadline was added and tested. The flake risk (grace 3 s, `test_infra_guards.py:307`) is unchanged. |
| D13 enh002 nanargmax / empty masks | **OPEN** (Low) | `enh002.py:97,107` is unguarded, and the 8 warnings remain. Not used by P4. |
| D14 gD032_c3 carry-overs | **OPEN** | There is no gitleaks secret-after-cache_key case. `check_test_weakening` does not flag `assert True`, `or True`, `raises(Exception)` or `approx(abs=)`. BUG-012 appears 4 times in BUGS.md. Not launch-blocking, but it should be ticketed before P4b adds tests. |

**D1 detail.** `scripts/gpu_wave1_p4.py` provides:
- the planner: D-038 clips first, then T1 (51), then T3 (52) = 103 jobs;
- per-job S3 sync and skip;
- restore from S3;
- planning against the ≤ 4 h session cap and the price × hours limit;
- the per-clip `clip_gate` (one Audio and one Video chunk, shape, T, finite, words, GPU, revisions).

The T scope is decided as T1 + T3.

**D3 detail.**
- Instance names now carry the launch time and the deadline.
- `reap-deadline` needs no ledger.
- The driver refuses to launch without a pod timer or a valid `--external-terminator-at` inside the window [deadline + 900 s, + 3600 s]. Tested.
- The dead-man is now the first ssh command after ssh comes up.

Residual: the driver cannot check that the external scheduled session exists, or that the session has `LAMBDA_API_KEY`. The orchestrator must check both. Before ssh comes up (≤ ~30 min), only that terminator covers the box.

**D9 detail.** `cache_archive` handles:
- safe extraction;
- re-insertion of media by sha256;
- an exact match against the sums;
- an atomic move;
- `verify`.

The round trip is tested through to an identical cached predict, and the dry run restores across boxes. It has **never run on a GPU box**. See the recommendations.

## New launch-blocking defects

**N1 — the D-038 STOP is not latched. A plain re-run bypasses it.** A failing D-038 job appends a row with `gate_pass: false` and exits 1. However, `load_state`, `is_done` and `run_session` never look for an earlier D-038 failure, so the next invocation simply retries the clip.

I reproduced this with the dry-run backend (`rerun_differs` fault on yct_0016.t1, then the fault cleared):
- session 1 returns rc 1 with `stop` set;
- session 2 returns rc 75, re-runs yct_0016.t1, passes it, and carries on to T1.

v2.md:411-412 says a Gate 1 or Gate 2 failure "is a STOP". The driver's own docstring tells the operator to "re-run until it exits 0". So an agent orchestrator that loops on non-zero exit codes would retry a STOP until it passes, which is a forking-paths and cost problem.

Fix:
- `run_session` refuses to start (before the sweep and the launch) while the manifest holds any `d038` row with `gate_pass` false, unless a human-signed override file or decision is cited.
- Change the docstring to "re-run while it exits 75; exit 1 needs a human".
- Add a test: STOP, then re-run, gives a SystemExit and no launch.

Optionally, cap ordinary gate-fail retries (for example, refuse a third attempt on the same job).

**N2 — `PodBackend.s3_get_text` treats every `aws s3 cp` failure as "object absent".** It uses `check=False` and returns `None` on any non-zero rc: credentials, throttling, network or 5xx errors, as well as a real 404. This breaks two guarantees that D8 and the resume path rely on:
- **Manifest truncation.** In `Store.append_rows`, if both reads of `manifest.jsonl` fail transiently, both give `""`, `check_append("", "")` passes, and the manifest is replaced by the new row alone. Every earlier job then looks not-done. The next session re-extracts them, hits `OverwriteRefusedError` on each tar, and burns a session before exiting 1. Recovery is manual, from `rows/`.
- **Immutability bypass.** In `put_file`, a failed sidecar read uploads over an existing object, which can have different content.

The dry-run backend cannot show either failure.

Fix: tell 404 apart from other errors. For example, use `aws s3api head-object` and treat only "Not Found"/404 as absent; anything else raises. Then add a unit test with a fake `_aws` that returns rc 1 with a non-404 stderr, and check that it raises rather than writing.

## Real-run risks the dry run cannot catch (not blocking; recommendations)

1. **Restore on a GPU box is unexercised.** The tar sets mtime to 0, and media go through `cp` without `-p`. If TRIBE/exca keys its internal cache on path, mtime or anything else not in the sums, a restored entry will miss the cache. Offline predict then fails, closed, with exit 1. Recommendation: in session 1, after the D-038 clips, deliberately restore one synced entry onto the same box in a fresh `fc2/` root and predict it, so the first crash is not also the first test of restore.
2. **Crash window between the tar upload and the `entries/<job>.json` put.** A crash there leaves a tar without an index. The next session re-extracts, gets the same key but a different tar sha256, and hits `OverwriteRefusedError` permanently on that job. The window is seconds wide and fails closed, but it needs manual repair. Writing `entries/` first (or a pending marker) would close it.
3. **The watcher's idle rule.** `lambda_gpu watch` kills a box that was never busy 30 min after launch, or 15 min after the GPU was last busy. Boot, ssh wait, ship and `remote_setup` (up to a 2700 s wait) must reach the first extraction inside 30 min. That worked in the P2b sessions, but a slow weights fetch would cause an idle-kill. The result is exit 1 (error), not data loss.
4. **No stop-file.** Hung `run_clip` steps wait up to 3 h each. Only the box dead-man (deadline) and the terminator bound them, which is acceptable.
5. **External terminator.** Pass `--external-terminator-at` at least about 30 min past now + max_hours + 15 min. `preflight` and `inputs` (sha256 of 103 clips over SSM) run before the window check, and a value that is too early is refused before launch, which costs nothing.

## Not defects (verified)

- **Firewall.** The driver never loads a prediction array, and the sanitised records hold numbers and hashes only. The raw run_clip JSON, which holds feature names, is deleted from the pod after it is fetched.
- **Exit codes.** 0, 75 and 1 propagate through `run_with_provenance`.
- **T3 duration.** T3 is gated on its own duration, from ffprobe on the box rather than the T1 csv duration, so the shared `duration_s` column is harmless.
- **Transcript manifest parsing.** The parse in `PodBackend.inputs` matches the `[video_id, tsv_sha256]` layout.
- **GPU name.** The `"NVIDIA A100-SXM4-40GB"` string matches the 136 earlier records.
- **Instance names.** Names stay ≤ 64 characters, and `pod_terminator_script` fails non-zero when the timer is not listed.
- **Teardown.** It always terminates, including on SystemExit raised inside the try, through `finally`.

## Cycle 3 verification (a07f421, D-065)

This section covers commit a07f421, pulled at a fast-forward. Checks:
- CI run 44232612904 passed on a07f421.
- The 78 tests in the P4 driver, terminator, cache and qc suites passed.
- `ruff check .` is clean.
- I re-ran my own N1 and N2 reproductions; both now pass (details below).

**N1: CLOSED.**
- I re-ran my cycle-2 reproduction: a `rerun_differs` fault on yct_0016.t1, then the fault cleared.
- Session 1 returns rc 1, writes `stops/s1.json` and records a failing D-038 row.
- Session 2 now raises SystemExit with "D-038 STOP latched by run(s) ['s1']…". It launches no instance (`FakeLG.launched` stays at 1).
- The latch works from either the marker or the failing manifest row, so it survives a missing marker.
- The only way to clear it is `--clear-stop D-NNN`, and that requires a DECISIONS.md entry naming every stopped run id. Tests cover the latch, the clear, and `--clear-stop` refusing when no STOP exists.
- The docstring now says exit 1 needs a human.

**Running the orphan sweep before the STOP refusal is acceptable, and better than the reverse.**
- reap, reap-deadline and the liveness-aware sweep can only terminate instances: they never launch, extract or write P4 data.
- An orphan left over from the stopped session is exactly what should still be cleaned up.
- The refusal still happens before the budget check, before preflight and before `launch`.

**N2: CLOSED.**
- `s3_get_text` returns None only on `(404)` or `(NoSuchKey)`.
- With fake `_aws` results, 403, connection failure, SlowDown and an empty stderr all raise S3ReadError.
- Dropping `--quiet` was necessary, because it suppressed the stderr that the 404 match reads.
- A manifest that reads as absent while `rows/` exist is now refused by both `load_state` (SystemExit) and `append_rows` (ManifestConflictError). This closes the truncation path.
- Every immutable `put_*` now fails closed on read errors.

Residual (Low, not blocking): the STOP marker is written before the manifest row. If that marker's own S3 read or write fails, the run exits 1 through the generic error path with no latch. Exit 1 still requires a human, so this is acceptable.

**Final verdict: GO** for launching full-model T1+T3 P4 extraction, conditional on two operator checks for each session:
- the external terminator is set up (a scheduled session with `LAMBDA_API_KEY`, and `--external-terminator-at` set past now + max_hours + about 30 min);
- the session is restarted only while the driver exits 75.

Strongly recommended for session 1: a deliberate restore-on-GPU smoke test (risk 1 above). The open Low defects (D7, D10, D12 flake, D13, D14) should be ticketed before P4b.
