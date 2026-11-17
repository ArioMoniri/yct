# G-D032 — Neuroscientist review (TRIBE v2 + surface atlases)

Reviewed at 529652d (HEAD aaf6cd3 differs only in the curation log). I did not read `data/sealed/`.

**Vote: FIX.** The atlas foundations are correct. Six defects must be fixed before P6. None is a STOP.

## Verified (18 tests pass)
- All atlases are (20484,), LH then RH.
- **Schaefer-400.** 400 parcels. Ids 1..200 are all `_LH_` and ids 201..400 are all `_RH_`. The medial wall (id 0) has 870 LH and 873 RH vertices.
- **Yeo-7.** Deriving it from the Schaefer names works.
- **HCP-MMP1.**
  - The raw annot has 163,842 vertices per hemisphere and 181 names; id 0 is `???`.
  - The first-10,242 truncation is valid (the meshes are nested). It gives `???` = 868 LH and 874 RH, which matches the known-issues doc.
  - There is no hemisphere cross-labelling.
  - `???` is the background, so BUG-004 is handled.
- **Four-view plot.** I rendered a synthetic map. All four views appear (lateral, medial, ventral, dorsal), and the medial wall is never coloured.
- **Confound crop geometry.** Frames are resized so the short edge is 292, then cropped to the central 256 (`media.py:97-114`, `confounds/core.py:151-155`). `motion_energy_crop` is computed inside the crop.

## Defects
**D1. Destrieux medial wall** (`atlas.py:195-198`, `localize.py:35-38`).
- Background is id 0 = `Unknown`, which has 0 vertices.
- `L/R Medial_wall` (ids 42/117, about 885 vertices per hemisphere) counts as a real label, so it can be reported as a parcel's anatomy.
- **Fix:** remap ids 42 and 117 to 0. Add a test that `Medial_wall` is not in `names[1:]`.

**D2. The medial-wall mask is Schaefer-only** (`atlas.py:201-204`).
- tribe_known_issues implication 6 mandates the union of Schaefer MW and HCP `???`.
- The two masks disagree on 463 vertices.
- 8 parcels are 29–62% HCP `???`:
  - `Cont_Cing_1/2` (both hemispheres);
  - `Default_pCunPCC_4` (LH) and `_2` (RH);
  - `RH_Default_PFCdPFCm_6`;
  - `LH_Default_PFC_12`.
- These parcels enter H1/M1.
- **Fix:** before P6, a DECISIONS entry choosing union or Schaefer-only (with the 8 parcels listed). Apply the chosen mask identically in `spatial_standardize`, `peak_table` and the plots, and add a test for it.

**D3. Weak HCP labels** (`localize.py:35-42`).
- Best-overlap fraction: median 0.54, minimum 0.22. 15 parcels are below 0.30.
- v2.md:101 says "nearest HCP-MMP area", which the code does not compute.
- **Fix:**
  - Amend the text to "best-overlap HCP area (fraction)".
  - Print the fraction.
  - Add the second-best area when the fraction is below 0.5.

**D4. Unreliable vertices are greyed, not hatched as the protocol requires** (v2.md:102 vs `localize.py:11,123`).
- In the render, greyed vertices appear near-white. In `RdBu_r` near-white means ≈0, so they are confusable with null effects; only a thin outline separates them.
- **Fix:** add a real hatch/stipple overlay, or a fixed mid-grey outside the colormap with a legend plus a DECISIONS amendment. Add a test on the face colours.

**D5. The P4b face regressor is not computed inside the crop** (`confounds/core.py:194-218`).
- v2.md:352 requires every regressor inside the 256² crop.
- `face_present_frac` and `face_area_frac` are full-frame.
- **Fix:**
  - Add `face_area_crop_frac` (inside area / 256²) and `face_present_crop`.
  - Name `face_area_crop_frac` as the FFC regressor.
  - Add a test with an off-centre synthetic face.

**D6. T3 statistics are full-frame** (`photometric.py:26-70`).
- V-JEPA2 sees only the crop, which excludes about 51% of a 16:9 frame's width.
- So the targets (Y 0.45, RMS contrast 0.20) are met on pixels TRIBE never sees.
- **Fix:**
  - Keep one global transform per video, but estimate the statistics on the 292→256 crop (reuse `_crop_box`).
  - Report after-stats both in the crop and over the full frame.
  - Pre-specify that videos with `clip_frac > max_clip_frac` are *excluded* from T3, not just flagged.
- Minor: untagged files decode as BT.601 while the luma weights are BT.709; tag the colorspace.

**D7 (doc).** `tribe_requirements.md:86` still says the subcortical checkpoint is "not released".

## T3 physiology
- V-JEPA2 uses fixed ImageNet normalisation, so per-video exposure and colour grade do reach the features. T3 is therefore a meaningful check, mainly for early-visual and colour-sensitive ventral predictions.
- Gray-world correction distorts scenes dominated by brand colours. Report the distribution of channel gains, for example the share of videos with any gain above 1.3.

## ENH-002 (P4b dry-run): support
- Mean-pooled tokens make V1–V3 motion the weakest control.
- Dry-run (a)–(d) on the reference clips only.
- If the control is weak, the only remedy is a pre-lock DECISIONS entry. It may:
  - replace V1–V3 with MT+ (MT ∪ MST ∪ FST ∪ V4t); or
  - add scene-cut rate as a covariate.
- Fix the ROI id lists (FFC, PH, A4∪A5, V1–V3) in config, with tests. Searched src/ for FFC, V1_ROI, A4 and PH: found none.

## ENH-003 (subcortical): GO as EXPLORATORY, if all of these hold
1. Pin `facebook/tribev2-subcortical@214a5d9` with the revision enforced, run offline, and record the sha256 (issue #3).
2. Pre-specify the bilateral structures before P6: amygdala, NAcc, caudate, putamen, thalamus, hippocampus. Pallidum and brainstem are excluded for low SNR.
3. Interpret a structure only if its reliability (published or on the reference clips) exceeds a threshold fixed in advance. Otherwise report it as "not interpretable".
4. Keep it separate from the cortical model: never in M1 or H4. Apply BH-FDR within the subcortical family, adjust for M0, and report estimates with CIs.
5. No reverse inference: "NAcc = reward" is forbidden. P9 states: cortical primary model; subcortical is an exploratory, separate checkpoint.
6. Budget the second inference pass (cc-by-nc-4.0).
