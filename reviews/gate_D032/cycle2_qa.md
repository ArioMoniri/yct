# G-D032 cycle 2: QA review (fresh context)

**Vote: FIX (merge-blocking).** CI is now real and green. Two cycle-1 required changes (D6, D7) were neither done nor deferred. Both guard votes are conditional, because each guard can be evaded (shown below).

## What I ran
- `python -m pytest -q`: **256 passed**, 0 skipped.
- `ruff check .` (pinned 0.17.5): clean.
- `make guards`: whole history, 42 commits, OK, 6 ALLOWLISTED. `make guards BASE=HEAD` is refused as an empty range (D4 fixed).
- CI run 44109304890 (headSha b140dd6, success). From the log and ci.yml:
  - install with `--require-hashes` from the lock, then `pip check`, on Python 3.11.18;
  - atlas cache missed, and `fetch_atlases.py` fetched and sha-verified all 6 annots;
  - `YCT_OFFLINE` appears nowhere in ci.yml, and a test asserts it stays absent;
  - "256 passed", no skips, lint "All checks passed!" with the same ruff pin.
- So the real-atlas tests ran in CI.

## Cycle-1 QA items
- **Fixed:**
  - D1: neuro extra, atlas cache, and no silent skips (`load_or_skip` now fails).
  - D2: lint and ruff pin.
  - D4: guard range.
  - D5: test_normalize.py:198-214 hashes the full T1 bytes before and after T3, asserts `"t3" in again`, and checks that T3 is in a separate directory.
  - D8: lock in sync; I re-compiled it with uv and got the same lock.
- **Superseded:** the matplotlib `importorskip`. A collection error beats a silent skip.
- **NOT fixed, not deferred:**
  - D6: both photometric test files still measure through the module's own `iter_rgb_frames` (rgb24, no matrix or range set). There is no signalstats check, and the tolerance is still ±0.02. The T3 output is untagged (ffprobe shows range, space, transfer and primaries all `unknown`). My independent signalstats check: crop YAVG 0.449 (target 0.45; module reports 0.444). Small risk, but untested.
  - D7: test_photometric.py:85-90 asserts only a flag and a file suffix. A no-op smoother passes.

## Defects
1. **The allowlist lets an agent excuse its own changes.** config.yaml `guards:` is unprotected. In a clone, commit A added a test with `pytest.skip`, and commit B added an allowlist entry for A under the existing ticket BUG-010. Result: `ALLOWLISTED … OK`, exit 0. `human_signed_since` can be moved forward the same way.
2. **The deleted tests were not fully replaced (BUG-009).**
   - 8005ceb removed `test_unsigned_protected_change_fails`, which covered `DATA_DECISION.md` and `docs/owner_age.pub`.
   - `ALWAYS_FORBIDDEN` now protects only `UNBLIND_TOKEN` and `infra/BUDGET_USD`.
   - In a clone, swapping owner_age.pub for an attacker key and editing DATA_DECISION.md passed all of human_signed, append_only and prereg. That key is the blinding root (v2.md:261).
   - The other removals were replaced by stricter tests.
3. **BUG-010 loses recall, despite its commit message.** Two cases were caught before the change and are missed now:
   - a line that closes a triple-quoted string and then calls the skip, `"""; pytest.skip("x")`, because the regex pairs the quotes across the call;
   - `exec("pytest.skip('x')")`.
   
   Older gaps, still missed: `importorskip`, `add_marker("skip")`, `skipif` changed to `skip`, `raises(ValueError)` changed to `raises(Exception)`, an assertion replaced with `assert True`, and a tolerance moved into a variable.
4. **The allowlist has a dead entry.** The 8005ceb test_guards_test_weakening.py skip entry no longer matches since BUG-010 (only 6 of 7 entries print). Unused entries are accepted silently.

## Votes
- **BUG-009 allowlist:** approve c35c53c (the skip path now fails and is tested). Approve e4cdc4e and 8005ceb **only together with change 1**.
- **BUG-010:** FIX. The precision gain is real, but the claim "recall preserved" is false.

## Required changes
1. Add `docs/owner_age.pub` and `DATA_DECISION.md` to `ALWAYS_FORBIDDEN`, with a fixture test for each.
2. Fail any commit that changes config.yaml `guards:` unless its message has `[QA-approved test change]`. Add a test that reproduces the two-commit bypass. Fail on unused allowlist entries and delete the dead one.
3. Detect skips with `tokenize` over the whole file before and after the change, instead of the per-line regex. Add `importorskip`, `add_marker`, and skip calls inside `exec`/`eval` strings.
4. D6: measure the T3 crop with ffmpeg `signalstats` YAVG. Tag the output bt709 / tv range. Tolerance ±0.01.
5. D7: assert that frame-to-frame mean-Y variance on a flickering input is strictly lower with smoothing on than with it off.
6. Makefile `lint:` should run `$(PY) -m ruff`. The PATH `ruff` here is 0.16.9.
