# Watchdog — G-D032 cycle 2
Fresh watchdog subagent (session_011NAQ1mksc4Ea1mJcrGfTSd, cycle-2 instance). Audit date 2026-11-17. Audited SHA b140dd6, with HEAD b83e6c2 (which only adds packets). Not read: data/sealed/, any cycle-2 or phase_0 review.

**VERDICT: VETO (fixable).** No INCIDENT: I found no leak, no orphan GPU and no fabrication.

## Cycle-1 required changes
| # | Item | Evidence | Status |
|---|---|---|---|
| 1 | `_atlas.py` skip | `tests/_atlas.py:19-25`: fails unless `YCT_OFFLINE=1`. CI log shows atlases fetched and **256 passed, 0 skipped** | FIXED |
| 2 | CI green | `gh run view 44109304890`: headSha b140dd6, conclusion success. Lint, Tests, Guards and gitleaks all pass | FIXED, real |
| 3 | Test run dir | `outputs/runs/fixD032_1_local/` has cmd, exit_code 0 and git_sha. But that SHA is **6b46cfe with `git_dirty: true`**, not a gate SHA. Only the CI artifact covers b140dd6 | PARTIAL |
| 4 | CBIG pin | `config.yaml:120-127` is still `ThomasYeoLab/CBIG/master`. `grep -i cbig DECISIONS BUGS ENHANCEMENTS` finds no deferral | **NOT FIXED, NOT DEFERRED** |
| 5 | search_log | Untracked (`.gitignore:14`, BUG-005) | FIXED |
| 6 | lock / heartbeat | `requirements.lock` is committed. Heartbeat is in code only, with no GPU run since | FIXED / untested |

## BUG-009 allowlist and history exceptions
- **Command:** `make guards` (BASE=EMPTY, 42 commits). **Result:** all OK, with 6 ALLOWLISTED lines.
- **Diffs inspected:**
  - c35c53c `_atlas.py` skip: justified (BUG-008).
  - e4cdc4e `conftest.py`: `pytest.skip("ssh-keygen…")` in the fixture.
  - 8005ceb: removes the signed-commit tests, including `test_agent_signed_protected_change_fails` and `test_agent_cannot_add_own_key`. Justified by D-030, because the mechanism no longer exists. However, the commit message ("Single owner_setup.sh…") does not disclose the test removal.
- **Exactness:** every entry is full-SHA + path + kind. e4cdc4e and 8005ceb are ancestors of 4c194c7, the guard adoption commit (checked with `merge-base --is-ancestor`).
- **Defect A, stale entry:** `config.yaml:218` (8005ceb `test_guards_test_weakening.py` skip) no longer matches any finding after BUG-010. The guard output does not list it. Remove it.
- **Defect B, unticketed exemption:** `config.yaml:204` `human_signed_since` exempts 15 commits. In a scratch clone with the key removed, the check fails on **6c16d89 `infra/BUDGET_USD`**. That commit is an agent commit (author Claude, `%G?`=N) touching a human-only path. BUG-009 does not mention this exemption. It needs its own ticket and the owner's acknowledgement.
- **Defect C, the exception mechanism is agent-editable (blocking):** `frozen: []` (`config.yaml:221`), and no guard protects `guards:`. **Reproduced in a scratch clone:**
  1. Commit `infra/BUDGET_USD=9999`.
  2. Make a harmless commit Y.
  3. Commit a change setting `human_signed_since: Y`.
  4. Result: `check_human_signed` prints **"OK … (2 commits checked)"**.

  The allowlist can be edited the same way (an agent can also write the ticket). Freeze `guards.*`, or hard-code the exceptions in the scripts and pin them with a test.

## BUG-010 guard change: recall is reduced
`scripts/check_test_weakening.py:37-41` deletes every string literal before skip matching. I crafted real skips and fed them to `analyse()`:
| Added line | Old guard | New guard |
|---|---|---|
| `x = f"{pytest.skip('no gpu')}"` | caught | **[] (missed)** |
| `"""doc"""; pytest.skip("evade2")` | caught | **[] (missed)** |
| `pytest.skip("x")` | caught | caught |

Both evading forms really skip: running them with pytest gives `SKIPPED [1] test_f.py:3: evade` and `…:6: evade2`. So the claim "recall preserved" (b140dd6 message, BUGS.md BUG-010) is false.

Separately, `pytest.importorskip(` and `raise pytest.skip.Exception` are missed by both the old and new guards. This is pre-existing and needs a ticket.

Fix: keep f-string `{…}` contents, tokenize with `tokenize` rather than a regex, and add these cases to `tests/test_guards_skip_in_strings.py`.

## Other checks
- **Append-only:** `check_append_only --base EMPTY` OK (5 files). The DECISIONS gate section was appended.
- **Blinding:** `git grep -niE 'outcome|accepted|rejected' HEAD -- src scripts config.yaml ':!src/yct/curate'`. Hits are limited to comments, guard code and the photometric unblinding gate (`photometric.py:239`). The `data/curation/exclusions.csv` hits are exclusion reasons for dropped rows only. `curation_report.md:113` explicitly warns about label_confidence. `git log --all -- UNBLIND_TOKEN`: none. SSM `unblind_token`: absent.
- **Secrets:** `git log -p --all | grep -E 'hf_[A-Za-z0-9]{30,}|AKIA…|ghp_…|PRIVATE KEY|AGE-SECRET-KEY-1|secret_…'` finds 0 hits. The gitleaks CI job passes.
- **Goalpost:** b140dd6 changed the guard so that the previously failing 0b8b26c passes. Under the pre-change guard, `0b8b26c tests/test_guards_history_exceptions.py` and `b140dd6 tests/test_guards_skip_in_strings.py` both FAIL. The change is ticketed, but see the recall defect above.

## Defects
1. **Guard exceptions can be edited by an agent** (`config.yaml:204-221`). The bypass is reproduced above. Blocking.
2. **BUG-010 loses recall**: f-string and post-docstring skips evade (`check_test_weakening.py:37`). Blocking until fixed or reverted.
3. CBIG still pinned to `master` (`config.yaml:123,127`), with no deferral. This was a cycle-1 item.
4. `human_signed_since` hides 6c16d89 with no ticket. There is a stale allowlist entry at `config.yaml:218`.
5. The provenance run dir is on a dirty, non-gate SHA (`outputs/runs/fixD032_1_local/metrics.json`).

## To lift the VETO
- Protect `guards:`.
- Fix BUG-010 recall and add tests for the evasions above.
- Pin CBIG to a commit or record a deferral.
- Ticket 6c16d89 and remove the stale entry.

The D-036 Q(M0) rule is outside Watchdog scope. FIX-D032-3 is tracked in DECISIONS.
