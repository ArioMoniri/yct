# Council D-081: watchdog review (BUG-038)
Read: BUGS.md BUG-038; bug038_rootcause.md; d081_draft.md; git show 6ba2230 28e35c3; bug038_audit_v3.json; config.yaml rule_reasons. Did not read sealed data, labels, transcripts or outputs. Ran the 5 refstim audit test files: 112 passed.

**Verdict: APPROVE.** The conditions below go into the D-081 freeze. None of them needs more code review of the fix.

## Root cause: proven
- The frozen `rule_reasons` gives `personality_rights` to C1, F7 and B4. The old audit tested `reason in c1_reasons`. A flip-listed v1 C1 reject that passes C1 and is then rejected by B4 therefore hits the contradiction branch. That is exactly the STOP.
- The alternative (a template that really was present) is ruled out. The replay reads the same batch `order[100:150]`, 35/35 logged `templates_sha256` match, and read_revid equals the snapshot revid. The single-title replay gives B4, clip [0.977, 0.023], under the frozen seed and threads.
- Two committed v3 rows (face 44 F7, body 48 B4) already show `personality_rights` without the template. The v1 logs show the same pattern.
- One residual: the run's own STOP row was not kept, so the B4 attribution is a deterministic replay, not a recording. That is acceptable, and `write_stop_evidence` closes this gap from v4 on.

## Fix: correct and outcome-blind
- `is_c1_reject` checks `rule == "C1"`. It fails closed on a reject with no rule, and on C1 with a non-C1 reason. All committed logs have 0 rejects without a rule and 0 C1 rows with a non-C1 reason, so the check cannot STOP on legitimate history.
- `audit_v2` computes `a_c1` and `b_c1` outside the revid-drift `try`, so a missing rule can never be excused as drift. `dry_pair` now uses `pred[1] == C1_RULE`.
- The fix also closes the dangerous direction: an unlisted C1 to F7/B4 change was previously exempted silently as c1_equivalent. The re-audit shows this did not occur.
- `evaluate_image`, thresholds, ordering, `rule_reasons` and the flip list are untouched.
- The re-audit of 627 v3 rows gives 0 STOP and no decision change. The only reclassified rows are the 2 already known. The amendment follows from the frozen map, not from pass counts.

## Test fixtures (28e35c3 edits 4 existing files): not weakened
- No assertion, parametrisation or expected value changed. Only the row builders `r()` / `row()` gained `"rule": rule_for(decision, reason)`.
- `rule_for` takes the first rule per reason from the live frozen map. `personality_rights` and `licence` map to C1, which is the only meaning the pre-fix fixtures could have had. Non-C1 mappings (for example text_or_logo to C4) only feed `is_c1_reject`, so they cannot flip an outcome.
- The `dry_pair` fixtures in test_refstim_d080 already set explicit rules and are unchanged.
- Minor: `rule_for(reject, None)` returns "C0", so the old suites never exercise the no-rule STOP. The new test_refstim_bug038 covers that path, so this is acceptable.

## Open questions
1. Separate reason code for F7/B4 (`not_adult`): **no.** It would change the frozen `reject_reasons` vocabulary and the meaning of logged rows for no gain, because the rule-based audit is sufficient. Instead, freeze a test that every reason shared by C1 and a non-C1 rule is classified by rule. Today that is only `personality_rights`; `licence` is C1 only.
2. Safeguard 3 (0-STOP post-download re-audit): **in code, as a frozen launch precondition.** `check_frozen_d081` should recompute the offline re-audit over every superseded log, v3 included, and refuse launch on any STOP or on a sha that differs from the frozen `bug038_audit` sha. A procedure alone is what let BUG-036/037/038 through.
3. Wording fix: §4 says "any v3/v4 difference is an audit STOP". That is not quite true, because c1_equivalent and duplicate_exempt pairs pass. State it exactly.

## Cheaper path than a full v4: none the frozen rules allow
- The D-080 `finality` and `other_audit_stop` rules say "v4 only for a code defect, from rank 1, for every category".
- Keeping the v3 face log (20 passes) or resuming body at rank 136 would be a post-hoc amendment chosen after the face outcomes are known. That is not outcome-blind. Reject both.
- The only saving consistent with the rules: v4 face from rank 1 is expected to reproduce v3 exactly, and the v3 logs as superseded evidence make any drift a STOP. The rerun costs compute, not risk.
