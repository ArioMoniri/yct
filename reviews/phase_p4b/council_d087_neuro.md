# Council D-087 draft: neuro member review

Reviewed: reviews/phase_p4b/d087_draft.md, 4fa86c0, 0b0a44a (locscreen.py, refstim_auto_run.py targets, talkface_face, config). tests/test_d087.py 20/20 pass. **Verdict: REVISE.**

**Q1 (screen body+place only, face recorded).** Correct reading. The D-085 gate is "no face on non-face LOC TRs and all LOC_SCR TRs"; face images are required to carry faces (face_hit ≥ 0.9, family-pooled), so gating them would invert the localiser contrast. The owner must be told explicitly (it narrows the literal wording). Add the converse to the record: for each face patch, record whether YuNet detects ≥ 1 face post-SHINE, and report a projected pooled face_hit. Joint SHINE over all 60 means replacing a body/place image changes every face patch too; build 2 was 19/20 = 0.95, one miss from the 0.9 line. Descriptive only; no replacement on it.

**Q2 (rebuild check).** MOT, MOT_STAT, FLASH and GREY_CTRL must stay byte/decoded-equal to build 1. All 20 LOC and 20 LOC_SCR clips are new, including the unreplaced slots (joint SHINE). C3 therefore covers nothing in LOC/LOC_SCR. Replace it with a screen-to-build link: the screen record stores a sha per post-SHINE patch, and the build asserts its rendered intact patches equal those shas before QC. Without this, "screened" and "built" images are not proven identical.

**Q3 ($0.39).** Counting it against the v2 cap is conservative and right; the NAT session-0 output is reused by v2. Keep `spend_carried_usd` in the report.

**Scramble seeds per slot.** Fine. Latin row, onsets, category order and switch times stay identical, so only image content changes. Gap: LOC_SCR is gated on every TR, but the screen never sees scrambles. New body/place images and re-SHINEd faces give new scrambles that go straight to the final QC. The seeds are known before the build, so run YuNet on the scramble and swap of every slot in each round. At minimum record the result; better, gate on it, with a flagged scramble replacing its slot image. Tell the owner either way.

**TALKFACE rule.** Sound (it never reuses a screened or used face). With faces not gated, no face is ever consumed past slot 20, so the rule always reduces to rank 492. State this, or keep the D-085 rule with an assert.

**Continuation past 20.** Acceptable. Same v4 log, order and frozen checks, a 20-pass cap per category, snapshot exhaustion = STOP, deterministic re-run from round 1 (tested). Report how many extra passes each category used.

**Outcome-blindness.** Within (h): a redesign is by definition chosen after a failure, it changes stimuli only, `post_hoc: true` is disclosed, and the rule targets the failed criterion uniformly over all 60 in a frozen, pre-specified order, not just place_14. It stays blind only if the rule (categories, scramble handling, threshold) is frozen before any v2 YuNet output. Note: the screen threshold 0.5 equals the QC threshold, with no margin for x264. Better: run the screen on an encode-decode of each patch through the frozen ffmpeg settings, or use a pre-declared stricter screen threshold (e.g. 0.4).

**Pod driver missing.** Nothing calls `locscreen.select` with real patches, the joint SHINE, the sha-pinned YuNet, NeedMorePasses → continuation → re-run, or the manifest_v2/screen-record writers. That driver is the experiment, so it must exist, be tested end to end on synthetic data and be reviewed before the D-087 freeze.

**Blocking:** (1) pod driver; (2) screen-to-build patch sha link replacing C3 for LOC/LOC_SCR; (3) scramble/swap screen in each round (at least recorded, preferably gated), told to the owner; (4) owner told about Q1 face handling. Recommended: face-detect record plus projected face_hit; encode-decode screen or 0.4 margin; TALKFACE simplification.
