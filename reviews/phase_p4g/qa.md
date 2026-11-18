# FIX-P4G — QA review (code correctness, test adequacy)

Reviewed commit 823d505 (`git show HEAD`). 82/82 targeted tests pass; ruff clean. No GPU/AWS/Lambda calls; no labels, titles, URLs or transcript text read.

**Verdict: GO-WITH-FIXES** (no P0; F1 is cheap and should go in before the verification session).

## What checks out
- Clamp (`word_events.py:82-84`): `end_abs = ev.start − o + last − 1 ms` maps the file-level audio end (`last` = max(offset+duration) over the file's chunks) onto the event timeline. Right bound: unchunked → `ev.start + d − 1 ms`; chunked → file end, never chunk edges (tested). Starts never move; `astype(float)` handles int/str dtypes; words starting past the bound get duration 0, not a negative one.
- QC T1 (`qc.py:117-122`): `50 ≤ dur ≤ 58.5`, `|T − dur| ≤ 1`, `T ≤ 59`. This matches D-039 (keep a clip when trimmed duration ≥ W_end + min_tail = 45 + 5) and touches no frozen key. `T1_MIN_S` is pinned to `window.end_tr + window.min_tail_s` by a test (`test_tribe_qc_gate.py:90-93`). The clamp-version requirement is enforced.
- Driver: superseded rows and entries are filtered in both `load_state` and `_finish`. The revisions mixing check therefore sees only the new stack. A superseded run's D-038 STOP rows and `stops/` markers still latch (no STOP exists in s1–s4 run metrics). Every S3 key was checked for collisions with s1–s4 objects:
  - `feature_cache/<key>`: the key hashes the revisions, which now include the clamp version (`feature_cache.py:104-111`), so it is a new key.
  - `records/…<run_id>`, `rows/<run>/`, `stops/<run>`, `runs/<run>/`, `ledger/<run>`: all keyed by run.
  - `pred_clampv1/`, `entries_clampv1/`, `d038_fresh_clampv1/`: new prefixes.

  Nothing that s1–s4 wrote can be overwritten, restored or counted as done. A partial upload left by the killed s2/s3 sits under old keys only.
- Fail-safe: if TRIBE still drops the clamped word, the per-clip gate (`n_words == .tsv rows`) fails and nothing is published.

## Findings
1. **P1 — `n_tsv_words_past_end` never leaves the box.** `sanitize_metrics` copies only a fixed whitelist of `bug018_word_check` keys (`qc.py:59-61`), and this key is not on it. The packet says the record carries it, but the synced record and the manifest do not. That count is the evidence that yct_0072 (1 word clamped) passes *because of* the clamp. Fix: add the key to that tuple, and add a test that it survives `sanitize_metrics`.
2. **P1 — `manifest.jsonl` still holds passing pre-clamp rows** (s1–s4, `pred/…` keys, other revisions). Today only the driver filters them. Any P4b loader that reads the manifest directly gets two passing rows per job and mixed stacks. Fix: give one shared helper the filtered-state logic (`load_state` + `superseded_run_ids`), require P4b readers to use it, and add a test asserting a single `revisions_sha256` and only `pred_clampv1/` keys. Freeze `p4.superseded_run_ids` at the P4b lock.
3. **P2 — a NaN duration becomes "until end of audio"** (`word_events.py:91`). `du.where(st+du <= end, …)` treats NaN as a violation and replaces it with `end − st`. Fix: use `cond = (st + du <= end) | du.isna()`. The pinned .tsv files have no NaN, so this is latent only.
4. **P2 — zero-duration words.** A word starting within 1 ms of the end, or after it, is kept with duration 0. TRIBE may drop it, which would fail the gate (fail-safe). None exists in the data (no start > 58 s). Fix: document it, or add a test of `check_word_events` with a 0-duration word.
5. **P2 — the timeline-offset test does not test an offset.** The test is called `…_timeline_offset` (`test_tribe_word_events.py:209`), but `chunked_events` sets `start == offset`, so `ev.start − o` is always 0. Fix: add a case with `start = offset + 10` and assert that the clamped end is `10 + last − 1 ms`.
6. **P2 — the diagnostic and the clamp use different durations.** `n_words_past_end` uses the ffprobe video duration (`run_clip.py:215`), while the clamp uses the Audio event's duration. The two can differ by a frame. Fix: note this in the docstring, or compute the count from the audio duration.
7. **P2 — the mechanism is unconfirmed.** The fake `ExtractWordsFromAudio` does not reproduce the downstream drop, so the tests prove the clamp, not that the word survives. Keep `--limit` so the verification session reaches yct_0072 T1 (job 7) and yct_0186 T1 (job 16), and require `n_words == n_tsv_rows` there before continuing (the plan already does this).
8. **P2 — superseded entries cost reads.** Each `load_state` still reads every old `entries/*.json` before discarding it. This affects cost only. Fix (optional): skip by prefix once all `entries/` objects are known to be superseded.
