# D-080 draft: BUG-037 audit amendment of D-079, v3 image logs

Status: DRAFT for the five-member council. Not in DECISIONS.md and not frozen. The runner refuses to run v3
until `controls.refclips_d080` and `controls.refclips_d080_artifacts.dry_audit_sha256` are frozen
(`ra.check_frozen_d080`).

## 1. Trigger (BUG-037)

The D-079 v2 run 1 (frozen commit f3b25d1) stopped at face rank 19 with 0 passes after 18 rows. The
determinism audit compared `File:Massimiliano M. Schiraldi.jpg`: the v1 face log had `licence` (C1), and v2
had `personality_rights` (C1). The file is a C1 reject both times. Under BUG-036, the truncated template list
hid `Template:Personality rights`, and the licence template was missing too. So v1 fell through to the
`licence` branch, while the fixed client reads the personality-rights template first. The BUG-036 flip list
records only inadmissible → admissible changes, so it never covered a reject → reject change of reason. The
frozen `stop_resolution.other_audit_stop` therefore applies: a code defect, a BUG entry (BUG-037) and v3 from
rank 1 for every category.

## 2. Amendment (audit rule only; selection unchanged)

- **Audit rule (option b), config `controls.refclips_d080.audit_c1_equivalence: true`.** When both the new
  row and a superseded row are C1 rejects (`licence` and/or `personality_rights`, the frozen
  `audit.c1_reasons`), the pair is `c1_equivalent`: the file is rejected at C1 both times, so the selection
  outcome is identical.
  - The run logs both reasons: `row.audit_c1_equivalent = {superseded log: its reason}`.
  - Every other D-079 rule is unchanged:
    - the flip list is checked first, and a listed title still rejected at C1 is a STOP;
    - inadmissible → admissible without listing is a STOP;
    - admissible → inadmissible is a STOP;
    - the re-check B2 duplicate rule stands;
    - identity_changed is exempt;
    - anything else is a STOP treated as a code defect.
  - Tests: `tests/test_refstim_d080.py` (equivalence in both directions; off when the flag is false, i.e. the
    D-079 behaviour; the flip precedence; that admissibility changes are not covered).
- **v3 logs.** `controls.refclips_d080.logs` are `image_{face,body,place}_auto_log_v3.jsonl`,
  `log_version: v3`. The runner and finalise read them through `rs.effective_cfg`, which overlays D-080 on
  D-079 without editing the frozen D-079 key.
  - Preload and finalise refuse any row whose log_version is not `v3`.
  - The order stays face → body → place.
  - C3 state comes only from the v3 logs already run.
- **Superseded logs.** The v1 logs (D-079) plus the v2 run-1 face log (18 rows, 946d391) are kept
  byte-identical as evidence and read only by the audit.
  - The v2 run-1 rows were made by the fixed client with the same frozen filters, so v3 must reproduce them
    exactly. Their log name is in no flip list.
  - The flip file stays keyed to the D-079 v1 logs (`flip_logs`). Its sha is unchanged.
- **Unchanged:** snapshots (D-074, D-078 union), ascending sha256(title) order, the first 20 passes per
  category, every D-075 filter and threshold, `reject_reasons` + `identity_changed`, `stop_resolution`,
  identity and revid rules, the D-078 union kept as frozen (owner, 2026-11-21), and the disclosures of D-078
  and D-079.
- **Finality:** `v3_is_selection`. A v4 is allowed only for a code defect found by a fail-closed check or a
  BUG entry, from rank 1, and disclosed. It is never allowed because of v3 outcomes.

## 3. Pre-launch dry audit (no surprises at C0–C4 or the identity metadata stage)

`scripts/refstim_d080_dry_audit.py` makes metadata reads only (fixed client, `rs.page_meta_c4`): no download,
no detector, no log write. For every title in each category's superseded logs it predicts the v3 decision
before the download. The prediction uses the identity metadata stage, then the frozen `evaluate_image` run up
to the download (C0–C4; C3 inert because it depends on earlier passes). It then classifies each pair with
`ra.dry_pair`:

- `equal`
- `c1_equivalent`
- `flip`
- `duplicate_exempt`
- `identity_changed`
- `reaches_download` (later rules are re-evaluated in the run)
- `would_stop`

The output, `data/refstim/d080_dry_audit.json` (counts plus sha256(title) keys of every would_stop pair), is
committed. Its sha goes in `controls.refclips_d080_artifacts.dry_audit_sha256` and is frozen with D-080.

- **Launch rule:** v3 launches only if the dry audit has 0 `would_stop` pairs. Otherwise each is a defect
  to diagnose (BUG entry) before D-080 is frozen.
- **Limit (disclosed):** the dry audit cannot predict rules after the download (C5, F*, B*, P*). It also
  cannot predict C3 or a Commons revision that moves between the dry audit and the run. Those stay covered
  by the in-run audit and its frozen stop rules.

Dry-audit counts: see §5, filled in from the pod run.

## 4. Disclosure (v1 report)

- D-079 v2 run 1 stopped at face rank 19 (BUG-037). Its 18 rows are superseded evidence and never selection.
- The audit rule was widened only for C1 → C1 reason changes, and the dry audit was run before launch.
- The selection rule is unchanged, and no filter outcome was used to choose this amendment. The only v2
  information used is the identity of the STOP row and its two reasons.
- v3 is the selection set.

## 5. Dry-audit result (pod, commit 8148366, exit 0)

`data/refstim/d080_dry_audit.json`, sha256 35bb0b9530e11dd1b1912c65cd3053d4c2571dc271edfac7b36880df3eed6fe7.
The sha is set in `controls.refclips_d080_artifacts.dry_audit_sha256` but not yet frozen.

| superseded log | equal | c1_equivalent | flip | reaches_download | would_stop |
|---|---|---|---|---|---|
| image_face_auto_log.jsonl (v1, 948) | 451 | 2 | 260 | 235 | 0 |
| image_face_auto_log_v2.jsonl (v2 run 1, 18) | 12 | 0 | 0 | 6 | 0 |
| image_body_auto_log.jsonl (v1, 568) | 346 | 9 | 108 | 105 | 0 |
| image_body_d078_auto_log.jsonl (v1, 15) | 9 | 1 | 3 | 2 | 0 |

- `would_stop` = 0, so the launch rule in §3 is met.
- No `identity_changed`, no `duplicate_exempt` (C3 is inert in a dry run) and no missing sha1.
- The 12 c1_equivalent pairs are the whole BUG-037 class. Under D-079 every one of them would have stopped
  the run; the BUG-037 title is one of the 2 face pairs.
- The flip counts equal the committed BUG-036 flip list (260 / 108 / 3).
- The 2 face files whose Commons page was edited since the snapshot give no would_stop at the metadata stage.
- The place category has no superseded log, so there is nothing to audit there.
