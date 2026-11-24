# BUG-050 diagnosis: feature-cache collision between byte-identical reference clips

Run: `outputs/runs/p4bref_20261124T063058Z` (session 2, 364f4e2). Error: `GREY_CTRL_01.ref`:
`OverwriteRefusedError: refusing to overwrite feature_cache/b9ff59ee…0805.tar: existing sha256 858643719616 != aa0f682635e4`.
Diagnosed from code, keys, shas and manifest metadata only; no prediction content was read (U6).

## 1. Root cause (confirmed, reproduced in a dry run)

- **The cache key is content-addressed.** `feature_cache.cache_key` = sha256(video sha256 + transcript sha256 +
  extractor revisions sha256). It contains no clip identity. Per the module docstring, features are extracted
  *exactly once per cache key* (BUG-006: GPU extraction is nondeterministic; prediction from cached features is
  bit-identical).
- **GREY_CTRL_00 and GREY_CTRL_01 are byte-identical inputs** in the frozen manifest: mp4 `bd083cce…`,
  tsv `e24a6eea…`, wav `13a3bc7a…`. They get the same key, `b9ff59ee…`. The existing tar `858643719616…` is the
  one GREY_CTRL_00 wrote in session 1 (ref manifest row `GREY_CTRL_00.ref`, `tar_sha256 858643719616…`).
- **Restore is looked up by job id, not by content key.**
  - On the new session-2 box the local cache was empty. `restorable()` (scripts/gpu_wave1_p4.py) looks up
    `st.entries[job.id]`, and `GREY_CTRL_01.ref` has no entry of its own, so nothing was restored.
  - The box therefore re-extracted on the GPU. Extraction is nondeterministic, so it produced different
    feature bytes and a different entry tar under the same key.
  - `Store.put_file` then correctly refused to overwrite the immutable object.
  - Nothing was published for GREY_CTRL_01: the tar upload is the first write, so there are no predictions, no
    entry index and no manifest row.
- **The same thing would happen for every duplicate group in the frozen v1 manifest** (mp4+tsv identical):
  - `grey_ctrl_00 = grey_ctrl_01`;
  - `flash_00 = flash_01 = flash_04`;
  - `flash_02 = flash_03`.
- **Within one session there is no error.** The box's local FeatureStore already reuses the entry by key, so
  the bug only appears when the duplicate lands on a new box (a later session).
- **The tar is deterministic.** Its bytes are not the issue: the two tars differ because the extracted features
  differ, which is BUG-006 nondeterminism, not tar metadata.

Reproduced by `tests/test_bug050_cache_collision.py::test_identical_clip_on_a_new_box_restores_by_content_key_and_does_not_reextract`,
which fails today with the same `OverwriteRefusedError`.

## 2. P4 analysis-set cache: NOT affected

I read S3 `wave1/derived/p4/manifest.jsonl` (138 rows; metadata fields only):

- there are 128 cache keys;
- **no key is shared by two different jobs**;
- **no key has more than one tar sha**.

So no P4 job ever reused or collided on a key, and the frozen P4 predictions are unaffected. The P4b reference
store so far has 13 rows and 13 distinct keys, also with no shared key. The P4 manifest sha is unchanged
(`03322d84…`, before and after session 2).

## 3. D-038 claims still hold

- **GREY_CTRL_00, SPK_00, MOT_00:** each has its own entry, written on its own box, with a bit-identical
  cached rerun and a passing fresh-drift gate. BUG-050 does not touch them.
- **Effect of the fix on GREY_CTRL_01:** it will predict from GREY_CTRL_00's cached features. Its prediction is
  then bit-identical to GREY_CTRL_00's, as the content-addressed design intends.

## 4. Proposed minimal fix (stated before any further output)

**(a) Restore by content key: recommended.**

- Make `restorable()` also find an entry for any full-model job whose cache key equals the job's expected key.
- The orchestrator can compute that key before staging, from information it already has:
  - the mp4 sha and tsv sha (from the inputs it already measures);
  - the campaign's single revisions sha (`State.revisions_sha256()`, frozen across P4 and P4b).
- The entry is restored onto the new box exactly as after a crash, an existing tested path. The job then
  predicts from the cache with no extraction, and `tar_sha256` equals the existing object.
- Require that any key collision between two jobs restores, never re-extracts. If the expected key cannot be
  computed (no revisions sha yet, i.e. before the first job), keep today's behaviour.
- This keeps "extract exactly once per key" and needs no change to any frozen artifact.

**Options rejected:**

- **(b) Deterministic tar or comparing extracted contents.** It does not help, because the extracted features
  themselves differ between GPU runs.
- **(c) Clip identity in the key.** It would re-extract the duplicates with different nondeterministic
  features. That breaks the content-addressed design, the v3 key scheme and the P4 cache semantics, and
  changes how the frozen D-063 keys are built.

**For the council (not decided here):** the v1 design has 2 identical GREY_CTRL clips and two groups of
identical FLASH clips. Under (a) each group gives bit-identical predictions. If D-071 treats them as
replicates, they add no independent information. The readout must handle them as one stimulus, or the report
should disclose it.

## 5. Tests

`tests/test_bug050_cache_collision.py`:

- **`test_fixture_has_two_identical_grey_clips`:** passes.
- **`test_identical_clip_in_the_same_session_reuses_the_local_entry`:** passes. This is the control: within one
  box there is no error.
- **`test_the_frozen_manifest_duplicate_groups_are_known`:** passes. It pins the 3 duplicate groups.
- **`test_identical_clip_on_a_new_box_restores_by_content_key_and_does_not_reextract`:** **fails until the
  fix.** The test-weakening guard forbids skip/xfail markers, so this test sits on a local branch
  (`bug050-failing-test`), not on the campaign branch.
