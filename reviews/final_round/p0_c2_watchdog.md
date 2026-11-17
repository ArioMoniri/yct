# Watchdog: Phase 0 cycle 2
Fresh watchdog subagent, session_011NAQ1mksc4Ea1mJcrGfTSd, final-round instance.
- **Audited:** HEAD 31235e6 (cef030e plus the packet). CI run 44146611274 is green.
- **Read:** packet.md and reviews/phase_0/*.md only. I did not read data/sealed/.

## VERDICT: PASS
The PASS has conditions, which must be met before any P4 GPU work:
- No orphan GPU, fabrication or secret found.
- Defect 1 is a disclosure defect. The underlying data are present and re-compute.

## Cycle-1 required changes
1. **Smoke run dir.** PARTIAL. `outputs/runs/p0rerun_20261117T155528Z` has git_sha 0e3ed3e, cmd, and `git_dirty: true`. Its `exit_code` is **1**, which is undisclosed (defect 1). The cached rerun is bit-identical A==B==C (sha 3de2734c…).
2. **Determinism ruling and GPU feature_cache check.** FIXED: D-038 (DECISIONS.md:62), exact on the A100.
3. **Budget fails closed.** FIXED: `infra/lambda_gpu.py:59-65` (BudgetUnverified; cap = min(file, SSM)).
4. **Latency window-bounded.** FIXED: D-039 and `docs/prompts/v2.md:26`.
5. **Guard defects.** FIXED, with a residual (see gD032_c3_watchdog.md).
6. **Heartbeat.** FIXED: `infra/gpu_heartbeat.sh:3-11` (GPU util below 5% for 15 min; 10-min stale). The ledger has 176 heartbeats.
7. **ARN pin.** FIXED: `config.yaml:330`, frozen.
8. **hf_token via SendCommand (BUG-013).** DEFERRED-OK, but the owner must close it before the next GPU launch.
9. **A10.** FIXED: D-041, which allows A10 only with an A100-equivalence test.

## Re-runs
- **Metric.** Fresh-drift reliability in p0rel_20261117T163701Z: I took the minimum over `rel_*.reliability.json`. All three equal `summary.json` and pass the gate, with 0 unreadable.

  | Clip | Arrays | Min reliability |
  |---|---|---|
  | smoke | 19 | 0.999710 |
  | long70 | 174 | 0.999538 |
  | long110 | 556 | 0.991348 |

- **Cost.**
  - `lambda_gpu.py list` gives `[]`; `spent` gives **4.4175 USD**.
  - The ledger agrees: 5 launch/terminate pairs, 7991 s at 1.99 USD/h. That is 2.2% of 200.
  - The run totals reconcile: 0.7703 + 1.2035 + 1.7382 + 0.705 for the two short attempts.
- **SSM.** `/yct/owner/budget_usd` is 200 (v1; modified by the pinned root ARN). `/yct/owner/data_decision` is SIGNED (v1). I did not read age_key or hf_token.
- **Tests.** 521 passed.

## New defects
1. **A hidden provenance failure.**
   - p0rerun_155528Z `metrics.json` has exit_code 1, and `stdout.log` shows "JSONDecodeError … char 24000" after long110.
   - `summary.json` and `report.md` came later, from `--collect-only` at a different SHA, 86fcdda (`collect_cmd`, `collect_git_sha`).
   - `report.md` says "Steps (rc): all 0". There is no erratum and no BUGS entry.
2. **Gate evidence from dirty, non-gate SHAs.**
   - p0rerun is 0e3ed3e (dirty). p0rel is 86fcdda, a WIP commit (dirty). p0rel `recompute_cmd` ran "working-tree code".
   - No D-038 evidence was produced at 5edcf04 or later.
3. **D-038 "≥3 real-like clips" is not met.**
   - All three clips are synthetic.
   - long110 is the BUG-018 broken clip (229 TRs, duplicated words), so its 0.9913 was computed on corrupt input.
4. **The run dirs leak curation columns.** `git_diff.patch` in p0rerun_154358Z and p0rerun_155528Z is tracked and contains `label_confidence`, `evidence_url` and `discovery_method`. The cause is `scripts/run_with_provenance.py:69`, which diffs the whole tree. This is the INCIDENT in p1_c2_watchdog.md.

## Required changes
- A BUGS entry and a report.md erratum for the exit-1 / collect-only recovery.
- Before P4: re-run the D-038 gate at a clean, committed SHA on at least 3 real-like clips, none longer than 70 s until BUG-018 is fixed, with exit 0.
- The owner closes BUG-013 before the next launch.
- `run_with_provenance.py` excludes `data/`, `outputs/` and `*.csv` from `git_diff.patch` (recording sha256 only), with a test.
