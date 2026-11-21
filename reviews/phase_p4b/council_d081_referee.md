# Council D-081: referee review (BUG-038 fix, v4)

**Verdict: APPROVE.** No blocking items. Read: BUGS.md BUG-038, bug038_rootcause.md, d081_draft.md, 6ba2230, 28e35c3, bug038_audit_v3.json. The 5 refstim audit test files pass (112). No sealed data, labels or outputs read.

## Root cause: proven to the standard needed
- In body, `personality_rights` can come only from C1 or B4 (F7 is face-only). The in-run batch `order[100:150]` re-read at the same revid 1216330296 has no Personality rights template, and 35/35 logged template hashes match. So C1 passed, and with the frozen detectors B4 fires (clip_adult 0.977/0.023). The committed v3 rows (face 44 F7, body 48 B4) show the same code path in-run.
- The in-run template list of the STOP title was not recorded, so this is an inference, not a direct observation. It still needs no external fault, and it explains why the dry audit predicted `flip`. Accepted.

## Fix: correct, and blind to outcomes
- `is_c1_reject` classifies by rule, and a missing rule or a C1/non-C1-reason mismatch fails closed. It runs outside the revid-drift `try`, so it can never be reclassified as drift. The fix follows from the frozen `rule_reasons` map. It also closes a silent exemption, an unlisted C1 → F7/B4 pair that the old audit passed as c1_equivalent, so it is stricter where it matters. Selection code is untouched.
- Every committed log row has a rule: 0 reject rows without a rule and 0 C1 rows with a non-C1 reason across all 6 logs. The new `b_c1` check in `dry_pair` therefore cannot crash the dry-audit re-run on legacy rows.

## Test fixtures (28e35c3 edits 4 existing test files)
- Not weakened. Only the row constructors `r()`/`row()` changed, to add `rule=rule_for(decision, reason)`. No assertion, expected value or parametrize case changed. `rule_for` maps each reason to its first rule in the frozen map (licence and personality_rights → C1), which is exactly what those fixtures meant under the old reason-based audit.
- Nit, not blocking: `rule_for` defaults unknown reasons to "C0". This would hide a future fixture with no rule. Prefer raising.

## Open questions
1. **Separate F7/B4 reason code (`not_adult`):** no. It would edit the frozen `reject_reasons`/`rule_reasons` after outcomes were seen, and the rule-based audit already makes it unnecessary. The v1 report should label F7/B4 rejects by rule ("adult proxy") so readers do not read them as licence rejects.
2. **Safeguard 3 (0-STOP post-download re-audit):** put it in code as a launch precondition, like `check_dry_audit`: a frozen sha of the generalised output, 0 stops, and the same code-change guard. Disclose its limit: it covers only rows already evaluated (v3 face 492, body 135). It says nothing about body ranks 136+ or about place.

## Cheaper path under the frozen rules
- None that skips work. D-080 finality fixes "v4 from rank 1 for every category", so accepting v3 face or resuming body at rank 136 is not allowed.
- The allowed saving: `fetch_verified` accepts a cached file once its sha1 is checked, so v4 can reuse the pod's v3 download cache if it is still there. The rerun of v3 face (492 rows) then costs only compute, and the v3 logs as superseded give a full v4 = v3 check for free.
