# Council review: D-078 + D-079, Biostatistician (independent re-review, 2026-11-21)

Scope: d078_draft.md, signoff_d078.md, d079_draft.md, BUGS.md BUG-036, commits a18b246 598ca0e d420fa2
e768363 feda068 (code and docs only). Not read: data/sealed/*, labels, transcripts, outputs/, log contents.
This is the independent Biostat re-review that signoff_d078.md lists as a pre-launch item.

**Verdict: REVISE** (5 required items, R1–R5). The D-078 rule and the D-079 direction are sound.

## D-078 (selection rule, union, ordering)
- The rule is outcome-blind given the union. Ordering is sha256(title), so the two sources interleave like a
  random order. The "first 20 passes" are then effectively a random draw from the passing files in the union.
  "Base first, dedupe by title" only sets the `source` label of the 1 overlapping title. It does not change
  order or membership. No bias from the union mechanics.
- The bias is in the composition, and it is real. 398/966 (41%) of the union are male-only, on top of the
  men already in the base. The expected male share of body passes therefore rises. It is disclosed (§6) but
  not quantified. See R4.
- The category rule was written after the counts were seen (disclosed, W1). It uses names and counts only.
  That is acceptable.
- The trigger is now invalid. The 10/568 STOP and the 1.8% yield (§6: "about 7 added passes, STOP likely")
  came from BUG-036-truncated C1 reads (108 body files wrongly rejected). The amendment was conditioned on an
  artefact. See R4.

## D-079 (supersede v1, re-run from rank 1)
- Fresh evaluation from rank 1 is the only valid option, and I support it. Reusing non-C1 v1 decisions is not
  valid:
  (a) the 371 files rejected at C1 never got a non-C1 decision;
  (b) C3 (duplicate) is path-dependent on the earlier passes, and those passes change;
  (c) mixing two client versions in one selection makes the rule unauditable.
- Keeping D-078 (§5) is correct. The recheck counts show that body admissibility from D-074 alone would rise.
  Dropping D-078 now would be a choice informed by C1 outcomes. Keeping it is the pre-committed path, and the
  composition cost goes into the disclosure (R4).
- Re-run bias. The sequence is: STOP → amend → run → bug → re-run. That is a forking path. It is acceptable
  only because each step was triggered by a fail-closed check (the STOP rule, then the determinism audit), not
  by the content of the images. D-079 must close the path from here on (R3).
- Face: 0/20 v1 passes became inadmissible, but 260 earlier-ranked files became admissible. The v2 face set
  will differ. Re-running face is driven by the bug, not by outcome. That is correct.

## Required items (REVISE-blocking)
R1. **v2 determinism audit must be specified.** The runner's `audit_prior` compares body with the D-074 log.
    In v2 it would either STOP on every C1 flip, or be silently dropped. D-079 must define the v2 audit for
    all three categories against the v1 logs, as follows:
    - Title admissible in both v1 and v2: (decision, reason) must be equal, except where either reason is
      `duplicate`.
    - v1 `licence` reject, admissible in v2: allowed only if the recheck listed it as inadmissible →
      admissible.
    - Admissible in v1, inadmissible in v2, or any other mismatch: STOP.
    - Add tests for these cases.
R2. **C3 preload and category order.** State that the v2 order is face → body → place, as in D-075. C3 state
    is preloaded only from v2 logs of the categories already run. No v1 log (face, D-074 body, D-078 body) is
    ever preloaded. The runner must refuse otherwise (tested).
R3. **Finality rule, stated before the v2 run.**
    - v2 is the selection.
    - A v3 is allowed only for a code defect found by a fail-closed check or a documented BUG entry, never
      because of v2 results. It must again run from rank 1 for every category, with disclosure.
    - No category is added, removed or reweighted because of v2 outcomes. The D-078 "<20 → STOP, no
      fallback" rule carries over unchanged.
R4. **Disclosure (DECISIONS D-079 and the v1 report).**
    (a) The D-078 trigger and its yield expectation were BUG-036 artefacts. D-078 is retained by a rule
        written before v2, not on the evidence.
    (b) Withdraw the D-078 §6 "STOP likely" statement. Before the v2 run, either state a new expectation
        (it may use the recheck C1 counts only) or state that none is made.
    (c) Report, for each source: the evaluated rows, the passes, and the source of each of the 20 body
        passes. This gives the realised male-only share, so the skew is measured, not just asserted.
R5. **Reconcile the counts.** BUG-036 reports 14 face files going admissible → inadmissible on a re-read. The
    recheck reports 0 admissible → inadmissible against the logs. State what was compared each time, so the
    "v1 only under-admitted" claim is not contradicted in the record.

## Advisory (non-blocking)
- 2 face files have a changed revid. State whether v2 reads C1 at the current revision or at the snapshot
  revid, and disclose the 2 files.
- Keep N = 20 and the sha256(title) order exactly. Any change now would be outcome-informed.
