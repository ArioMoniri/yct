# Normalisation recheck: Watchdog (process integrity)

Scope: the inventory (81 items), checked against config.yaml, `frozen:`, check_frozen_config.py, src/yct/{normalize,confounds,features,controls,interpret,tribe_run}, v2.md, ROADMAP and DECISIONS D-053 to D-085. Firewall D-063 B2 was respected: nothing was read from sealed data, labels, transcripts, pred_clampv1/ or analysis-set outputs.

## Inventory claims I checked
- N1 holds. `normalize`, `stimulus`, `vad`, `confounds`, `features`, `atlases`, `localize` and `m0` are YAML-identical between b24fc1c and HEAD. None of them is in `frozen:`.
- Since the P2/P3 run, the only code change in confounds is 4db5895. It refactors `word_rate_per_tr` and `speech_rate_summary` and leaves the outputs unchanged.
- `frozen:` covers only the window, p4 run sets and flags, `transcribe.wer`, MT_plus, `regressors.motion`, `descriptive`, the kernel acceptance rules, `pass`, the refclips subtrees and the seeds.
- A-01 is correct. The confounds use the same 292 short side and 256² crop as V-JEPA2, and `scene_cuts` is the only full-frame visual feature in M0.
- A-05 is correct: `hdr_source` is not in m0.py. D-060 recorded 0 HDR videos in wave 1, so wave 1 is unaffected, but wave 2 can contain HDR.
- M-12b is correct. kernels.py receives `d_std` without saying which standardise function produced it.
- Provenance gap. P2 records depend on the system ffmpeg, x264, zscale and swscale builds. pyproject only requires ffmpeg ">= 6", and run_with_provenance records pip packages but not the ffmpeg build. Only refclips_build records it.

## Verdicts by risk (all label-free; none needs an outcome)
**Blocking for the lock: forking paths and wave consistency**
1. **A-17 + wave 2.** v2.md says wave 2 is "analysed once with the locked protocol", but no rule says whether wave 2 re-estimates or reuses wave 1's fitted parameters. Parameters re-estimated on wave 2 would include the M0 z-score means and SDs, the pitch and lag imputation medians, the variance order of optional Q terms, the merge trigger (rank > ⌊N/3⌋ at wave-2 N) and the era dummy (wave 2 may be one era, which aliases the dummy). The rule also has to cover the S-* subsets. Proposed rule: compute everything within the analysed set, as T1 does now, and say so explicitly. T3 already reuses the T1 values (A-23). Freeze this before P6.
2. **N1 freeze coverage.** Wave 2 must go through byte-identical P2/P3/P5. Add `frozen:` rows now, because P2/P3 has already consumed these keys: normalize, stimulus.{fps, min_short_side_px, center_crop_px, t1_trim_s, t1_max_probe_s}, vad, confounds, transcribe.whisperx, atlases and features.medial_wall. Freeze `features.*` and `m0.*` at the latest before the first analysis-set W-average (B2), not at P6. Also pin the ffmpeg/x264/zscale build used by P2 (version string and sha of the binary) and record it in every P2 run dir. A wave-2 P2 on a different ffmpeg is a silent protocol change.
3. **M-20 (H2 composite).** It has no config key and no code, and it does not say whether areas are weighted by vertex or by area. Choosing the weighting after maps exist is a free choice on a Holm-family test. Add `features.h2_areas` plus `weighting: vertex`, with a test, and freeze them before any analysis-set readout.
4. **A-10 (CV scaling, C grid) and A-15 (Freedman–Lane PCA centring).** Neither is specified for H3, H4 or H4b. h4sim uses in-fold StandardScaler while production M0 is globally z-scored. Write one rule (in-fold scaler on M0 + R, fitted on the training fold only; PCs from globally z-scored M0) into config, then freeze it. P5b must validate this exact code path.
5. **P4b unfrozen gate inputs (A-18, A-19, A-20, A-21).** These are unfrozen: `partial_out`, `regressors.{face, luminance_change, speech_envelope}`, `kernel.{window_tr, type, shift_by_L}`, `readout_lag_tr` and the FFC/PH/AUD/V1_V3 area lists. The speech envelope's band, smoothing and decimation are not defined at all. Gate (c) reads analysis-set predictions, so retuning any of these after a FAIL is outcome-adjacent. Specify each one, freeze it, and only then implement (a) to (d). Watchdog position on drift: keep the intercept-only rule as frozen and report a drift or onset term as a disclosed sensitivity only. Do not add it to the gate after the fact.

**Major: correctness**
6. **S-23/S-24.** The speech provider must trim each item to its −40 dBFS span before placement, RMS matching and word timing. Otherwise espeak's leading and trailing silence shifts onsets and inflates gain. Fix this before D-085 is frozen, with a test.
7. **M-12b.** The kernels and the K-check must call networks.standardise, which fails on zero SD or non-finite values. Add a test that `d_std` is produced by that function. Record that ENH-002 used the duplicate (L = 0 only, no impact).
8. **S-14 dynamic-mode fallback.** This is the only P2 branch that changes TRIBE input for individual videos, and it could co-vary with production style and therefore with group. Report the label-free count of `loudnorm_mode=dynamic` from the P2 records. If the count is > 0, add a pre-declared sensitivity that excludes those videos (outside α).
9. **S-10/A-05 `hdr_source`.** Wire it into m0.py with a test before the lock, because wave 2 may contain HDR. Wave 1 is unaffected.

**Needed? (each one needs a decision before the lock; no post-hoc adoption)**
10. **S-18 q480.** It has no consumer. Remove it from the P2 DoD, or declare it an unrun descriptive copy. Keep the files.
11. **S-07 crop coverage, S-08 `stratum_9x16`, source bitrate/codec/fps.** v2.md calls these "confounds" or a "stratum", but nothing reads them. Watchdog recommendation: demote them to descriptive/QC, with one pre-declared rule: if ≥ 10 analysis videos are 9:16, run a sensitivity that excludes them. Adding them to M0 would spend the ⌊N/3⌋ budget and change Q, so that would need a D-entry before P5b.
12. Keep, needed: S-06 (geometry for confounds and T3), S-05 (determinism), S-14 (WhisperX and `rms_db`), S-09, S-16 (cache hazard) and M-12/M-16.
13. **`rms_db` in M0.** Keep it. The merge list already handles redundancy, and the decision is label-free.
14. **A-01 scene cuts on the full frame.** Do not change it, because P3 has already run. Disclose it. A crop rerun would be a second P3 fork.

**Minor or clarify**
15. **A-22 / v2.md §T3 l.153.** Group means need labels too, so they also exist only after unblinding. Fix the wording. Pre-declare one shared vmax for the two group maps, because per-map scales mislead side-by-side comparison. The difference map keeps its own scale.
16. **S-19 secondary T3** excludes the 12 clipped clips (D-060). Pre-declare that this subset is descriptive only.
17. **S-22.** Tag the reference clips bt709/tv to match the P2 output spec. The cost is trivial and there is no effect on TRIBE.
18. **N6 (S-19 gamma, S-27 aperture, S-26 ICC).** Disclosure only is fine. Do not change these now.

## Roadmap changes (proposed R-11, append-only, with a DECISIONS entry)
- **P2/P3:** add the DoD item "toolchain (ffmpeg, x264, zscale build + sha) recorded and pinned". Drop q480, or mark it unrun. Restate crop coverage, 9:16 and bitrate as descriptive, with the 9:16 sensitivity rule.
- **New gate before P5 (pre-W-average):** freeze-row commit for P2/P3/P5 keys plus `features.h2_areas`, with Watchdog sign-off.
- **P4b:** freeze and specify the A-18 to A-21 keys. Make the speech span trim and the standardise unification test-first prerequisites of D-085.
- **P5b:** validates the frozen CV-scaling, C-grid and Freedman–Lane code path, not h4sim's.
- **P6:** add a "wave-2 estimation scope" section (item 1), `hdr_source` wired, and the dynamic-loudnorm sensitivity.
- **Waves:** wave 2 reruns P2 to P5 with frozen keys and the pinned toolchain. A config-diff check against the lock tag must be empty.
