# P4-entry: Biostatistician

**Scope.** Reviewed at HEAD 421c7ef against:
- the packet and every source it cites (D-038, D-044, D-053, D-060–D-062; BUG-018 and BUG-027; ENH-002 and ENH-008);
- the run dir `wave1p2b_20261118T002855Z` (`metrics.json`, `report.md`, `feature_cache_manifest.json`);
- `data/manifest.csv` (analyst columns), `data/wave1_{normalize_qc,confounds_summary,transcripts_summary}.csv`;
- `docs/prompts/v2.md`, `src/yct/features/m0.py`, `src/yct/tribe_run/feature_cache.py`, `analysis/power/pw.py`;
- the prior Biostat reviews p0_c2, p1_c2 and gD032_c3.

**What I ran.**
- 40 M0/Q tests pass (`tests/test_m0*.py`).
- Scratch script `/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/lev.py` runs the production `m0.q_m0` on the real wave-1 M0 proxies (full 58 s means from the confounds summary, because W is not frozen yet) and computes hat values.

**What I did not touch.** No labels, no `data/sealed/`, no AWS. I edited nothing except this file.

## Q1 verdict: **GO (conditional)**

The study's determinism policy (D-038) makes TRIBE inference a fixed function of video plus transcript, and P4 reads no labels. Nothing I found makes the inference itself invalid. Four items are pre-specification items, though, and they lose their value once the P4 outputs exist and someone has looked at them.

**Conditions C1–C4.** Commit them as one DECISIONS entry, plus one small assert, **before launch**:
- **C1. Freeze W now** (D2).
- **C2. Freeze the analysis set and the inference set**, including the yct_0644 deadline and the low-fps rule (D3; Q2, Q3).
- **C3. Assert one GPU class** per video and in the feature-cache sidecar (D5).
- **C4. Make the P4 campaign re-run the D-038 Gate 2 fresh extraction** on the same 3 clips, with the fresh *predictions* persisted, so the gate can be evaluated on M1 and parcel features as v2.md requires (D4).

**Not P4-blocking but must close before P5 (R / M0 freeze):** D1, the Q(M0) leverage problem. It is now confirmed on real data.

## Answers

### Q2. yct_0644 (source unavailable)

**Yes: a pre-unblinding exclusion, with reason "source unavailable".** Fix the rule now:
- It is excluded unless the raw file is on the pod **before the P4 launch**.
- There is no later re-entry. A separate one-video GPU campaign would break the "one campaign, one GPU type" rule and invite a forking path.

**Counts after the exclusion:**

| Set | N | Notes |
|---|---|---|
| Analysis set (T3/T2-type sets) | 52 | |
| T1, after yct_0483 | **51** | Primary H4 N |
| non-YouTube | 6 (was 7) | yct_0644 is `web`, era block E3 |

**Q(M0) at the new N:**
- ⌊51/3⌋ = ⌊52/3⌋ = 17.
- `voiced_any` is constant (all 52 have voiced speech), so it is aliased. That leaves 15 effective required columns and **2 optional terms**: `motion_energy_crop²` and `pitch_mean_hz²` on the proxies.
- The v2.md table at N = 53 (16 required, 1 optional) therefore does not describe the real Q. The prereg must print the realised table.

**Missingness is plausibly not at random.** Link-rot on a web-hosted video may correlate with outcome.
- At unblinding, report a CONSORT-style table of exclusion reason × label: 0644, 0483 (T1), the qc_pass drops, and any low-fps exclusion.
- From the P1 c2 worst-case split (30/23), two further exclusions leave **≥ 21 per group** at worst. The ≥ 20 stop rule is not triggered, and the owner can confirm this from totals only.

**Label-free MDE** (`analysis/power/pw.py`, two-sided α .05, power .80):

| Set | Single network d | Holm worst case (α/4) | Bonferroni 7 |
|---|---|---|---|
| N = 53 | 0.785–0.809 | 0.947–0.976 | 1.006–1.038 |
| N = 52 | 0.792–0.814 | 0.956–0.983 | 1.017–1.045 |
| **N = 51 (T1)** | **0.801–0.820** (AUC 0.714–0.719) | **0.966–0.989** | **1.027–1.052** |
| N = 50 | 0.809–0.825 | 0.976–0.997 | 1.038–1.060 |

- **H4 power:** 0.404 / 0.682 at effect sizes 1.06 / 1.5 for N = 53 (D-053g). It will be marginally lower at 51; I did not rerun it.
- **H4 MDE stays > 1.5.** The change from 53 to 51 is immaterial next to that. v2.md §0 must be restated at the final N.

### Q3. Sub-16 fps sources

**The packet miscounts.** yct_0641 has `qc_pass = False`, so it is **not in the analysis set**. Only **yct_0626** (12.5 fps, E12, YouTube) is affected.

yct_0444 (17.15 fps) is above the floor but also frame-duplicated to CFR-30. It stays, and the flag should record it as `src_fps < 24` (informational).

**v2.md §5 P2 states "sources must be at least 16 fps".** That is the only rule written before the data, so keeping yct_0626 is an amendment, not an interpretation. Both options are label-blind and acceptable *if fixed now, before P4 outputs*:

- **(a) Preferred: follow the text.**
  - Primary = exclude `src_fps < 16` (ffprobe avg_frame_rate).
  - The "all sources" analysis is a sensitivity: outside Holm, no α, same W, Q rule, seeds and blocks, T3-style survive/fragile wording.
  - T1 N becomes 50, so ⌊N/3⌋ = 16 and Q loses one optional term.
- **(b) The packet's D-060 proposal: keep, with a `low_fps_source` flag and an excluding sensitivity.**
  - Acceptable only if the DECISIONS entry explicitly amends the v2.md "must" sentence.

**Either way:**
- Write the rule into v2.md for **every wave**. Wave 2 must inherit it mechanically.
- Do not add `low_fps_source` to M0 or Q. As a one-video indicator it would have leverage 1 (see D1).

### Q4. ENH-002 visual control (Biostat angle only; the content is the Neuroscientist's)

**The choice must rest on the reference-clip evidence alone.** Make it before any P4b control statistic is computed on wave-1 videos. Pre-specify **one** control per role. No fallback chain is allowed after wave-1 control results are seen, because that is control-shopping and the STOP criterion would lose its meaning.

- **MT+ is already the pre-registered fallback** in config `controls:`. Choosing it by DECISIONS entry now is procedurally clean.
- **V1–V3 is then reported descriptively.**
- **Keeping V1–V3 risks a predictable STOP.** ENH-002 already shows a flat, weak V1–V3 response (0.06 vs MT+ 0.46). A STOP on a control known in advance to be weak says nothing about pipeline validity.

### Q5. WER

**Not blocking for P4. Blocking for P5**: it must finish before the W-averaged M0/M1 freeze and before the P5b runs.

The reason: a transcript change after P4 changes the cache key, and that forces full re-inference. Pre-specify the action rule now:
- **The threshold:** median WER > 10 %, or any clip > 25 %.
- **The action:** a DECISIONS entry plus re-transcription and P4 re-run. Otherwise WER is reported, not gated.
- **The clip choice is fine.** The 5 WER clips are the first 5 sorted ids, a label-blind choice.

### Q6. ENH-008 caption flag

**Not blocking for P4 or P5. A limitation, unless it is implemented before P6.**
- **Not in the primary M0.** Q is saturated (2 free columns at N = 51). A forced caption binary would displace an optional quadratic, and adding it now would be a post-hoc covariate.
- **If it is implemented** (label-blind proxy or human rating) before P6: report it descriptively, plus an **S-CAPTION** sensitivity (+ caption flag, linear binary) outside Holm.
- **If it is not implemented:** state the limitation in the prereg.
- Decide which before P5, so the dimension table is frozen once.

### Q7. BUG-027

**No statistical implication.** I defer adequacy to QA and the Watchdog. My one requirement: a P4 campaign that is interrupted must **resume from the content-addressed cache**. Gate 1 guarantees identity, and nothing may be re-extracted mid-campaign. Log per video which run produced its cache entry.

### Q8. Anything else before P4

Conditions C1–C4 above. The details are in D2–D5.

## Defects

### D1 [MAJOR, before P5; decide now]. Q(M0) gives one video leverage 1.000 on real data (gD032_c3 N1 has now materialised)

**The data.**
- `scene_cuts` in the analysis set: **51 videos = 0, yct_0528 = 34 cuts** (z = 7.1, kurtosis 52).
- As a linear M0 term this is a dummy variable for yct_0528, so its hat value is **1.000**. Its R row is identically 0 for every M1 feature, and it carries no information in M0 + R.

**What the production `q_m0` gives on the proxies** (T1, N = 51):
- the top hat values are 1.000 (yct_0528), **0.957** (yct_0247: motion energy z = 4.0, with `motion_energy²` admitted as the first optional term by var(z²) = kurtosis order), 0.891 (yct_0186) and 0.870 (yct_0310);
- the same holds at N = 52, in the YouTube-only set and after the low-fps exclusion.

**gD032_c3 required change #1 is not implemented:**
- no robustification;
- the optional order is still `optional_term_order` by var(z²), `m0.py:354`;
- there is no leverage assert.

**Winsorising alone does not fix this.** Any monotone transform of a two-valued feature is still a dummy.

**Fix** (label-free; DECISIONS entry plus code and tests before P5):
1. **Sparsity rule.** A continuous M0 feature with fewer than 5 values different from its mode in the analysis set is replaced by its merge-list step: `scene_cuts` → (ii) `visual_change` = mean z(motion_energy_crop, scene_cuts). A feature without a merge step is dropped and logged.
2. **Winsorise z at ±3** before forming squares and products (and the linear terms).
3. **Fixed optional order** from a config list, not from kurtosis.
4. **Assert max h_ii ≤ 0.9.** On failure, apply the next merge step; never drop a video. Log all leverages.
5. **Recompute the realised dimension table** at the final N and print it in the prereg.

**Related: verify yct_0528 by watching** (D-047 `is_original_application_video` rubric):
- it has 34 cuts, 24 words, 28 wpm and 22 words in W, the minimum;
- that pattern suggests a montage or demo cut;
- exclude it only through that pre-written rubric, never because it is a statistical outlier.

### D2 [MAJOR, before launch]. W, and therefore T1 N, is not pinned

**The problem.**
- v2.md sets W "once in P4 from the label-free group-mean time course and the P0 latency", but gives no algorithm.
- The T1 exclusion (trimmed duration < W_end + 5) makes N a function of L:

  | L (TR) | 0–1 | 2–3 | 4 | 5 |
  |---|---|---|---|---|
  | T1 exclusions | 1 | 2 | 3 | 4 |

- The ENH-002 flash peak at 4 TR (on a plateau) is already on file as a temptation.
- yct_0528, the leverage-1 video, is 51.3 s long, so it is dropped at L ≥ 2. The 20-words-in-W rule also depends on W (yct_0528 has 22).

**Fix.**
- A DECISIONS entry before launch: **W = [5, 45) TR** (L = 0 from D-055, ENH-002 speech → AUD peak at 0 TR).
- The P4 group-mean time course is a QC report only and cannot move W.
- Alternatively, write a fully deterministic algorithm now.

### D3 [MAJOR, before launch]. Freeze the analysis set and the inference set

**One DECISIONS entry must list:**
- **the T1 primary set:** the 51 content_ids (or 50 under Q3a), with each exclusion and its reason;
- **the T3 set:** the T1 exclusions reused (v2.md T3 rule);
- **the inference set.**

**Inference set.** Run TRIBE (T1, T3, ablations) on **all 57 normalised videos in one campaign**. That includes the 4 normalised non-`qc_pass` rows, for the A+B sensitivity, so no second GPU campaign is ever needed. The analysis sets are then defined by manifest flags, never by what was run.

**Also fix the packet and D-060 text:** yct_0641 is not in the analysis set.

### D4 [MAJOR, before P5; set up in the P4 campaign]. The D-038 Gate 2 evidence does not measure what v2.md gates

**What v2.md requires.** §5 P4 and the P0 c2 condition require reliability ≥ 0.99 "for **every M1 feature and the parcel values**".

**What D-062 reports instead:**
- `feature_cache.reliability` = 1 − var(a−b)/(var a + var b) **within one clip's backbone tensors**: min 0.99903 (text/Llama; max |Δ| 0.31);
- reliability over the raw 58 × 20,484 prediction (≥ 0.999994, max |Δpred| ≤ 0.0045, against pred SD 0.156).

**Why that is not the gate.**
- Within-clip reliability is dominated by between-vertex and between-dimension variance. It is not the between-video reliability of a W-averaged network mean.
- A crude bound on the M1 drift is |Δ| ≲ 0.0045 / 0.156 ≈ 0.03 spatial-SD units. Whether that is small depends on the between-video SD of M1, which is unknown until P4.
- The fresh predictions are not persisted. `extraction_drift` discards `fresh_preds`, and the kept fresh features sat on the terminated box.
- **No STOP is implied.** Gate 1 (bit-identical cached rerun) is what protects inference, and it passed 3/3.

**Fix.**
1. In the P4 campaign, re-run the fresh extraction on yct_0016, yct_0034 and yct_0036 and **persist the fresh predictions** (and features) to S3 with their sha256.
2. After P4, compute the W-averaged M1 (6 networks + spatial SD, plus the limbic network for H1) and the 400 parcel values, cached vs fresh.
3. Compute reliability_k = 1 − mean(Δ_k²) / var_between-videos(k), using the 51 T1 videos (label-free).
4. Gate at ≥ 0.99 for every M1 feature, and report the parcel distribution.
5. Until then, word the D-062 statement as "raw-prediction reliability ≥ 0.99999; the M1-level gate pending".

**Deviation to record:** D-062 already notes that the clips were chosen by sorted id rather than the seeded sha the text specifies. That is label-blind and fine; record it in the prereg deviations list.

### D5 [MINOR, before launch]. The feature-cache key and sidecar omit the device class

- **v2.md:** key = sha256(video ‖ transcript ‖ revisions ‖ **device class**).
- **`feature_cache.cache_key`** hashes only the video and transcript. Revisions are checked against the sidecar (good). The GPU is neither keyed nor checked, so a fallback instance type (A100 PCIe or 80 GB) would silently mix device classes.

**Fix.** Record the `nvidia-smi` GPU name in the sidecar and refuse a mismatch. The P4 driver asserts `gpu_1x_a100_sxm4` / "NVIDIA A100-SXM4-40GB" for every video; any other type needs the v2.md §3 equivalence test.

### D6 [MINOR, before P5]. `speech_frac` saturates

- `speech_frac` is energy-VAD based (`confounds/core.py:134`), so music beds count as speech.
- 16 of 52 videos are > 0.99 (skew −1.7, max |z| 3.5).
- Both its square and its product with speech rate are forced into Q, so the ceiling feeds leverage.
- D1's winsorisation covers the statistics. Whether to define `speech_frac` from WhisperX word coverage instead is a construct question for the Referee and Neuroscientist. If it changes, it changes by DECISIONS entry before P5.

### D7 [MINOR, before P5/P6]. Carry-forward Biostat items still open

None of these blocks P4.

**From gD032_c3:**
- **#3:** the P5b `included_term` band is still two-sided (`v2.md` P5b). It must be ≤ 7.1 %, with conservatism reported separately.
- **#4:** `h4_null_sim` has no `blocks=`, no diffuse scenario and no per-replicate term list.
- **#5:** the BCa caption lacks "approximate (small n)".

**From p1_c2:**
- **#2:** `v2.md` l.375 still says "20–29 per group is confirmatory", which contradicts D-046.
- Also #2: there is no wave-2 N_target or calendar stop.
- **N2:** `qc_pass` is not written as an every-wave rule. The source-unavailable and low-fps rules (Q2, Q3) now join it.

**Blocks:**
- Blocks were coded on 58 rows (BUGS:32 gives sizes 4/4/45/5).
- They must be recoded owner-side on the **final T1 set** before P5.
- Report the effective N. Two blocks under 6 that cannot merge across route reduce the effective permutation space.

**h4sim:**
- The ≥ 500-dataset `h4sim` rerun at the final N must use the **production** Q (17 columns, heavy-tailed real M0, D1 fixes).
- The current simulation uses Gaussian M0 with P0 = 12.

## Summary of blockers

| When | Items |
|---|---|
| **Before launch** | D2 (freeze W), D3 (freeze the analysis/inference sets, the yct_0644 deadline, the Q3 rule), D5 (GPU-class assert), and the C4 set-up for D4 |
| **Before P5** | D1 (Q leverage: sparsity merge, winsorise, fixed order, h ≤ 0.9), D4 (M1-level Gate 2), WER rule (Q5), D6, block recode |
| **Before P6** | D7 items, S-CAPTION decision (Q6), realised Q table and MDE at the final N |
