# Council D-080: watchdog review (BUG-037 amendment, v3 image logs)

Reviewed: reviews/phase_p4b/d080_draft.md, 8148366, 4118fa2, data/refstim/d080_dry_audit.json, config.yaml
controls.refclips_d079/d080. I did not read sealed data, labels, transcripts or predictions. **Verdict: REVISE (1 blocking item).**

## C1 equivalence: outcome-blind and safe? Yes
- C1 runs before every later rule, so a C1 reject stops evaluation. `licence` vs `personality_rights` changes
  only the reason label. The pass set, the order and the first-20 selection are the same either way.
- `audit_pair` is narrow: both sides must be `reject` with both reasons in the frozen `c1_reasons`. The flip
  list is checked first, a listed title still at C1 STOPs, and no admissibility change is covered. Tests cover both directions, flag off and flip precedence.
- The only v2 information used is the STOP row and its two reasons (option b was written in BUG-037 before
  any count). Finalise reads only title/decision/reason; the new `audit_c1_equivalent` field cannot reach selection.
- Rule choice is general, not tuned: the 12 c1_equivalent pairs were counted after the rule was fixed.

## Dry audit: adequate? Yes for C0-C4 and identity, with the disclosed limits
- It reuses the frozen `evaluate_image` (no reimplementation drift) and stops at the download. `missing_sha1` gives would_stop, and the flip counts (260/108/3) reconcile with the committed flip file. would_stop = 0.
- The download-stage rules (C5/F*/B*/P*, 235 face + 105 body reaches_download pairs) rely on the detectors being deterministic. Weak
  evidence: the 6 v2 run-1 rows that reached download matched v1. Non-blocking.

## What can still STOP or bias selection
**B1 (blocking): Commons drift after the dry audit has no non-defect resolution.**
- Under `revid_rule: evaluate_current_log_both`, a template edit after the dry audit can turn admissible into C1 (or the reverse) on a superseded title.
  The draft says two face pages were already edited. That pair STOPs, `other_audit_stop` calls it a "code defect" and forces a v4 that is not a code defect.
- The rerun would be informed by v3 outcomes, which finality forbids, and the dry-audit JSON records no read revids, so the drift cannot be dated.
- Fix before freeze, in both D-080 and the config: (a) have the dry audit record per-title read revid (or the sha256(title) keys whose revid differs from the superseded row); (b) add `stop_resolution.audit_revid_drift`.
  When the v3 `read_revid` differs from both the superseded row's `revid` and the dry-audit revid, the current-revision decision stands (it is the frozen revid rule), both are logged, the run resumes at the next rank and the case is disclosed.
  Alternatively state "STOP to council, no v4". Either way, decide it now, not after a STOP.
- Non-blocking: freeze at a commit whose src/ and scripts/ match 8148366 (4118fa2 changed only config and data; check `git diff 8148366 <freeze> -- src scripts` is empty), and launch soon after freezing.
