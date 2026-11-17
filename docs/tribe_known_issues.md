# TRIBE v2: known issues and caveats audit

Audit date: 2026-11-17.

**Sources**
- A clone of `facebookresearch/tribev2`.
- The GitHub issue and PR pages, read as web pages because the API is blocked in this session. 47 issues, 36 PRs; about 20 read in full, the rest by title.
- The HF card, API, discussions and the config at `f894e78`.
- The arXiv:2605.04326 PDF.
- The `neuralset==0.0.2` source code.

The GitHub Discussions tab is not enabled (404). Of 14 HF discussions, only #2 and #10 are substantive.

**Upstream state**
- `main` is still at `af58661` (2026-06-23). There are no later commits, no tags and no releases.
- **No community bug-fix PR has been merged.** The pin therefore loses nothing, but any fix we need has to be patched into our own copy.
- The HF sha is still `f894e78`.

## Findings

| # | Finding | Source | Status | Severity (ours) |
|---|---|---|---|---|
| 1 | **Word timing is wrong for audio longer than 60 s.** `ChunkEvents` (max 60 s) gives chunk 2 `offset=60`. `ExtractWordsFromAudio` then computes `start += audio_event.start + audio_event.offset`, which shifts that chunk's words by +120 s. Every chunk also receives the *full* transcript, so words are duplicated (a 119 s clip gives 239 rows instead of 120). Text features are *summed*, so the text input doubles. Our injected `.tsv` goes through the same loop. | PR #29, PR #81; `eventstransforms.py` l.188-205 (verified) | Open, unmerged | **CRITICAL for T2** (any clip > 60 s); NONE for T1 (58 s = 1 chunk) |
| 2 | **Discontinuity at the 60 s chunk boundary.** Audio is z-scored per chunk (neuralset `audio.py` l.68-72). The bidirectional w2v-BERT context ends at the chunk edge (paper §5.2). V-JEPA frames are clamped with `max(0, t−t2)` (`video.py` l.290). | Code, paper | Inferred from code; check in P0 | MAJOR (T2) |
| 3 | **The HF revision is not enforced.** `from_pretrained` has no `revision` argument and calls `hf_hub_download(repo_id, …)`, which fetches `main` (`demo_utils.py` l.200-203). The backbones also load without a revision (neuralset `text.py` l.337, `audio.py` l.485). | Code | Verified | MAJOR |
| 4 | The config is loaded with `yaml.UnsafeLoader` (`demo_utils.py` l.205). | PR #59 | Open | MINOR |
| 5 | **exca/neuralset import breakage.** exca 0.5.26 moved `NoValue`, which breaks the import. Later neuralset releases drop `AddText`. | #65, #69, PR #67 | Fixed in our pin (`38b3db0`, `exca==0.5.20`) | NONE if the lock holds |
| 6 | **WhisperX call.** `uvx whisperx` runs an unpinned version. `float16` is hard-coded, so it fails on CPU. `--language en` is hard-coded. | PRs #20, #22, #58; `eventstransforms.py` l.108-123 | Open | MINOR (P2b already bypasses this call); English-only is a hard constraint |
| 7 | **Silent or speechless video.** Prediction still runs: with no words, text is zero-filled; only `plot_stimuli` crashes. A video with no audio track gets no Audio event, so audio is zero-filled as well (`transforms/audio.py` l.44-48). A *silent track* is different: it is not zero-filled, and per-chunk z-scoring (`1e-8 + std`) amplifies its noise floor to unit variance. | #46, PR #47; code | Plot bug open | MAJOR |
| 8 | **Speech rate scales the text input.** `text_feature.aggregation: sum` adds up the words in each 0.5 s bin. | Config; paper §5.2 | By design | MAJOR (confound for H2 and M1) |
| 9 | **V-JEPA patch tokens are mean-pooled.** The authors "expect [this] to deteriorate encoding performance in low-level visual areas" (retinotopic cortex). | Paper §5.2 | By design | MAJOR (risk that the P4b(a) V1–V3 motion control fails, triggering a STOP) |
| 10 | **HCP medial-wall pseudo-ROI.** The annot contains `???`: 868 left-hemisphere and 874 right-hemisphere fs5 vertices (checked on the local `?h.HCPMMP1.annot`). `get_hcp_labels` strips 2 characters and keeps the label as `"?"`, so `summarize_by_roi` and `get_topk_rois` can rank the medial wall as a region. | `utils.py` l.213-247, 309-318 | Vertex counts verified; the `"?"` name assumes MNE's naming | MAJOR (P9 tables) |
| 11 | `get_topk_rois(hemi="both")` raises IndexError, because `np.array(dict_keys)` is 0-d. | PR #30; `utils.py` l.316-318 | Open | MINOR |
| 12 | **A subcortical checkpoint exists:** `facebook/tribev2-subcortical` (sha `214a5d9`, 2026-05-13, cc-by-nc-4.0). The maintainer closed #23 on 2026-05-21. Issue #79 is out of date; `tribe_requirements.md` §3 was corrected in v2.4 G-D032 (D-034). Per-subject heads are still unreleased (#62, HF #10). Use is DEFERRED (ENH-003). | HF API; #23 | Released | MINOR |
| 13 | **R_group needs the cohort-average target.** With it, LPP gives 0.2125, which reproduces the paper; per-subject targets give 0.053. The same issue reports: lag peak at 0 s; feature widths 1408/3072 (the paper says 1280/2048); an error at `pl_module.py:114` in average-subject eval; nilearn `filter=None`; missing checkpoint metadata; unreleased meshes. | #78 | Reporter-resolved; the side bugs are open | MINOR |
| 14 | Preprocessing of the test datasets is undocumented (fMRIPrep options, detrending). No maintainer reply. | #15 | Open | MINOR |
| 15 | The first 4 s of video clamp to frame 0. Combined with the 5 s offset, the early TRs are degenerate. | `video.py` l.290 | Verified | MINOR (supports W ≥ 5) |
| 16 | OOM at 14.56 GiB; the failing stage is not stated. | #28 | Open | MINOR |
| 17 | #5/#7, PR #1, PR #44, #50/#51; also Windows #10, ZeroGPU #24, py3.10 #2 (fixed `fb1eac6`). | Issues and PRs | Open | NONE. The config has `temporal_smoothing: null`, `extractor_aggregation: cat` and `temporal_dropout: 0.0`; #44 affects training only. |
| 18 | **Licence.** HF #2 corrected the card's licence from cc-by-4.0 to cc-by-nc-4.0 on 2026-03-27. Commercial inquiries (#8, #17, #25, #45, #49, #66, #82) have no public answer. #48 is closed. | GitHub, HF | — | NONE (NC stands) |

Searched, nothing official: fp16 nondeterminism, hemisphere ordering, output scaling beyond §5.8 z-score/detrend, letterbox, short/static clips, cache staleness (code-derived only).

## Implications for v2.2 / ROADMAP

1. **P2b/P4, T2 (findings #1, #2).** For clips longer than 60 s, either:
   - insert our own absolute-time `Word` events into `df` (the word step skips itself when words are present, `eventstransforms.py` l.162-164); or
   - vendor PR #81 together with its test.

   Add tests that assert:
   - every `Word.start` is at most the clip duration;
   - the `Word` row count equals the `.tsv` row count;
   - there are no duplicate (text, start) pairs.

   T2 must exclude ±5 TRs around 60 s and 100 s, or treat those TRs with a covariate.
2. **P0 pins (#3).**
   - Run `snapshot_download(revision="f894e78…")` and pass the local directory.
   - Pre-download the three backbones at recorded revisions.
   - Set `HF_HUB_OFFLINE=1` during inference and log every sha.
   - Add a test that no network fetch happens during `predict`.
3. **P2/P3 QC (#7).**
   - Log `has_audio_track`, `n_words` and `speech_fraction`.
   - Exclude videos that have no audio track or fewer than 20 words in W. The threshold is fixed and label-free.
   - Apply identical silence trimming to every video.
4. **P3 M0 (#8).**
   - Add words/s and speech fraction over W.
   - Both are always in Q(M0): linearly, squared, and their product (D-034, D-037; v2.5 C3).
   - Report the correlation between the H2 composite and words/s.
5. **P0/P4b (#9).**
   - Dry-run P4b(a)–(c) on the reference clips before the lock.
   - If the V1–V3 control is weak, settle the matter through DECISIONS before P6. Never tune it afterwards.
6. **P5/P9 (#10, #11).**
   - Drop `?` and `???`.
   - Build the medial-wall mask as the union of the Schaefer medial wall, HCP `???` and Destrieux `Medial_wall` (993 LH + 987 RH vertices; D-034).
   - Write our own top-k code instead of using `get_topk_rois`.
   - The union removes > 40% of 7 Schaefer parcels; peak tables disclose `n_vertices` and `mw_removed_frac` and flag them (`mw_shrunk`; config `localize.mw_shrunk_parcels`, v2.5 C3):

     | Parcel | Vertices before → after |
     |---|---|
     | RH_Default_PFCdPFCm_6 | 37 → 14 |
     | RH_Cont_Cing_1 | 52 → 23 |
     | LH_Default_pCunPCC_4 | 38 → 17 |
     | RH_Cont_Cing_2 | 35 → 16 |
     | RH_Default_pCunPCC_2 | 22 → 11 |
     | LH_Cont_Cing_1 | 43 → 22 |
     | LH_Cont_Cing_2 | 44 → 23 |

     HCP `L_H` (hippocampus) drops from 81 to 0 vertices, as expected.
7. **P9 (#12).** The limitation becomes: "cortical model only; a subcortical checkpoint exists but is not used" (ENH-003 deferred). `tribe_requirements.md` §3 has been updated (v2.4 G-D032).
8. **P4b reliability mask (#13, #14).** Correlate with the group mean (R_group), and use `predict()` rather than `TribeExperiment` test mode.

## Atlases on fsaverage5

| Resource | How to get it | Names / peaks |
|---|---|---|
| HCP-MMP1 (180 parcels per hemisphere) | `tribev2.utils.get_hcp_labels(mesh="fsaverage5", hemi=…)`, which uses mne `fetch_hcp_mmp_parcellation(accept=True)`. `combine=True` gives the coarse areas. | Short names (`STSva`, `45`). Full names: Glasser 2016 Supplementary Neuroanatomical Results Table 1 (third-party CSVs unverified). Drop `???`. |
| Schaefer-400, 7 or 17 networks | CBIG `…/FreeSurfer5.3/fsaverage5/label/?h.Schaefer2018_400Parcels_7Networks_order.annot`, read with `nibabel.freesurfer.read_annot` | Names look like `7Networks_LH_Default_PFC_3`: the network is the 3rd field and the subregion the 4th |
| Yeo-7/17 | Derive from the Schaefer names, or CBIG `Yeo2011_7Networks_N1000.split_components.annot` (fs5) | Vis, SomMot, DorsAttn, SalVentAttn, Limbic, Cont, Default |
| Destrieux | `nilearn.datasets.fetch_atlas_surf_destrieux()` (native fs5; label 0 `Unknown` is empty; the medial wall is `L/R Medial_wall`, folded into the union mask and never reported) | Anatomical names; used only for labelling |
| Any fsaverage annot | Take the first 10,242 vertices per hemisphere; right-hemisphere indices are +10,242 | — |

**Peak table — SUPERSEDED** (v2.4 G-D032; v2.5 C3). The recipe below (top k per hemisphere, peak-vertex labels) is kept for the record only and must not be implemented. The binding specification is `docs/prompts/v2.md` §1 "Activation localisation outputs" (`yct.interpret.localize.peak_table`): top k overall on the T1 spatially standardised W-averaged map, best-overlap HCP-MMP area with overlap fraction, company-cluster BCa CIs, stability, BH-FDR q (difference map), unreliable and medial-wall-shrinkage columns, fixed caption.

~~nilearn's `get_clusters_table` is volumetric only, so we build the table ourselves: (1) map averaged over W, medial wall masked; (2) per-parcel means with `np.bincount`; (3) top k per hemisphere with the HCP name, Schaefer network and Destrieux label of the peak vertex; (4) descriptive only.~~

`neuromaps` support for fsaverage "10k" in spin tests is UNVERIFIED here.
