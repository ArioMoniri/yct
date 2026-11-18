# FIX-P4G — Neuroscientist / TRIBE review

**Verdict: GO-WITH-FIXES** (no P0; two P1, three P2)

1. **Q1, clamping is the right handling (P2, endorse).** The word really was spoken, and its onset is inside the clip. Clamping keeps the onset, so the text embedding sits in the same 0.5 s bin. Only the 10–30 ms of the word that falls past the cut is lost. Dropping the word would delete a real stimulus. Re-trimming the transcript means changing the media or the .tsv that was hashed in P2, which is a bigger change for no gain. The Llama features are contextual over *preceding* words and placed at word onset, so the last word cannot change any earlier word's embedding. With `sum` aggregation (known issue #8), the only change is one word's vector in the bin at about 57.5–58 s. Audio (w2v-BERT) and video features are untouched. Inside W = [5, 45), the word could matter only through TRIBE's bidirectional temporal transformer and the 5 s output offset. D-055 measured backward leakage of about 4 TR, and this word is about 13 s after the end of W. So I expect the effect inside W to be negligible, though not exactly zero.

2. **Q1, confound if left unfixed (P1, the fix closes it).** Whether a video lost its word depends on whether the 58 s cut fell mid-word. Denser, faster speech makes that more likely, and speech rate is already a known confound. A clip-dependent input deletion that tracks speech rate should not be left in, however small its effect in W. One rule for all clips (the clamp) is correct. Add `n_tsv_words_past_end` to the label-free P4 QC table so its distribution can be disclosed.

3. **Q1, the clamp target may not be the dropping boundary (P1, check before launch).** The line in neuralset that drops the word was not located. The clamp uses the end of the *Audio event*, but the event could instead be dropped against the video or container duration, which can be a frame (about 33 ms) shorter. Before the session, take the pod-side ffprobe stream durations (audio, video, format) of the 6 BUG-029 clips; this is numeric only. If any stream ends before the audio, clamp to the minimum of all three. Also confirm that no clamped word ends up with duration ≤ 0, because a zero-length event may also be dropped. The gate's n_words check would catch either case, but it would cost a session.

4. **Q2, re-run everything on one stack (P1, endorse).** For a word-free overrun clip, the clamp makes no difference in principle. But the revisions sha and cache key differ between the two stacks, and the invariant "one stack for all of P4" is what makes predictions exchangeable across clips. Re-running costs about $15. Keep the old objects. A hash-only bonus that does not touch the firewall: for the pre-clamp passes with `n_tsv_words_past_end == 0`, record whether the new `pred_sha256` equals the old one. Equal hashes confirm the clamp was a no-op and the GPU is deterministic. Do not compare values.

5. **Q3, T1 clips of 50–58 s (P2, acceptable; add a sensitivity check).** The rule follows D-039 (end of W 45 + min tail 5) and keeps the T1 trim fixed at 58.0 s. In a 53 s clip the end of the sequence is 8 TR after W ends, and with a 5 s tail it is 5 TR. That exceeds the roughly 4 TR backward leakage, so it is adequate. Two residual edge effects remain, both small:
   - per-clip audio z-scoring uses statistics from clips of different lengths;
   - the transformer's end-of-sequence boundary sits closer to W.

   Pre-register a label-blind sensitivity analysis that drops T1 clips shorter than 58 s (currently 2), or adds duration as a covariate. Report how many such clips there are. Spend no α on it.

6. **Q5, GPU verification (P2, adequate with additions).**
   - Set `--limit` to at least 16, so that both yct_0072 (job 7) and yct_0186 (job 16) run in the watched session.
   - Assert in the record that yct_0072 has `n_words == n_tsv`, `n_tsv_words_past_end == 1` and `bug018_word_end_clamp == v1`.
   - Assert that yct_0186 has `|T − duration| ≤ 1` and T ≈ 54.
   - Check the D-038 Gate 1/2 clips first, as frozen.
   - Add the `pred_sha256` no-op check from item 4 for any clip run in that session that had 0 overrunning words.
   - Keep exit 1 → human.
