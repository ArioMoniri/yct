# Council BUG-050: QA review. Verdict: APPROVE fix (a), with the conditions below

Read: bug050_diagnosis.md, BUGS.md BUG-050, 6460da1, 38d32d5 (bug050-failing-test), d071_v3.md (a)/(b), refclips58.py, gpu_wave1_p4.restorable, feature_cache.cache_key. No sealed data, labels, transcript text or prediction content was read.
**Checks.** The campaign-branch test file passes 3/3. The red test from 38d32d5, run from a temp copy that was then removed, fails with the same `OverwriteRefusedError` on the tar upload. That reproduces the incident faithfully. `make guards` exits 0: all 7 guards OK, frozen config unchanged, no test weakening.
**Q1. Root cause: confirmed.** `restorable()` looks up `st.entries[job.id]` only (it falls back to base_id for non-full jobs), but `cache_key` contains no clip identity. When a duplicate lands on a new box, it re-extracts nondeterministically (BUG-006) and the immutable store refuses the upload. Behaviour within one session is correct.
**Q2. Identity is by design, not a build bug.** D-071 (a) specifies one seeded bed (20261117), and "visual-only clips carry the control audio bit for bit". GREY_CTRL has no events and no draws. FLASH depends only on shift(i) = (i//2) mod 2, so {00,01,04} have s=0 and {02,03} have s=-1. refclips58's docstring records the one-bed reading as a reported interpretation. D-071 (b) says "the noise bed of each clip", which contradicts (a). This is a spec wording defect: disclose it, do not rebuild, because a rebuild changes frozen shas.
**Q3. Readout.** Fix (a) makes each group's predictions bit-identical, which is correct for a deterministic model on identical input. There is 1 distinct GREY stimulus and 2 distinct FLASH stimuli, weighted 3:2 by clip count.
- K6's "clip-bootstrap CI" (FLASH − GREY) resampling 5 FLASH clips treats copies as independent, so its width is not a stimulus-level CI. Run the frozen procedure as specified.
- The report must disclose the groups. It must add a labelled non-preregistered sensitivity analysis on deduplicated stimuli (unit = distinct stimulus, equal weights).
- Any n quoted for FLASH or GREY must give both clip count and stimulus count (5/2, 2/1). No frozen artifact changes.
**Conditions on the fix (blocking before session 3):**
- C1. The expected key comes from the same `feature_cache.cache_key`/`revisions_sha256` code, not a reimplementation. After staging, the box-side key must equal the restored entry's `cache_key`. A mismatch is a STOP, never a silent re-extract.
- C2. The donor entry must be unique per key (one tar_sha256 across non-superseded entries), gate-passed, and condition "full". More than one candidate, or a donor from a superseded run, is a STOP.
- C3. The restored row records `cache_reused: true` and the donor job id (provenance), with `tar_sha256` equal to the donor's.
- C4. The red test lands on the campaign branch in the same commit as the fix, with no xfail or skip. Also add:
  - (i) the FLASH 3-member group across 3 sessions;
  - (ii) when the revisions sha is unknown, today's behaviour is unchanged;
  - (iii) C1 mismatch leads to STOP;
  - (iv) a P4-store regression: a P4 job with a unique key is unaffected.
- C5. Recheck the P4 manifest sha (03322d84…) before and after the next session, and record it in BUGS.md.
**Non-blocking.** Confirm the D-038 fresh-drift gate is only required for the 3 D-038 clips, so that GREY_CTRL_01 needs no fresh extraction. The red test asserts zero extractions, which relies on this.
**Owner questions.** None. No frozen change is proposed. Amending K6 to bootstrap on distinct stimuli would be an owner decision, but QA does not recommend it.
