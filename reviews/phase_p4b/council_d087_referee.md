# Council D-087 draft (p4b_ref/v2): referee review

Verdict: **REVISE**. The rule is sound and within D-071 (h). Freezing is blocked by the missing driver and by two gaps in the text.
I read: d087_draft.md, 4fa86c0, 0b0a44a, locscreen.py, refclips58 (seeds), the v4 log pass counts, and DECISIONS D-071 (h) and D-085. I read nothing sealed.

**Q1 (screen body and place only):** this is correct. D-085 QC gates "no face" only on non-face LOC TRs and on all LOC_SCR TRs, so it never gates an intact face TR. The screen exists to pre-empt that QC on intact patches. The literal reading would replace all 20 faces and break the face category, which cannot have been the intent. Still, it departs from the owner's words, so the owner must confirm it, on record, before the freeze (B3).
**Q2 (rebuild check):** MOT, MOT_STAT, FLASH and GREY_CTRL must match build 1, both byte and decoded (C3 as frozen). LOC and LOC_SCR are new clips, and joint SHINE changes all 60 patches, unreplaced faces included. So v2 has no build-1 comparison for them. A replacement check is needed: the rendered LOC patches in the rebuild must byte-equal the final-round post-SHINE patches whose shas the screen record holds. The D-085 twin-identity check and §1.5 checks still apply (B2).
**Q3 ($0.39 against the v2 cap):** yes. It is conservative and disclosed. Any pod time used by the filter continuation or the screen also counts. T-DRV-V2 (`cost_cap_usd` wired into `guard_launch`) must land before any v2 spend (B5).

**Seeds:** retaining them per slot is correct. `item_seed(cfg, fam, i, k)` depends on the clip and the onset, and LOC clip i shows image i of each category. A replacement in slot i therefore keeps its clip, onset and both seeds. The scramble pixels change with the image, which is expected.
**TALKFACE:** the rule is right. Under Q1 no face is ever replaced, so `max_consumed_face_rank` is 492 = D-085. State that in §4. The face v4 log ends at rank 492 (pass 20), so TALKFACE needs a face continuation in every case; name the path that runs it.
**Continuation past 20:** this is not an edge case. Every v4 log ends exactly at its 20th pass: face at rank 492, body at 533, place at 144. Any flag, including place_14 itself, triggers `NeedMorePasses`, so the continuation is the main path. §2.6 and §3 must say so. They must also state where the continuation runs and what it costs, and that the appended log rows leave the frozen v1 `image_manifest_sha256` untouched. Each `NeedMorePasses(c, nxt+1)` asks for one more pass and then re-runs from round 1, which is deterministic but slow. Allow requesting the remaining need in one call. This is optional.
**Outcome-blindness:** this is within (h). A redesign after a STOP is what (h) allows, and the rule changes stimuli only. The rule is mechanical (frozen rank order, the QC's own detector and threshold), and it is fixed before any v2 YuNet run. Disclose two points. First, round 1 is partly known: build-2 QC flagged only place_14 among the body and place images, but on decoded frames, not on patches. Second, threshold = QC threshold leaves no x264 margin (§7 already says this). Do not lower the threshold now. The owner was told this rule, and lowering it would be a change informed by the outcome.
**Scramble gap (disclose):** D-085 gates every LOC_SCR TR, face scrambles included, but the screen covers intact patches only. A scramble hit after the rebuild is a final STOP. Either record a descriptive, non-gating pre-build YuNet run on the rendered scramble patches, or state plainly that this residual risk is accepted.

**Blocking items**
- B1. There is no pod or offline driver that connects `select` to `patch_of`/`shine_fn` (locimg), YuNet, the `NeedMorePasses` handling with `refstim_auto_run --target`, and the writing of the screen record, the v2 manifests and the shas. There is also no change that makes `refclips_build` read the v2 manifests under the v2 sha in place of the frozen v1 sha. Commit the driver with tests, and have the council review it before the D-087 freeze.
- B2. Add the Q2 check (rebuild LOC patch shas = screen final-round shas) and C3 for the four families without slot images to `controls.refclips_d087.qc`.
- B3. Record the owner's confirmation of the Q1 reading (body and place gate; face detections descriptive) before the freeze.
- B4. Rewrite §2.6 and §3: the continuation is required for any flag. Add where it runs, its cost, and its effect on the log and manifest shas. Add the TALKFACE = 492 note and the face continuation path.
- B5. T-DRV-V2 (`guard_launch` enforces the $75 cap with $0.39 carried) must land before any v2 spend.
- B6. Add the scramble-gap disclosure, or a descriptive pre-build scramble screen, to §7.

## Re-check (v2: 71bd4b3, tests c54daf6; owner rulings 2026-11-23)

Verdict: **REVISE**, with one blocking item. I read d087_v2.md, the response matrix, locscreen_v2.py, the refclips_build `--images v2` path and test_d087_v2.py (42 passed). I read nothing sealed.
- B2–B6 are closed. B2: `rebuild_identity.loc` (patch sha = screen record) plus `.build1`, restricted to the four build-1 families. B3: the owner's rulings are on record and enter D-087 at freeze step 2. B4: §3 now makes the continuation the main path and gives its cost, byte identity and commit-before-rescreen, and §4 states TALKFACE = 492. B5: `campaign_cap` and the carried $0.39 are enforced. B6: scrambles and swaps of every slot now gate, and round 1 being partly known is disclosed.
- The owner rulings are consistent with the rule: body and place gate, face is descriptive, and a face slot is replaced only on a scramble or swap hit. The place_14 pre-exclusion is correctly marked post_hoc and cited. It forces a place continuation before round 1, and v2 says so.
- Not adopting the QA lower threshold is acceptable. It is what I asked for: lowering it now would be a choice informed by the outcome.
- Not adopting the biostat compressed-image (x264 round-trip) check is also acceptable. It would change the screen method in response to the decoded-frame result. Pre-excluding place_14 removes the known case. The remaining risk (passing the screen, then failing the decoded QC, a final STOP) is disclosed in §7. Non-blocking: tell the owner plainly, in D-087, that this risk is accepted.
- B1 is only partly closed. `run_screen` is well tested with fakes. `main()`, which wires the real pieces, is never run: `fetch_sources` (S3 misses on the new v2 keys, then a content-sha fallback to the local scratch), `locimg.patch` on real crop boxes, `t_lic_yunet`, and the continuation subprocess. Its first real run would come after the freeze, so a wiring bug would force an amendment. Fakes alone are therefore not acceptable before freeze. A concrete gap: the continuation writes new passes into `SCRATCH`, but `--local` defaults to `/work/yct/refstim_auto_scratch`, so an operator who passes any other scratch path gets a SystemExit on every new pass.

**Blocking**
- R1. Before freeze, run an outcome-blind real-path smoke on the pod and commit its log. It must:
  - load and sha-verify all 60 round-1 sources through `main()`'s loader;
  - run `locimg.patch` with real crop boxes, joint SHINE and `rendered_loc_patches`, and check pixel-equality with `refclips58.loc_frames` on these real patches;
  - load and sha-check `t_lic_yunet`, running it only on a non-LOC fixture (never on a slot patch, so no screen outcome is seen before freeze);
  - check that `refstim_auto_run.py run --target <cat>=20` is a no-op.

  Also default `--local` to include `SCRATCH`.
