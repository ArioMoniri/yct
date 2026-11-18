# Watchdog, cycle 2: Gate P4-entry (verify FIX-P4E)
Watchdog subagent, session_011NAQ1mksc4Ea1mJcrGfTSd.
- **Audited:** HEAD 9c4cb32. The range 0c8e2bc..HEAD holds c616a9d, 11bc34d and 9c4cb32. The working tree is clean.
- **Not done:** I made no AWS or Lambda calls, decrypted nothing, and did not open data/sealed/. The only file I edited is this review.

## Re-runs
- **All 7 `scripts/check_*.py`: OK.**
  - append-only: 5 files;
  - blinding: 404 tracked files;
  - frozen_config: **15 frozen keys unchanged**;
  - guard_config: 104 commits;
  - human_signed: 3 BUG-011 exemptions;
  - test_weakening: OK. Only the old allowlist entries match, and the range has no new finding.
  - prereg: no lock yet.
- **`pytest -q`:** 693 passed, 0 failed, 0 skipped (248 s).
- **Blinding grep of the diff and commit messages:** I searched 0c8e2bc..HEAD (guard code and tests excluded) for the sealed column names and outcome words. There were 0 real hits; "outcome" occurs only as a driver variable and in the D-063 context line.
- **Data and run dirs:** the range adds no files under data/ and no new outputs/runs dir, so no real-data P4 output exists.
- **Ledger:** 445 events, and every launch has a matching terminate, so no instance is live per the ledger.

## Scrutiny items

### 1. `test_guards_frozen_config` rewrite: not a weakening
- **Before:** `assert cfg["frozen"] == []`.
- **After:** `assert cfg["frozen"] == [{"key": k, "frozen_at": "c616a9d…"} for k in D063_FROZEN]`. This is exact equality on all 15 keys, their order and the full sha.
- **Why it is stronger:**
  - Any addition, removal or re-dating of a freeze entry now fails the test, where before only the "nothing frozen" state was checked.
  - The other default assertions are untouched.
  - The rename (one test def out, one in) leaves the counts unchanged, and the guard agrees.
- **Procedure:**
  - frozen_at = c616a9d, the commit that introduced the values, and it is an ancestor of HEAD.
  - The freeze was made in a separate commit (11bc34d), 5 minutes later.
  - check_frozen_config confirms the values are unchanged since c616a9d.
  - Both commits come before any P4 output. **CLOSED.**

### 2. Firewall (D-063 B2)
- **Tests:**
  - an AST import ban on yct.features/interpret/stats/predict/report/confounds for the driver, qc, cache_archive, feature_cache and gpu_p0_rerun;
  - a source-token ban on window/controls/features/localize/start_tr/end_tr/parcel;
  - records restricted to {record, gate, d038}, with no pred_mean/pred_std/feature_sha256;
  - a subprocess dry run that asserts no forbidden module is loaded.
- **Driver:** it runs only per-clip shape, finite, T, chunk and word checks.
- **Adequate for launch.**
- **Residual (minor, w1):**
  - The token ban is lexical; for example, `cfg.get("window")` would pass it.
  - After P4, nothing mechanical stops an analysis script from reading `s3://…/p4/pred/` before the P4b design entry.
  - Suggestion: a check script that fails if any src/scripts module both reads `p4/pred` and imports features/stats before a `P4b-design` DECISIONS tag. This is not launch-blocking, because the firewall binds downstream analysis, not extraction.

### 3. Terminator, sweep and cost safety
- **Non-yct instances cannot be killed:**
  - `list_ours()` filters on the yct- prefix;
  - `terminate()` refuses non-yct instances;
  - `reap_deadline` only iterates `list_ours()`;
  - tested in test_infra_terminator (an "other-…" instance with a past deadline survives) and in test_infra_guards.
- **A concurrent yct run is safe:**
  - `reap()` keeps a foreign-ledger instance whose name deadline is in the future;
  - `sweep` keeps an instance with a touch ≤ 20 min old, or one that is booting (< 30 min, no heartbeat);
  - `reap-deadline` kills only instances past their name deadline + margin.
- **Cost cap:**
  - `launch()` still enforces ≤ 4 h and spent + price×h ≤ min(BUDGET_USD, the owner SSM budget);
  - the driver adds a session cap of min(p4.session_max_hours, budget.max_hours_per_instance, 4);
  - it adds `--usd-limit` (default $10);
  - it refuses to launch without a pod timer or an `--external-terminator-at` in [deadline+15 min, +75 min];
  - it re-checks the external terminator against the real deadline after launch and terminates if it is too early;
  - it terminates at once if scheduling the pod timer fails with no external terminator;
  - the dead-man switch now starts first and also halts at the absolute deadline.
- **Worst-case exposure per launch:** about 3.75 h + 1.25 h ≈ 5 h × $1.99 ≈ **$10**.
- **Whole P4:** about 103 jobs in about 4 sessions is ≈ $30–40, against $9.23 spent of $200. **CLOSED.**
- **Residual (minor, w2):**
  - `--usd-limit` counts only `max_hours`, not the terminator tail.
  - `sweep` treats an unknown touch age (ssh failure) on an instance older than 30 min as an orphan. That is "unknown", not "stale" as D-063 Q7 says. It is acceptable while only one instance runs at a time.

## Cycle-1 items
| Item | Status | Evidence |
|---|---|---|
| B1: no P4 driver | **CLOSED** | `scripts/gpu_wave1_p4.py`: resumable sessions ≤ 4 h, per-job immutable S3 sync, skip of synced jobs, cache restore without re-extraction, append-only manifest, run sets from config (52/51, recomputed by tests from label-free columns), records hold numbers and hashes only, GPU name in the gate and the cache key, `revisions_sha256` in metrics. Tested by a dry run of 103 jobs over 4 sessions plus fault tests. The pod runs the repo at `git checkout <git_sha>` (preflight). QA sign-off is QA's call. |
| B2: label-blind rulings before output | **CLOSED** | D-063 (0c8e2bc) records Q2 (yct_0644 out), Q3 (yct_0626 kept and flagged, S-LOWFPS; the explicit, reasoned deviation I asked for, voted 3–1), Q4 (MT ∪ MST ∪ FST), Q5 (WER > 0.25, any video) and B1 (L = 0, W = [5,45)). All of them are in config and frozen at c616a9d before any P4 output. |
| B3: container-independent terminator | **CLOSED** (with a launch condition, C1) | Pod systemd timer via SSM key (needs an owner action), or an external one-shot scheduled session (`reap-deadline --margin-s 0`). The driver refuses to launch without one. Tests in test_infra_terminator and test_gpu_wave1_p4. BUG-027 status line appended. |
| M1: T2/M0b silently out of scope | **OPEN** (not launch-blocking) | No DECISIONS entry defers T2/M0b. The one-GPU rule is now enforced mechanically (a cache root refuses two revision sets). Record the deferral before the P4b lock. |
| M2: cache key without revisions/device | **CLOSED** | Key v3 = sha256(video ‖ transcript ‖ sha256(revisions incl. GPU model, word-fix flag)) (D-064b). |
| M3: pod-only untracked scripts | **CLOSED for P4** | The P4 driver runs only repo code at the checked-out sha. The historic `wave1_summ.py`/`wave1_p2p3.py` are still uncommitted: OPEN, minor. |
| M4: prior-watchdog items unticketed | **OPEN** (not launch-blocking) | No BUG/ENH lines. `reviews/watchdog/audit_log.jsonl` is missing. Scratchpad `repair_16837/`, `gl/` and `gl2/` are still present (`rm -rf`, per BUG-017). |
| m1 ROADMAP, m4 D-038 rule line, m5 accent flag ENH | OPEN, minor | Not addressed. |
| m2 packet Q3 mis-frame | CLOSED | Corrected in D-063 Q3. |
| m3 partial-run note | OPEN, minor | No note was added to wave1p2b_20261117T234829Z. |
| m6 ledger only in the container | **CLOSED** for P4 | `backend.mirror_ledger(run_id)` runs in teardown. |
| m7 sweep kills concurrent runs | **CLOSED** | Liveness-aware sweep; `--force` is explicit. |

## Verdict: **GO** for full-model T1 + T3 P4 extraction
No ablations, and the firewall stays in force. There are no new launch-blocking defects. Launch conditions (procedural, no code change):
- **C1. Terminator before every launch.** Until the owner creates SSM `/yct/lambda_api_key`:
  - before each launch, create the one-shot scheduled session at deadline + 15–75 min;
  - pass its time as `--external-terminator-at`;
  - its prompt should run `python infra/lambda_gpu.py list` and then `reap-deadline --margin-s 0`, and report any error (missing LAMBDA_API_KEY, API failure) as a failure, not silently;
  - never use `sweep --force` in it.
- **C2. First session, watched.** Run it with `--limit 3` (the D-038 clips only), because PodBackend has run only as a dry run. Continue only if `alive_after` is [], `usd_spent_this_run` is plausible and Gates 1 and 2 pass. A D-038 STOP is final for this gate.
- **C3. Before each launch:** confirm `pytest` and the guards are green at the launch sha and that the sha is pushed (the pod checks out that sha).
- **C4. Firewall:** until the P4b design entry is committed, no session loads `p4/pred/*.npy` for any statistic, and that includes "quick looks".
