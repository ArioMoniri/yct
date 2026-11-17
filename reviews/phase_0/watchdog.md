# Watchdog — Phase 0 gate
Fresh watchdog subagent (session_011NAQ1mksc4Ea1mJcrGfTSd, phase-0 instance). Audit date 2026-11-17. Audited SHA b140dd6. Not read: data/sealed/, other phase_0 reviews.

**VERDICT: VETO (fixable).** No INCIDENT: every smoke number I checked matches, no GPU is alive, and I found no secret in git or in SSM command history.

## Checks
**1. Provenance.** I re-derived latency from `latency_*_{ctrlsub,raw}.csv` using the `latency.py:54-60` window `[onset, onset+15]` and baseline `[onset-6, onset)`.

| Measure | Recomputed | metrics.json |
|---|---|---|
| visual ctrlsub peak / baseline / diff | 15 s, 0.0925, 0.0312, 0.0613 | identical |
| auditory ctrlsub | 25 s, 0.2370, −0.0156, 0.2526 | identical |
| raw peaks, visual / auditory | 25 s, 39 s | identical |
| auditory response to the flash, 12–17 s | 0.20–0.29 | report ✓ |

- Determinism: 3.569e-3 / 0.1395 = 2.56% ("≈2.5%" ✓).
- Peak VRAM is 13,411 MiB in metrics, the report and `tribe_requirements.md:160`.
- Fabrication checks:
  - HF `paths-info` for best.ckpt@f894e78 gives oid `9c79ffff…f321`, 708,856,138 B. **TRUE.**
  - `git ls-remote tribev2 HEAD` gives `af58661`. **TRUE.**
  - HF vjepa2 sha is `875c192`. **TRUE.**

**2. Cost.**
- `python infra/lambda_gpu.py list` returns `[]`.
- `spent` returns 0.7703. Recomputed from the ledger: (1794925717.28 − 1794924323.81)/3600 × 1.99 = 0.7703. Reconciled.
- The ledger has 1 launch and 1 terminate.
- The effective cap is 200.0, owner-verified from SSM.

**3. Secrets.**
- `grep -rniE 'token|hf_|secret|send-command|Authorization' src/yct/tribe_run infra scripts/*.sh`: the token never appears on a command line.
- `aws ssm list-commands`: 9,370 command parameters scanned for `hf_…|AGE-SECRET-KEY-1|AKIA…`, **0 hits**.
- The single token command, ed84d315, pipes `get-parameter --with-decryption` into `ssh … cat > token`. Its stdout is `38`, a byte count, and contains no secret.

**4. owner_actions.**
- `pytest tests/test_owner_actions.py`: 13 passed.
- Live: `budget_usd()` = 200, `unblind_token()` = None.
- The version/value consistency check and the history-pinned identity (`owner_actions.py:58-98`) are sound.

## Defects
1. **The smoke run dir has no provenance.**
   - `outputs/runs/smoke_20261117T142354Z/` has no git_sha, cmd or exit_code. This is cycle-1 defect 3, still unfixed.
   - BUG-006 relies on "cached-feature rerun = 0.0", which is not in `metrics.json`. It exists only on the pod (`smoke_report.md:24`).
2. **The determinism DoD is not met.**
   - `ROADMAP.md:125` requires `test_determinism` with an empty cache, and the run gives 3.57e-3, which fails 1e-4.
   - BUG-006 redefines the test. That needs a QA vote plus a DECISIONS entry.
   - `feature_cache.py` is CPU-mock tested only, with no GPU re-run.
3. **The latency estimate is censored.** `latency.py:54` starts the window at onset, and both peaks sit on its first bin. The visual curve is already 0.078–0.082 at 13–14 s. §10 should say "L ≤ 0 (window-bounded)", not VERIFIED L = 0.
4. **The heartbeat does not match the spec.** `v2.md:273` requires instance heartbeats and an idle-GPU kill (<5% for 15 min). `lambda_gpu.py:148-161` writes heartbeats from the watcher only, and `grep -i 'util|idle'` returns nothing. A hung job keeps "heartbeating".
5. **The budget fails open.**
   - `owner_actions.py:12` says callers must stop on OwnerActionError.
   - `lambda_gpu.py:48-51` instead catches every exception and uses the file cap of 200.
   - The documented default when unset or unverified is 50 (`v2.md:271`, `owner_actions.py:21`).
6. **Owner identity is trust-on-first-use.** The `YCT_OWNER_ARN` pin (`owner_actions.py:95-97`) is never set: grep over src, infra, scripts, .github and docs finds only the reader.
7. **hf_token is reachable through SendCommand.** `owner_setup.sh:73-77` denies `tribe-pod-manager` hf_token. That user can still send a command to the pod, whose role reads it, and command ed84d315 used this path. Nothing leaked, but the claim "no hf_token" at `owner_setup.sh:81` is not enforced.
8. **The P0 guards share the cycle-2 defects:** the guard exceptions can be edited by an agent, and BUG-010 lowers recall. See `reviews/gate_D032/cycle2_watchdog.md`.

## To lift the VETO
- Produce a smoke `outputs/runs/` dir with SHA, cmd, exit code and the cached-feature result.
- Get a QA and DECISIONS ruling on the determinism DoD, plus GPU verification of feature_cache, or defer it to P4 with a ticket.
- Make the budget fail closed (min(file, 50)).
- Restate the latency as window-bounded.
- Fix guard defects 1-2 from the cycle-2 review.
- Ticket items 4, 6 and 7.
- Defer ENH-004 (A10): 13.4 GB was measured on clips of 40 s or less, not on 58 s T1 clips.
