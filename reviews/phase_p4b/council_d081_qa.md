# Council D-081, QA review (BUG-038 fix, v4 plan) - verdict: REVISE (1 blocking item)

Checked: BUGS.md BUG-038, bug038_rootcause.md, d081_draft.md, 6ba2230, 28e35c3, bug038_audit_v3.json
(sha 0259b3b3...ccf9 matches). pytest (bug038, d080, d080_council, d079, d079_recheck): 112 passed. make guards: OK.

## Root cause: proven
Shared reason code `personality_rights` (C1 and F7/B4 in the frozen rule_reasons) read as C1 by the audit. The
replay (35/35 template sha equal, no Personality rights template in the batch, title gives B4 at clip_adult
0.977) together with the committed F7/B4 `personality_rights` rows explains the STOP completely.

## Fix: right direction and outcome-blind, but one hole (BLOCKING)
- B1. `audit_pair` still returns `equal` when (decision, reason) match before it looks at the rule. Reproduced:
  v4 B4/personality_rights vs v1 C1/personality_rights -> `equal`, and C1 vs F7 -> `equal`. That is a C1
  admissibility change, which the root-cause table says must STOP, so this is the same bug class left open.
  Fix: STOP when `a_c1 != b_c1` while both are rejects, before the `a == b` test (also in `dry_pair`, through
  `audit_pair`). Add tests for both directions. Then re-run scripts/refstim_bug038_audit_v3.py. My offline check
  of the committed logs finds no same-reason/different-rule pair, so I expect 0 STOP again.
- The rest is correct: by-rule C1, fail-closed on a missing rule (all 1,549 superseded reject rows have a
  rule), the rule computed outside the drift `try`, and stop evidence written before the raise. Selection code
  and thresholds are untouched, so the fix is outcome-blind.

## Test fixtures: not weakened
The 4 edited test files only add `rule` to their row helpers through tests/_refstim_rules.rule_for. It gives
C1 for exactly {licence, personality_rights}, which is the old reason-based semantics, so every existing
assertion means the same as before. No assertion was removed or changed (the guard agrees). The new behaviours
are covered by test_refstim_bug038.py. Non-blocking: rule_for falls back to "C0" for unknown reasons.

## Open questions
- Separate reason code for F7/B4: NO. It would change the frozen reject_reasons and the v1/v3 comparisons;
  classifying by rule (with B1 fixed) is enough.
- 0-STOP post-download re-audit: YES, in code. It should be a launch precondition with a frozen sha, run at the
  fix commit, cover every superseded log (including v3), and be covered by the code-change guard.

## Cheaper path: none allowed
The frozen `other_audit_stop` requires v4 from rank 1 for every category. Resuming body at rank 136, or reusing
the v3 face logs, would mean amending the stop rule after seeing v3 outcomes, which is not allowed. The cost is
already kept low: the v3 logs go into the superseded set, so v4 is checked against them and any difference STOPs.

## Re-sign-off (cycle 1, 1d67b4a + f9a4e56): APPROVE
- B1 fixed: `audit_pair` STOPs on reject/reject with `a_c1 != b_c1` before the `equal` test; `dry_pair` reaches it via `audit_pair` (-> would_stop). Tests cover C1 vs B4 and C1 vs F7 both ways, directly and through `audit_v2`; same-class pairs stay `equal`.
- Re-audit: recomputed `post_download_reaudit_cfg` here hashes to eeb292e8...cf6d = file = config `reaudit_sha256`; 0 STOP, 0 same-reason/different-class pairs in face and body, as predicted.
- Dry audit: `d081_dry_audit.json` sha 3c859369...3856 = config; code_commit 1d67b4a; would_stop [] for both; no src/scripts change since 1d67b4a, so the code guard holds.
- `check_frozen_d081` is fail-closed (unfrozen keys, missing or wrong sha, any stop or pair) and runs in both `run()` and `finalise()`; the re-audit script is in `DRY_AUDIT_CODE_PATHS`.
- Test edits do not weaken anything: the d080 tests only drop `refclips_d081` from their CFG so they keep testing the v3 layer they were written for, and no assertion changed. `rule_for` is now pinned and raises on an unknown reason (my nit is closed).
- pytest bug038 + d080 + d080_council + d081: 85 passed. make guards: OK.
- Non-blocking: the D-081 keys are not frozen yet. The runner refuses to launch until the freeze commit.
