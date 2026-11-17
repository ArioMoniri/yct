# Phase 0 cycle 2: QA review (fresh context)

**Verdict: GO.** P0 closes. One hard condition: required change 1 must land before any T2 run in P4. T1 can proceed. Nothing here blocks P2.

## What I ran
- pytest 521 passed, 0 skipped; ruff clean; `make guards` rc 0; gitleaks no leaks; CI run 55 green with real atlases.
- Fresh `python3.11 -m venv` + `pip install --require-hashes -r requirements.lock` + `--no-deps -e .`: `pip check` clean, 521 passed, ruff clean (venv deleted).

## Cycle-1 QA required changes
1. **FIXED.**
   - src/yct/config_schema.py: every section is a pydantic `M` model with `extra="forbid", strict=True` (:23-24).
   - tests/test_config_schema.py: full top-level coverage (:26), unknown (:31) and missing (:47) key per section, wrong type/value (:72), commit-pinned atlas URLs (:87).
   - `load_config` validates by default (src/yct/config.py:14-22).
   - Mutant `extra="ignore"` is killed.
   - Coverage: every `.get("<key>"` config read in src/scripts/infra exists in config.yaml; Optional fields are only url, column/from/op, note, human_signed_since; other `yaml.safe_load` callers are history-reading guards.
2. **FIXED.**
   - outputs/runs/smoke_20261117T142354Z now has cmd, git_sha, config_sha, exit_code and provenance.json.
   - provenance.json states `"backfilled": true` and says the run was NOT executed via run_with_provenance.
3. **FIXED (and it found a real bug).** The GPU runs were p0rerun_20261117T155528Z and p0rel_20261117T163701Z.
   - smoke A, B and C: B and C ran with cache_reused=True, and the predictions are bit-identical (A==B, A==C).
   - rel_* cached reruns are bit-identical.
   - Fresh-drift reliability_min ≥ 0.9913, so the gate passes.
   - long70: T_within_1 True.
   - long110: shape [229, 20484], T_within_1 False, 276 words after duration. This is ticketed as BUG-018.
4. **FIXED.** scripts/run_with_provenance.py:89-105 records the lock sha256, platform and pip_freeze.txt, and the run dirs contain them.
5. **DEFERRED-OK (optional).** ci.yml still uses @v4 tags (Node-20 warnings in run 55).

## Mutation check (new and changed P0 test files)
These mutants were killed:
- infra/lambda_gpu.py: the idle-kill busy filter dropped, and budget_cap returning BUDGET_USD instead of failing closed (tests/test_infra_guards.py);
- the offline snapshot check disabled (test_tribe_offline.py);
- owner_actions ARN pin ignored (test_owner_actions.py);
- the p0_rerun_report bit-identity check forced True (test_p0_rerun_report.py).

## New defects
1. **run_clip does not fail closed on BUG-018.**
   - src/yct/tribe_run/run_clip.py:163-171 computes `T_within_1` and `words_after_duration` but never raises.
   - p0rerun_20261117T155528Z report: "Steps (rc): … 'long110': 0", although the output has the wrong shape.
   - Exposure: in data/manifest.csv, 20 of the 53 analysis-set rows have duration_s > 70 (aggregate count only).
   - Consequence: any T2 (untrimmed) run would silently write corrupted predictions with exit 0. "T2 blocked" exists only in prose (BUGS.md BUG-018).
2. **The rerun report prints false evidence for runs that did not happen.**
   - scripts/p0_rerun_report.py:33-34 evaluates `bool(None) and …` to `False`.
   - p0rel_20261117T163701Z/report.md therefore says "bit-identical A==B: **False**, A==C: **False** (sha256 None)", but that run has no smoke_a/b/c.
   - A reader sees a determinism FAIL that never happened. It should print N/A.
3. **BUG-018 has no regression test.**
   - Grep of tests/ for words_after_duration / T_within_1 / run_clip: only report formatting (test_p0_rerun_report.py:14) and static source checks (test_tribe_env_pins.py:23, test_tribe_offline.py:81,104); nothing exercises the shape/word-time check.
   - So nothing pins either the fix for BUG-002/018 or the refusal.

## Required changes
1. run_clip.py: exit non-zero, and write `"error"` to metrics, when `not T_within_1` or `words_after_duration > 0`. Until BUG-018 is fixed, also refuse inputs longer than 60 s unless they come from the T1 trim. Add a CPU test with a fake predictor of shape (229, ·) for a 110 s input that expects SystemExit.
2. p0_rerun_report.py: when the runs are absent, emit `None`/"N/A" rather than False. Regenerate the p0rel report.md, and add a test for a run dir that has only rel_* runs.
3. Optional: pin Actions by SHA.
