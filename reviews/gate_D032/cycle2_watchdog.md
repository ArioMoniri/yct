# Watchdog — G-D032 cycle 2
Fresh watchdog subagent (session_011NAQ1mksc4Ea1mJcrGfTSd, cycle-2 instance). Audit date 2026-11-17. Audited SHA b140dd6, with HEAD b83e6c2 (which only adds packets). Not read: data/sealed/, any cycle-2 or phase_0 review.

**VERDICT: VETO (fixable).** No INCIDENT: I found no leak, no orphan GPU and no fabrication.

## Cycle-1 required changes
| # | Item | Evidence | Status |
|---|---|---|---|
| 1 | `_atlas.py` skip | `tests/_atlas.py:19-25`: fails unless `YCT_OFFLINE=1`. CI fetched atlases; **256 passed, 0 skipped** | FIXED |
| 2 | CI green | `gh run view 44109304890`: headSha b140dd6, success. Lint, Tests, Guards and gitleaks all pass | FIXED, real |
| 3 | Test run dir | `outputs/runs/fixD032_1_local/` is on **6b46cfe with `git_dirty: true`**, not a gate SHA. Only the CI artifact covers b140dd6 | PARTIAL |
| 4 | CBIG pin | `config.yaml:123,127` still point at `CBIG/master`. `grep -i cbig DECISIONS BUGS ENHANCEMENTS` finds no deferral | **NOT FIXED** |
| 5 | search_log | Untracked (`.gitignore:14`, BUG-005) | FIXED |
| 6 | lock / heartbeat | `requirements.lock` is committed. Heartbeat is in code, with no GPU run since | FIXED / untested |

## BUG-009 allowlist
- **Command:** `make guards` (BASE=EMPTY, 42 commits). **Result:** all OK, with 6 ALLOWLISTED lines.
- **Diffs inspected:**
  - c35c53c skip: justified (BUG-008).
  - e4cdc4e `conftest.py`: an ssh-keygen skip.
  - 8005ceb: removes the signed-commit tests, including `test_agent_cannot_add_own_key`. Justified by D-030, but the commit message does not disclose the removal.
- **Exactness:** each entry is full-SHA + path + kind. e4cdc4e and 8005ceb are ancestors of the guard adoption commit 4c194c7 (`merge-base --is-ancestor`).
- **Stale entry:** `config.yaml:218` (8005ceb `test_guards_test_weakening.py`) no longer matches anything after BUG-010. Remove it.
- **Unticketed exemption:** `config.yaml:204` `human_signed_since` exempts 15 commits. In a scratch clone with the key removed, the check FAILs on **6c16d89 `infra/BUDGET_USD`**. That is an agent commit (unsigned) touching a human-only path. BUG-009 does not mention it.
- **Agent-editable exceptions (blocking):** `frozen: []` (`config.yaml:221`), and nothing protects `guards:`. **Reproduced in a scratch clone:**
  1. Commit `BUDGET_USD=9999`.
  2. Make a harmless commit Y.
  3. Commit a change setting `human_signed_since: Y`.
  4. Result: `check_human_signed` prints **"OK … (2 commits checked)"**.

  The allowlist can be abused the same way, because an agent can also write the ticket.

## BUG-010: recall is reduced
`scripts/check_test_weakening.py:37-41` deletes every string literal before skip matching. I fed crafted lines to `analyse()`:
| Added line | Old guard | New guard |
|---|---|---|
| `x = f"{pytest.skip('no gpu')}"` | caught | **missed** |
| `"""doc"""; pytest.skip("evade2")` | caught | **missed** |
| `pytest.skip("x")` | caught | caught |

Running both evading forms under pytest gives `SKIPPED … evade` and `SKIPPED … evade2`, so they are real skips. The claim "recall preserved" (commit b140dd6, BUGS.md BUG-010) is false.

Both the old and new guards also miss `pytest.importorskip(` and `raise pytest.skip.Exception`. This is pre-existing and needs a ticket.

## Other checks
- **Append-only:** `check_append_only --base EMPTY` OK (5 files).
- **Blinding:** `git grep -niE 'outcome|accepted|rejected' HEAD -- src scripts config.yaml ':!src/yct/curate'` returns only comments and the unblinding gate at `photometric.py:239`. `exclusions.csv` hits are reasons for dropped rows. `git log --all -- UNBLIND_TOKEN` is empty, and the SSM unblind_token is absent.
- **Secrets:** `git log -p --all | grep -E 'hf_…{30,}|AKIA…|ghp_…|PRIVATE KEY|AGE-SECRET-KEY-1'` finds 0 hits, and CI gitleaks is green.
- **Goalpost:** b140dd6 was written to clear a red guard. Under the old guard, 0b8b26c `test_guards_history_exceptions.py` FAILs. It is ticketed, but see the recall finding above.

## Defects
1. **Guard exceptions can be edited by an agent** (`config.yaml:204-221`). The bypass is reproduced. Blocking.
2. **BUG-010 recall loss** (`check_test_weakening.py:37`). Blocking.
3. **CBIG is still pinned to `master`**, with no deferral. This was a cycle-1 item.
4. **6c16d89 is hidden with no ticket**, and `config.yaml:218` is a stale allowlist entry.
5. **The provenance run is on a dirty, non-gate SHA.**

## To lift the VETO
- Freeze `guards.*`, or hard-code the exceptions in the scripts and pin them with a test.
- Make BUG-010 work on tokens (`tokenize`, keeping f-string expressions) and add the evasion tests to `tests/test_guards_skip_in_strings.py`.
- Pin CBIG to a commit SHA.
- Ticket 6c16d89 and drop the stale entry.

The D-036 Q(M0) rule is outside Watchdog scope. FIX-D032-3 is tracked in DECISIONS.
