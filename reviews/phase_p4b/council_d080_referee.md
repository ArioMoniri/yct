# Council D-080: referee review (draft d080_draft.md, commits 8148366, 4118fa2)

Verdict: **REVISE** (one blocking item, small). Not read: data/sealed/*, labels, transcripts, outputs/.

## Outcome-blindness of C1 equivalence: yes, and safe
- The audit selects nothing: it only decides STOP vs continue. Selection is still the frozen evaluate_image
  in sha256(title) order up to 20 passes, so widening the audit cannot change which file passes.
- `licence` and `personality_rights` are both C1 rejects (frozen `audit.c1_reasons`), so the selection
  outcome is the same. The only v2 information used is the STOP row's two metadata reasons (0 passes).
  No detector or pass outcome entered the choice.
- `audit_pair` precedence is right: flip first (a listed title still at C1 is a STOP), then equal, then the
  §C duplicate rule, then c1_equivalent only if both are `reject` with C1 reasons. Admissibility changes are
  not covered. Both reasons are logged (`audit_c1_equivalent`). 59 d079+d080 tests pass locally.

## Dry audit: adequate for its stated scope
- It reuses the frozen evaluate_image, stopped at the download (`_NoDetectors`), plus the identity stage.
  A missing sha1 counts as would_stop. Every superseded title is checked against every log that lists it.
- Cross-checks hold. The file sha 35bb0b95… matches the config. The flip counts equal the committed flip
  file (260/108/3). The 2 face `revid_changed` rows match "2 edited pages". The 18 v2 run-1 rows give 12
  equal + 6 reaches_download. The 12 c1_equivalent pairs include the BUG-037 title.
- The limit is disclosed correctly: rules after the download, C3, and Commons drift after the dry audit stay
  under the in-run audit, and its STOPs resolve to v4 under the frozen rule. That is acceptable, because a
  STOP is fail-closed, not biasing.

## Blocking
- **B1. Enforce the launch rule in code.** `ra.check_frozen_d080` checks only that the sha is frozen and
  set. It never hashes `dry_audit_file` against `dry_audit_sha256`, and it never checks that every
  category's `would_stop` is empty. Add both checks (STOP otherwise), with a test, so that "0 would_stop" is
  enforced fail-closed and not only by people. Without this, the frozen sha protects nothing at run time.

## Non-blocking
- Add the code commit, the UTC time and the snapshot shas to the dry-audit JSON (or put them in §5) as
  provenance.
- Launch v3 soon after the freeze to keep the drift window short. Disclose the time between the dry audit
  and the launch.
- Remaining STOP risks are post-download determinism of the 348 reaches_download pairs (detectors, decode)
  and revision moves. Both are fail-closed, and neither biases selection.

## Re-sign-off (d080_v2.md, c5ccdfb, e7f87c8): **APPROVE**
- B1 resolved. `ra.check_dry_audit` (refstim_auto.py:575) re-hashes the file against `dry_audit_sha256`, requires `would_stop == []` and every category and superseded log, requires `code_commit`, and STOPs on a `git diff` of the code paths. `refstim_auto_run.py run` calls it before rank 1. Each refusal has its own test, and 110 d079/d080 tests pass locally.
- I checked the committed file. Its sha ca87244c… matches config.yaml. It has code_commit c5ccdfb, both categories, all 4 superseded logs, and an empty would_stop list. Its counts match the draft run.
- §A revid drift is outcome-blind. It only decides STOP vs resume, never which file passes. It is stated before the run and disclosed in image_revid_drift_v3.json.
- Non-blocking: (1) At run time the runner compares only commits and does not look at the working tree. A dirty checkout in the code paths at launch would pass the check. Add a `git status --porcelain` check for those paths (the dry-audit script already does this) or record the clean state in the run rows. (2) config.yaml is not in DRY_AUDIT_CODE_PATHS. It is covered only by the frozen shas, so confirm that the c1/exempt reasons are inside the frozen surface. (3) Provenance still lacks a UTC time and the snapshot shas. Disclose the gap between the dry audit and the launch in the v1 report.
