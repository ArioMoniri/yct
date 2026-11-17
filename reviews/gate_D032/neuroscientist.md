# G-D032 — Neuroscientist review (TRIBE v2 + surface atlases)

Reviewed at 529652d. HEAD is aaf6cd3, which differs only in `data/curation/search_log.csv`. I did not open `data/sealed/`.

**Vote: FIX.** The atlas foundations are correct. Six defects in localisation, confounds and T3 need fixing before the P6 lock. None of them is a STOP.

## Verified correct (by running the code on the cached atlases)
- **Atlas loading.** All 4 atlases load with shape (20484,), LH then RH. The 18 atlas and localize tests pass.
- **Schaefer-400.**
  - 400 distinct parcels.
  - LH ids are 1..200 and all named `_LH_`. RH ids are 201..400 and all named `_RH_`.
  - Label 0 is the medial wall: 870 LH and 873 RH vertices.
- **Yeo-7.** The networks derived from the Schaefer names give plausible vertex counts (Default 4177, Limbic 1383, medial wall 1743).
- **HCP-MMP1.**
  - The raw annot has 163,842 vertices per hemisphere and 181 entries, with entry 0 = `???`. There are no −1 labels.
  - Truncating to the first 10,242 vertices gives `???` = 868 LH and 874 RH, which matches tribe_known_issues #10.
  - No `R_` label appears in the LH and no `L_` label in the RH.
  - The truncation is valid because the icosahedral meshes are nested. It samples labels at single points, without majority voting, so parcel boundaries alias. That is acceptable for labelling.
- **BUG-004 (HCP `???`).** `???` is the HCP background (id 0), so `_modal_label` never reports it.
- **Four-view plot.** I rendered a synthetic map (scratch PNG). The plot shows lateral, medial, ventral and dorsal views for each hemisphere. The medial wall shows sulcal grey and is never coloured, even when it carries large values.
- **Confound crop geometry.** Frames are resized so the short edge is 292 (`media.py:97-114`), then cropped to the central 256 (`confounds/core.py:151-155,179`). This matches the V-JEPA2 processor. `motion_energy_crop` is computed inside the crop.

## Defects

**D1. The Destrieux medial wall is not treated as background** (`atlas.py:195-198`, `localize.py:35-38,77`).
- In the a2009s colour table, id 0 is `Unknown`, which covers 0 vertices.
- The medial wall is ids 42 and 117 (`L/R Medial_wall`, about 885 vertices per hemisphere, 31 of them outside the Schaefer medial wall).
- Effect: `destrieux` can report "Medial_wall" as a parcel's anatomy. No parcel does so today, but nothing guards against it.
- **Change:** in `load_destrieux`, map the `Medial_wall` ids to 0 and name label 0 `Medial_Wall`. Add a test that `Medial_wall` never appears in `names[1:]`.

**D2. The medial-wall mask is Schaefer-only, which contradicts tribe_known_issues implication 6 ("union of Schaefer MW and HCP ???")** (`atlas.py:201-204`).
- The two masks disagree on 231 + 232 vertices.
- Eight Schaefer parcels are 29–62% HCP `???`: LH/RH `Cont_Cing_1/2`, `Default_pCunPCC_4/2`, `RH_Default_PFCdPFCm_6` and `LH_Default_PFC_12`. These are Default and Cont parcels, which enter H1 and M1.
- **Change:** record a DECISIONS entry *before P6* choosing between two options, add a test for the chosen mask, and use it identically in `networks.spatial_standardize`, `peak_table` and the plots.
  - (a) the union mask, as the issues doc says; or
  - (b) Schaefer-only, with the rationale and the 8 affected parcels listed.

**D3. HCP "best-overlap" labels are often weak** (`localize.py:35-42`).
- The overlap fraction has median 0.54 and minimum 0.22. 15 parcels are below 0.30, for example `LH_Default_PFC_4` → `L_a24` at 0.22.
- v2.md:101 says "nearest HCP-MMP area". The code computes something else.
- **Change:**
  - Amend v2.md:101 to "best-overlap HCP-MMP area (fraction)".
  - Add the second-best area to the table whenever the overlap is below 0.5.
  - Print the overlap fraction in every report table.
  - Ideally, also report the HCP area of the peak vertex, as the issues doc recommended.

**D4. The plot greys unreliable vertices instead of hatching them; the protocol requires hatching** (v2.md:102 vs `localize.py:11,123`).
- With `RdBu_r`, white-grey means "≈0". The greyed region renders as white, so it is visually confusable with null effects. I confirmed this on the render; only the thin black outline separates the two.
- `bg=-1` also stretches the sulcal normalisation, so the rest of the background renders darker.
- **Change:** either
  - draw a real hatch or stipple (a contour fill), or
  - use a fixed mid-grey for unreliable vertices with a legend entry, and amend v2.md via DECISIONS.

  In either case, add a test that the unreliable vertices' face colours are outside the colormap.

**D5. The P4b face regressor is not available inside the crop** (`confounds/core.py:194-218`).
- v2.md:352 requires *all* regressors inside the central 256×256 crop.
- `face_present_frac` and `face_area_frac` are computed over the full frame. Only `face_area_outside_crop_frac` is crop-aware.
- **Change:**
  - Add `face_area_crop_frac` (inside area / 256²) and `face_present_crop` (any box intersecting the crop by at least 50%).
  - Name `face_area_crop_frac` as the FFC regressor in the P4b spec.
  - Add a test using a synthetic frame with the face off-centre.

**D6. The T3 statistics are computed over the full frame, but V-JEPA2 sees only the crop** (`photometric.py:26-70`).
- The targets (Y 0.45, RMS contrast 0.20) are met over pixels that TRIBE never sees. On 16:9 input, about 51% of the width lies outside the crop.
- For example, a dark speaker on a bright side-wall would stay under-normalised in the crop.
- **Change:**
  - Keep the transform global (one per video), but estimate the mean and contrast on the resized 292 → central 256 region, reusing `_crop_box`.
  - Report the after-stats both inside the crop and over the full frame.
  - Log the per-video distribution of `clip_frac`.
  - Pre-specify that videos with `clip_frac` above `max_clip_frac` are excluded from T3. Flagging them is not enough.
  - Minor: the rgb24 decode uses ffmpeg's default matrix (BT.601 when the file is untagged) while the luma weights are BT.709. Tag the colorspace, or state that the mismatch is negligible.

**D7 (doc).** `tribe_requirements.md:86` still says the subcortical checkpoint is "not released". Update it (ENH-003, known issue #12).

## T3 physiology note
- A single global gain/offset plus gray-world correction preserves within-video dynamics, which is correct.
- V-JEPA2 applies fixed ImageNet normalisation, so per-video exposure and colour grade do reach the features. T3 is therefore a meaningful sensitivity check, mainly for early visual (V1–V4) and for colour-sensitive ventral predictions.
- Gray-world will distort scenes with dominant brand colours. Report the size of the channel gains (for example, how often any gain exceeds 1.3).

## ENH-002 (P4b dry-run)
- I support it. Mean-pooled V-JEPA tokens (#9) make the V1–V3 motion control the weakest of the controls.
- Before the lock, dry-run (a)–(d) on the reference clips only.
- If V1–V3 is weak, the only allowed remedy is a DECISIONS entry, written before any study prediction is inspected. That entry may:
  - replace V1–V3 with the MT+ complex (`MT ∪ MST ∪ FST ∪ V4t`, which is motion-selective and less retinotopy-dependent); or
  - add scene-cut rate as a covariate.
- Hard-code the ROI id lists (FFC, PH, A4∪A5, V1–V3) in config with tests. Today `src/` has none: I searched for FFC, V1_ROI, A4 and PH and found nothing.

## ENH-003 (subcortical checkpoint): GO as EXPLORATORY, with these conditions
1. Pin `facebook/tribev2-subcortical@214a5d9` with an enforced revision, offline (known issue #3), and record its sha256.
2. Pre-specify the bilateral structures before P6: amygdala, nucleus accumbens, caudate, putamen, thalamus and hippocampus. Pallidum and brainstem are excluded because of low SNR and susceptibility.
3. Include a structure only if its published or reference-clip reliability exceeds a threshold fixed beforehand. Otherwise report it as "not interpretable".
4. Report the outputs separately from the cortical model.
   - Never mix them into M1 or H4.
   - Use BH-FDR within the subcortical family, adjust for M0, and give estimates with CIs.
5. No reverse inference ("NAcc = reward/value" is forbidden). P9 keeps "cortical primary model; subcortical exploratory, separate checkpoint".
6. Confirm that the cc-by-nc-4.0 licence holds, and budget a second inference pass.
