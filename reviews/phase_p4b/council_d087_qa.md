# Council D-087 draft (p4b_ref/v2), QA review (4fa86c0, 0b0a44a)

**Verdict: REVISE.** The rule is mechanical, rank-ordered, a priori with respect to v2 outcomes, and within D-071 (h). Five items need fixing before the freeze.
Checks: `pytest tests/test_d087.py tests/test_refclips_qc85.py` 32 passed; `make guards` rc=0 (blinding, test weakening, guard config OK).

**Q1, face slots.** Gating body and place only is the correct reading of the owner's rule for *intact* patches. The D-085 gate is "no face on non-face LOC TRs and all LOC_SCR TRs", and face images must still score face_hit ≥ 0.9, pooled per family. Face detections on intact faces are descriptive. But the draft screens only intact patches. The D-085 gate also covers every scramble TR, including phase scrambles of **face** images (refclips58 L172-173, seeds `item_seed(LOC|LOC_SCR, i, k)`). Joint SHINE re-normalises all 60 patches whenever one image is replaced, so the face scrambles change too and are never screened. The screen must also run YuNet on the rendered scramble and swap patches of all 60 images, using their frozen per-event seeds. A hit replaces the source image. Tell the owner the final reading at the freeze; it is not a change of intent.
**Q2, rebuild.** C3 for v2 means MOT, MOT_STAT, FLASH and GREY_CTRL must be decoded-equal to build 1, with wav and tsv byte-equal. This also fulfils D-071 (g) "MOT/MOT-STAT carried over by manifest sha". LOC and LOC_SCR are new, and as written nothing replaces C3 for them. Add a screen-to-build identity check: the build's post-SHINE patches (`locimg` processed) must be byte-equal to the patches screened in the final round, by per-patch sha in the screen record. LOC audio wav must still match build 1.
**Q3, cost.** Counting the $0.39 against the v2 $75 cap is acceptable. It is strictly conservative, and (h) only forbids sharing the cap, not this tighter count. Disclose it. T-DRV-V2 (`cost_cap_usd` into `guard_launch` and `check_projection`) must land before any GPU launch.

**Other judgements**
- Scramble seeds are a pure function of (family, clip i, event k), so they are not chosen per image and allow no seed shopping. OK. The draft wording "per clip and slot" is right. Keep: a scramble hit never re-draws the seed.
- TALKFACE `max_consumed_face_rank`: the rule is sound (never reuse a face used or screened out for LOC). But with face slots never gated it always equals 492, so it is dead unless the Q1 scramble gate can replace a face. Keep it, with the test that it equals 492 when there is no face replacement.
- Continuation past 20: OK. The cap of 20 extra is a priori, the log is append-only, the dry-audit guard is untouched, and re-running from round 1 is deterministic (tested). `NeedMorePasses` asks for one pass at a time. Batch the request to the number of flags in the round, or state that repeated runs are fine. State that continuation CPU and pod time count against the v2 cap.
- Outcome-blindness: choosing the redesign after the place_14 STOP is exactly what (h) allows (stimuli only; K rules, thresholds and on_fail frozen; `post_hoc: true`). The rule is blind to the v2 screen. One real gap: the 0.681 hit was on the **x264-decoded** patch, while the screen runs on the rendered patch. place_14 may therefore not be flagged, v2 would equal v1, and the run would fail finally. §7 also says "place_14 is not in v2" unconditionally, which contradicts the rule.

**Blocking items**
1. Screen the scramble and swap patches of all 60 images (Q1). Fix the owner's reading in the D-087 text.
2. place_14 handling: either pre-exclude the trigger image a priori (round 0, disclosed), or screen an x264 round trip of each patch with the frozen encoder settings. Make §7 consistent.
3. Add the screen-to-build patch identity check and the per-patch shas to the screen record (Q2). Write C3 for v2 into the frozen text.
4. Pod driver missing: no script wires `locscreen.select` to the real `locimg` patches, SHINE, YuNet, the continuation and the writing of the v2 manifest and screen record. Write it, test it with fakes, and have the council review it before the `refclips_d087` freeze, since every later failure is final.
5. Land T-DRV-V2 (the cost-cap wiring) before any v2 GPU session.

## Re-check (d087_v2.md, c54daf6 + 71bd4b3)

**Verdict: APPROVE**, with one condition added to the freeze plan. Checks: `pytest tests/test_d087.py tests/test_d087_v2.py` 42 passed; `make guards` rc=0.
- B1 scrambles: closed. Every slot's scramble and swap is gated, face slots included (`gate_from_cfg`, `rendered_loc_patches`, pixel-equal to `loc_frames`, tested). Face intact is descriptive, and `face_absent` is recorded, per the owner's ruling.
- B2 place_14: closed by option (a). Round-0 `pre_excluded` is post_hoc, cites STOP_NOTE, and §7 is now consistent.
- B3 identity: closed. Per-slot `patch_sha256` is in the record, the builder checks it before any clip, and the build1 families are compared separately (C3 split).
- B4 driver: written; reviewed here. B5 T-DRV-V2: `campaign_cap` plus the carried $0.39 in `guard_launch` and NAT `check_projection`, tested.
- Two suggestions not adopted (my x264 margin, the biostat compressed-image check): acceptable. Pre-excluding place_14 removes the one known decoded-only hit. Lowering the threshold or adding a screen surface now would be a choice made after the result. §7 discloses the residual risk (screen-pass, decoded-QC-fail, final STOP).
- Driver tested with fakes only: acceptable for the config freeze, not for the first real screen. `main()` (fetch_sources over all pass candidates, the S3 uploads to v2 keys, the scratch vs `--local` paths after a continuation, `t_lic_yunet`) has never run.
  **Condition (freeze plan, between steps 3 and 4):** run one outcome-blind pod smoke before the first real screen, and commit its log:
  - the imports;
  - the YuNet sha check;
  - fetch plus `locimg.patch` and SHINE on the 60 v1 slot images;
  - per-slot `patch_sha` equal to the builder's patches for the same rows;
  - YuNet called once on a synthetic image only. No detector call on the real patches, so round 1 stays unseen.
  - The continuation's output dir must be in `--local`.
