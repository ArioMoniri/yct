# Watchdog: G-D032 cycle 3
Fresh watchdog subagent, session_011NAQ1mksc4Ea1mJcrGfTSd, final-round instance.
- **Audited:** HEAD 31235e6, which is cef030e plus the packet. CI run 44146611274 on cef030e: test, guards and gitleaks all green.
- **Read:** packet.md and the gate_D032 reviews only. I did not read data/sealed/ or the other final_round files.

## VERDICT: PASS
- One guard weakness is still present. I reproduced it (item 1 below).
- It does not block, because owner actions are authoritative only in SSM (D-030). `infra/lambda_gpu.py:59-65` takes min(file, SSM) and fails closed, so a forged exemption cannot raise the budget.
- A ticket for it is required.

## Cycle-2 required changes
1. **Freeze guards.** FIXED in mechanism, but a bypass remains. `scripts/check_guard_config.py:37,102-108` accepts any commit-message token. Reproduced in a `--no-hardlinks` clone, since deleted:
   1. agent commit `BUDGET_USD=9999`;
   2. a harmless commit;
   3. add a `human_only_exempt` entry for step 1, with message "tidy [QA-approved guard change: BUG-011]".

   Result: `check_human_signed` prints "EXEMPT … OK (79 commits)" and `check_guard_config` prints "OK".
2. **BUG-010 recall.** FIXED. Crafted lines run through `check_test_weakening.analyse()`:
   - caught: f-string skip, `"""doc"""; pytest.skip`, `importorskip`, `raise pytest.skip.Exception`, alias import, `unittest.SkipTest`, `mark.skip`, `xfail(run=False)`;
   - correctly ignored: skip text that is only a string.
3. **CBIG pin.** FIXED at `config.yaml:136-143` (commit 634f676…).
4. **6c16d89 ticket and stale entry.** FIXED: BUGS.md:15 (BUG-011) has exact pairs at `config.yaml:305-311`, and the dead entry is gone.
5. **Provenance at the gate SHA.** FIXED: the run-55 artifact `run-ci_…`. Locally `pytest -q` gives 521 passed.

## Re-runs
- **Random test file** (seed 20261117): `tests/test_gitleaks_allowlist.py`, 4 passed.
- **`make guards`** (whole history, 76 commits): all OK, with 3 BUG-011 exemptions and 6 allowlisted lines.
- **`gitleaks git --config .gitleaks.toml --redact`:** 78 commits, no leaks. A `git log -p --all` grep for hf_/AGE-SECRET-KEY-1/PRIVATE KEY finds only quoted commands.
- **Append-only check:** OK, 5 files.

## New defects
1. **The approval token is self-asserted** (`check_guard_config.py:37`). The bypass is reproduced above. The guard scripts are not frozen either, including `APPROVED_UNTAGGED` at :44-47.
2. **gitleaks exceptions are unfrozen.** `.gitleaksignore` (BUG-023) and the `.gitleaks.toml` allowlist (BUG-020) sit outside `PROTECTED` (config.yaml `guards`/`owner` only). One line with no token would silence a real leak.
3. **Residual skip evasions** (low severity). Not detected:
   - `getattr(pytest, "sk"+"ip")(…)`;
   - conftest `collect_ignore`;
   - pyproject `addopts`/`--deselect`.
4. **The §2b.5 audit trail is missing.** `reviews/watchdog/` and `audit_log.jsonl` do not exist.
5. **Scratchpad hygiene** (file names only; no file name carries a label):
   - `repair_16837/yct.git` is a full history mirror, including f48a331;
   - `gl/` and `gl2/` hold gitleaks probes;
   - `empty_objects_moved/` is also present.

## Required changes (ticketed; not blocking)
- Bind each guard token to a QA vote file committed in a strict-ancestor commit, with its hash pinned (as for BUG-019).
- Freeze `.gitleaksignore`, `.gitleaks.toml` and `scripts/check_*.py`.
- Ticket defect 3.
- Create `reviews/watchdog/audit_log.jsonl` and add this round to it.
- Remove `scratchpad/repair_16837` and `gl*` with `rm -rf`. Never shred them (BUG-017).
