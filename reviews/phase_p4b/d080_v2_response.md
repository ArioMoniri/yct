# D-080 cycle 1: response matrix

| Member | Item | Response | Where |
|---|---|---|---|
| Watchdog | B1 (a) dry audit records per-title read revid | `read_revids` (sha256(title) → revid) per category in the dry-audit JSON | `scripts/refstim_d080_dry_audit.py`; `d080_v2.md` §A |
| Watchdog | B1 (b) pre-stated resolution for drift after the dry audit | `stop_resolution.audit_revid_drift: current_revision_stands_log_both_resume_next_rank`; `ra.revid_drifted`, `revid_drift_rows`, `revid_drift_disclosure`; finalise writes `image_revid_drift_v3.json`; no v4 | `config.yaml`, `config_schema.py`, `refstim_auto.py`, `refstim_auto_run.py`; tests `test_drift_*`, `test_no_drift_*`, `test_title_missing_*`, `test_revid_drift_disclosure_lists_rows` |
| Referee | B1 runner re-hashes the dry-audit file and requires would_stop empty | `ra.check_dry_audit` before rank 1: sha, would_stop, categories, logs | `refstim_auto.py`, `refstim_auto_run.py run`; tests `test_launch_rule_refuses_*` |
| Biostat | (a) recompute sha == frozen sha | as above | `test_launch_rule_refuses_a_sha_mismatch` |
| Biostat | (b) would_stop == [] for every category; every superseded log present | as above | `test_launch_rule_refuses_would_stop`, `_a_missing_superseded_log`, `_a_missing_category` |
| Biostat | (c) code commit recorded; refuse if code changed since | `code_commit` in the JSON; the script refuses with uncommitted changes in `DRY_AUDIT_CODE_PATHS`; runner `git diff` check | `test_launch_rule_refuses_without_a_code_commit`, `_changed_code`, `test_dry_audit_code_paths_cover_the_client_and_the_script` |
| Neuro | non-blocking: run in the same pod environment; launch soon after the freeze | noted for the freeze/launch step | — |
| Neuro | nit: check_frozen_d080 does not re-hash | resolved by `check_dry_audit` | — |
| QA | APPROVE | — | — |

The dry audit was re-run at the code commit c5ccdfb; results in `d080_v2.md` §C.
