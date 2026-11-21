# D-079 v2 — response matrix to council cycle 1 (council_d078_d079_*)

Each required item and where it is applied. "§" refers to d079_v2.md.

| Member | Item | Response | Where |
|---|---|---|---|
| Watchdog | 1 independent review of D-078 before any v2 run; DECISIONS note that D-078 was frozen and run before review | The cycle-1 council is the independent D-078 review; v2 re-check pending; append-only DECISIONS note added | §5.1; DECISIONS "D-078 note"; signoff_d078.md addendum |
| Watchdog | 2 owner re-decision A/B with corrupted premise shown | Asked 2026-11-21 after showing the 108 wrong body rejects: "Keep it as frozen" (A); B and the premise disclosed | §0; DECISIONS note |
| Watchdog | 3 revid rule + test | evaluate_current_log_both; lastrevid in the same request, STOP if it changes during paging; both revids logged | §2.6; `ra.revid_fields`, `rs.query_pages`; tests d079 + bug036 |
| Watchdog | 4 keep or retire the determinism audit | Kept: fail-closed, non-selecting, vs every v1 log | §3; `ra.audit_v2` |
| Watchdog | 5 disclose red suite at d420fa2; v2 from a green commit | Disclosed; green-suite precondition; `run_commit` in every row | §2.9, §5.1; BUGS.md note |
| Watchdog | 6 v2 log names / log_version as amendment, two-commit freeze, frozen-config test rows | New key `controls.refclips_d079` (amends D-078 routing); freeze rows + test rows in the freeze commit after sign-off | §2.2, §2.10 |
| Referee | 1 audit against v1 logs in all categories, exempt only duplicate + committed C1 flip list | As specified; flip list committed and sha-frozen; `prior` source and exemptions changed in the runner | §3; config `audit`; runner |
| Referee | 2 D-078 trigger and 1.8 % yield produced under BUG-036; outcome-blind principle; per-source counts pre-stated | Disclosed; principle stated; counts written by finalise | §0, §5.2, §5.3 |
| Referee | 3 revid-drift rule for every category | §2.6 (all categories) | §2.6 |
| Referee | 4 signoff_d078 addendum; process disclosure; no DECISIONS D-079 / freeze before five sign-offs | Addendum appended; disclosed; D-079 not in DECISIONS, keys unfrozen, runner refuses | signoff_d078.md; §2.10 |
| Biostat | R1 audit rules with tests | §3 table, one test per case | tests/test_refstim_d079.py |
| Biostat | R2 order face→body→place; C3 only from v2 logs; refusal test | `ra.preload_v2` (order + version refusal) | §2.3; tests |
| Biostat | R3 finality rule | `finality: v2_is_selection` | §2.8 |
| Biostat | R4 disclosure a/b/c | Trigger artefact; §6 expectation withdrawn, none made; per-source counts + source of each body pass | §5.2, §5.3; d078_draft.md addendum |
| Biostat | R5 reconcile 14 vs 0 | Two truncated readings vs truncated-vs-complete | §4 |
| Neuro | 1 male-only / FFC note; per-source counts; sex never labelled | Note added (DECISIONS + §5.4); no sex count | §5.4 |
| Neuro | 2 file-identity rule, pre-chosen, tested | `identity_rule: stop`; `ra.check_identity` before rules and on the downloaded bytes | §2.7 |
| Neuro | 3 contact-sheet check applies to v2; content will differ | Stated | §5.5, §5.6 |
| QA | 1 audit baseline + exemptions; amend D-078 §3/§5; tests | As Referee 1 | §3 |
| QA | 2 v2 naming/routing tests: refuse v1 resume/append, C3 from v2 only, finalise v2 only, missing/unfrozen log_version STOP | `rs.image_log_v2`, `rs.check_d079_routing`, `ra.preload_v2`, `ra.check_frozen_d079`; runner + finalise use v2 only (source test) | tests/test_refstim_d079.py |
| QA | 3 untested fail-closed paths | Added: missing/invalid, unrequested, normalized, non-terminating continue, Personality rights in a continuation, page_meta_c4 truncated | tests/test_refstim_bug036.py |
| QA | 4 log full template list (or sha) and read revid; drift logged | `templates`, `templates_sha256`, `snapshot_revid`, `read_revid`, `revid_drift`, `commons_sha1` per row | runner; §2.6 |

Not yet done (needs the sign-offs first): run the re-check with `--flips` on the pod, commit the flip
file and its sha, then the freeze commit and DECISIONS D-079.
