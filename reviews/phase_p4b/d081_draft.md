# D-081 draft: BUG-038 fix, v4 image-filter run (council review pending; not in DECISIONS; nothing frozen)

## 1. Trigger
The v3 run (D-080, addab10) stopped at body rank 136 on an audit "flip list contradiction". Under the frozen
`stop_resolution.other_audit_stop` this is a code defect: a BUG entry, then **v4 from rank 1 for every
category** after council review (D-079 §2.8 / D-080 finality).

The root cause (reviews/phase_p4b/bug038_rootcause.md) is that the audit read the reason code
`personality_rights` as meaning C1. That code is shared by C1 and by the post-download F7/B4 adult proxy.
Commons and the template merge are not at fault (replay: 35/35 template hashes equal).

## 2. Amendment (audit only; selection unchanged)
- A C1 reject is identified by `rule == "C1"`. `audit_pair` uses `a_c1`/`b_c1`, computed by rule, for the flip, duplicate-exemption and c1_equivalent tests.
- A reject row without a rule, or a C1 row with a non-C1 reason, is a STOP.
- An audit STOP writes `<log>.stop.json` holding the full row (templates and their sha, rule, values) before it raises.
- Unchanged:
  - `evaluate_image` and every filter, threshold and ordering;
  - the first-20 rule, `rule_reasons`, `reject_reasons` and the flip list;
  - `stop_resolution` and `audit_revid_drift`;
  - the C3 preload order (face → body → place) and D-078.
- No filter outcome was used to choose the amendment. It follows from the frozen `rule_reasons` map, and it is the stricter rule for unlisted C1 admissibility changes.

## 3. Proposed safeguards for v4 (to freeze before the run)
1. **v4 logs.** New `_v4.jsonl` logs from rank 1 for face, body and place, with `log_version: v4`. The v3 logs and the v2 run-1 log are kept as evidence and added to the superseded logs read by the audit, so v4 must reproduce them under the fixed audit.
   - The offline re-audit already shows 0 STOP over all 627 v3 rows (data/refstim/bug038_audit_v3.json).
2. **Dry audit re-run.** `refstim_auto.py` changed, so the D-080 code-change guard requires a fresh `scripts/refstim_d080_dry_audit.py` at the fix commit. Its sha replaces `dry_audit_sha256` by two-commit freeze, and a launch requires 0 would_stop.
3. **Post-download audit replay before launch** (new). Before the v4 launch, `scripts/refstim_bug038_audit_v3.py` (generalised to every superseded log) must report 0 STOP. This covers post-download rows, which the metadata-only dry audit cannot see.
4. **Stop evidence.** Kept as in §2. A v5 is allowed only for a code defect found by a fail-closed check (D-079 finality unchanged).

## 4. Disclosure
The v1 report states:
- D-080 → D-081;
- the BUG-038 cause;
- that v3 face (20 passes) and body (8) were evaluated but superseded by v4;
- the expectation that v4 reproduces the v3 decisions, since decisions do not depend on the audit and all 627 v3 rows audit clean.

Any v3/v4 decision difference is itself an audit STOP.

## 5. Open for council
- Whether `rule_reasons` should give F7/B4 their own reason code (for example `not_adult`) for v4. This would change the frozen `reject_reasons`; the draft prefers not to, because the rule-based audit makes it unnecessary.
- Whether safeguard 3 should be a frozen launch precondition in code (recommended) or a procedure.
