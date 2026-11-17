# G-D032 cycle 2 — Neuroscientist review (fresh context)

Reviewed at b83e6c2. I did not read `data/sealed/`.

**Vote: FIX.** Five of the six cycle-1 neuro defects are fixed. D4 (hatching) is not: the stipple is not legible in the default render.

## Verified independently
- **Medial-wall union (D2).** Counted with nibabel from the raw cached annots (first 10,242 vertices), not via the repo loaders:

  | Mask | LH | RH |
  |---|---|---|
  | Schaefer 0 | 870 | 873 |
  | HCP `???` | 868 | 874 |
  | Destrieux `Unknown` ∪ `Medial_wall` | 888 | 881 |
  | **Union** | **993** | **987** |

  `load_all()` gives the same mask, and every atlas's background equals it. No Schaefer parcel is empty (minimum 11 vertices).
- **Destrieux medial not reportable (D1).** Names go from 151 to 149, with no `*Medial_wall` left. Tested.
- **Crop math (D5, D6).**
  - 640×360 → 520×292, crop x ∈ [132, 388). The test comment says 519/131, which is harmless.
  - Torchvision `Resize(292)` + `CenterCrop(256)` matches to within 1 px.
  - 1920×1080 → source crop 947 px (49.3% of the width).
  - Face boxes are intersected with the crop, and the FFC regressor is `face_area_crop_frac`. Off-centre, centred and edge faces are tested.
  - T3 statistics are on the crop, with before/after stats for the crop and the full frame.
- **Best-overlap (D3).** The `hcp_overlap` and `hcp_mmp_2nd` columns exist (the 2nd-best when < 0.5). v2.md:118 is amended.
- **§3 subcortical (D7).** Corrected.
- **T3 clipping.** I asked for exclusion. The council chose "kept + fragile rule" (D-034), an explicit, reasoned decision, which I accept.

## Defects
**N1 (major; D4 not fixed). The stipple renders as background grey.**
- I rendered a test map with `plot_four_views` at its defaults (dpi 110, 2×4 panels; LH `Vis_1..10` unreliable).
- The unreliable region looks like sulcal-grey medial wall, with sparse dots visible only in the ventral view.
- At 300 dpi with a single view, the stipple is clear.
- Cause: each fsaverage5 face is smaller than a pixel, so the alternating per-face pattern aliases away.
- The test checks `_facecolor3d`, not the raster, so it passes while the figure fails.
- Required:
  - Use a solid out-of-colormap fill (e.g. `#ffd400`) with a hatched outline, or a stipple on vertex clusters; or set dpi ≥ 300 as the asserted default.
  - Add a **raster test** at the default dpi: pattern pixels cover ≥ 50% of the projected unreliable area and differ from medial-wall pixels.

**N2 (minor). Exact zeros are drawn as hidden.**
- `threshold = 1e-6·vmax` renders vertices equal to 0 as background, so they look like medial wall. Parcels set to 0 appeared as grey holes.
- Required: hide vertices with a mask (NaN or alpha), not a threshold.

**N3 (minor). Shrinkage is undisclosed.**
- The union removes 48–62% of 7 parcels:

  | Parcel | Vertices before → after |
  |---|---|
  | RH_Default_PFCdPFCm_6 | 37 → 14 |
  | RH_Cont_Cing_1 | 52 → 23 |
  | LH_Default_pCunPCC_4 | 38 → 17 |
  | RH_Cont_Cing_2 | 35 → 16 |
  | RH_Default_pCunPCC_2 | 22 → 11 |
  | LH_Cont_Cing_1 | 43 → 22 |
  | LH_Cont_Cing_2 | 44 → 23 |

- HCP `L_H` drops from 81 to 0 vertices (hippocampus, which is expected).
- Cycle-1 asked for this list. D-034 omits it.
- Required:
  - Add `n_vertices` (post-mask) and `mw_removed_frac` columns to the peak table.
  - List these parcels in `tribe_known_issues.md`.

**N4 (minor; D6 colorspace, neither fixed nor deferred).**
- `iter_rgb_frames` decodes untagged yuv420p as BT.601, while `luma_weights` are BT.709. The P2 output (`core.py:389`) is untagged.
- Required: tag the P2 output bt709 and decode with `in_color_matrix=bt709`, or record a DECISIONS deferral.

**N5 (doc/ticket).**
- `tribe_known_issues.md` #12 and implication 7 still say §3 is "out of date".
- The cycle-1 ENH-002 request is still open: the P4b ROI id lists (FFC, PH, A4∪A5, V1–V3, MT+) are not in `config.yaml`. Ticket them before the P4b dry run.

## Required for GO
- **N1:** fix plus a raster test.
- **N2, N3:** code changes.
- **N4:** fix or a DECISIONS deferral.
- **N5:** doc edits and the ticket.
