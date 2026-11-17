# Phase 1 (wave 1) cycle 2 — Strict Referee (fresh, adversarial)

**Scope.**
- Commit 31235e6; data/sealed/ not opened; no per-row/per-company outcome info here.
- I read only label-free manifest aggregates: 58 in_primary, 53 with qc_pass (53 companies); platforms 46/6/1; era_block E3 43 / E12 10; `upload_lag_days` empty in 53/53.

## Verdict: GO for P2 downloads and normalisation of wave 1

P1 is **not** closed (pHash/pilot-hash checks DEFERRED-OK to P2); P3/P4 stay blocked until B1–B6 are done.

## Prior required changes

- **D1 (blinding).**
  - Logged: **FIXED** (BUGS.md:22).
  - The exposed rows are outside the analysis set (DECISIONS:81–82).
  - Salted `company_id`: **NOT FIXED**. The column is still the plain name.
- **D2 (counts).** **FIXED** (DECISIONS:75). The analysis set is 53 rows, one per company.
- **D3 (platform/timing).**
  - (a) **NOT FIXED** in code: the covariates are absent from config.yaml:175–186, and lag is empty (DECISIONS:76).
  - (b) **FIXED**: v2.md:104.
  - (c) **FIXED** in the spec (v2.md:368), but missing from ROADMAP P2 (ROADMAP.md:79–99).
  - (d) **DEFERRED** to unblinding. There is no flag before unblinding.
- **D4 (query-class sealing, NEUTRAL sensitivity).** **NOT FIXED.**
  - No query class is recorded anywhere.
  - The blocks were built from the fallback `discovery_method` (owner_label_qc.sh:59–60, 249–257), not from the OPEN/TARGETED rule (v2.md:98).
- **D5 (watching).** **DEFERRED-OK** to P2 (v2.md:358). 16 of 53 rows run longer than 75 s.
- **D6 (era merge).** **FIXED** (config.yaml:32–38).
- **D7 (tools and tests).**
  - Manifest schema and κ: **FIXED** (test_manifest_schema.py, test_owner_label_qc.py).
  - verify_labels.py, the quote/snapshot test and the pair file: **NOT FIXED** (ROADMAP.md:57, 60).

## New defects

**N1. Blocks deviate from D-040 and were computed on the stale set.**
- BUGS.md:32 reports 4 blocks over 58 rows, sizes 4/4/45/5.
- After the "merge < 6 within route" step, only one block per route can stay below 6. Three small blocks therefore mean the route has ≥ 3 sparse levels, not two (OPEN/TARGETED).
- Small single-route blocks are likely label-pure, so the effective N is at most about 45; codes are also stale (58 ≠ 53).

**N2. Group totals and the stop rule have not been restated for the 53 rows.**
- D-050 dropped 5 rows by derivation agreement.
- v2.md:23 still says "56 companies … 30/26".
- There are no owner-side totals, so neither ≥ 20 per group nor the MDE has been verified.

**N3. Watching is a blinding risk.**
- Post-decision re-uploads may show the outcome.
- v2.md:358 does not say who watches or what they may output.
- ROADMAP P2 omits the re-encode, the codec/bitrate logging and the rubric.

**N4. Exposure is untracked.**
- The BUG-021 ids are not recorded, even in sealed form.
- There is no sensitivity analysis that excludes the exposed rows (BUG-013, BUG-021).

## Required changes

**Before the first watch or encode**
- **C1.** Commit the rubric (submitted / re-edit / compilation / outcome-revealing). A Curator or sealed agent does the watching and outputs only {keep, exclude, reason-code}.
- **C2.** Add the D-047 tasks to ROADMAP P2 and fix ROADMAP.md:76.

**Before P3/P4**
- **B1.** Owner-side, recompute the blocks on the 53 rows using OPEN/TARGETED. Print only the block sizes and the N in label-mixed blocks.
- **B2.** The owner or Curator releases the group totals for the 53 rows. Restate v2.md:23 and the MDE.
- **B3.** Fill `upload_lag_days` and wire it into `m0:`, or decide otherwise per G-D032 N2.
- **B4.** Replace `company_id` with a salted hash; keep the mapping sealed.
- **B5.** Seal the first-hit query class; add a NEUTRAL-only sensitivity outside Holm.
- **B6.** Commit verify_labels.py (BUG-022 rules) and the pair file. Record the BUG-021 ids sealed, and add an exposed-rows-excluded sensitivity.
