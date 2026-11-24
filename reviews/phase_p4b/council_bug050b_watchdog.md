# BUG-050b council: watchdog — APPROVE (with binding conditions)

Read: bug050b_diagnosis.md, BUGS.md BUG-050b, cc95d90, d8d725c, tests/test_bug050b_restore_modes.py, 506fe32, `do_job`/`restorable`/`put_file` in scripts/gpu_wave1_p4.py, `restore_entry` in src/yct/tribe_run/cache_archive.py. I read no sealed data, labels, transcripts, features or predictions.

- **Correct.** The cause is shown by member metadata: `filter="data"` clears g/o write bits, and `gettarinfo` writes mode into the header. The offline `fully_trusted` round trip is bit-identical, and the 0o644 control isolates mode as the only variable. Judging identity by FILES_SHA256SUMS (names + content of every member, media included) is the right invariant. Tar bytes were never a content claim.
- **Outcome-blind.** Every input to the decision is a header, mode or sha. GREY_CTRL_01 has no row and no prediction was seen. The rule was written down before any rerun. Content mismatch still STOPs.
- **Umask: no, not instead, and not now.** Restore already normalises modes, and that is the side that differs. A box umask change would alter the headers of future fresh tars. That is harmless for new keys, but it is a mid-campaign environment change for no correctness gain. If the team wants it, do it as a separate, disclosed hygiene item after P4b. Chmodding back to the recorded modes is correctly rejected.
- **Frozen P4 / D-038: no risk found.** No stored object is rewritten. There are 0 `restored_from_s3` rows (per diagnosis), and D-038 reruns happen on the same box without a restore.

Binding conditions (to be met in the fix commit; none needs another council round):
1. Compare `sha256(re-archived sums)` against the **recorded** `restore["sums_sha256"]` (entry record / `.sha256` sidecar), not only against the downloaded sums text. Staging sha-checks the tar but not the sums object (gpu_wave1_p4.py:1215-1216), and media are restored by the hashes in that sums text.
2. Apply the same check-and-skip to the job-id restore path too, meaning crash recovery and non-full conditions restoring `base_id` (line 344). Skip **both** `put_file` calls (lines 488-489) for every restored job. The row's `tar_sha256`/`sums_sha256` (line 507) must be the stored values. `rearchive_tar_sha256` is descriptive only.
3. Promote 506fe32's test onto the branch together with the fix, plus the two tests the diagnosis names (sums differ → STOP; crash-recovery restore of a group-writable entry → no upload, no refusal). Add a third: a non-full condition restoring a group-writable base entry. Keep `test_p4_campaign_is_unaffected` green.
4. Add a BUGS.md / disclosure line saying stored ref tars carry 0o777/0o664 modes, which is a header fact and not a content fact.
