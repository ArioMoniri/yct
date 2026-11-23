# Council, reference session 1 pre-launch (refcampaign_ready.md @ bab3bb8): Referee
**Verdict: REVISE.** Do not launch until B1–B6 are done. Read: the record, gpu_p4b_ref.py, the manifest (keys only), D-071 (c)(d)(k), 6440ebf/0edb3d8/bab3bb8. 35 tests pass (p4b_ref, guards, cap).
**U1, adapter: APPROVE.** The adapter is pure and read-only; manifest bytes and the frozen row do not change. The adapter must assert: `name == f"{family.lower()}_{i:02d}"`; i runs 0..n-1 per family (true for all 10 families); `clip_id = FAMILY_ii`; mp4 = `sha256.mp4`; tsv = `sha256.tsv` only (never `transcript` or `wav`). Test it on the committed file: 120 unique ids, with GREY_CTRL_00, SPK_00 and MOT_00 present.
- The manifest has no `duration_s`, and both backends hardcode 58.0. That is tolerable for built clips. Before any NAT job, ffprobe the pod mp4 and gate the real duration (T1 rule).
**U2, NAT tsv: option (a), with conditions. Option (b) is rejected:** it would gate a sha that was not frozen before upload, against D-071 (d). Option (a) is outcome-blind: there is no reference prediction, the NAT selection is closed, and the conversion is deterministic frozen code. Feeding the WhisperX transcript to TRIBE as text is correct, not a confound: D-071 (c) runs NAT through P1/P2/P2b/P3 "identical to analysis T1", so analysis videos get the same ASR text stream. Conditions:
- (i) Call the same frozen functions as `wave1_p2b_pod.py ingest` (`whisperx_segments_to_words`, `store_transcript`, `transcribe.tsv_columns`, the BUG-029 clamp with the ffprobe media duration). Write into a ref-scoped dir only. The stock `ingest` writes `/work/yct/transcripts` and the wave-1 transcript manifest; it must not touch either.
- (ii) Only shas, n_words and flags leave the pod. No agent views the words.
- (iii) A `tsv_invalid` result, or an empty or failed conversion, is a STOP to the owner, never a drop. The m0 `min_words_in_W` flag is recorded and never used as a NAT filter: it is not a D-071 (c) filter.
- (iv) v1.1 adds only `sha256.tsv` to the 15 NAT rows. A test asserts that v1.1 minus those keys parses equal to v1. v1 stays committed as the record.
- (v) Two commits: set, then freeze the new row with a short D- entry citing this cycle.
- Equally acceptable: a sidecar `nat_tsv_manifest.json` under its own `refclips_artifacts` key and `frozen:` row, which leaves the d1141cf1 row untouched.
**U3, upload: BLOCKING.** `check_inputs` requires all 120 clips on the pod, so it is needed even for `--limit 3`. Also needed:
- private S3 objects only (TALKFACE from the private mirror), immutable, with `.sha256` sidecars, never overwritten;
- the `name`→`clip_id` rename recorded;
- a committed upload record (hashes only);
- a no-launch preflight (`--check-inputs-only`) that runs the driver's own `load_clip_manifest` + `check_inputs` and passes on the pod.
**U4/U5: BLOCKING.** They are D-071 (k) and D-066 launch conditions: L4 reconcile, a pushed CI-green commit, and spend recorded. Lift `check_projection`, the CI-green check and reconcile into `ref_campaign` (or a shared module) and reuse them; do not fork a third copy. The tests need refusal cases.
**U6: deferral APPROVED.** The (b)–(d) readout must be written, tested on synthetic data and committed before anyone loads a `full/` array.
- Add a firewall test for gpu_p4b_ref like P4's: no yct.features/interpret/stats/report/confounds import and no prediction load. Today it imports `yct.predict.p4_index`, which is JSON-only and acceptable, but no test asserts this.
**Other items:**
- (B6) Correct record P4. NAT session 0 and the TALKFACE drivers already called `ensure_baseline` on the same s3_root, so the baseline should exist. Verify that it predates the first `yct-p4b-ref` launch and record its sha. If it is absent, that is a finding, not a fresh write.
- (N1) Disclose that the v2 campaign (D-087) lives under the frozen `.../p4b_ref/v1/` s3_root and pod path, and that the manifest says `version: p4b_ref/v1`. Confirm no v1 prediction objects exist there.
- (N2) Session 1, job 1 is GREY_CTRL_00, whose tsv is header-only (0 words). No TRIBE run has seen a zero-word tsv yet. Add a CPU test that the tsv loader and `clip_gate` accept 0 rows (n_words == 0 == rows). Otherwise expect an exit 1 on the first job.
**Session 1 is otherwise adequate as specified:** `--limit 3`, the D-038 clips, Gate 1/2, watched, an external terminator re-armed per retry, and a send_later reap. The record's worst case of $3.48 and projection of $66.3 ≤ $75 are consistent.

## Re-sign-off (89d828b..bfbb90a, D-091): APPROVE
- U1 adapter, U2 route (c) sidecar (43db439a… frozen 556f637/24440be; 15/15 valid, 2 builds identical, stop [], wave-1 manifest aa93a8c8… unchanged, ffprobe media duration), U3 upload (120/360, 0 pod + 0 S3 mismatches, c26fcf3c…), U4 projection, U5 shared launch_checks: closed as asked. B6 baseline (2807, 4261f62b…), N1 disclosure and N2 zero-word test: done. 77 tests pass locally (p4b_ref, session1, frozen guards, d071 config).
- check-only at 7ab9da6: rc 0, clip sha d1141cf1… unchanged, plan GREY_CTRL_00/SPK_00/MOT_00, projection $66.33 ≤ $75, L4 2817 lines, no open/live.
- Conditions before launch (not new work): (1) freeze `controls.refclips_d091` in two commits plus its guard row; (2) after the freeze, at the CI-green pushed HEAD, re-run `--reconcile-only` (commit the record) and `--check-only`. The real `pre_launch` only computes the U4 projection when d091 is frozen and otherwise skips it without a word, so a launch without the freeze would bypass U4. Confirm the freeze row exists before launching. Better still, make `pre_launch` refuse when d091 is not frozen.
- Non-blocking: the firewall test for gpu_p4b_ref (no features/interpret/stats/report/confounds import, no prediction load) is still missing. Add it before U6 or session 2.
