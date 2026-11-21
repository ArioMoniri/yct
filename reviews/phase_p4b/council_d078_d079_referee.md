# Council review: D-078 (independent re-review) and D-079 — Strict Referee

Date: 2026-11-21. Scope: d078_draft.md, signoff_d078.md, d079_draft.md, BUGS.md BUG-036, commits a18b246,
598ca0e, d420fa2, e768363, feda068. I did not read sealed data, labels, transcripts or any outputs/ predictions.

**Verdict: REVISE.** D-078 can be kept, but only with the corrections below. D-079 is the right
direction, but it is not yet fully pre-specified.

## D-078 (independent re-review of the self-signed cycle 1)
- Justified at the time it was made. The STOP path handed the decision to the owner. The added category was
  chosen on names and counts only, and the draft discloses that the counts were read before the rule was
  written. The base was taken verbatim and the union is evaluated from rank 1, so no outcome is used. The
  two-commit freeze is in the history (a18b246, then 598ca0e).
- Hostile-reviewer problem: its trigger no longer holds up. The body STOP at 10/568 came from the bug.
  The re-check finds 108/566 body rows wrongly rejected under C1. D-078 §6 gives an expected yield of about
  1.8 %, which is also a BUG-036 artefact. A reviewer will read this as "a male-only category was added
  because of a parser bug".
- Process: DECISIONS D-078 was appended and frozen in 598ca0e on a sign-off written by the implementer. The
  15-row D-078 run (d420fa2) then went ahead before any independent review. The draft discloses this and
  makes independent review a pre-launch item, so it is not a violation of its own rule. The record still
  has to show that this review is that independent pass. 598ca0e also left test_guards_frozen_config red
  until e768363. That must be disclosed.
- Not blocking: a stricter rule written in advance would have excluded gender-specific categories (for
  example "People walking seen from behind", 205 files). Changing the category now would be a choice made
  after seeing 15 D-078 rows and the re-check, so I do not ask for it. The disclosure must be strengthened
  instead (item 2).

## D-079
- Justified: BUG-036 is real. The probe showed 18/50 pages with 0 templates. Decisions depended on batch
  composition, which is not a property of the file. The fix pages to batchcomplete and fails closed.
  Every change in the re-check goes one way (371 inadmissible → admissible, 0 the other way), so the v1
  first-20 sets are not the sets the frozen rule gives. Re-running from rank 1 with all filters, ordering
  and N unchanged is the only outcome-blind repair. Keeping v1 logs byte-identical as superseded is correct.
- Keeping D-078 (D-079 §5) is acceptable. Of the available options it is the one least driven by outcomes,
  because dropping it would use the re-check's body counts. §5 must name the principle it relies on and must
  disclose that the trigger was an artefact (item 2).
- Gap, determinism audit: D-078 §3, which is frozen in `audit_exempt_reasons: [duplicate]` and in the
  runner's `prior` read of image_body_auto_log.jsonl, compares the new body log with the v1 D-074 log.
  Under the fixed client, about 108 licence flips will STOP by construction. D-079 does not say whether
  the audit is amended, dropped or extended. It also does not say whether face and place get the same
  reproducibility check. Leaving this open would mean deciding it after the first STOP.
- Gap, revision drift: v2 reads current page metadata, but the snapshots record revids. The re-check shows
  2 face files with a changed revid. No rule says whether the current revision is used, the file is
  rejected, or the run stops.
- Disclosure is otherwise adequate (§6). The re-check counts are computed and labelled as not used for
  selection, and the files it reads are named.

## Required items (REVISE-blocking)
1. Fix the v2 determinism audit in D-079 and freeze it in config before any v2 call. Compare each v2 row with
   its v1 row in all three categories (body against both v1 body logs). Exempt only pairs where either
   reason is `duplicate`, or where C1 admissibility changed according to the committed re-check. Exempt
   pairs must be listed by title in a committed file, not inferred at run time. Any other mismatch is a
   STOP. Update the runner's `prior` source and `audit_exempt_reasons` to match.
2. D-079 §5, and an append-only note on D-078 in DECISIONS, must say all of the following:
   - the D-078 trigger (10/568) and the §6 yield figure (1.8 %) were produced under BUG-036;
   - D-078 is kept under a stated, outcome-blind principle: a frozen amendment is not revisited on
     knowledge gained after it;
   - the v1 report will state, as a pre-stated descriptive item, how many of the 20 final body images
     come from each source, alongside the male-only limitation.
3. Before the run, state a rule for revid drift between the snapshot and the current Commons page (for
   example: evaluate the current revision and log both revids, or STOP). Apply it to every category.
4. Process record:
   - append an addendum to signoff_d078.md saying cycle 1 was not independent and naming this council
     cycle as the independent re-review;
   - disclose the red guard test between 598ca0e and e768363;
   - do not append D-079 to DECISIONS, or freeze its keys, until all five independent members have
     signed off.

## Not blocking
- QA should consider a live paging probe that asserts tlcontinue is followed on a known multi-template batch.
- Note the CPU or download cost of re-evaluating the face list from rank 1 against the $75 cap.
