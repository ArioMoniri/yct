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
