# Council: p4b_ref/v1 non-NAT build STOP (biostat)

**Verdict: REVISE.** MOT, MOT_STAT, GREY_CTRL and FLASH stand as built. LOC and LOC_SCR need one pre-run D-entry. No reference output exists, so this is a pre-run amendment (precedent: D-074 to D-081) and does not consume D-071 (h). Inputs read: refclips_build_v1.md, qc.json, diag.json, STOP_NOTE, the contact sheet, D-071 (a)/(b)/(h), BUG-044, refclips58.stimulus_qc, locimg.py and confounds.core.

## 1. LOC / LOC_SCR QC: the rule is right, the frozen stimuli are infeasible
- **The QC detector was not mis-specified.** §1.5 deliberately runs the real regressor code: Haar, minNeighbors 5, min size 0.08 × 292 px, on the full frame. The point is to check `face_area_crop_frac`, the FFC gating regressor, on the clips themselves. Swapping in another detector for QC only (for example YuNet) would cut the QC loose from the regressor it is meant to check. Changing the detector for the regressor itself is a main-analysis change, out of scope.
- **The real gap is at T-LIC.** B3, P2 and F6 ran on the pre-SHINE 256-px crop. No filter ever saw a phase scramble or the post-SHINE, encoded patch. D-071 froze a zero-tolerance rule, a fixed seed formula and "no substitution" without a feasibility check on rendered scrambles. That combination is a design defect, not a build defect.
- **(1a) face_hit_frac: an implementation-reading issue.** There is one face event per clip, so the per-clip "≥ 90 %" is a binary test on n = 1, and the 90 % has no meaning at that level. D-071 (a) says "≥ 90 % of LOC face-event TRs", which reads naturally as pooled over the family: 19 / 20 = 0.95, PASS. Proposal: rule that the pooled reading is the text, and give the reason (n = 1 makes per-clip 90 % meaningless). Disclose that the ruling came after the miss. If the council rejects it, face_00 is a substitution question for the owner.
- **(1b) Scramble-period hits, 344 + 13 TRs: re-seed, keep the rule.** Proposed rule:
  - Extend the frozen seed string to `f"{seeds.refclips}:{family}:{i}:{k}:{r}"`, with r = 0..R−1 and R = 10 fixed now.
  - For each scramble and each swap scramble, take the first r whose rendered frames, run through the real `video_features`, give `face_area_crop_frac` = 0 on every TR it covers. LOC and its LOC_SCR twin share the scramble seed.
  - If any exemplar exhausts R, STOP to the owner.
  - Why it is safe: phase scrambling keeps the amplitude spectrum, so luminance, contrast and spectrum stay invariant to r, and no confound enters. Selection acts on the control's face-free property, which is the property the rule asks for.
  - Supporting note: the shared-scramble hits are identical in both twins (e.g. loc_00 and loc_scr_00: the same 18 TRs, area 0.0309). They cancel in the twin-subtracted (d) readout, so the practical cost of the defect was nil. That is not a licence to relax the rule.
- **(1c) Intact body/place hits (10 of 40 non-face event TRs, 25 %): owner decision.** No tolerance can be derived from the design. A 10 % rate, mirroring the 90 % face rule, still fails, and any number ≥ 25 % chosen now is post hoc. Options for the owner:
  - **(i)** Accept and disclose. The hit areas (0.016–0.16) are far below face events (≈ 0.44). Before the owner chooses this, the council must state whether these false positives make the FFC gating conservative (noise in the regressor) or anti-conservative.
  - **(ii)** Add a filter "regressor-Haar = 0 on the rendered post-SHINE patch" and re-run selection from rank 1 under first-20. Caveat: SHINE runs jointly over all 60 images, so this filter depends on the whole set; an iteration rule and a cap must be frozen first.
  - Biostat leans (i) if the council finds the effect conservative, else (ii).
- **No lever on SHINE or crop.** Neither may be used to make the QC pass.

## 2. Speech corpus (SPK 60 / BURST 15 / TALKFACE 3): council-only, deterministic and unwritten by hand
- **Sources:**
  - SPK draws from a frozen public word list (a named frequency band of a published list, sha recorded), as seeded adjective+noun or verb+noun pairs.
  - BURST and TALKFACE take the IEEE/Harvard sentences in list order.
- **Engine:** espeak-ng, version pinned, voice `en-us`, rate and pitch fixed a priori. Rate is set from the 2–3-word to 1.0–1.5 s target before any synthesis.
- **Filters:**
  - a frozen exclusion list (YC, startup, pitch, money and company vocabulary);
  - the duration window, measured on the synthesised wav with a stated silence threshold;
  - distinctness, with no repeated content word within SPK.
- **Selection:** order candidates by sha256(text) and take the first N that pass; if fewer than N pass, STOP. Freeze the file as `speech_corpus_sha256` before synthesis. Never edit sentences after hearing them.

## 3. SHINE interpretation: ratify (council-only)
Each choice was fixed in code (82aa000) before the build and matches the toolbox:
- quantisation to uint8 at every step;
- the final step is lumMatch, so DC handling has no effect.

The contact sheet shows ghost and halo texture in many patches, so add a diagnostic-only pre/post-SHINE Haar comparison to the D-entry record. Ratify as-is either way: changing SHINE after the QC is a forking path.

## 4. Contact sheet (place_07 logo, body_03 jacket): no action, disclose (council-only)
D-075 replaced human judgement with frozen automatic rules, and P3 and B5 passed both images. An eyeball veto now would bring back the judgement D-075 removed and act as a post hoc filter. The only check is whether the logo is YC or analysis-company imagery under the frozen no-YC rule; if so, STOP to the owner.

## 5. BUG-044: accept the workaround (council-only)
- Sources are gated by content sha256 and uploaded to the frozen `s3_key`.
- Add a post-upload sha re-read of each key, recorded in the manifest.
- Do not rename: that would change the frozen manifest sha for cosmetic gain. Disclose the URL-suffix names.

## Owner vs council
- **Owner:** 1c, (i) or (ii). 1a only if the council rejects the pooled reading.
- **Council D-entry (owner notified):** 1a ruling, 1b re-seed rule with R = 10, 2 corpus spec.
- **Council-only:** 3, 4, 5.

## Forking-path flags
- **Highest risk:** any tolerance number or detector change chosen after seeing 25 % / 344 TRs.
- **Also flagged:**
  - re-seeding without a fixed R;
  - tuning SHINE;
  - hand-written or audited-by-ear sentences;
  - the post hoc 1a reading (mitigated by the n = 1 argument and disclosure).
- All QC results so far are stimulus-property checks; no TRIBE output exists. Disclose everything in the v1 report.
