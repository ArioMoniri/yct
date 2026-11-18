# Gate P4-entry, cycle 2: Neuroscientist / TRIBE v2

Reviewed at HEAD 9c4cb32 (code c616a9d + 11bc34d). Read-only: git, grep, pytest. No AWS, no decryption, no `data/sealed/`, no labels.
Tests: `test_tribe_qc_gate, test_p4_config, test_controls_config, test_gpu_wave1_p4, test_tribe_p4_cache` → 71 passed. `test_controls_config` with `YCT_OFFLINE=1` → 8 passed, 0 skipped, so the atlas vertex counts were actually checked.

## Verdict: **GO** for full-model T1 + T3 P4 extraction

Conditions: no ablations, output firewall (D-063 B2) in force, one A100-SXM4-40GB type for every session, and a terminator per launch as D-064(e) describes.

## Cycle-1 items

| Item | Status | Evidence |
|---|---|---|
| C1 / D1: resumable P4 driver | **CLOSED** | `scripts/gpu_wave1_p4.py` covers the cycle-1 conditions:<br>• sessions of ≤ 4 h<br>• per-job S3 sync of the cache tar, predictions, records and the appended manifest<br>• synced jobs are skipped<br>• a synced cache entry is restored and predicted from, never re-extracted<br>• the D-038 clips run first, and a Gate 1/2 failure means STOP<br>• exit codes 0/75/1<br>The dry run completed 103 jobs over 4 simulated sessions. The cache key v3 holds the GPU model, and a cache root refuses to hold a second revision set, which makes "one GPU type for all of P4" executable. |
| C2 / D2: per-clip gate | **CLOSED** | `qc.clip_gate` fails closed. It requires Audio == 1 and Video == 1 chunks, counted from the TRIBE events frame (the same source that showed `[0,60]+[60,60]` on the 120 s reference clip, so the count is real). It also requires shape (T, 20484), all values finite, T1 T = 58 ± 1 with duration ≤ 58.5 s, T within 1 of the duration for T3, n_words == .tsv rows, no word after the clip end, offline with no ASR and no uvx, GPU == A100-SXM4-40GB, the word fix on, and matching sha/revision hashes.<br>Where it is enforced: in run_clip (`--qc-gate`) and again in the driver on the sanitised record. A non-zero exit code fails the job even when the gate passes.<br>The word fix is identical to upstream for a single chunk (D-057), so running it on every clip is safe. |
| C3: yct_0644 | **CLOSED** | D-063 adopted a stricter rule than mine: unconditional exclusion. `p4.analysis_excluded`; T3 = 52, T1 = 51. |
| D3: ablations | **OPEN, does not block launch** | D-063 defers ablations to their own spec and a GPU smoke test. The driver has no ablation path (`grep features_to_use\|ablat` finds nothing). My D3 (i)–(iv) still apply to that spec, including the "text-only (pinned-ASR words)" label instead of "text+TTS". |
| Q3: low-fps | **CLOSED** (one minor open) | `p4.flags.low_fps_source` = [yct_0626] with its rule. The S-LOWFPS sensitivity is defined. v2.md:383 now reads "should" and says the flag is disclosed beside both TRIBE and M0 results (the `motion_energy_crop` aliasing). Packet correction accepted: yct_0641 is not in the analysis set.<br>Still open, minor, before P5: the per-video `vjepa_unique_frame_frac` log is not implemented. |
| Q4: MT+ gating ROI | **CLOSED** | `controls.rois.MT_plus` = MT ∪ MST ∪ FST, 139 vertices, checked on the real atlas. `motion.roi` = MT_plus with `gating: true`. V4t is dropped. V1–V3 is descriptive only, and luminance_change has `gating: false`. These keys are frozen. v2.md:417/420 is amended. |
| Q4 items 3–6 (FFC vs PH selectivity, reference clips v2 / kernel recipe, naturalistic clips) = D4–D6 | **OPEN, before the P4b lock** | Not launch items. D-063 Q4 requires kernels re-derived from 58 s baseline-corrected clips. The (b) FFC-vs-PH contrast and the kernel recipe (baseline over lags −10…−5, peak over 0…+8) still have to go into the P4b design entry. |
| D7: language ID | **OPEN, before P5** | No language-ID code yet. Add it to the D-063 "before P5" list. |
| D8b: W centroid sensitivity | **CLOSED** | W = [5, 45) is fixed and frozen, which implicitly rejects [7, 47). |
| D10–D12 | Unchanged, not launch items | D10: disclose Llama re-extraction drift in T3. D12: T2 boundary rule. Both stay out of this gate. |

## New launch-blocking defects

None.
