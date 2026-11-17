# G-D032 cycle 3: QA review (fresh context)

**Verdict: GO.** Not merge-blocking. Changes 1-2 below are due in the next CI commit. They are not a reason to escalate to the owner.

Packet 31235e6; HEAD 2a4ef09 adds 2 DECISIONS.md lines. data/sealed/ not read.

## What I ran
- pytest 521 passed, 0 skipped; ruff 0.17.5 clean; `make guards` rc 0 (78 commits); gitleaks 8.21.2 no leaks.
- CI run 55 (44146611274, cef030e): `--require-hashes` + `pip check`; atlas cache hit, all 6 annots OK; "521 passed", no skips (missing atlas fails, tests/_atlas.py:24; YCT_OFFLINE unset); guards and gitleaks green.

## Cycle-2 QA required changes
1. **FIXED.** `docs/owner_age.pub` and `DATA_DECISION.md` are in ALWAYS_FORBIDDEN (scripts/check_human_signed.py:35-36). Tests: tests/test_guards_human_signed.py:75,84. Removing the owner_age.pub key kills a test.
2. **FIXED.**
   - The two-commit self-allowlisting bypass is tested at tests/test_guards_guard_config.py:57.
   - Moving `since` forward is tested at :37,48.
   - Unused entries now FAIL (check_test_weakening.py:192-196, check_human_signed.py:86), and the dead 8005ceb entry is gone.
3. **FIXED.** scripts/skip_tokens.py tokenizes the whole file and covers exec/eval/compile (:29), importorskip and add_marker. Tests: tests/test_guards_skip_in_strings.py:63-97. Emptying EXEC_NAMES kills a test.
4. **FIXED.** test_photometric_bt709.py:
   - checks the bt709/tv tags (:68);
   - checks signalstats YAVG within ±0.01 (:88-92);
   - checks an independent BT.709 decode (:95);
   - checks that a BT.601 decode would disagree (:108).
   
   A `-color_range pc` mutant kills a test.
5. **FIXED.** A flickering input has strictly lower frame-to-frame variance with smoothing on (:137-140). Identity and mean checks are at :144,157.
6. **FIXED.** Makefile:22 runs `$(PY) -m ruff check .`.

## Mutation check (scratch `--no-hardlinks` clone, one line per new test file, reverted, clone removed)
- 18/19 killed by their own file; `human_signed_since` check off (check_guard_config.py:124) is killed by test_guards_guard_config.py instead.
- **One survivor:** removing the trailing `[ \t]*$` from the .gitleaks.toml allowlist regex. tests/test_gitleaks_allowlist.py still passes (4 passed). See defect 1.
- Not mutated: test_sealed_checksums.py. It tests data/sealed, which I may not touch.

## New defects
1. **BUG-020 regression is not pinned (confirmed with gitleaks 8.21.2).**
   - Scratch probe: a PAT-shaped string ('gh'+'p_'+random) *after* a hex `"cache_key"` on one line. Real config reports 3/3 probes; anchor-less mutant 2/3.
   - test_secret_on_same_line_as_cache_key_not_allowed (:35-39) puts the secret only *before* the key, so the `^` anchor alone satisfies it.
2. **The test-weakening guard misses whole weakening classes.** Scratch-clone commits to tests/test_owner_actions.py, each "OK no test weakening detected":
   - `assert oa.budget_usd(client=c) == 200.0` changed to `assert True`;
   - the same assert with ` or True` appended;
   - the same assert changed to `== pytest.approx(200.0, abs=1e9)`;
   - `pytest.raises(oa.OwnerActionError, match=…)` changed to `pytest.raises(Exception)`.
   
   The docstring (:13-15) claims that loosened tolerances are caught. Assertion counting alone cannot see a rewrite that keeps the count.
3. **Ticket IDs are not unique, but guards trust them.**
   - BUGS.md has two BUG-012 lines (16, 18), two BUG-013 lines (19, 21) and two BUG-014 lines (20, 22).
   - BUG-013 is both the renumbering of the first BUG-012 and an unrelated P1 item.
   - `g.ticket_exists` only checks presence, so `[QA-approved guard change: BUG-013]` or an allowlist `ticket: BUG-013` cannot be traced to one decision.

## Required changes
1. Add a same-line case with the secret *after* the hex cache_key to test_secret_on_same_line_as_cache_key_not_allowed. It must fail when `$` is removed.
2. In check_test_weakening, flag:
   - an `assert` line whose expression becomes a constant or gains `or True`;
   - a `pytest.raises` argument widened to `Exception` or `BaseException`;
   - `abs=`/`rel=` newly added to a previously exact comparison.
   
   Add a fixture test for each. Tag the commit `[QA-approved guard change: <new ticket>]`.
3. Add a guard test that ticket IDs in BUGS.md and ENHANCEMENTS.md are unique, ignoring the documented legacy duplicates (append-only). New tickets must take a fresh ID.
