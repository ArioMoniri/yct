# P4b design v1: QA review (council cycle 1)

Reviewer: QA (test and engineering quality). Read-only: git, grep, pytest. No AWS, no decryption, nothing read from data/sealed/ or data/wave2_pool/, no labels, no prediction arrays, no commit.
Reviewed: reviews/phase_p4b/design_v1.md; src/yct/predict/p4_index.py and tests/test_p4_index.py (b632d6d); scripts/gpu_wave1_p4.py; src/yct/tribe_run/{qc,make_reference_clips,enh002}.py; config.yaml `controls:`, `p4:` and `frozen:`; ROADMAP P4/P4b; DECISIONS D-063, D-066, D-067; BUGS.md BUG-027/028/031/033.

Tests run (HEAD 08e3964 plus the untracked review directory):
- `pytest tests/test_p4_index.py tests/test_gpu_wave1_p4.py tests/test_infra_guards.py tests/test_infra_terminator.py tests/test_controls_config.py tests/test_enh002_latency.py tests/test_p4_config.py tests/test_guards_frozen_config.py tests/test_guards_frozen_section.py tests/test_tribe_p4_cache.py` gave 118 passed.
- The full suite gave 733 passed in 239 s.
- No test exists yet for any §7 ticket. This is expected for a design, but it means none of the design's guarantees are executable yet.

## Verdict

**GO-with-conditions** for building the reference-clip tickets (T-REF58, T-REFRUN, T-KERNEL).
**Running the reference-clip GPU job is NO-GO until B1–B6 are closed.** "Closed" means code plus tests, CI green, and a pushed commit.
B7–B10 do not block the GPU job. They block the P4b design entry and lock.

The design is sound overall: the separate prefix, the label-free synthetic clips, the STOP-without-tuning stance and the single loader are all right. However, the GPU-job section assumes that scripts/gpu_wave1_p4.py can be "reused with a job list of 27 ref clips". As written, it cannot. Six hard-wired P4 assumptions would either crash the run or silently weaken its guards (B2, B3). Two open driver bugs that the design handles only in prose are still open in code (B1).

## Blocking items

Scope tags: **[GPU]** blocks building or launching the reference-clip GPU job. **[LOCK]** blocks the P4b design entry and lock.

**B1 [GPU] BUG-033 and BUG-028 are still open in the driver. The design covers them only with prose rules.**
- Evidence (BUG-033):
  - `price = lg.types()[itype]["usd_per_hour"]` (scripts/gpu_wave1_p4.py:430) still raises KeyError when capacity vanishes.
  - `lg.launch(...)` (:451) has no handling for HTTP 400.
  - BUGS.md BUG-033 says "driver fix still open". The pod-side retry loop is a manual workaround that is not in the repo.
- Evidence (BUG-028):
  - The only cap is `--max-hours ≤ min(session_max_hours, 4)` (:385–387), and the CLI default is 3.75 (:1070). That is above the 2 h harness limit that killed s2.
  - BUG-028 reads "Open: add a guard asserting max-hours < launcher limit". The design's "--max-hours ≤ 1.4" is a rule nobody enforces.
- Required:
  - A missing type or capacity at price lookup, and a launch HTTP 400 with no instance created, both exit 75 ("retry") with no run-dir debris.
  - A guard such as `p4.launcher_limit_h` or a ref-wrapper constant refuses `--max-hours` above 1.4.
- Tests:
  - FakeLG with `types()` lacking the type gives exit 75 and nothing billed.
  - FakeLG.launch raising HTTP 400 gives exit 75, nothing billed, and an empty ledger delta.
  - `--max-hours 1.5` on the ref wrapper is refused.

**B2 [GPU] The driver cannot run "track ref" as written. The wrapper's parameterisation must be specified and tested.**
Hard-wired P4 assumptions in the driver:
- `plan_jobs` builds only from `p4.run_set_t1/t3/d038_clips` (:140–148).
- `clip_gate` raises `ValueError` for any track not in `TRACKS = ("t1", "t3")` (qc.py:31, :93). `run_clip --qc-gate` also takes only `t1`/`t3` (run_clip.py:110).
- `PodBackend.inputs` reads P2-normalised t1/t3 rows (:873–905).
- The S3 root is `cfg["p4"]["s3_prefix"]` (:829).
- `PRED_PREFIX`, `ENTRY_PREFIX` and `D038_PREFIX` are module constants (:85–87). The only existing way to change them is monkeypatching, as the tests do (tests/test_gpu_wave1_p4.py:422).
- The D-038 Gate 1/2 clips come from `p4.d038_clips`, which are analysis-set videos.

The design must state, and T-REFRUN must test, each of these:
- (i) The storage track is `ref`, and the QC gate applied is the T1 gate: 1 Audio and 1 Video chunk, 50 ≤ duration ≤ 58.5, |T − duration| ≤ 1, T ≤ 59, 0 == 0 words for the event-free clips, plus offline, GPU, word fix and clamp. Add a dry-run test that all 27 clips pass the gate.
- (ii) The S3 root is passed explicitly (constructor argument, not monkeypatch). A test asserts that every key the wrapper writes, in dry run, starts with the ref root.
- (iii) Three named reference clips (say ref_control58, ref_flash58_0, ref_speech58_0) run the D-038 cached-rerun gate. A STOP latches under the ref root's `stops/`.
- (iv) A wrapper test, run under the existing D-063 B2 import/config firewall test (tests/test_gpu_wave1_p4.py:233–260), shows the wrapper imports no yct.predict/features/stats and reads no `controls:` config.
- (v) A test shows that adding the full set of ref-root objects to a store leaves `load_state` / `p4_index` on the P4 root unchanged (same 103 refs, same revisions hash, no new latched stop).

**B3 [GPU] "revisions sha equals the P4 sha, else refuse" is not what the driver does.**
- Evidence: `ctx["rev_sha"] = st.revisions_sha256()` comes from the manifest of the store being written (:453, :214–219). `expected["revisions_sha256"]` is set only when that value exists (:315–316), and the first passing job then defines it (:376–377).
- On a fresh `p4b_refclips_v1/` root, `rev_sha` is None. Job 1 is therefore accepted with any revisions set, and later jobs are only checked against job 1. Same-stack is then not enforced against P4.
- Required: the wrapper reads the P4 root manifest (driver `load_state(..., superseded_run_ids).revisions_sha256()`; no array access) and seeds `ctx["rev_sha"]` with it. It refuses to launch if that value is None or mixed.
- Tests:
  - A ref job with a different revisions dict fails the gate on job 1.
  - An empty or mixed P4 manifest refuses before launch.
  - The same holds for the GPU name (`gpu_1x_a100_sxm4` / `NVIDIA A100-SXM4-40GB`).

**B4 [GPU] Clip determinism and provenance: the planned rebuild test cannot run, and nothing ties GPU inputs to the frozen manifest.**
- Evidence:
  - `_mux` encodes libx264 and AAC with default threading and no `-bitexact`/`-fflags +bitexact`/`-map_metadata -1` (make_reference_clips.py:89–95). Container metadata carries the encoder version.
  - The module says it "runs on the GPU box with the system python" (:11–12). A Lambda image with a different ffmpeg or espeak-ng would give different mp4/wav bytes.
  - CI installs ffmpeg but not espeak-ng (.github/workflows/ci.yml:25). A "bit-identical rebuild" test for the speech clips would skip in CI and never execute.
- Required:
  - Build the 27 clips once, on the pod or in CI, with a pinned toolchain (ffmpeg and espeak-ng versions recorded in the manifest) and bit-exact flags.
  - Upload them with a sha256 manifest under the ref root.
  - The wrapper stages only those objects and gates `input_sha256` and `transcript_sha256` against the frozen manifest. It never rebuilds on the box.
- Tests:
  - wav/tsv (pure stdlib, seeded) are bit-identical on rebuild in CI.
  - mp4 is bit-identical on rebuild under the recorded toolchain (install espeak-ng in CI, or mark the test toolchain-gated and record the result as a build artifact).
  - The wrapper refuses a clip whose sha256 differs from the manifest.
  - The bed is identical: the per-sample audio and per-frame video outside event windows equal ref_control58.

**B5 [GPU] The motion family's stimulus and its acceptance test are inconsistent. Fix this before any clip is built.**
- Evidence: the base frame is black (make_reference_clips.py:98–100, `color=c=black`). A high-contrast grating or dot field whose mean luma matches a black frame is impossible: matching mean luma to black means the patch itself is black.
- The T-REF58 test "Δ mean luma within 1% of the bed" therefore either fails, or passes only for a grey patch on a grey frame, which changes the bed. A patch appearing on black is a luminance event, which is exactly what D-063 Q4 forbids for the MT+ kernel.
- Required: fix the stimulus, for example a static grating present for the whole clip (including in its own control) that drifts only during events, or a mid-grey frame for this family with its own control58. Then specify the test on the per-frame mean-luma series in the 256×256 crop (max |Δ| from its control under a stated tolerance) and on the `luminance_change` regressor.
- This interacts with Q6.

**B6 [GPU] The kernel STOP rules must be executable and frozen before any reference prediction exists, so they cannot be tuned afterwards.**
- (a) The split-half rule contradicts itself. The peak is chosen on k = 0, 2, 4 and tested on k = 1, 3, which gives 2 × 4 = **8** test events, but K1 says "one-sample t across the 20 events". Pick one and pin it in a test (with 8 events, p < .001 needs t(7) ≈ 5.4).
- (b) The K1–K5 thresholds, the lag window, the split assignment and the gating/descriptive split are not in config. They live only in design prose. Add them under `controls.kernel.stop` (or similar), add them to `frozen:` before launch, and test that the code reads them from config.
- (c) Fail closed: NaN or truncated windows, zero pre-onset SD in K3 (control subtraction of a shared bed can give SD ≈ 0, and division then gives inf, which "passes" SNR ≥ 3), and an all-zero mean course (`kernel = mean_course / nanmax(abs(...))`, enh002.py:97) must give STOP, never PASS.
- (d) Tests for each of: K3 low SNR; K5 standardised-vs-raw disagreement; V1_V3 reports K1–K5 but never STOPs; and T-CTRL refuses when kernels_v1.json has any gating STOP or a sha256 different from the pinned one.
- (e) Kernel derivation must be byte-reproducible from the stored arrays (same inputs give the same kernels_v1.json sha256, with canonical float formatting), because §8.2 freezes that sha.
- These tests and config keys must be committed before the GPU job. The criteria are not "fixed" if they can still be edited after the kernels are seen.

**B7 [LOCK] The freeze items are enforced by prose and a DECISIONS sha, not by tests.**
- Evidence: `frozen:` (config.yaml:446–) does not contain `p4.superseded_run_ids`, `controls.kernel`, `controls.pass`, `controls.regressors.{face,speech_envelope,luminance_change}`, `controls.partial_out`, `controls.readout_lag_tr` or `controls.aud_selectivity_run`. §8 items 1, 2, 5, 6, 7 and 8 have no config key at all (reference-clip spec, kernels sha, n_perm/seed/blocks, B-option run ids, reference naturalistic set, archive/qc_report sha).
- L1 proposes "a config test pinning the list and its sha256". The repo already has the right mechanism: `frozen:` plus scripts/check_frozen_config.py, plus check_test_weakening.py for the tests.
- Required: put every §8 item that is a value or sha into config, add it to `frozen:` at the design-entry commit, and add a test that each pinned sha256 equals the sha of the file on disk or in S3 (dry backend).

**B8 [LOCK] p4_index is the single reader, but it does not carry the guards the design attributes to it.**
- (a) Ordering (§8.9): only T-CTRL "refuses to run until DECISIONS holds the P4b design entry". The firewall should live in the one place every reader passes through. Add a `p4_open(ref)` (or a guard in `p4_index`) that refuses until the pinned design entry id exists, and verifies the bytes' sha256 equals `pred_sha256` on read. Today the loader returns `pred_sha256` from the row and nothing ever checks it.
- (b) Latched D-038 STOPs: the driver refuses to proceed on an uncleared `stops/` marker or a failing D-038 row (`latched_stops`, :243). p4_index ignores both. The loader must refuse while any STOP is uncleared.
- (c) `PRED_PREFIX = "pred_clampv1/"` is a literal in p4_index.py:13, while the driver uses `f"pred_clamp{WORD_END_CLAMP}"` (:85). Add a test pinning the two equal (or derive one from qc.WORD_END_CLAMP).
- (d) The L1 grep test "no other module opens pred_clampv1/ keys" will miss the driver's f-string and any `pred_key` read from a row. Replace it with an allowlist test: only p4_index (read) and the driver (write) reference `PRED_PREFIX` / `pred_key`, checked by AST over src/ and scripts/.
- (e) The claim "p4_index refuses any key outside pred_clampv1/, so reference clips can never enter the analysis set" is relative to the store root. A ref root written by an unmodified driver also holds `pred_clampv1/` keys. The real protection is the run-set filter: track ∈ {t1, t3} and the video in the frozen run sets. Assert the store root equals `p4.s3_prefix`, and add a test that rows with track `ref` or a non-run-set video are ignored.

**B9 [LOCK] The P4/P4b DoD is only partly ticketed.**
- (a) ROADMAP P4b DoD lists `controls_report.md`. No ticket produces it.
- (b) The `qc_report.html` test "no numeric prediction fields" is a denylist. Make it an allowlist: every value in the report traces to a named manifest-row, gate or ledger field. Add a test that it builds from the dry-run store (103 jobs) and holds every DoD element in L3 (gate, T, n_words vs tsv rows, chunk counts, D-038, revisions, GPU, run_id, sessions/aborts BUG-027/028/031/033), plus its sha256 for §8.8.
- (c) Ledger reconciliation has no closure criterion. "Compare with the invoice when the owner provides it" can stay open forever. Define PASS as |Σ(terminate − launch) × usd_per_hour − `spent_usd()`| ≤ a stated tolerance, with orphan minutes per BUG-027/028 event taken from ledger events, and the invoice check as a separate owner sign-off.
- (d) State whether the P4b reference-clip spend (and any B1 audio-only spend) is in the reconciled total, or reconciled again at P5 entry.
- Tests: use a fixture ledger with an orphan, a capacity miss (nothing billed) and a double-terminate.

**B10 [LOCK] T-CTRL and T-ENV cannot be "only via p4_index" while §4(b)/T-AUDIO keys predictions by track and the loader hard-codes t1/t3.**
- If B1 or B2 (Q1) is chosen, the loader extension needs its own tests, and the single-loader property must hold for both tracks: the same superseded handling, its own revisions check (and whether it must equal the full-model revisions set apart from `features_to_use`), and its own prefix.
- Add a T-AUDIO test that the audio-only cache key differs from the full-model key only in `features_to_use`.

## Non-blocking items

- **N1 The session and cost estimate is low.**
  - With SETUP_EST_S 1800, TEARDOWN_S 600 and EXTRACT_EST_S 360 (:90–93), a 1.4 h session leaves about 2640 s, which is about 7 jobs. That matches the design's own "7–9 jobs per 1.4 h".
  - 27 clips plus 3 D-038 reruns is therefore about 4 sessions, about 5.5 GPU-h, about $11, not "2 sessions, $6–7".
  - `--usd-limit 8` per session is fine. Update the estimate and the budget line.
- **N2 Nesting under the P4 root.** `<p4 s3_prefix>/p4b_refclips_v1/` puts ref objects into every `s3_list("")` of P4 `load_state` (:228) and into the L2 "every object under the P4 S3 root" archive. A sibling prefix (`wave1/derived/p4b_refclips_v1/`) is cleaner. If nesting is kept, L2 must list ref objects separately, and the B2(v) test covers P4 invariance.
- **N3 Gaps in tests/test_p4_index.py.** Add tests for:
  - a missing manifest (SystemExit);
  - an empty manifest;
  - track case (`"T3"`);
  - rows of other tracks or videos are ignored;
  - a smoke test on the real config `p4:` section with 103 synthetic rows (ties the test to the frozen run sets and the D-067 c superseded list rather than a toy CFG).
  The `d038` helper argument is unused.
  The "103 refs, 1 revisions hash" claim in b632d6d was made on the live store and is not reproducible in CI. Record the run (keys and hashes only) as an artifact.
- **N4 The first session should be watched and capped.** D-066 bound P4 session 1 to a watched `--limit 3` plus a restore smoke test. Apply the same to the reference job: `--limit 3` covers the 3 D-038 reference clips, then a human check.
- **N5 Speech modalities.** config `controls.dry_run.n_speech_bursts` is annotated "audio-only, text-only, both". The design builds only "both". Either amend the config comment through the design entry, or plan the audio-only reference run (Q1 B1/B2) in the same campaign to avoid a separate boot (about 30 min setup per session).
- **N6 End-of-clip edge.** The last window ends at TR 57 for k = 4, so it depends on TRIBE emitting T = 58 and a clean final TR. Assert onset + 8 ≤ T − 1 against each clip's actual segments.csv when the kernel is derived, and handle a truncated window by STOP or a documented drop, not by a silent NaN mean.
- **N7 Control subtraction by index.** enh002 subtracts `p − ctrl` by index and only asserts the shapes match (enh002.py:93–95). With 27 clips and one control, assert that the segment start times are equal before subtracting.
- **N8 Pre-onset activity in K3.** ENH-002 found the speech rise starting about 3 TR before onset (bidirectional context; ENHANCEMENTS ENH-002 status). Because the pre-onset lags −4…−1 used as the K3 "noise" baseline carry signal, K3 can STOP AUD by construction. Add a planted-kernel test with a −3 TR rise so the behaviour is known before the run (see Q5).
- **N9 CI-green is not machine-checked.** `preflight` checks that the pod repo is at the commit. CI status is not checked. Optional: refuse launch unless `gh run list --commit <sha>` reports success.
- **N10 ROADMAP P4 tasks without a ticket.** "Reliability mask" and the OOD check (L5 is a spec only) have no tickets. They are not DoD items, but they should be scheduled before P5.
- **N11 Input parity.** Reference clips are 640×360 at 30 fps, encoded directly, and skip P2 normalisation (loudness, fps, resolution), while analysis clips are P2-normalised. Either pass the reference clips through `yct.normalize` or record the difference in the design entry. Add a test that the reference-clip ffprobe matches the P2 output spec where it matters (fps, sample rate, crop geometry).

## Answers to Q1–Q6 (QA aspects only)

- **Q1 (b) audio-only.**
  - No preference between B1 and B2 on science.
  - B3 is not acceptable in engineering terms either. `controls.aud_selectivity_run: audio_only` is in config, so B3 would mean a config change plus a DECISIONS entry, and the test would no longer match v2.5 C3.
  - If B1 or B2 is chosen, B10 applies, and the audio-only reference run should go in the same campaign as the full-model reference run (N5).
  - B1 adds about 4 sessions, so B1 should also be gated on B1 (driver fixes) being closed.
- **Q2 localiser stimuli.** QA accepts either. If a public set is used: commit a licence file plus a sha256 manifest of the exact images, and add a test that the clip builder refuses images not in the manifest. Freeze the manifest sha in §8.1.
- **Q3 reference naturalistic clips.**
  - From QA's side, prefer public non-YC clips with a sha256 manifest.
  - Non-primary wave-1 rows sit next to sealed labels. Even without reading labels, they widen what check_blinding must guard and would need their own blinding test.
  - Whichever is chosen, the set must be frozen (config plus `frozen:`) before any analysis-set read, because it changes which videos (a) uses when fewer than 15 remain.
- **Q4 permutation blocks.** Either option is testable. Implement `blocks` as a frozen config value (`none` | `era_route`) with the seed and n_perm beside it. Test that permutations stay within blocks and that the result is identical for a fixed seed. The council must pick one before the lock.
- **Q5 K1–K5 thresholds.** Acceptable as fixed values, provided B6 holds: in config, frozen, executable, fail-closed, and with the 8-versus-20 event contradiction resolved. Two QA notes:
  - Events within a clip, and clips that differ only by phase, are not independent draws: the model is deterministic and the bed is identical. A p < .001 across them measures consistency, not significance. State that in the design entry.
  - The K3 baseline issue is in N8.
- **Q6 motion / MT+.**
  - The stimulus first needs fixing (B5).
  - `controls.regressors.motion` has `gating: true` and is in `frozen:` (config.yaml:345, frozen list), so a K1 failure for MT_plus is a STOP under the current config.
  - Turning it into a "disclosed limitation" would mean changing a frozen key. If the council wants that escape route, it must be written as a DECISIONS rule and config before the reference GPU job runs, not after the kernel is seen.
