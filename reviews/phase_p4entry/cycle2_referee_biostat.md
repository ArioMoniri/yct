# Gate P4-entry (wave 1), cycle 2: Strict Referee and Biostatistician

**Session.** session_011NAQ1mksc4Ea1mJcrGfTSd. One agent wrote both sections, and each was judged on its own.

**Scope.**
- HEAD 9c4cb32, on top of the FIX-P4E commits c616a9d and 11bc34d.
- What I read:
  - cycle2_packet.md;
  - my cycle-1 strict_referee.md and biostatistician.md;
  - DECISIONS D-063 and D-064;
  - config.yaml (`window`, `transcribe.wer`, `controls`, `p4`, `frozen`);
  - the v2.md diff from 0c8e2bc to 11bc34d;
  - the cache-key and revisions code: feature_cache.py and run_clip.py `_revisions`;
  - the D-038 and firewall paths of scripts/gpu_wave1_p4.py;
  - tests/test_{p4_config, gpu_wave1_p4, tribe_p4_cache, tribe_qc_gate, infra_terminator}.py.
- What I ran:
  - those 5 test files: **72 passed**;
  - `scripts/check_frozen_config.py`: **OK, 15 frozen keys unchanged**.
- Constraints kept: read-only, no AWS access, no decryption, no labels read. I opened no manifest columns myself; the tests read only `video_id`, `in_primary` and `qc_pass`.

---

## Section A: Strict Referee

| Cycle-1 item | Status | Evidence |
|---|---|---|
| **B1:** L and W undefined | **CLOSED** | `window.latency_l_tr` = 0 and `start_tr`/`end_tr` = 5/45 are in `frozen:`. A test asserts start = max(5, 4 + L + 1) and a length of 40. v2.md §1 and §5 P4 now read "W fixed now", replacing "set from the time course". The frozen guard refuses any change to a value, any unfreezing and any re-pointed `frozen_at`. W therefore cannot move without a QA-visible guard change, which is stronger than the textual move rule. |
| **B1 (follow-up):** the move rule | CLOSED for launch; carry-forward m-A | D-063 says "W may not move after any analysis-set prediction is W-averaged". Read literally, W could still move after the group-mean time course is seen, if nothing has yet been W-averaged. The firewall plus the frozen guard make that unreachable now. Before the P4b design entry, add one D-note line: "the group-mean time course is descriptive/QC only and never moves W". |
| **B2:** output firewall | **CLOSED** | D-063 B2 is written in v2.md §5 P4 and in the config `p4:` comment. Tests check that the driver and the qc, cache_archive and feature_cache modules import no `yct.features/interpret/stats/predict/report/confounds`. A test checks that the driver source holds no `window`, `controls`, `start_tr`, `parcel` or `network_means` tokens. Records hold only numbers and hashes: no `pred_mean`, no `pred_std`, no feature sha. |
| B2 (sub-asks) | Partly; carry-forward m-B | Two sub-asks are not stated explicitly: (i) commit the sha256 of the P4 archive manifest before the first analysis touch; (ii) no per-video inspection of the exposed ids. The S3 objects are immutable with sha256 sidecars and the manifest is append-only, so (i) is cheap. Commit it as part of the P4 result entry, before the P4b design entry. Neither blocks launch. |
| **B3:** Q2 and Q3 recorded before launch | **CLOSED** | `p4.analysis_excluded` = {yct_0644: source_unavailable}, frozen, and D-063 says "never re-admitted". `p4.flags.low_fps_source` = [yct_0626] by the rule `src_fps < stimulus.min_source_fps`, with S-LOWFPS. v2.md P2 now reads "must → should" plus the flag and the sensitivity. A test recomputes the flag from the P2 QC table. yct_0641 is asserted to be outside the analysis set. |
| Run sets | **CLOSED** | T3 = 52 = (in_primary & qc_pass, 53) − yct_0644. T1 = 51 = T3 − yct_0483. Both lists are frozen, and the tests recompute them from label-free columns and the tail rule (only yct_0483 is below 50 s). The driver plans the D-038 clips first, then `run_set_t1`, then `run_set_t3`. No ablations are run. |
| Q7 (i): run and instance ID on every record | **CLOSED** | `entries/<job>.json` stores the producing run and instance. Each run's manifest rows are also kept immutable (`rows/<run>/`). |
| Q7 (ii): one revisions set across P4 | **CLOSED** | Two checks enforce it: `_refuse_mixed_revisions` (one cache root holds one revisions set), and `clip_gate` requires the revisions sha256 to equal that of every other P4 entry. |
| m2: cache key differs from spec | **CLOSED** | Key v3 = sha256(video ‖ transcript ‖ sha256(revisions)). The revisions include `gpu` = `torch.cuda.get_device_name(0)`, the backbones, the checkpoint, the TRIBE commit, the package versions and `bug018_word_fix`. Tests: `test_cache_key_includes_revisions_gpu_and_backbones` and `test_other_gpu_is_refused...`. |
| M3: Gate 2 on M1/parcels | Set up (**CLOSED** for launch); the gate itself is OPEN and blocks P5 | The driver runs `--fresh-drift --keep-fresh` on yct_0016, yct_0034 and yct_0036. It saves the fresh predictions and features to `p4/d038_fresh/` and checks the sha256. Gate 1 or Gate 2 failing (backbone level) is a STOP. D-063 corrects the D-062 wording. **Still open before P5:** v2.md:412 still says "chosen label-blind by seeded sha". Amend it to the sorted-id rule actually used, or list it under deviations. |
| WER rule (my Q5: needs an action threshold) | **CLOSED** | `transcribe.wer.action_threshold` = 0.25 with `rule: any_video`, frozen before any reference exists. It is the strictest faithful reading of D-063 Q5. **Confirmed.** The accent flag and the random-vs-sorted sample choice remain P5 items. |
| v2.md faithful to D-063 | **CLOSED** | Checked against D-063: W/L, the run sets, the fps rule ("should"), the firewall, MT+ = MT ∪ MST ∪ FST (139 vertices) with V4t dropped, V1–V3 descriptive only, and no luminance-only kernel. Each change is tagged "(v2.7 P4E; D-063)" and the old text is struck through, not deleted. Minor gaps: v2.md does not record my Q3(d) point (yct_0444 at 17.2 fps is unflagged by rule), and the wave-2 inheritance is implied by the config rule rather than stated. Neither blocks launch. |
| M1, M2, M4–M7, m1, m3, m4 | Unchanged (P4b, P5 or P6) | D-063 re-scoped these, as I proposed. None of them blocks launch. |

**Not in my remit:** the terminator's dependence on the owner SSM parameter or an external scheduled session. That is a cost risk, not a validity risk; it belongs to the Watchdog and QA. An aborted extraction still cannot enter the results: an entry without its sidecar or with mismatched revisions is refused.

### Referee verdict: **GO**
GO for launching full-model T1 (51) and T3 (52) P4 extraction, with the firewall in force and no ablations. Carry-forwards m-A and m-B must be closed before the P4b design entry. The v2.md:412 sorted-id amendment must be done before P5.

---

## Section B: Biostatistician

| Cycle-1 item | Status | Evidence |
|---|---|---|
| **C1/D2:** freeze W (and with it T1 N) | **CLOSED** | L = 0, W = [5, 45) and `min_tail_s` = 5 are frozen. T1 N is fixed at 51 and does not depend on L afterwards. yct_0528 (51.3 s; the leverage-1 video; 22 words in W) stays in T1. The time course cannot move W because of the frozen guard (see m-A in Section A for the wording). |
| **C2/D3:** freeze the analysis and inference sets, the yct_0644 deadline and the Q3 rule | **CLOSED** | T3 = 52 and T1 = 51 are frozen, with each exclusion and its reason in config (`analysis_excluded`, `t1_excluded`). yct_0644 is excluded unconditionally, which resolves the deadline. I proposed option (b) for Q3 (keep + flag + S-LOWFPS), and it is adopted with the v2.md "must" amended. `low_fps_source` is not an M0 or Q term. **My D3 suggestion is not adopted:** I had asked to also run the 4 normalised non-`qc_pass` rows, to allow an A+B sensitivity without a second campaign. No such sensitivity is pre-specified in v2.md, so this is a cost option only, not a validity gap. Not blocking. |
| **C3/D5:** one GPU class | **CLOSED** | The GPU name is in the revisions dict, so it enters the cache key and is checked against the sidecar. One cache root holds one revisions set. `clip_gate` asserts "NVIDIA A100-SXM4-40GB", and `p4.gpu_type` = gpu_1x_a100_sxm4. |
| **C4/D4:** Gate 2 re-scorable on M1/parcels | **CLOSED (set-up)** | Fresh predictions for yct_0016, yct_0034 and yct_0036 are persisted with a sha256 check (`test_fresh_predictions_are_saved_with_sha_but_never_reported`). The cached predictions are kept under `pred/t1/`. Both inputs of reliability_k = 1 − mean(Δ_k²)/var_between(k) will therefore exist. That computation is a cross-video statistic, so the firewall correctly defers it until after the P4b design entry. **The gate itself stays OPEN and blocks P5:** ≥ 0.99 for every M1 feature, with the parcel distribution reported. |
| Q2/Q3 power bookkeeping | Noted | At N = 51, ⌊N/3⌋ = 17, the same as at N = 53, so the Q dimensions are unchanged. The MDE at T1 N = 51 is single-network d 0.80–0.82 and Holm worst case 0.97–0.99 (my cycle-1 table). Re-print it at the final N (P6). |
| WER rule | **CLOSED: confirm `any_video` > 0.25** | My cycle-1 rule had two parts: median > 10 % **or** any clip > 25 %. D-063 adopted the any-clip part only, and `any_video` is its faithful, strictest reading. **I do not amend the gating rule:** `transcribe.wer` is frozen, and a median over 5 clips is a weak second gate. I do ask, before P5, that the median and the maximum WER both be **reported**. If the median is > 0.10 while no clip exceeds 0.25, record it in the deviations list as a known ASR-noise limitation on the text path. |
| D1: Q(M0) leverage (yct_0528 h = 1.000) | OPEN, before P5 | D-063 lists it before P5. Not launch-relevant. |
| D6 `speech_frac` saturates, D7 carry-forwards, block recode | OPEN, before P5 or P6 | D-063 re-scoped them. Not launch-relevant. |
| v2.md faithful to D-063 (statistical content) | **CLOSED** | S-LOWFPS uses the same W, M0, Q rule, seeds and blocks, sits outside Holm and uses the T3 survive/fragile rule. The firewall covers W-averaging and every cross-video statistic. The controls have one gating role each (MT+ motion; V1–V3 descriptive), so there is no fallback chain to shop from. This matches my Q4. |

**No new launch-blocking statistical defect found.**
- Inference stays a deterministic function of video + transcript + revisions: Gate 1 is required on the D-038 clips, and any failure is a STOP.
- The driver never loads a prediction array.

### Biostatistician verdict: **GO**
GO for launching full-model T1 (51) and T3 (52) P4 extraction. These stay open before P5:
- D1;
- the M1/parcel Gate 2 computed on the saved fresh predictions;
- WER, with median and maximum both reported;
- D6;
- the block recode on the 52-row set.
