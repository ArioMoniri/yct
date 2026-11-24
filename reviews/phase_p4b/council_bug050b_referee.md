# Council BUG-050b: referee. Verdict: REVISE (one blocking item; the rest of the fix is approved)

Read: bug050b_diagnosis.md, BUGS.md BUG-050b, cc95d90, d8d725c, tests/test_bug050b_restore_modes.py, 506fe32, and gpu_wave1_p4.py do_job/stage/restorable*, plus cache_archive.archive_entry/restore_entry. I read no sealed data, labels, transcripts or feature/prediction values.

- **Cause confirmed.** `restore_entry` extracts with `filter="data"`, which strips g/o write bits. `archive_entry` keeps `gettarinfo` modes in the headers, so the re-archived tar differs while the content sums stay identical. The two characterisation tests pin this, and 506fe32 reproduces the driver STOP.
- **Rule is correct.** Judging a restored entry by FILES_SHA256SUMS is sound. The sums list every regular file in the entry, media included, and the tar holds nothing else because `_files` returns regular files only. Keeping the stored tar as the record is also required: if a row recorded the re-archive sha, the next content-key lookup would see 2 tar shas for one key and STOP (`restorable_by_content`, len(tars)>1). 506fe32 already asserts g1.tar_sha256 == g0.tar_sha256. Skipping re-upload is needed too, because `put_file` would otherwise raise OverwriteRefusedError on the crash-recovery path.
- **Outcome-blind: yes.** The decision uses only hashes of files and headers. It was written down before any rerun and does not change the gate, config or prediction path.
- **BLOCKING 1: the sums anchor is not sha-verified today.** The diagnosis says the stored sums were "already sha-verified on the pod at staging". `stage()` checks only `entry.tar` against `restore['tar_sha256']`. `entry.sums` is copied with no check, and `restore_entry` then trusts it for media and member checks. The fix must:
  - (a) Check the sha256 of the staged `entry.sums` against the recorded `restore['sums_sha256']` at staging, failing closed.
  - (b) After the run, compare the re-archived sums sha with that recorded `sums_sha256`, not with whatever file was staged.
  - (c) Apply the rule to both restore kinds: crash recovery (`restorable()` entry, including condition jobs restoring the base entry) and content key.
  - (d) Add a test for each of (a) and (b), alongside the two tests already planned (sums mismatch is a STOP; crash restore of a 0o777 entry does not re-upload or refuse).
- **Umask / permissions: no, neither instead of nor in addition to the fix.**
  - Extraction already normalises permissions (filter="data"), and a restore-side umask cannot bring back bits the filter strips.
  - Normalising mode in `archive_entry`, or setting umask 022 on the box, changes the bytes of future fresh tars relative to the 16 stored ones. It also leaves the stored 0o777 entries as they are, and it is a box/config change in the middle of a campaign.
  - Content identity is the correct invariant. If anything, umask 022 is optional hardening for a later campaign.
- **Frozen P4 / D-038: no risk.**
  - P4 changes only in the never-exercised crash-recovery branch (0 `restored_from_s3` rows in 138 + 13). Existing tests already pin the fresh-path upload and row as unchanged.
  - D-038 Gate 1/2 compare `pred_sha256` reruns on the same box, and `fresh_feat.tar` is untouched. GREY_CTRL_00, SPK_00 and MOT_00 were extracted fresh, so their claims stand.
  - Record `rearchive_tar_sha256` as descriptive only, and never use it as an identity.

## Re-sign-off (fc3c27b, ae80106): APPROVE
- (a) Staging is anchored: live `stage()` now fails closed on sha256(entry.sums) != recorded `sums_sha256` (an empty or missing value also fails), and so does the dry-run `stage()`. The tar check is unchanged.
- (b) In `do_job`, the post-run re-archived sums sha must equal `restore['sums_sha256']` (the recorded value, not the staged file) and the key must match, else `RestoreIntegrityError`. The check runs before any upload or row append.
- (c) Both restore kinds go through the same `if restore:` branch: content key, and job id including non-full conditions restoring `base_id`. Both get their dict from the stored entry JSON, which carries `sums_sha256`.
- (d) Restored jobs skip both `put_file` calls. The row and entry carry the stored tar and sums shas, and `rearchive_tar_sha256` is descriptive only. No umask or mode change.
- Tests: staging mismatch, post-run mismatch with no upload, crash restore of a umask-0 entry, non-full base restore, and the 506fe32 driver test. All 15 BUG-050/050b tests pass locally. No blocking items.
