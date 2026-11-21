# Council D-081: neuro member (BUG-038)
Read: BUGS.md BUG-038, bug038_rootcause.md, d081_draft.md, git show 6ba2230 28e35c3, bug038_audit_v3.json, config rule_reasons. No sealed data, labels, transcripts or outputs were read. 112/112 refstim audit tests pass at 28e35c3.

**Verdict: REVISE (1 blocking item).**

**Root cause: proven, with one residual.** In the frozen `rule_reasons`, C1, F7 and B4 all map to `personality_rights`. The old `reason in c1` test therefore reads a flip-listed title that passed C1 and was rejected by B4 as "still C1", which is exactly the STOP. Three pieces of evidence agree:
- the in-run batch re-read matches 35/35 templates_sha256 at the same revid;
- the single-title replay gives Cc-zero, then B4 with clip [0.977, 0.023];
- the committed rows face 44 (F7) and body 48 (B4) are `personality_rights` with no template.

The residual is that the run's own row was not kept, so the B4 attribution rests on a replay. The 0.95 margin makes CLIP numeric nondeterminism implausible, and `write_stop_evidence` closes this gap from v4 on.

**Fix: outcome-blind but incomplete.** Selection code (`evaluate_image`, thresholds, ordering, flip list) is untouched, and the fix follows from the frozen map. All committed logs have 0 reject rows without a rule and 0 C1 rows with a non-C1 reason, so the fail-closed checks cannot fire on history.

**BLOCKING B1** (independently confirmed; biostat found it too). `audit_pair` returns `equal` on `a == b` (decision, reason) *before* any C1-class test. As a result:
- v1 C1/personality_rights against v3 B4 or F7/personality_rights, not flip-listed, gives `[('L','equal',None)]` (I ran it at HEAD);
- the reverse, C1 against F7, gives the same.

That is an unlisted C1 admissibility change, exempted silently. It is the "dangerous direction" that rootcause.md and BUGS.md say is closed, so the table row in rootcause.md is overstated.
- Fix: return `equal` only if `a == b and a_c1 == b_c1`; otherwise fall through to STOP. Add tests for both directions.
- Extend the offline re-audit to count pairs with the same reason but a different C1 class, then regenerate bug038_audit_v3.json and its sha.
- I checked all v3 rows against every superseded log: 0 such pairs. The hole is latent, and the v3 conclusions stand.

**Fixtures (28e35c3, 4 existing test files): not weakened.** Only the row builders changed, to add `rule: rule_for(decision, reason)`. No assertion or expected value changed. `rule_for` maps licence and personality_rights to C1, which is what the pre-fix fixtures meant. Non-blocking nits:
- pin the map explicitly rather than relying on YAML key order;
- `rule_for(reject, None)` returns "C0", so the old suites never reach the no-rule STOP; test_refstim_bug038 covers that path.

**Open Q1, separate F7/B4 reason code: no.** It would edit the frozen `reject_reasons`, and it would turn every v1/v3 F7/B4 row into a reason mismatch, causing new audit STOPs. State in D-081 that `rule` is the audit key and `reason` is a reporting label. From a neuro view, also disclose the count of F7/B4 "child" rejects per category. The adult proxy rejecting an adult rear view at 0.977 is a stimulus-validity limitation of a frozen filter, not a bug, and must not be tuned now.

**Open Q2, 0-STOP post-download re-audit: in code.** Make it a fail-closed launch precondition like `check_dry_audit`. It recomputes over every superseded log, v3 included, with the B1 check, refuses launch on any STOP, and its output sha is frozen by two-commit freeze.

**Wording.** §4 says "any v3/v4 decision difference is a STOP". That is true for decisions; c1_equivalent and duplicate_exempt pairs pass on reason. State it exactly.

**Cheaper path than a full v4: none the frozen rules allow.** Both alternatives would be amendments chosen after the face outcomes are known, so they are not outcome-blind:
- reusing v3 face (20/20);
- resuming body at rank 136.

The only saving consistent with the rules is that all checks run offline before launch. A v4 face run that reproduces v3 is a check, not a new selection, and it costs compute, not validity.

## Re-sign-off (cycle 2, at f9a4e56): APPROVE
- **B1 fixed.** `audit_pair` now STOPs on reject/reject with `a_c1 != b_c1`. The check sits after the flip branch and before `equal` and exempt, so a same-reason pair in a different C1 class can no longer pass as `equal` or `duplicate_exempt`. It is tested in both directions (C1 vs B4, C1 vs F7), directly and through `audit_v2`/`dry_pair`. A same-class pair is still `equal`.
- **Re-audit.** `d081_reaudit.json` shows 0 STOP and 0 same_reason_diff_class in face and body, with adult_proxy_rejects v3 face 1, body 1 (disclosed as asked). Its sha eeb292e8… matches config, and `check_frozen_d081` enforces it at both run() and finalise(). The dry audit at 1d67b4a gives would_stop 0 in face and body, and its sha 3c859368… matches.
- **Tests are not weakened.** test_refstim_d080*.py only pop `refclips_d081` from a module-level copy, so they keep pinning the v3 layer. No assertion was removed. v4 routing and the launch gate are covered in test_refstim_d081.py. The `rule_for` map is now pinned explicitly, and an unknown reason raises KeyError instead of returning C0, which is stricter. 249/249 refstim tests pass.
- **Not blocking.** The D-081 keys are not frozen yet. The runner refuses to launch until they are, which is tested, so the two-commit freeze stays a precondition and is not a defect.
