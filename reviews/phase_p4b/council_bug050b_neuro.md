# Council BUG-050b: neuro. Verdict: REVISE (one blocking item, concurring with referee/biostat; the rule itself is approved)

Read: bug050b_diagnosis.md, BUGS.md BUG-050b, cc95d90, d8d725c, tests/test_bug050b_restore_modes.py, 506fe32, gpu_wave1_p4.py (do_job post-run check l.484-507, live stage l.1201-1222), and the other three council_bug050b_* notes. I read no sealed data, labels, transcripts or feature/prediction values.

- **Cause and rule are correct.** Mode bits are tar-header metadata. No extractor, encoder or TRIBE forward pass reads them: tensors, `.jsonl`/`.data` and `inflight.db` are read by content. Equal FILES_SHA256SUMS (names + bytes of every regular member, media included) means the features fed to the model are the same, so a header-only difference is no scientific difference. Keeping the stored tar/sums as the single identity, with no re-upload and a STOP on any sums difference, is right.
- **Outcome-blind: yes.** The inputs are hashes, modes and member names only. The rule was written before any rerun, GREY_CTRL_01 has no row, and no gate, config or prediction path changes.
- **BLOCKING 1: anchor the sums to the recorded sha.** The live `stage()` (l.1215) copies `entry.sums` without checking it, and `restore_entry` then trusts that copy for the media and member checks. The fix must:
  - fail closed at staging (live and dry-run) when sha256(entry.sums) differs from `restore["sums_sha256"]`;
  - after the run, compare the re-archived sums sha with that recorded value;
  - cover both restore kinds: crash/job-id restores, including non-full conditions restoring `base_id`, and content-key restores;
  - skip both `put_file` calls for restored jobs, with a test for each point.
- **Umask / permission normalisation: no, neither instead of the fix nor in addition to it.** `filter="data"` already normalises on restore, and a umask cannot bring back the stripped bits. Changing the box umask or normalising modes in `archive_entry` mid-campaign changes the headers of fresh tars relative to the 16 stored ones and gains nothing in correctness. That could be hygiene for a later campaign, under its own D- entry.
- **Frozen P4 / D-038: no risk.** P4 changes only in the crash-recovery branch, which has never run (0 `restored_from_s3` rows in 138 + 13). D-038 Gates 1/2 are same-box fresh reruns compared by `pred_sha256`, with no restore. `rearchive_tar_sha256` stays descriptive only.
- **Non-blocking:**
  - If a later extractor version opens `inflight.db` read-write during prediction, sqlite page writes could change its bytes. The sums check would then STOP, which is the correct, conservative outcome. Session 3 shows it does not happen today.
  - A restored GREY_CTRL_01 reuses GREY_CTRL_00's features. Keep the n_eff = 1 disclosure.

## Re-sign-off (fc3c27b, ae80106): APPROVE, BLOCKING 1 is resolved
- (a) Staging fails closed when sha256(sums) != the recorded `sums_sha256`, in the dry-run `stage()` (RestoreIntegrityError) and in the live `stage()` (`set -euo pipefail` with an explicit exit, or a KeyError when the field is missing). (b) The post-run check in `do_job` compares the re-archived sums sha with the recorded value and raises before any `put_file`, row or entry write.
- (c) A single `if restore:` branch covers content-key and job-id/`base_id` restores. (d) Restored jobs skip both `put_file` calls. Rows and entries carry the stored tar/sums shas, and `rearchive_tar_sha256` is descriptive only. There is no umask or mode change.
- Tests: `tests/test_bug050b_fix.py` (4) and the 506fe32 driver test cover each point, and 13/13 pass locally, `test_p4_campaign_is_unaffected` included.
- Non-blocking: no test covers a post-run sums mismatch on a job-id restore, or the live staging script (dry-run only). Rows from earlier gate checks (gate_fail, D-038 stop) can still be appended before the sums check for a restored job. That is pre-existing behaviour.
