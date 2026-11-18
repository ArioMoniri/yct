# FIX-P4G review packet (BUG-029, BUG-030) — P4 inference halted at exit 1

## What happened (label-blind; no labels, titles or transcript text were read)
P4 session 4 (run wave1p4_s4_20261118T075035Z) ran 12 T1 jobs; the per-clip QC gate failed 8 (nothing was
published for them: predictions only sync after a gate pass). Two causes:

1. **BUG-029 (6 jobs: yct_0072, 0104, 0105, 0199, 0206, 0269 T1)**: `n_words = .tsv rows − 1`. A pod-side
   numeric check of the pinned T1 .tsv files (start/duration columns only) shows each failing clip has exactly
   one word whose end (start + duration) is after the 58.0 s clip end (58.010–58.030 s: the 58 s trim cuts the
   last word); the 5 passing clips checked have none. No word starts after 58 s, none has NaN/empty text,
   no duplicates. Conclusion: TRIBE/neuralset drops a Word event that extends past the audio. (tribev2 is
   not installed on the pod, so the exact dropping line was not located; evidence is 6/6 vs 0/5.)
2. **BUG-030 (2 jobs: yct_0186 53.08 s → T 54; yct_0247 → T 56)**: qc.clip_gate demanded T1 `|T − 58| ≤ 1`,
   contradicting D-039, which keeps a T1 clip when its trimmed duration ≥ window end (45) + min tail (5) = 50 s.
   These source videos are simply shorter than 58 s. The window W = [5, 45) TRs lies inside them.

## Fix (FIX-P4G; diff in this commit)
- `src/yct/tribe_run/word_events.py`: in the BUG-018 absolute-word transform, each word's duration is cut so
  that its end ≤ (file audio end − 1 ms). Start times never move; words ending earlier are untouched; chunk
  boundaries are not clamped (only the file end). `WORD_END_CLAMP = "v1"`.
- `src/yct/tribe_run/run_clip.py`: revisions gain `bug018_word_end_clamp: v1` (→ part of the feature-cache key
  and revisions_sha256); the record adds `n_tsv_words_past_end` (count of clamped words, numeric only).
- `src/yct/tribe_run/qc.py`: gate requires `bug018_word_end_clamp == v1` (one stack for all of P4); T1 rule
  becomes `50 ≤ duration ≤ 58.5`, `|T − duration| ≤ 1`, `T ≤ 59`. `T1_MIN_S` is test-pinned to
  `window.end_tr + window.min_tail_s` (frozen keys; not changed).
- `scripts/gpu_wave1_p4.py` + `config.yaml p4.superseded_run_ids` (new, not frozen): rows and entries of the 4
  earlier runs (s1–s4, pre-clamp stack) are ignored for done/restore/revisions, so EVERY job (incl. the 3
  D-038 clips and ~14 jobs that passed pre-clamp) re-runs on one stack. Their S3 objects are kept (append-only).
  New outputs go to versioned prefixes (`pred_clampv1/`, `entries_clampv1/`, `d038_fresh_clampv1/`) because
  S3 objects are never overwritten. D-038 STOP rows are never ignored.
- Tests: word clamp (T1 last-word regression, chunked file-end only, unit), QC (short-T1 D-039 cases incl.
  yct_0186 regression, clamp-version required, T1_MIN_S == config), driver (superseded runs re-run, old
  objects kept, manifest append-only, superseded D-038 STOP still latches).

## Not changed
Frozen config (15 keys), W, L, run sets, D-038 clip list, firewall (no prediction statistic computed).
Cost of re-running all 103 jobs ≈ 11 GPU-h ≈ $15; spent so far ≈ $28 of $200.

## Questions for the council
Q1 Is clamping the cut word's end (vs dropping the word, vs re-trimming the transcript) the right fix
    scientifically for TRIBE text/audio features? Any effect inside W = [5, 45) TRs?
Q2 Is re-running everything (one stack for all of P4) required, or may the ~14 pre-clamp passes with zero
    overrunning words be kept?
Q3 Is the BUG-030 T1 rule consistent with D-039/D-063 and the frozen keys?
Q4 Code correctness, test adequacy, S3 append-only / no-overwrite invariants, blinding and firewall.
Q5 GPU verification plan: next session runs in the frozen order (D-038 clips first, then run_set order: yct_0072
    = BUG-029 case is job 7, yct_0186 = BUG-030 case is job 16); --limit caps the session to verify them
    first; any gate failure → exit 1 and stop.
