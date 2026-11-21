# Council review: D-078 and D-079, Watchdog (independent, 2026-11-21)

Scope: process integrity, forking paths, post-outcome choices, append-only/freeze discipline, D-059 scope.
Read: d078_draft.md, signoff_d078.md, d079_draft.md, BUGS.md BUG-036, `git show` of a18b246 598ca0e d420fa2
e768363 feda068. Not read: data/sealed/*, labels, transcripts, outputs/, or the row content of any image log.

**Verdict: REVISE**

## What holds
- D-078 §0 picks the category by a name/count rule with no member outcomes seen, and §6 discloses that the
  counts were read before the rule was written. Taking the base snapshot verbatim keeps D-074 membership fixed.
- The D-078 determinism audit worked: it fail-closed at row 15 (d420fa2) and that STOP exposed BUG-036. No
  manifest, LICENSES.md or image output exists. The v1 logs are kept byte-identical, which is correct.
- D-079 §5 (keep D-078) was written in e768363, before the re-check counts arrived in feda068. So it was not
  chosen after the 108-row body count was seen. Evaluating from rank 1 with no carry-over is blind to outcomes.
- The fix goes in a fail-closed direction (CurationError means STOP, never a reject). The re-check script only
  reads and prints counts. Nothing shows a D-059 scope breach: the work ran on the yct pod and touched no
  intake resources.

## Problems
1. **D-078 was frozen and run with no independent review.** signoff_d078.md was written by the implementing
   worker in a single context. Even so, 598ca0e wrote D-078 into DECISIONS.md, and d420fa2 ran filters under
   it. D-079 says nothing is frozen until five sign-offs. D-078 broke that rule. The re-review was deferred to
   "before the GPU campaign", but v2 body selection depends on D-078, so the deferral is too late.
2. **The D-078 premise is now false, and the fork is not in front of the owner.** The owner chose "Add 2nd
   category" because of a STOP at 10/568. BUG-036 shows 108 body C1 rejects were wrong. Whether D-074 alone
   would reach 20 is unknown. Keeping D-078 is outcome-blind with respect to v2, but it rests on an owner
   decision made from corrupted evidence. Making D-078 conditional on a v2 D-074-only STOP is also a valid
   a-priori option, and it is closer to the original D-074 STOP path. The council should not pick between
   these on the owner's behalf. This is the main forking path in the package.
3. **Revision drift is not specified.** The runner logs the snapshot `revid` but reads licence templates from
   the current revision (2 face revids already differ). D-079 does not say which revision is evaluated, or
   what happens when the live revid differs from the snapshot. Whoever runs v2 would decide that ad hoc.
4. **A guard is removed silently.** v1 logs are "never read". That also drops the D-078 determinism audit,
   the only cross-run reproducibility check, and it is the check that found BUG-036. D-079 neither keeps it
   (for example, a non-C1 equality check on rows admissible under both clients, never used for selection)
   nor says it is retired, or why.
5. **Tests were red.** e768363 says test_guards_frozen_config was "red since 598ca0e". The d420fa2 run
   therefore happened on a red suite. This is not disclosed in BUG-036 or D-079.
6. Minor: BUG-036 still says "Fix needed (not applied)" above the FIXED status line. Leave it as written
   (append-only) but cross-reference it. D-079 should also name the log files whose names change from the
   frozen D-078 config (`image_body_d078_auto_log.jsonl` → v2). That change amends a frozen key and needs the
   two-commit freeze and a row in the guard list.

## Required before D-079 is frozen or any v2 call is made
1. Run an independent five-member review of D-078 (this cycle counts if all five are independent). Record in
   DECISIONS (append, no edits) that D-078 was frozen and run before independent review.
2. Put a fresh owner decision on keep vs conditional D-078 (option A: union as frozen; option B: union only if
   v2 D-074-only body STOPs at fewer than 20). State that the owner has seen the re-check counts. Record the
   choice before any v2 filter call. Disclose the alternative and the corrupted premise in the v1 report.
3. Fix the revision rule a priori: either evaluate the snapshot revid, or evaluate the current revision, log
   the revid actually read, and STOP (or follow a stated rule) on a mismatch. Test it.
4. Either keep a v1→v2 determinism audit restricted to non-C1 reasons, as fail-closed and non-selecting, or
   state explicitly in D-079 that the audit is retired, with the reason.
5. The v2 run must start from a commit with a fully green test suite. Disclose the red-suite run at d420fa2 in
   BUG-036/D-079.
6. Bring the v2 log names and the `log_version` key in through the two-commit freeze, with rows in
   test_guards_frozen_config, as an amendment of the frozen D-078 log name.
