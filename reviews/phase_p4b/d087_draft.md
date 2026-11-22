# D-087 draft: p4b_ref/v2, the single D-071 (h) redesign (localiser image set only)

Status: DRAFT for council review. Nothing here is frozen, nothing is in DECISIONS, and no v2 YuNet, filter
continuation or pod run has happened. Owner decisions (AskUserQuestion 2026-11-23): "Redesign v2" and a v2
cost cap of "$75".

## 0. Trigger and v1 record (reported in full)

- **v1 build 1** (21a2239, `outputs/runs/refclips_v1_nonnat_build1/`): the frozen D-071 (a) Haar QC STOPped
  (LOC 6/20, LOC_SCR 3/20; MOT, MOT_STAT, GREY_CTRL, FLASH passed). The council ruled the QC rule defective,
  not the stimuli.
- **D-085 part 1** (0d01a59 / b4fafdf): the QC was amended (YuNet no-face gate, family-pooled face_hit,
  §1.5 checks), with stimuli unchanged and (h) not consumed.
- **v1 build 2** (pod at f9f71ee, 5a33bb1, `outputs/runs/refclips_v1_d085_build2/`):
  - the rebuild matched build 1 (0 mismatches);
  - all families passed except LOC 19/20: on loc_14, YuNet scored 0.681 on the intact place_14 at TR 28.
  place_14 passed the T-LIC P2 YuNet on the pre-SHINE image; the hit is on the post-SHINE patch. Under
  D-085 this is a STOP to the owner under D-071 (h).
- The v1 report gives both builds, every QC record, the Haar results and this STOP in full. No v1 clip ever
  reached TRIBE; the only P4b GPU spend is NAT session 0 ($0.39).

## 1. What changes, and what stays frozen

**Changes (stimuli only, D-071 (h)):** which 60 images fill the 60 LOC slots (20 per category). The images
come from the same frozen v4 filter logs through the replacement rule in §2. Every clip that shows a slot
image is rebuilt from the new set.

**Unchanged:**
- D-071 (a)–(k): the K rules, thresholds, `on_fail`, design, timings, clip layout and seeds.
- D-075/D-079–D-081: the frozen T-LIC filters, logs, order and snapshot.
- D-085 QC: every rule, threshold and detector, applied once to the v2 rebuild.
- D-084: the NAT continuation.
- D-086: normalisations.
- The SHINE parameters and the `locimg` processing.

**Scrambles and LOC_SCR:** rebuilt from the v2 slot images with the same seed rule. Seeds come from
`refclips58.item_seed(family, i, k)`, which is per clip and slot, not per image, so the seed of every slot
is unchanged.

## 2. The replacement rule (written before any v2 YuNet run)

Code: `src/yct/tribe_run/locscreen.py` (`select`), with tests in `tests/test_d087.py`.

1. **Candidates:** each category's passes in v4 log order. Rank is the 1-based row in
   `data/refstim/image_<cat>_auto_log_v4.jsonl`. This order is never changed by any screen result.
2. **Start:** slot k of each category holds the k-th pass, i.e. the v1 selection.
3. **Each round:**
   - the 60 slot images go through `locimg.patch`;
   - then joint SHINE over all 60, in `loc_categories` order;
   - then the frozen T-LIC YuNet (`refclips_auto.face_detector`, sha-pinned, score ≥ 0.5 = the D-085 qc
     threshold) runs on every post-SHINE 316-px patch, resized as T-LIC (`refclips_qc85.to_bgr640`, long
     side 640).

   Only `screen.categories` gate (draft: body, place). A face patch carries a face by design, so its
   detections are recorded as descriptive and never trigger a replacement (see §8 Q1).
4. **Replacement:** every flagged slot (category order, then slot order) takes the next unused pass of its
   category by rank. A flagged image never returns. A round with no flag ends the loop.
5. **Round cap:** at most 5 rounds. If any slot is still flagged after round 5, that is a final STOP to the
   owner, with no v3.
6. **Running out of passes:** if a category has no unused logged pass, the driver runs the v4 filter
   continuation (§3) to the needed count, then re-runs the loop from round 1. The loop is deterministic, so
   re-running gives the same rounds plus the extension (tested).
   - If the snapshot runs out before the needed pass, the frozen runner STOPs ("passes < need in the full
     snapshot").
   - More than 20 extra passes in one category is a STOP to the owner (`continuation.max_extra_per_category`).
7. **Slot rule:** a replacement takes the flagged image's slot, so its clip, onset and seeds are unchanged.
   Manifest rows keep slot order (`<cat>_<slot>`). The v1 manifests and their frozen sha are never edited:
   v2 writes `image_<cat>_manifest_v2.json`.
8. **Rendered patches only:** the screen runs on rendered patches, never on a built clip frame. It refuses
   until `controls.refclips_d087` is frozen (`require_frozen`).

## 3. The v4 filter continuation (built, not run)

`scripts/refstim_auto_run.py run <model_dir> <scratch> --target <cat>=<n>` continues the same v4 log past
pass 20, under every frozen check (the D-079/D-080/D-081 launch preconditions, the audit and the
append-only log).
- Only the stop count changes, through `effective_need`.
- A target above 20 needs D-087 frozen and at most 20 extra passes.
- A target below 20 is refused.
- No file under the dry-audit code guard (`src/yct/curate/refstim*.py`, the two audit scripts) changed, so
  `check_dry_audit` still holds.

## 4. Clip manifest and TALKFACE

- The overall clip manifest (D-071 (d)) is built from the v2 rebuild and frozen before any upload.
  `refclips_d087_artifacts.image_manifest_v2_sha256` and `screen_record_sha256` are set, then frozen in the
  next commit.
- **TALKFACE:** the face is the first face pass after the highest face rank consumed by the v2 LOC
  selection, whether selected or screened out (`talkface_after: max_consumed_face_rank`). This is
  `refclips_qc85.talkface_face(..., after_rank=...)`, which amends the D-085 "after rank 492" rule (still
  unfrozen part 2). If no face slot is replaced, it equals rank 492, as in D-085.

## 5. Cost cap

- v2 has its own $75 cap (owner), not shared with v1.
- Spend carried: $0.39 (NAT session 0), counted against the v2 cap as a conservative choice.
- The NAT continuation sessions (D-084) and the TALKFACE session count against the v2 cap. The D-084
  `check_projection` uses the $75 figure; wiring `cost_cap_usd` into `guard_launch` is ticket T-DRV-V2.

## 6. After the screen

The flow, with no second amendment at any step:
1. Write the v2 manifests and the screen record (rounds, flags, scores, replacements), and commit them.
2. Freeze the shas.
3. Rebuild once, all non-NAT visual families, on the pod CPU.
4. Run the frozen D-085 QC once.

Any QC failure after that is a final STOP to the owner (`on_fail: stop_owner_final`). The rebuild sha check
against build 1 (C3) does not apply to v2 clips with new images. Clips that show no LOC slot image (MOT,
MOT_STAT, FLASH, GREY_CTRL) must still match build 1, while LOC and LOC_SCR are new. See §8 Q2.

## 7. Disclosure (v1 report and v2 report)

- D-071 (h) is consumed by v2. This is decided after the build-2 result (`post_hoc: true`).
- Every round, flag, score and replacement is reported. The 60 v2 images differ from v1 only in the
  replaced slots.
- place_14 is not in v2; v1 stays in the report.
- The screen threshold equals the D-085 QC threshold. A v2 image can therefore pass the screen and still
  fail the decoded-frame QC through x264 changes; that is a final STOP.

## 8. New keys and freeze plan

**New keys:**
- `controls.refclips_d087`:
  - decision, redesign, consumes_redesign, amends, post_hoc, trigger and changes;
  - cost_cap_usd and spend_carried_usd;
  - screen, continuation and manifests;
  - scrambles, talkface_after, qc and on_fail.
- `controls.refclips_d087_artifacts`: `image_manifest_v2_sha256` and `screen_record_sha256`.

**Freeze plan:**
1. DECISIONS D-087 plus the freeze of `controls.refclips_d087`.
2. Continuation run if needed, then screen, then v2 manifests and screen record.
3. Freeze of the two artifact shas.
4. Rebuild plus QC.

**Open questions for the council:**
- **Q1, face slots:** the rule as presented to the owner says "every post-SHINE patch of all 60 images". Read
  literally, every face would be replaced, since a face patch carries a face by design. The draft screens
  body and place only (`screen.categories`) and records face detections descriptively. The council should
  confirm this reading, and the owner should be told; it is not a change of intent.
- **Q2, rebuild identity:** C3 for v2 means the visual families without slot images must match build 1, and
  the LOC/LOC_SCR clips are new.
- **Q3, cost cap counting:** is counting the NAT session-0 spend against the v2 cap right?
