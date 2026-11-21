# Council D-081, biostat member: REVISE (1 blocking item)

**Root cause: proven.** Three independent strands agree. (i) The committed v3 logs already hold F7 and B4 `personality_rights` rows that have no template (face row 44, body row 48). (ii) The in-run batch re-read matches 35/35 `templates_sha256` at the same revid. (iii) A single-title rule replay gives C1 pass (Cc-zero), then B4 at clip_adult [0.977, 0.023]. This explains the STOP without needing a Commons or merge fault. `rule_reasons` (C1, F7 and B4 all map to `personality_rights`) supports it.

**Outcome-blind: yes.** Only the audit changes; `evaluate_image`, thresholds, ordering and the flip list are untouched. The amendment follows from the frozen `rule_reasons`, not from any pass or reject.

**Fixtures (28e35c3): not weakened.** The four edited files change only the row helper, which adds `rule` through `tests/_refstim_rules.rule_for`. No assertion was removed or relaxed (`git diff` shows only the helper lines). The mapping takes the first rule per reason, so `licence` and `personality_rights` map to C1, which is what the pre-BUG-038 fixtures meant. 112/112 pass. Nit: the mapping depends on YAML key order. Pin it explicitly (`{"licence": "C1", "personality_rights": "C1", ...}`) so a config reorder cannot silently change what the fixtures mean.

**BLOCKING B1: the "dangerous direction" is still open.** `audit_pair` returns `equal` on `a == b`, where `a` and `b` are (decision, reason), before any C1-class test. So v1 C1 `personality_rights` against v3 B4/F7 `personality_rights` (not flip-listed) is classified `equal`. That is an unlisted C1 admissibility change, exempted silently, which is exactly what rootcause.md §"both directions" and D-081 §2 say the fix closes. Verified at HEAD:
`audit_v2(B4/personality_rights vs C1/personality_rights)` returns `[('L','equal',None)]`. The reverse pair (C1 vs F7) gives the same result.
- Fix: in `audit_pair`, test `equal` only when `a == b and a_c1 == b_c1`; otherwise fall through to STOP.
- Add tests for both directions: the reason is the same and the rule class differs, expect a STOP.
- Extend `refstim_bug038_audit_v3.py` to count pairs whose reason is equal but whose C1 class differs.
- I checked all v3 rows against every superseded log: there are 0 such pairs, so the v3 conclusions and the 0-STOP re-audit stand. The hole is latent, but v4 must not run with it.

**Open Q1, a separate code for F7/B4: no.** Renaming would change the frozen `reject_reasons` and the reason comparisons with v1/v2 logs, and would create new audit mismatches across logs. Rule-based classification is the correct fix, provided B1 is closed. State in D-081 that `reason` is a reporting label and `rule` is the audit key.

**Open Q2, safeguard 3 in code: yes.** Make it a fail-closed launch precondition, as `check_dry_audit` already is. The runner should recompute the post-download re-audit (with the B1 check) over all superseded logs and refuse to start unless the result is 0 STOP. Its output sha should be frozen like `dry_audit_sha256`.

**Cheaper than a full v4?** Not within the frozen rules. D-079 §2.8 and D-080 finality require any rerun to start "from rank 1 for every category", so reusing v3 face (complete, 20 passes) or resuming body at rank 136 would be a post-hoc amendment made after seeing outcomes. The only legitimate savings are pre-launch:
- the offline re-audit and dry audit catch defects before any download;
- the expected v3 = v4 reproduction makes the v4 face pass a check, not a new selection. Any difference is a STOP.

The cost of the face rerun is the price of the frozen finality rule. Do not trade it away.

**Verdict:** REVISE on B1. APPROVE once B1 is fixed with its tests, the re-audit is regenerated and safeguard 3 is in code.

## Re-sign-off (cycle 2, 1d67b4a + f9a4e56): APPROVE
- B1 closed: `audit_pair` now STOPs when both rows are rejects and `a_c1 != b_c1`, before `equal`/exempt. Verified at HEAD: same-reason (personality_rights) C1 vs non-C1 STOPs in both directions, and same-class pairs stay `equal`. Tests cover both directions, the direct path, audit_v2 and dry_pair.
- Diff-class count: `bug038_audit_v3.py` (pinned to D-080) and `post_download_reaudit` count these pairs, and both find 0. Rule-less rejects still fail closed through `is_c1_reject`.
- Re-audit: recomputed from the committed logs, sha eeb292e8… equals the file and `reaudit_sha256`; 0 STOP and 0 diff-class in face and body. Dry audit: sha 3c858693… matches, and it was run at 1d67b4a.
- Safeguard 3 is in code: `check_frozen_d081` (frozen keys, sha, 0 STOP and 0 pairs) runs in `run()` and `finalise()`, and the re-audit script is under `DRY_AUDIT_CODE_PATHS`.
- Test edits are not weakening: test_refstim_d080*.py only drop `refclips_d081` from the module CFG so they keep pinning the v3 layer, and no assertion changed. `rule_for` is explicitly PINNED and raises KeyError on an unknown reason, which is stricter than before. d080/d080_council/d081: 74/74 pass.
- Non-blocking: the runner's D-081 check is gated on `controls.refclips_d081` being present. The freeze commit should make sure a v4 run cannot start without it, for example by tying log_version v4 to that key.
