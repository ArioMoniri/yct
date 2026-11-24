# BUG-050b diagnosis: false CacheKeyConflictError after a content-key restore

Session 3 (`p4bref_20261124T090803Z`, launched from e51f6c8) stopped on its first job. GREY_CTRL_01.ref restored GREY_CTRL_00.ref's
cache entry by content key `b9ff59ee…` (the BUG-050 fix). After the run, the driver re-archived the entry and got a tar sha of
`8705275e…`, against the stored `858643…`. The post-run identity check raised `CacheKeyConflictError`. Nothing was uploaded and no row was written.

Nothing here reads feature or prediction values. The evidence is tar member names, modes, sizes, mtimes, per-member sha256,
and the FILES_SHA256SUMS text.

## 1. Evidence

- **The stored and re-archived tars hold the same files with the same content.**
  - The stored tar comes from S3 `feature_cache/b9ff59ee….tar`. The re-archived tar is the one the box produced. It is still
    on the pod at `/work/yct/p4/runs/p4bref_20261124T090803Z/GREY_CTRL_01.ref/GREY_CTRL_01.ref.entry.tar`, because `collect`
    copies it before the check.
  - Both have the same 14 members, with none missing or extra.
  - All 14 have identical content (per-member sha256 equal), identical sizes, and mtime 0, uid/gid 0.
  - The comparison was run on the pod with `scripts/bug050b_members.py`.
- **Only file modes differ, on 7 members.** The 6 `.jsonl` / `.data` / `inflight.db` files under both extractor dirs went from
  0o777 to 0o755, and `features.meta.json` went from 0o664 to 0o644.
- **The content sums are byte-identical.** The stored `FILES_SHA256SUMS` and the box's re-archived one have the same sha,
  `fa0e6ebb…`, which `cmp` confirms. These sums cover the media too.
- **Offline repro.** `scripts/bug050b_repro.py` extracts the stored tar under each tarfile filter and re-archives it with the
  same member loop as `archive_entry`:
  - `filter="data"` and `"tar"` give modes {0o644, 0o755} and a different tar.
  - `filter="fully_trusted"` keeps the modes and gives back `858643…` bit for bit.
  - So the archiver itself is deterministic. The change comes from extraction.

## 2. Cause

`cache_archive.restore_entry` extracts with `tarfile.extractall(..., filter="data")`, which is the right choice for safety. That filter
clears group and other write bits. The GPU box wrote the original cache files with 0o777 / 0o664 (its extractor's umask).
`archive_entry` puts each file's mode in the tar header (`gettarinfo`), so it normalises mtime, uid, gid and names, but not mode. A restored
entry therefore re-archives to different bytes with the same contents. The post-run check in `gpu_wave1_p4.py`
(`files["entry_tar"][1] != restore["tar_sha256"]`) compares tar bytes, so it fires on a header-only difference.

The dry-run tests did not see this because files written under umask 022 are already 0o644, which "data" leaves unchanged.
`tests/test_bug050b_restore_modes.py` pins both cases: group-writable files give different tars with the same sums, and 0o644 files
give identical tars.

## 3. Same latent issue in the crash-recovery restore (P4 and ref)

The crash-recovery path stages through the same `restore_entry` and then re-archives in `collect`. It then calls `put_file` on the same
`feature_cache/<key>.tar`. The immutable store would refuse, because it holds the same key with different bytes (`OverwriteRefusedError`). This
is the latent issue, but it has never been exercised in production. The P4 manifest has 138 rows and the ref manifest 13, and neither has
a row with `restored_from_s3: true`. No frozen P4 result went through this path. A real crash recovery on a GPU box would fail the
same way.

## 4. Proposed fix (written down before any further run; needs a council check)

For any job whose entry was restored (crash recovery or content key), the entry's identity is the stored object, which was already
sha-verified on the pod at staging. The rule:

1. **Identity check on content, not tar bytes.** After the run, compare the re-archived `FILES_SHA256SUMS` text with the
   stored sums object (stored `sums_sha256`), byte for byte. That covers every member including media, and asserts the staged
   members are unchanged after the run. Keep the existing checks that the cache key is equal and that `FeatureStore.verify`
   passes before and after prediction.
   - Sums differ: this is a real conflict, raise `CacheKeyConflictError` and STOP, as today.
   - Sums equal: record the stored `tar_sha256` and `sums_sha256` on the row and the entry record. Do NOT re-upload the
     re-archived tar or sums, since the stored objects stay the single identity. Record the re-archived tar sha as
     `rearchive_tar_sha256` (descriptive), with a note that the difference is header-only.
2. **Scope.** Only restored jobs are affected. Freshly extracted jobs keep today's behaviour of archiving and uploading the tar.
   The P4 (D-063) path changes only in the latent crash-recovery branch, where it becomes correct. No frozen config or
   artifact changes, and no stored tar is rewritten.
3. **Rejected options:**
   - Normalising the mode in `archive_entry` would change the bytes of every future tar relative to the 16 stored ones, and
     would not fix entries already archived with 0o777.
   - Extracting with `filter="fully_trusted"` gives up the safety of the "data" filter.
   - Chmodding to the recorded mode after extraction re-creates world-writable files on the box.
4. **Tests.**
   - On the campaign branch, now: `tests/test_bug050b_restore_modes.py` (2 tests, pass).
   - On local branch `bug050b-failing-test` (506fe32, not pushed because the guards forbid xfail):
     `test_bug050b_restored_entry_with_group_writable_files_is_not_a_false_conflict`. It runs session 1 under umask 0, as on the box,
     and session 2 restores by content key. It reproduces the exact `CacheKeyConflictError` and passes once the fix lands.
   - The fix should also add two tests: sums differing after the run is a STOP, and the crash-recovery restore of a
     group-writable entry neither re-uploads nor refuses.

## 5. Effect on results so far

- No prediction was published for GREY_CTRL_01 in session 3.
- The 13 passing jobs (sessions 1–2) were all extracted fresh, not restored, so this does not affect them.
- The D-038 bit-identical claims for GREY_CTRL_00, SPK_00 and MOT_00 still hold. Their cached re-runs happened on the same box,
  with no restore.
