# Phase 1 cycle 2: QA review (fresh context)

**Verdict: GO.** P2 downloads and normalisation of wave 1 may start. Required changes 1-2 must close before P3 confounds or M0 are computed. Change 3 must close before any wave-2 curation commit. I did not read data/sealed/, and I write only aggregate counts here.

## What I ran
- pytest: 521 passed.
- ruff: clean.
- `make guards`: rc 0 (check_blinding: 281 tracked files OK).
- gitleaks: no leaks.
- CI run 55: green.

## Prior QA required changes for P1
- **None to verify.** The P1 cycle-1 council had no QA review (reviews/phase_1/ has packet, biostatistician, strict_referee and watchdog only).
- I checked that the QA vote items still hold (reviews/qa_votes/BUG-019-020.md):
  - **D-050:** in_primary=True 58; analysis set (in_primary & qc_pass) 53; qc_pass=True & in_primary=False 0. FIXED, pinned by tests/test_manifest_schema.py:148.
  - **BUG-019:** the hash-pinned APPROVED_UNTAGGED is used (check_guard_config.py:44-55). FIXED. Mutant forcing the hash compare True is killed by tests/test_guard_config_bug019.py.
  - **BUG-020:** anchored `(?m)^…$` regex in .gitleaks.toml:13. FIXED. The test gap is in the G-D032 file.

## Mutation check
These mutants were killed:
- dropping qc_pass from `analysis_set` (test_manifest_schema.py);
- disabling the URL outcome word `reject` (test_guards_blinding.py);
- κ without the `/(1-pe)` term (test_owner_label_qc.py);
- control-ROI tail margin 5→2 in config.yaml (test_controls_config.py).

test_sealed_checksums.py was not mutated because it tests data/sealed.

## New defects
1. **The forced M0 covariate `upload_lag_days` is not populated, and many dates are not usable.**
   - data/manifest.csv has upload_lag_days empty in all 661 rows. That is documented as "empty for now" in D-048.
   - In the 53-row analysis set, `upload_date` is `UNKNOWN` in 15 rows (28%). The other 38 are YYYYMMDD.
   - v2.md:104 requires a `lag_unknown` flag plus median imputation, but the manifest has no such column.
   - `validate()` (src/yct/curate/manifest.py:122-161) never checks upload_lag_days against `fill_upload_lag`. Recomputing it gives 129 non-empty values across the manifest that differ from the stored ones, and validate stays silent.
2. **`validate()` accepts impossible values.** I probed copies of the real manifest; each of these returned `[]`:
   - duration_s `-5`;
   - duration_s `abc`;
   - upload_lag_days `9999`;
   - qc_pass=True on an in_primary=False row.
   
   duration_s drives T1 eligibility (`window.min_tail_s`) and BUG-018 exposure (20 of 53 rows > 70 s), so it should be typed and range-checked.
3. **The URL blinding scan (scripts/check_blinding.py:35) misses common outcome phrasings.** I ran synthetic URLs through `outcome_words()`; these returned no hit:
   - `…/our-yc-acceptance`
   - `…/admitted-to-y-combinator`
   - `…/getting-into-y-combinator`
   - `…/denied-by-yc`
   - `…/why-we-did-not-get-in`
   - `…/how-we-got+into+yc` (`unquote` does not map `+` to a space)
   
   P2 adds no new URLs, so this does not block downloads. It matters for wave-2 curation and for any new tracked text.
4. **Known open items:**
   - BUG-022 (missing round-2 quotes): non-blocking for P2. The verify tool must treat a missing quote as needs-recheck.
   - BUG-021: owner-side; no repo change.
   - `is_original_application_video` watch-verification: needs the P2 downloads, so it is correctly deferred. All 53 rows are currently `true`.

## Required changes
1. During P2, fill `upload_date` from the downloaded metadata where it is UNKNOWN (label-free). Then run `fill_upload_lag` and add the `lag_unknown` column. Make `validate()` assert `upload_lag_days == fill_upload_lag(...)` and that a flag is present for every empty lag. Add tests.
2. In `validate()`:
   - duration_s must be numeric and > 0;
   - upload_date must be YYYYMMDD, YYYY-MM-DD or UNKNOWN;
   - qc_pass=True implies in_primary=True.
   
   Add one failing-fixture test per rule.
3. In check_blinding:
   - extend OUTCOME_WORDS to accept(ed|ance), admit(ted), denied, `did(n'?t| not)[-_ +]get`, `into[-_ +](yc|y[-_ ]?combinator)`, and `+` as a separator;
   - apply `unquote_plus`;
   - add these probes to tests/test_guards_blinding.py.
