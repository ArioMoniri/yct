# G-D032 conditions: Neuroscientist verification (fresh reviewer)

Scope: the two conditions in DECISIONS.md "Final council round" (G-D032 cycle 3), as implemented in D-053a/b at commit 21e3dca. This is not a full re-gate. No sealed data was read. No outcome information was used.

**Verdict: condition (1) MET. Condition (2) MET. Both are closed, so the D-032 additions may be adopted. The advisories below do not block.**

## Condition 1: BT.709 colour matrix on the P2/T1 path — MET

### Code
- `normalize/core.py:99-150` and `:402-405, :459-462, :516` implement the conversion:
  - The T1 encode is `scale=…:in_color_matrix=<src>:in_range=<src>:out_color_matrix=bt709:out_range=tv`.
  - The output is tagged `-colorspace/-color_primaries/-color_trc bt709 -color_range tv`.
- The q480 copy (`:343-377`) keeps bt709/tv explicitly and re-tags.
- `rec["color"]` logs the source tags and the rule. An untagged source is flagged `source_color_untagged`.

### Tests
- `tests/test_normalize_color.py` and `tests/test_reliability_mask.py` pass locally: 15 passed.

### Independent check
- Script: scratchpad `neuro_d032/colcheck.py`. The project's ffmpeg/swscale code is not used to encode or decode.
- Source clips: an 8-patch RGB chart (saturated R/G/B/Y/C/M, mid-grey, skin tone) was built in numpy as YUV using the explicit BT.601 or BT.709 equations. It was encoded losslessly (x264 `-qp 0`) with the given tags.
- Each clip went through `normalize_video`.
- Decode: the output was read as raw yuv420p (no ffmpeg matrix step) and converted to RGB with my own BT.709/tv equations. Each patch was then compared with the true RGB.

| source (tag / bytes / size) | rule → in | T1 and q480 tags | max \|ΔRGB\| (8-bit) read as 709 | same output read as 601 |
|---|---|---|---|---|
| smpte170m / 601 / 640×360 | tagged → smpte170m | bt709/bt709/bt709/tv | 4.11 | 24.0 |
| bt470bg / 601 / SD | tagged → bt470 | bt709/…/tv | 4.11 | 24.0 |
| bt709 / 709 / SD | tagged → bt709 | bt709/…/tv | 1.56 (= source quantisation) | 23.7 |
| untagged / 601 / 640×360 | untagged_sd → smpte170m (flagged) | bt709/…/tv | 4.11 | 24.0 |
| untagged / 709 / 1280×720 | untagged_hd → bt709 (flagged) | bt709/…/tv | 1.56 | 23.7 |
| untagged / 709 / 720×1280 portrait | untagged_hd → bt709 | bt709/…/tv | 1.56 | 23.7 |
| untagged / 601 / 480×854 portrait | untagged_sd → smpte170m | bt709/…/tv | 4.11 | 24.0 |
| smpte170m / 601 **pc range** | tagged → smpte170m/pc | bt709/…/tv | 2.93 | 22.5 |
| bt709 / 709 / 1280×720 | tagged → bt709 | bt709/…/tv | 1.56 | 23.7 |

What the table shows:
- The matrix is genuinely converted, not just relabelled. A BT.601 read of the output is about 6 times worse.
- Full range is compressed to tv range (output Y spans 70–181 for patches that started at 71–180).
- Both outputs (T1 and q480) carry bt709/tv tags in every case.
- A bt709 source passes through bit-for-bit, so its error is only the source quantisation.

### Decoders
- The confounds decoder (`media.iter_gray_frames`, `media.py:97-119`) uses an explicit `in_color_matrix=bt709:in_range=tv`. For gray output only the Y plane and range matter, and both are explicit.
- The photometric/T3 decoder and encoder (`photometric.py:62-78, 172-175`) are hard-wired to bt709/tv and raise an error on any other value.
- No other decoder of T1 exists in `src/yct` (no decord, cv2 or torchvision.io).

### Untagged rule
- An untagged source is treated as HD (bt709) if its long side is ≥ 1280 px or its short side is > 576 px. Otherwise it is treated as SD (smpte170m).
- This follows the usual decoder convention, and it handles portrait video correctly.
- The range defaults to tv. An unsupported tag falls back to the same rule and is labelled `unsupported_tag_*`.
- The rule is sensible and it is logged.

### Advisories (non-blocking)
- **A1. Small systematic bias on converted (601) sources.** The swscale default path gives a mean ΔRGB of −2.2 and a maximum of 4.1 code values. Mid-grey comes out with Y = 125 against an ideal 125.9, which suggests truncation in the RGB intermediate.
  - Fix: add `accurate_rnd+full_chroma_int` to the T1 `flags=` (currently `lanczos`). On the same clip this gives mean +0.35 and max 2.3.
  - Why it matters: the bias is about 1% of range, but it is correlated with source type (SD/BT.601 sources only). Luminance is already a modelled confound, so this is not blocking. Fix it before wave-1 normalisation if convenient. The T1 hash fixtures would change.
- **A2. HDR sources.** Only the matrix and range are mapped. `curate/download.py:53` uses `bv*+ba/b`, and yt-dlp's default sort can pick an HDR (bt2020nc + PQ/HLG) format when one exists, for example for phone-shot HLG uploads.
  - What would happen: such a stream would get a bt2020→bt709 matrix change with no transfer or tone mapping. Its colours would be wrong, and it would only be logged, not flagged.
  - Fix: either force SDR at download (`-S hdr:SDR` or a vcodec/dynamic-range filter), or flag/exclude any source whose `src_color_transfer` is `smpte2084` or `arib-std-b67`, or whose primaries are `bt2020`.
  - This goes beyond the condition as worded, and is cheap.

## Condition 2: unreliable-vertex mask — MET

### Source documented and fixed
The mask is documented in three places:
- config.yaml:252-266 `localize.reliability_mask`: source `susceptibility_dropout_hcp_mmp1`, the rule, the areas, `n_vertices` 732, and the sha256.
- D-053b.
- docs/tribe_requirements.md:97, which explains why per-vertex TRIBE reliability (option a) and paper-figure scores (option b) are unavailable before the lock.

The mask is label-free and fixed before any localisation output.

### Independent resolution
- Method: my own nibabel code on `~/.cache/yct/atlases`, taking the first 10,242 vertices per hemisphere. The union medial wall (Schaefer 0 ∪ HCP `???` ∪ Destrieux background/Medial_wall) came out at 1,980 vertices.
- The bilateral HCP OFC, pOFC, 11l, 13l, TGd and TGv minus the medial wall give **732 vertices (354 LH / 378 RH)**.
- The sha256 of the sorted `<i4` ids is **d54dcc19…6a012**, identical to the config value.
- The atlas files' sha256 match `atlases.hcp_mmp1` (lh d4da6346…, rh 744eff4e…).
- Per-area counts (L/R):

  | area | L | R | lost to medial wall |
  |---|---|---|---|
  | OFC | 73 | 83 | — |
  | pOFC | 35 | 45 | 5 RH vertices |
  | 11l | 43 | 58 | — |
  | 13l | 50 | 34 | — |
  | TGd | 111 | 112 | — |
  | TGv | 42 | 46 | — |

### Default use
- `peak_table`, `render_four_views` and `plot_four_views` default to `unreliable="config"` (localize.py:374-375, 529-530, 602-603).
- `attrs['unreliable_mask']` records the source and the hash prefix.
- No production caller passes `unreliable=None`.
- `reliability_mask` fails on count or hash drift, and on missing areas (it never silently returns an empty mask).
- I reproduced the 16 Schaefer parcels excluded at `unreliable_parcel_max_frac` 0.5: the Limbic OFC and TempPole parcels, LH Cont_OFC_1 and RH Cont_PFCl_1. Ten further parcels are partly masked and are still ranked.

### Scientific appropriateness
The set is a reasonable, conservative core of gradient-echo susceptibility dropout:
- orbitofrontal, from air–tissue interfaces at the frontal sinus and orbits;
- the temporal pole, near the petrous bone and sphenoid sinus.

It does not touch the H2 composite or the control ROIs, and a test enforces this.

### Advisories (non-blocking; any change is label-free and pre-lock, and needs a DECISIONS entry)
- **B1. Omissions in ventral anterior temporal cortex.** These areas are commonly dropout-affected and sit adjacent to TGv/TGd and the sphenoid/petrous region, but are not masked:
  - TF (83/86 vertices)
  - TE2a (74/81)
  - PeEc (77/60)
  - EC (33/27)

  The same applies to ventromedial and polar prefrontal areas: 10r, 10v, 25, s32 and 10pp (on average about 20–45 vertices per hemisphere each).
  - Recommendation: either add TF, TE2a, PeEc and EC, or state in the P9 limitations that ventral anterior temporal and vmPFC peaks are reported unmasked and are dropout-prone.
  - If this is not resolved, a peak in TF/TE2a/PeEc should carry a dropout caveat in the text.
- **B2. Anatomical dropout is not the same as model predictability.** The mask is a proxy for where TRIBE's training targets were degraded. It does not capture regions with low TRIBE encoding accuracy for other reasons. The paper reports per-parcel scores only as figures (tribe_requirements §4), and its accuracy is lowest outside sensory and language cortex, i.e. in prefrontal and limbic regions.
  - Recommendation: the legend currently says "unreliable vertices". It should say "susceptibility-dropout proxy (anatomical), not a measured reliability map".
  - Keep option (a) as the post-P4 exploratory replacement, as documented.
- **B3. Scope note.** The mask applies to the localisation outputs only. The H1 Limbic network score is still computed over this dropout-prone cortex. That is acceptable, because H1 is pre-registered at the network level, but the P9 text should say so.
