# Council D-087 draft: biostat (reviewed d087_draft.md, 4fa86c0, 0b0a44a; build-2 run dir only)

**Verdict: REVISE.** The rule is mechanical, order-invariant, a priori capped and tested, and fits within D-071 (h). Five items must be fixed before the freeze.

**Q1 (face slots):** Excluding face from the gate is the correct reading. The D-085 no-face gate never applies to intact face TRs, and gating faces on "a face is detected" would replace all 20 by construction. But the owner was told "all 60", so this is a wording change the owner must confirm before the freeze (blocking 1), not only be informed of. Face scores stay descriptive. Also record, descriptively, the faces with no YuNet hit post-SHINE: the pooled face_hit_frac ≥ 0.9 can still fail, and that would be a final STOP.
**Q2 (rebuild check):** For v2, C3 should be two checks:
- (i) MOT, MOT_STAT, FLASH and GREY_CTRL must be decoded-equal to build 1 (byte-equal wav/tsv). This matches D-071 (g): v2 "carries MOT and MOT-STAT over unchanged, by manifest sha".
- (ii) LOC and LOC_SCR are new. Their intact rendered patches must equal the sha256 of each post-SHINE patch, written in the screen record (screen→build identity).

Without (ii), the build is not tied to what was screened. Any mismatch is a final STOP. §7's "differ from v1 only in the replaced slots" holds for image identities only: joint SHINE changes the pixels of all 60 patches whenever one slot changes. Fix the wording.
**Q3 ($0.39):** Counting it against the v2 cap is acceptable: it is conservative and leaves less headroom. Report it in both the v1 and v2 ledgers, labelled as one spend, so the two totals are never summed as $0.78. Wiring `cost_cap_usd` into `guard_launch` (T-DRV-V2) blocks any GPU launch, not the freeze.

**Other points**
- Per-slot seeds: correct. The seed is a design attribute of the slot (clip, onset, k), so keeping it preserves the frozen design, and the scramble content follows the new image. No issue.
- TALKFACE after the max consumed face rank: sound, because it can never reuse a face that was screened or used. With face ungated it reduces to rank 492. Add a test that the v1 selection gives max_consumed_rank[face] == 492, so the D-085 equality is checked rather than assumed.
- Continuation past 20: the frozen filters, order and append-only log are unchanged, and the +20 cap is a priori. Fine. But neither the cap STOP nor snapshot exhaustion is declared *final*. The owner was told "any later failure = final STOP", so declare both final with no v3 (blocking 5).
- Outcome-blindness: within (h). (h) is by definition a post-failure redesign, limited to stimuli. No TRIBE output exists, the rule applies uniformly to all 60 in a frozen order, and it uses the frozen QC detector and threshold. `post_hoc: true` is disclosed. Selecting on the QC detector is legitimate here, because the QC protects the construct (no face in non-face images) and is not an outcome.
- **Surface gap (blocking 2):** the place_14 hit (0.681) was on the *decoded* x264 patch. It passed pre-SHINE, and nothing shows that it scores ≥ 0.5 on the rendered post-SHINE patch. As drafted, place_14 may survive the screen, and v2 would then STOP again, finally, at the same TR. §7's "place_14 is not in v2" is therefore unsupported.
  - Fix: also gate on an x264 round-trip of each post-SHINE patch, using the frozen encoder settings and the clip geometry. This screens the same image and is not a built clip frame. Alternatively, state a priori that place_14 stays if it is not flagged.
  - Either way, tell the owner.
- LOC_SCR and the scrambles in LOC are gated in QC but not screened. Phase scrambles can be computed before the build from the patch and the slot seed, so record their YuNet scores descriptively as a forecast. Do not gate on them without the owner's consent.
- **Missing pod driver (blocking 3):** `select` takes `patch_of`, `shine_fn` and `yunet` as callables, so the result depends on wiring that is not yet written. That wiring covers the locimg/SHINE parameters, the YuNet sha check, the NeedMorePasses → continuation → rerun loop, and writing the manifests and screen record with per-patch shas.
  - This is a one-shot run, so wiring errors are unrecoverable.
  - Commit and test the driver before the freeze, with an integration test on synthetic images.
  - Run it on the pod, in the build environment, and record the cv2/ffmpeg versions.

**Blocking items:**
1. Owner confirms Q1 (face excluded).
2. Close the surface gap: an x264 round-trip gate, or an a priori statement about place_14, with §7 fixed.
3. Pod driver plus integration test, before the freeze.
4. C3 split into (i) and (ii), using the per-patch shas in the screen record.
5. The continuation and exhaustion STOPs declared final.
