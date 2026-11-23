# Council, reference session 1 pre-launch (refcampaign_ready.md @ bab3bb8): Neuro
**Verdict: REVISE.** Do not launch until N-B1 to N-B5 are done. Read: the record, gpu_p4b_ref.py, the manifest (keys and sha equality only, no text), D-071 (c)(d)(k), d071_v3 §k, 6440ebf/0edb3d8/bab3bb8, wave1_p2b_pod.py, feature_cache.reliability. Not read: sealed data, labels, transcript or tsv text, Harvard texts, predictions.

**U1, read-only adapter: APPROVE.** It is a field mapping only, so the stimuli the model sees and the frozen bytes and row are unchanged. It must assert `name == family.lower()_ii`, `clip_id = FAMILY_ii`, tsv = `sha256.tsv` only (never `transcript` or `wav`), and carry `control`/`twin_of`/`onsets`/`shift` through unchanged for the later readout. Test it on the committed file. Session 1 resolves to grey_ctrl_00 (shift 0), spk_00 and mot_00.
**U2, NAT tsv: option (a), or the equivalent frozen sidecar. Reject (b).** It is outcome-blind: no reference prediction exists, the 15 NAT clips are closed, and the conversion is deterministic frozen code.
- Why this is right for TRIBE: the text stream is the clip's own spoken words, timed on the clip timeline. That is the same WhisperX to `whisperx_segments_to_words` to `store_transcript` path the analysis T1 videos used (D-062, 57/57 valid). D-071 (c) requires NAT to be "identical to analysis T1", so NAT has to reach the Llama text pathway exactly as analysis videos do.
- Rejected alternatives: a header-only tsv would silence the text pathway, so NAT would stop representing the analysis input. A new ASR model, or hand-corrected text, would make NAT's text input differ from the analysis input. Both break the comparison NAT exists for.
- D-071 (d) already lists a tsv sha per clip, so v1.1 completes the spec rather than changing it.
- Conditions:
  - Do not run the `ingest` CLI verbatim. It writes the wave-1 `/work/yct/transcripts/manifest.csv`, `summaries/wave1_transcripts_summary.csv` and `wer_pending/`. Call the frozen functions into a ref-scoped dir instead.
  - Assert that each json's recorded input equals the manifest NAT wav sha, so the word times belong to the trimmed 58 s audio, and that the WhisperX pin equals D-061.
  - Only shas, n_words, first/last word time and flags leave the pod.
  - `tsv_invalid` or 0 words means STOP to the owner, with no drop and no substitution.
  - Do not filter on word content. Unlike SPK, NAT speech may contain face, body, place or motion words. That is inherent to naturalistic clips; disclose it.
  - v1.1 adds only `sha256.tsv` to the NAT rows, tested as v1 plus those keys. Two commits plus a D-entry.
**U3, upload: BLOCKING.** `check_inputs` gates all 120 clips, even under `--limit 3`. The step copies and never builds, renames to `<clip_id>` with the tsv stem equal to the mp4 stem (TRIBE pairs them by stem), and re-verifies mp4/wav/tsv shas on the pod and in private S3. TALKFACE and NAT never go public. Commit an upload record (hashes only) and run a no-launch `check_inputs` preflight on the pod.
**U4/U5: BLOCKING.** These are D-071 (k) conditions: projection ≤ $75, a pushed CI-green commit, L4 reconcile, and spend plus budget_cap() recorded. Reuse the NAT/TALKFACE code and add refusal tests. The record also omits the "ENH-002 K-run committed" (k) precondition; cite it.
**U6, readout deferral: APPROVE, with a firewall.** The session-1 "human check" is operational only: gates, shapes, finiteness, shas and cost. No ROI time course, kernel or lag is computed or viewed from `full/` until the (b)–(d) readout script is committed and tested on synthetic data. Otherwise p*, the ROIs and `readout_lag_tr` could be reread against real outputs, a forking path that (l) does not cover before the first analysis read.

**Other neuro items for session 1:**
- N-B5: GREY_CTRL_00 is the first job and has a header-only tsv (MOT_00 shares the same sha). Before launch, a CPU test must show that the TRIBE text path and `clip_gate` accept 0 words deterministically, as either an empty or a zero-filled text feature, and that this matches how wave-1 handles silent spans.
- Disclose: Gate 2 on GREY_CTRL_00 and MOT_00 (static or near-static video, no text) is a weak drift test. `reliability` pools between-feature variance, so near-constant inputs pass easily. The only text-extractor Gate 2 in session 1 is SPK_00. Report the per-extractor values.
- Disclose: the D-087 v2 campaign runs under the `.../p4b_ref/v1/` root with manifest `version: p4b_ref/v1`. Confirm that no prediction objects exist there.
- Otherwise session 1 is adequately scoped: `--limit 3`, the D-038 clips, Gate 1/2, watched, the terminator re-armed, a $3.48 worst case, and a $66.3 projection.
