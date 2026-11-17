# G-D032 cycle 3 — Neuroscientist (fresh context)

I reviewed at HEAD 2a4ef09, which equals 31235e6 plus the DECISIONS D-051/052 lines. I did not read `data/sealed/`.

**Verdict: FIX (narrow).** The atlases, ROIs, mask, render and peak table are verified. Two items stay open, and one commit with tests closes both:
- N4 (colour matrix) for the P2/T1 path;
- the source of the unreliable mask.

## Independent checks
- **Raw annots** (own nibabel code, first 10,242 vertices, no repo loaders):
  - Union medial wall: LH 993 / RH 987.
  - Controls ROIs, post-mask: FFC 104, PH 113, A4∪A5 223, V1–V3 1,148, MT+ 168. These match config.yaml:261-267.
  - All ROIs are bilateral and none touches the medial wall.
- **Synthetic `plot_four_views` at dpi 150:**
  - The medial wall shows as grey.
  - Zeros take the colormap centre.
  - The green/yellow checker is legible in the lateral, medial and ventral views, and the legend is present.
- **Tests:** 40 targeted tests pass locally.

## Cycle-2 required changes
| Item | Status | Evidence |
|---|---|---|
| N1 stipple + raster test | FIXED | localize.py:447-468; config.yaml:227-229; test_localize_render_c3.py:30-63; my render |
| N2 mask, not threshold | FIXED | localize.py:507; test_localize_render_c3.py:66-84 |
| N3 shrinkage disclosed | FIXED | localize.py:376, 394-396; config.yaml:230-238; tribe_known_issues.md:80-86 |
| N4 BT.601/709 | **NOT FIXED (partial)** | T3 is fixed (photometric.py:14-18, 62-78). The P2 output, which is the T1 input, is still untagged with no matrix conversion (normalize/core.py:389, 245-257). There is no DECISIONS deferral. |
| N5 docs + ROI ticket | FIXED | tribe_known_issues.md:34, 89; config.yaml:257-298 |

## New defects
**G1 (major). T1 and T3 differ in colour matrix.**
- I ran ffmpeg 6.1 with the P2 chain. The output inherits the source tag:
  - untagged → `unknown`;
  - smpte170m → smpte170m;
  - bt709 → bt709.
- The T3 statistics force a BT.709 decode, and the T3 output is tagged bt709.
- Consequences:
  - For 601 or untagged sources, the T1 crop statistics do not describe what TRIBE decodes.
  - T3 − T1 contains a matrix change on top of the intended transform.
  - The matrix varies by source, and therefore by platform, which is an M0 covariate.

**G2 (major). The "unreliable" mask is undefined.**
- tribe_requirements.md:96 says it "has to be built by us … (to do)".
- No config key or v2.md rule fixes its source or threshold.
- The stipple and the `unreliable_parcel_max_frac` exclusion (localize.py:337-349) therefore act on an unspecified input, which is a researcher degree of freedom.

**G3 (minor). ROI interpretation.**
- PH overlaps Yeo DorsAttn 57% and Vis 43%: it is lateral occipitotemporal, not parahippocampal. Anatomical PPA ≈ PHA1–3 (194 vertices, 92% Vis).
- PH is kept only as the paper's proxy, from a list that is misaligned in the source (tribe_requirements.md:95).
- V4t (the paper's EBA proxy) is part of the MT+ motion fallback (config.yaml:267), so a motion control there partly indexes body content.

## Required changes
1. **G1/N4:**
   - P2 uses `scale=…:out_color_matrix=bt709:out_range=tv`, plus the `-colorspace/-color_primaries/-color_trc bt709 -color_range tv` tags.
   - Add a test that untagged and smpte170m sources come out of P2 as bt709 under ffprobe.
   - The confounds decoders use the same explicit matrix.
2. **G2:**
   - Add a DECISIONS entry plus `localize.unreliable_mask` before any localisation output. Either use paper-figure HCP parcel scores below a fixed threshold, or set it to `none` and drop the stipple.
   - Add a test that the key is set.
3. **G3:**
   - Annotate config.yaml:262 and 267.
   - Add PHA1–3 as a descriptive secondary place check in the ENH-002 dry run.
   - If MT+ is adopted, decide by a DECISIONS entry before the lock whether V4t is excluded.
