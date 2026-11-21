# Council D-078 / D-079 — QA review (code, tests, fail-closed)

Reviewer: QA (independent re-run; signoff_d078.md was single-agent, not independent). Date 2026-11-21.
Scope: refstim.py `query_pages`/`page_meta`, scripts/refstim_auto_run.py, scripts/refstim_bug036_recheck.py,
tests/test_refstim_bug036.py, tests/test_refstim_d078.py, d078_draft, signoff_d078, d079_draft, BUGS.md BUG-036,
commits a18b246 598ca0e d420fa2 e768363 feda068. No sealed data, labels, transcripts or outputs/ were read.

**Verdict: REVISE.** The BUG-036 code fix is correct and fails closed. D-079 is not yet runnable as written:
the v2 run would STOP again on the existing determinism audit, and the v2 routing is unspecified and untested.

## What I ran / checked
- `pytest -q tests/test_refstim_bug036.py tests/test_refstim_d078.py`: 24 passed (8 + 16; the a18b246 message
  says 19 D-078 tests, 16 are collected — nit). `tests/test_guards_frozen_config.py`: 10 passed (it was red from
  598ca0e to e768363, so the d420fa2 pod run started from a commit with a red suite).
- Scratch probes of `query_pages` with fake `get` (no network): normalized titles map back correctly;
  `missing`/`invalid` page, unrequested page and a non-terminating `continue` each raise CurationError;
  Personality rights arriving only in a continuation response is merged and wins in `licence_of`; imageinfo
  arriving only in a later response is picked up. CurationError in `run()` propagates before any row is
  appended, so no C1 reject can be written from an incomplete read. Fail-closed behaviour: confirmed.
- Recheck script: `lic is not None` equals admissibility here, because every label `licence_of` returns is
  in `image_licences` (PD-* included). Logic is sound for the counts reported.

## Required items (REVISE-blocking)
1. **Determinism audit under v2 is undefined, and as coded it STOPs.** `run()` audits every D-078 body row
   against the v1 D-074 body log (`audit_prior`, only `duplicate` exempt). The re-check shows 108 body rows
   going v1 `licence` reject → admissible, so the v2 body run hits the same STOP as d420fa2. D-079 must state
   the v2 audit baseline and exemptions. Suggested: compare v2 against each v1 log (face, body, place); exempt a
   pair only when the v1 reason is `licence` (re-check: 0 admissible → inadmissible) or `duplicate`; any other
   mismatch is a STOP. Explicitly amend D-078 §3 and §5 ("face 20/20, D-074 log"), and add tests.
2. **v2 log naming and routing: specify, implement and test before the freeze.** The D-079 file names
   (`image_body_auto_log_v2.jsonl`) do not match the D-078 routing (`image_<cat>_auto_log.jsonl` + frozen
   `log_suffix "_d078"`). Both `controls.refclips_auto.logs` and `controls.refclips_d078` are frozen, so the
   derivation has to change in code under the new `log_version` key. Give exact paths for face, body and place.
   Tests: `image_log_rel` gives the v2 path for all three categories; `run()` refuses to resume from or append
   to any v1 log; C3 state (`pass_sha1`/`pass_dhash`) is built only from v2 logs; `finalise` reads only v2
   logs; a missing or unfrozen `log_version` is a STOP.
3. **Fail-closed tests should match the claims.** BUGS.md and D-079 say missing/invalid pages are covered.
   Only the missing title, batchcomplete, imageinfo and zero templates cases are tested. Add: a page with
   `missing`/`invalid`, an unrequested page, normalized-title mapping, a non-terminating continue, Personality
   rights only in a continuation response, and `page_meta_c4` itself (the runner path, with a fake `rs._get`)
   raising on a truncated extmetadata reply.
4. **v2 rows must make C1 auditable offline.** v1 rows store only `licence`/`licence_template`, which is why
   BUG-036 could not be seen in the logs. Each v2 row should record the full template list (or its sha256) and
   the `lastrevid` the templates were read from. A read revid that differs from the snapshot `revid` should be
   logged (2 face rows drifted), with a stated rule for what happens next.

## Recommended (non-blocking)
- Add a fake-get unit test for scripts/refstim_bug036_recheck.py. `_revids` keys by the returned title, so a
  normalized title would count as `revid_changed` (conservative). `template_changed` is computed but not
  reported in the D-079 table.
- `range(10_000)` at a 5 s pause means about 14 h before the non-termination error. Raise at once on a
  repeated identical continue token.
- Pre-run gate: the full pytest suite must be green at the run commit, recorded in the run log header.
- Live probe (D-079 question to QA): yes, as an opt-in marked test (one known 50-title batch whose
  unpaged reply is truncated, asserting `tlcontinue` was followed and every page has ≥ 1 template). Not in CI.
- Watchdog/owner: the D-074 body STOP that led to D-078 was probably a BUG-036 artefact. Keeping D-078 is
  defensible (the union rule does not use outcomes), but the owner should be told explicitly.
