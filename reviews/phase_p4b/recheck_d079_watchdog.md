# Re-check: D-079 v2, Watchdog (independent, 2026-11-21)

Read: council_d078_d079_watchdog.md (my cycle 1), d079_v2.md, d079_v2_response.md, `git show d46d6b5 2370c0e`
(config, refstim, refstim_auto, runner, tests). Not read: data/sealed/*, labels, transcripts, outputs/, image-log rows.
Suite at HEAD 2370c0e: `pytest -q` 1025 passed.

**Verdict: APPROVE** (no blocking items)

## Cycle-1 items
1. Independent D-078 review + disclosure: resolved. DECISIONS "D-078 note" (append-only) records the freeze and run
   on a non-independent sign-off; this cycle is named as the independent review.
2. Owner fork A/B: resolved. §0 + DECISIONS note give the question, what the owner was shown (108 wrong rejects,
   corrupted trigger), the answer (A), and that it came before any v2 call. B is disclosed. Sufficient record.
3. Revid rule: resolved. `evaluate_current_log_both`. lastrevid comes in the same request (prop=info) and a change
   during paging is a STOP. Both revids and a drift flag are logged. Tests are in bug036 and d079.
4. Audit: resolved, kept. `audit_v2` runs against every v1 log, is fail-closed and non-selecting, and is called
   before append. The flip list is committed, sha-checked, refuses adm_to_inadm, and has one test per table case.
5. Red suite: resolved. Disclosed in BUGS and DECISIONS, with a green-commit precondition and `run_commit` per row.
6. Log names / log_version as an amendment: resolved in design. Commit 1 is done. The frozen rows and guard-test
   rows are in commit 2, and `check_frozen_d079` blocks the runner until then. I will check commit 2 when it lands.

## Open questions
(a) Revid drift stays non-exempt: yes. An exemption would be decided after seeing that those 2 titles drifted,
    and that is a post-hoc carve-out. Image bytes are pinned by the identity rule, so non-C1 filters must reproduce.
    A C1 change on a drifted page is real new evidence, and it should reach the owner, not pass silently. STOP is
    correct. A drift STOP is not a code defect, so `finality` does not cover it (see N1).
(b) Identity mismatch: STOP, not reject. A reject would silently remove a rank-ordered candidate because of an
    external event. A STOP makes it visible. The owner sees only the identity fact, not filter outcomes, so a STOP
    adds no outcome-dependent fork, provided the resolution path is stated in advance (N1).

## Non-blocking (fix in the freeze commit if cheap)
N1. State in advance how a drift-audit STOP or an identity STOP is resolved, so it is not decided ad hoc. For
    example: the owner records the event, the v2 decision at the read revision stands (drift), or the title is
    logged as `identity_changed` and skipped at its rank (identity). The run then resumes. That would not be a v3.
N2. `preload_v2` uses `r.get("log_version", "v2")`, so a row with no log_version is accepted. `finalise` refuses
    it. Make preload strict too, and add a test.
N3. `page_meta_c4` (extmetadata) is a separate request without prop=info, so it may read a different revision
    from the C1 read. Add prop=info and compare it with `read_revid`, or disclose it.
N4. The freeze commit must add the d079 rows to test_guards_frozen_config in the same commit, to avoid a repeat
    of the 598ca0e red suite.
