# FIX-P4G — Watchdog + Strict Referee review

Reviewed: packet.md, commit 823d505 (`git show HEAD`), BUGS.md tail, D-038/039/063/064/065/066. `check_frozen_config.py`: OK, 15 frozen keys unchanged. Targeted tests: 82 passed. No labels, titles, transcripts, sealed columns or secrets were read.

**Verdict: GO-WITH-FIXES.** One fix is needed before the GPU launch (F1). The other fixes are needed before the P4b lock.

## Findings

1. **P0: write D-067 and commit it before any launch.** D-064(c) recorded the T1 gate as "58 ± 1, duration ≤ 58.5 s", and D-066 granted GO on that gate. BUG-030 is a correction toward D-039, but it changes a rule that D-064 wrote down, so the change needs its own entry. The same applies to the clamp (a new stack revision), the new config key and the superseding of s1–s4. The commit is marked "WIP". D-066 requires a launch from a pushed commit with CI green, and that commit has to include D-067.
2. **P1 (cheap, recommended before launch): the verification count never leaves the box.** run_clip adds `n_tsv_words_past_end` to `bug018_word_check`, but the allow-list in `qc.sanitize_metrics` drops it, so the S3 record and the manifest never contain it. Add it to the allow-list (it is an integer count, so the firewall is unaffected). Then the yct_0072 check can show `n_tsv_words_past_end == 1` and `n_words == n_tsv_rows`, which is direct evidence of the fix and not just a passed gate.
3. **P1: re-running all jobs on one stack is required, not optional (Q2).** Keeping the ~14 passes made before the clamp would break the revisions-sha256-equality gate and the "one stack for all of P4" rule (D-038, D-065d). Superseding s1–s4 by a listed, non-frozen config key is append-only and not silent:
   - the S3 objects are kept;
   - new outputs go to versioned prefixes;
   - D-038 STOP rows still latch;
   - BUGS.md is appended.

   D-067 must name the four run ids.
4. **P1: forking-paths risk is low but must be capped.** The fix was made after seeing real outputs. Those outputs were label-blind per-clip QC numbers only. No prediction was read. The run sets (T1 51, T3 52), W, L and the frozen keys do not change. The gate change only lets members of the frozen set pass; it excludes nobody. Choosing clamp over drop or re-trim is still a researcher degree of freedom. D-067 must fix that choice now and state that a later gate failure produces a new BUG plus a new D- entry, never an exclusion of a single clip.
5. **P2: the effect inside W.** The clamped word lies at about 58 s, far outside W = [5, 45) TRs (5–45 s), and the change only shortens its end by ≤ 30 ms. Any effect inside W through TRIBE's temporal context should be nil. Neuro should confirm.
6. **P2: zero-duration edge case.** A word starting within 1 ms of the audio end gets duration 0. If TRIBE drops zero-length events, the gate (`n_words == rows`) catches it. That is acceptable.
7. **P2: firewall (D-063 B2) is respected.** The diff adds no prediction statistic and no label or transcript read. The committed run records contain counts, hashes, ids and costs only. `n_words_past_end` reads only the .tsv timing columns.
8. **P1: the verification plan needs a different cap (Q5).** Session 4 averaged about 7.7 min per job, and the D-038 jobs take longer. `--limit 16` (through yct_0186, job 16) will not fit under `--max-hours 1.75` (BUG-028), so the session would exit 75 before reaching yct_0186. Use:
   - **V1: `--limit 7`.** This runs the D-038 clips again on the new stack (Gate 1/2) and then yct_0072. It stops, and a human checks F2.
   - **V2: `--limit 9`.** This runs through yct_0186 and stops for a human check.
   - **Then uncapped sessions.**

   Any gate failure gives exit 1 and goes to a human (D-066). Keep the frozen job order; do not reorder to reach the test cases sooner. yct_0247 and the other five BUG-029 clips must also pass later.
9. **P2: optional free check.** For clips with zero clamped words, compare old and new `pred_sha256`/`cache_key`. This uses hashes only and needs no statistic.

## D-067 draft

- D-067 FIX-P4G (BUG-029, BUG-030). Label-blind: only per-clip QC numbers were seen and no prediction was read. Council: reviews/phase_p4g/*.md.
  - (a) **BUG-029 ruling.** Each transcript word's end is clamped to the file's audio end − 1 ms. The start time never moves and no word is dropped. Chunk boundaries are not clamped. This is recorded as `bug018_word_end_clamp: v1` in the revisions, so it is part of the cache key. The QC gate requires v1. The method is fixed now and will not be revisited after any prediction exists.
  - (b) **BUG-030 ruling.** The T1 gate becomes 50 s ≤ duration ≤ 58.5 s, |T − duration| ≤ 1 and T ≤ 59. 50 s = `window.end_tr` + `window.min_tail_s` (D-039). This **supersedes the T1 clause of D-064(c)** ("58 ± 1"). The frozen keys, the run sets (T1 51 / T3 52), W and L are unchanged, and no clip is added or excluded.
  - (c) **Superseded runs.** wave1p4_s1_20261118T040434Z, wave1p4_s2_20261118T050059Z, wave1p4_s3_20261118T070223Z and wave1p4_s4_20261118T075035Z are superseded. They are listed in `p4.superseded_run_ids`, a new key that is not frozen. Their S3 objects are kept, and D-038 STOP rows still latch. All 103 jobs re-run on one stack, with outputs under `pred_clampv1/`, `entries_clampv1/` and `d038_fresh_clampv1/`.
  - (d) **GPU verification.**
    - V1 runs with `--limit 7`: the D-038 Gate 1/2 checks on the new stack, then yct_0072 T1. The gate must pass with `n_words == n_tsv_rows` and `n_tsv_words_past_end == 1` in the S3 record.
    - V2 runs with `--limit 9`: through yct_0186 T1, which must pass the gate.
    - Only then do uncapped sessions run.
    - Any gate failure gives exit 1, and the work stops for a human with a new BUG and D- entry. No clip is excluded on its own.
  - (e) **Cost.** About 11 GPU-h, about $15. Total P4 spend is then about $43 of $200; the ≈ $28 already spent is sunk.
