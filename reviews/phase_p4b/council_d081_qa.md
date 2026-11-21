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
