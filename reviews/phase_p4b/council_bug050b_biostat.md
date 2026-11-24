# Council BUG-050b: biostat. Verdict: REVISE (one blocking item; the rule itself is approved)

Read: bug050b_diagnosis.md, BUGS.md BUG-050b, cc95d90, d8d725c, tests/test_bug050b_restore_modes.py, 506fe32, gpu_wave1_p4.py (restorable*, do_job post-run check, both stage()), cache_archive.archive_entry/restore_entry, council_bug050b_referee.md. No sealed data, labels, transcripts, or feature/prediction values read.

- **Cause and rule: correct.** The tar holds only regular files, and FILES_SHA256SUMS lists every one of them plus the media, so equal sums mean the same entry content. Mode bits do not enter any computation that produces a prediction. Keeping the stored tar_sha256 on the row and entry record is required: if the re-archive sha were recorded, `restorable_by_content` would see 2 tar shas for one key and STOP. Skipping re-upload avoids OverwriteRefusedError on crash recovery. A sums mismatch must stay a STOP.
- **Outcome-blind: yes.** The rule was written down before any rerun. It uses only file and header hashes, and changes no gate, threshold, config or prediction path.
- **BLOCKING 1 (concurring with the referee): the sums anchor is unverified.** The live `stage()` checks only `entry.tar` against `restore['tar_sha256']`. It copies `entry.sums` with no check, and `restore_entry` trusts that copy. The trust chain the fix needs is: tar sha verified → members verified against the sums → sums sha verified against the recorded `sums_sha256`. Its last link is missing. The fix must:
  - (a) Fail closed at staging if sha256(entry.sums) differs from the recorded `restore['sums_sha256']`, in both the live and the dry-run stage.
  - (b) Compare the re-archived sums sha after the run with that recorded value.
  - (c) Apply the rule to both crash-recovery and content-key restores, including condition jobs that restore the base entry.
  - (d) Add a test for (a) and a test for (b), alongside the two tests the diagnosis already plans.
- **Umask / permission normalisation: no, neither instead of nor in addition to the fix.** `filter="data"` already normalises modes on restore, and a umask cannot restore bits the filter strips. Normalising modes on archive, or setting umask 022 on the box, changes future fresh tar bytes relative to the 16 stored tars, is a box change in the middle of a campaign, and leaves the stored 0o777 entries as they are. Content identity is the correct invariant. umask 022 is at most optional hardening for a later campaign, under its own D- entry.
- **Frozen P4 / D-038: no risk.** P4 changes only in the crash-recovery branch, which has never run (0 `restored_from_s3` rows in 138 + 13). D-038 Gates 1 and 2 compare same-box `pred_sha256`, and their 3 clips were extracted fresh. Record `rearchive_tar_sha256` as descriptive only, never as an identity.
- **Non-blocking (stats):** a restored GREY_CTRL_01 reuses GREY_CTRL_00's features, so its prediction is not an independent draw. The R4 disclosure (GREY-CTRL n_eff = 1) already covers this, and it must stay in the report.

## Re-sign-off (fc3c27b, ae80106): APPROVE
- (a) Satisfied. Under `set -euo pipefail`, the live `stage()` checks sha256(entry.sums) against `restore['sums_sha256']`. The dry-run `stage()` raises `RestoreIntegrityError` before `restore_entry`, and a missing recorded value also fails closed.
- (b) Satisfied. In `do_job`, a restored job must have the same key and a re-archived sums sha equal to the recorded `sums_sha256`, else STOP before any upload or row. Both restore kinds pass the entry dict, which carries `sums_sha256`, so (c) is met, `base_id` included.
- (d) Satisfied. Restored jobs skip both `put_file` calls, the row and entry keep the stored shas, and `rearchive_tar_sha256` is descriptive only. The staging, post-run, crash-recovery, condition and 506fe32 tests are all present. I ran 13 tests and all passed. No umask change and no mode normalisation.
- Non-blocking: the R4 n_eff = 1 disclosure for GREY-CTRL stays in the report.
