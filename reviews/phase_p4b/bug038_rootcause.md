# BUG-038 root cause (v3 run STOP at body rank 136)

## Summary
The STOP was not a Commons or template-merge fault. The determinism audit classified "C1 reject" by the
**reason code**, but the frozen `rule_reasons` map gives the same code, `personality_rights`, to three rules:

- C1 (Template:Personality rights on the file page, metadata stage);
- F7 (face, CLIP adult proxy, after the download);
- B4 (body, CLIP adult proxy, after the download).

'File:Mohammad Bagher Adib Behrooz 2016 (Unsplash).jpg' **passed C1** in v3: it is Cc-zero and admissible, exactly as the BUG-036 flip list says. It was then rejected by **B4**: CLIP gave 0.977 for "a photo of a child" against 0.023 for "a photo of an adult". The audit read its reason `personality_rights` as a C1 reason, so it judged the flip-listed title to be "still a C1 reject in v2" and raised "flip list contradiction".

## Evidence
1. **The committed v3 logs show that `personality_rights` is not always C1.** Two logged rows carry reason `personality_rights` with no Personality rights template:
   - face row 44, 'File:Face in water.jpg', rule F7, licence Cc-by-4.0;
   - body row 48, 'File:Elderly Chinese American Man with Queue b.jpg', rule B4, licence PD.

   All other `personality_rights` rows are rule C1 and carry the template. The superseded logs show the same pattern: face v1 has one F7 row and body v1 one B4 row.
2. **Metadata replay** (pod, commit 6ba2230, `scripts/refstim_bug038_replay.py meta`, read-only). It re-read the exact in-run batch, `rs.ordered(body snapshot)[100:150]`, which is the batch the runner fetches at i = 100. Three raw responses were taken, including the continuation pages, and saved to `s3://yct-research-235229001983/refstim/bug038/raw/`.
   - No file in the batch carries Template:Personality rights.
   - The merged templates of all 35 logged rows of that batch (ranks 101–135) equal the logged `templates_sha256` exactly (35/35).
   - The STOP title is at read_revid 1216330296, the same as the snapshot and the dry audit.

   This rules out:
   - wrong-title attribution in the continuation merge;
   - normalisation or redirect mapping faults;
   - a different batch;
   - C4 query mixing;
   - revision drift.

   There is no cache on the metadata path.
3. **Rule replay** (pod, `scripts/refstim_bug038_replay.py rule`, frozen detectors, empty C3 state, nothing logged). The STOP title gives licence CC0 (Template:Cc-zero), admissible, then reject at rule **B4**, reason `personality_rights`, with clip_adult [0.977201, 0.022799] against the prompts ["a photo of a child", "a photo of an adult"].
4. **The dry audit could not foresee it.** It stops at the download, so it correctly predicted `flip` (C1 now passed). The B4 reject only exists after the download.

## The defect, both directions
The audit used `reason in c1_reasons` in three places in `ra.audit_pair` and once in `ra.dry_pair`.

| Case | Old behaviour | Correct |
|---|---|---|
| flip-listed v1 C1 reject → v3 F7/B4 reject | STOP (contradiction), **this STOP** | flip |
| v1 C1 reject (not listed) → v3 F7/B4 reject | **c1_equivalent (silently exempt)** | STOP (C1 admissibility changed) |
| v1 duplicate → v3 F7/B4 reject | STOP | duplicate_exempt |
| v1 F7/B4 reject, flip-listed | flip | contradiction STOP |

The second row is the dangerous one: an unlisted admissibility change would have been exempted. It has not happened. Every logged `c1_equivalent` note in v3 (face 1, body 2) is a C1-rule pair on both sides.

## Fix (TDD, `tests/test_refstim_bug038.py`, 11 tests, 9 failing before the fix)
- `ra.is_c1_reject(row, c1)`: a C1 reject is `decision == reject and rule == "C1"`.
  - A reject row with no rule STOPs; every committed log row has a rule.
  - A C1 row with a non-C1 reason also STOPs.
- `ra.audit_pair` takes `a_c1` / `b_c1` (by rule) as required keyword arguments and no longer reads reasons for the C1 class. `ra.audit_v2` and `ra.dry_pair` pass them. The rule is computed outside the revid-drift `try`, so a missing rule can never be reclassified as drift.
- Evidence: `ra.write_stop_evidence` writes the full evaluated row (templates, `templates_sha256`, rule, values) to `<log>.stop.json` before an audit STOP propagates. The runner wraps `audit_v2` with it. Every row already logs `templates` and `templates_sha256` (D-079).

## Impact on the v3 rows already logged (offline re-audit)
`scripts/refstim_bug038_audit_v3.py` (no network) writes `data/refstim/bug038_audit_v3.json`, sha 0259b3b3…ccf9.

- face: 492 rows, 20 passes. Fixed audit: flip 141, equal 368, c1_equivalent 1, **0 STOP**. 1 row reclassified by rule (Face in water, F7), whose audit is `equal` either way.
- body: 135 rows, 8 passes. Fixed audit: equal 74, flip 16, c1_equivalent 2, **0 STOP**. 1 row reclassified (Elderly Chinese American Man, B4), which has no superseded row.
- **No face pass and no face reject changes.** The audit selects nothing: decisions come from `evaluate_image` alone, and no row's audit outcome differs under the fix apart from the STOP title itself.

## Not a fault (ruled out)
The following were considered and ruled out:
- the Commons API or templatelinks;
- the `query_pages` continuation merge;
- title normalisation;
- batch reconstruction;
- caching;
- revision drift.

The BUG-038 note's two candidate causes ("transient Commons response", "merge defect") were both wrong.
