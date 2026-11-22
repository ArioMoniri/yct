# p4b_ref/v1 non-NAT reference clips: build record and items for the council

The clips were built on the pod (CPU only, `nice 19`, alongside the NAT CPU stage) with `scripts/refclips_build.py` at commit 21a2239. Output: `/work/yct/refclips_v1_nonnat/` on the pod.

## Built

- **Families:** GREY_CTRL 2, FLASH 5, LOC 20, LOC_SCR 20, MOT 16, MOT_STAT 16, so 79 clips in total.
- **Not built:** NAT (comes from the T-NAT manifest), and SPK, BURST and TALKFACE (see item 1).
- **LOC images:** the 60 frozen manifest images (`image_manifest_sha256`), each sha256-checked against its manifest row. Each is cut to its frozen `crop_box`, converted to BT.709 luma and resized with INTER_AREA to the 316-px patch. SHINE (specMatch → lumMatch, 2 iterations, mean 128 and RMS 32) is then applied to all 60 together, in `src/yct/tribe_run/locimg.py`.
- **QC:** the frozen §1.5 stimulus QC, `refclips58.stimulus_qc`, which uses the real `yct.confounds` code. Results: see "Results".
- **Partial manifest:** `refclips_partial_manifest.json`, with the per-file sha256 of each mp4, wav and tsv, the toolchain, the sources and the builder blob shas. It is marked `partial: true` and lists the missing families. It is NOT the D-071 (d) clip manifest, so nothing was frozen.
- **No upload of clips.** D-071 (d) requires the full clip-manifest sha to be frozen *before* any clip upload, and the full manifest needs NAT. The clips stay on the pod and are bit-exact rebuildable from the commit.

## Items for the council

1. **Speech corpus is not specified anywhere (blocking for SPK / BURST / TALKFACE).**
   - **What the design fixes:** D-071 (a) and design_v2 §1 fix the counts, durations and the engine:
     - SPK: 60 distinct utterances, 2–3 words, 1.0–1.5 s;
     - BURST: 15 utterances, 4–6 s;
     - TALKFACE: 3 utterances, 1–6 s;
     - engine: espeak-ng.
   - **What is missing:** no text, voice or rate is frozen in config or in DECISIONS. Writing the sentences now would be an unreviewed design choice for the families that gate AUD.
   - **Proposal:** a council-reviewed corpus file. It would hold generic, neutral sentences with no YC, startup or pitch vocabulary, balanced as design_v2 asks. It would also set the espeak-ng voice and rate, and give a duration check for every utterance.
   - **Freeze:** the file is frozen as `controls.refclips_artifacts.speech_corpus_sha256`. The builder refuses these families until that key is frozen (tested).
2. **SHINE interpretation (fixed a priori, to be ratified).**
   - **specMatch:** every image keeps its own phase and its own DC term; the target is the mean amplitude spectrum of all 60.
   - **lumMatch:** sets the mean to 128 and the population SD to 32.
   - **Rounding:** each step ends on the uint8 grid (round and clip), as SHINE writes 8-bit images.
   - **Downstream:** `refclips58.loc_frames` renormalises each patch to 128/32 again, which is unchanged.
3. **Crop edge overrun.**
   - **Cause:** the frozen `crop_box` comes from a ≤1600-px Haar pass scaled back up with rounding. On face_05 (3937 × 5400) the side is 3939, 2 px wider than the image.
   - **What T-LIC did:** it sliced with numpy, which silently clips, and then resized to a square.
   - **What the patch does:** it takes exactly the same pixels. The overrun bound is 16 px, set a priori; above it the build stops.
   - **Record:** overruns are listed in the partial manifest under `sources.crop_box_edge_overrun_px`.
4. **BUG-044.**
   - **Upload never happened:** T-LIC finalise wrote `s3_key` into the frozen image manifests but never uploaded the sources.
   - **How the builder recovers:** it takes each source from the pod T-LIC scratch by *content* sha256, then uploads it to the frozen `s3_key`.
   - **Names:** the manifest `file` / `s3_key` names carry the Commons URL query string. Renaming would change the frozen sha, so they are left as they are. The council decides whether that matters.
5. **Toolchain.** The pod's system ffmpeg 6.1.1-3ubuntu5 (libx264 inside) is recorded in the partial manifest. No separate x264 binary is pinned. A CI rebuild is gated on the same toolchain (design_v2 §1).
6. **LOC contact sheet** (`reviews/phase_p4b/loc_contact_sheet_v1.png`).
   - **Content:** one frame per LOC image: the intact image at each LOC event (onset + 0.5 s), decoded from the built mp4. The 60 images are laid out as 20 rows (loc_00–19) by 3 events.
   - **Scope:** it is for the D-079 §5 check that the frozen rules held (B1–B5, F1–F8, P1–P3), nothing else. The images are Commons files under the licences listed in docs/stimuli/LICENSES.md.

## Results: STOP to the council (frozen D-071 (a) stimulus QC; no substitution, no rule change)

The build ran at 21a2239 and exited 1. Records are in `outputs/runs/refclips_v1_nonnat_build1/`: `qc.json`, `STOP_NOTE.md`, and `diag.json` from `scripts/refclips_qc_diag.py`, which is diagnostic only. Because the build stopped, no partial manifest was written.

| family | QC pass |
|---|---|
| GREY_CTRL | 2 / 2 |
| FLASH | 5 / 5 (no QC check defined) |
| MOT | 16 / 16 (event / static motion ratio ≥ 1000, many ∞) |
| MOT_STAT | 16 / 16 |
| LOC | 6 / 20 |
| LOC_SCR | 3 / 20 |

What fails, by the frozen check `face_area_crop_frac == 0` on every non-face LOC TR and every LOC_SCR TR:

- **Haar fires on phase scrambles.** There are 344 of the 380 hit TRs across the 31 failed clips.
  - The hits are mostly whole scramble segments of a few exemplars: place_14 39, body_10 38, face_15 38, place_00 36, place_04 36, place_05 36, place_16 36, body_15 35, body_02 34 and face_07 19 TRs.
  - The other exemplars contribute 1 TR each.
  - The swap scrambles in LOC_SCR events add 13 more.
- **Haar fires on intact body and place images** at video resolution after SHINE. These are 10 TRs in 8 clips:
  - body_01, body_06, body_10, body_15, body_17, body_18 and body_19;
  - place_06, place_14 and place_18.

  At T-LIC these images passed B3 and P2 (YuNet 0.5 and Haar on the pre-SHINE 256-px crop). The video QC instead runs the confounds face detector on the 316-px patch inside the 640×360 frame.
- **face_hit_frac fails once:** loc_00 has face_00 detected on 0 of its face-event TRs, where ≥ 0.9 is needed. Every other face event is detected.

What this means: with this cascade, the frozen zero-tolerance rule cannot be met by phase scrambles of these exemplars. These are false positives of the confounds face detector on noise and on non-face photos. Every possible fix is a design decision that needs a council D- entry. The options are:

- new scramble seeds, which is a seed rule change;
- dropping or replacing exemplars, which is ruled out by "no substitution";
- a QC tolerance;
- a different detector.

Nothing was changed. MOT, MOT_STAT, GREY_CTRL and FLASH passed and can be reused unchanged once LOC is settled. The build is deterministic, bit-exact from the commit.

**Contact sheet** (`loc_contact_sheet_v1.png`): built from the mp4s after the STOP, for the council's D-079 §5 check. Two things to look at there:

- **place_07** shows a large printed logo on a field. P3 (OCR text area < 1%) passed it, so the council should judge whether that counts as text or a logo.
- **body_03** has a printed jacket design.

Nothing was acted on.
