# Council, p4b_ref/v1 non-NAT build 1 STOP: Watchdog review

Verdict on the build as it stands: **REVISE.** The STOP was correct. Nothing was substituted, re-seeded or uploaded, and no reference prediction exists, so every fix below is blind to the reference outcome. It is not blind to the QC outcome, so the forking risk comes from choosing a fix after seeing which exemplars failed.
Sources: refclips_build_v1.md, outputs/runs/refclips_v1_nonnat_build1/*, D-071 (a)(b)(d)(h), D-075 F6/B3/P2, refclips58.stimulus_qc, confounds/core.py and the contact sheet. No sealed data, labels or predictions were read.

## 0. Do first (anti-forking, blocking)
Commit a sha256 record of every build-1 mp4/wav/tsv (built at 21a2239) **before** any D-entry is drafted. Then any amended QC can be shown to have been run on bit-identical clips.

## 1. LOC/LOC_SCR QC: the rule is mis-specified (a design defect, not a stimulus failure)
- **The two QC rules look at different images.** D-075 F6/B3/P2 selected the exemplars with Haar on the *pre-SHINE* 256-px crop. D-071 (a) runs QC on the post-SHINE 316-px patch in a 640×360 frame, analysed at short side 292 with minSize 0.08. Nothing screened the scrambles at all.
- **Zero tolerance cannot be met.** Haar at 1.1/5 has a nonzero false-positive rate on 1/f phase noise, and a static scramble segment carries one hit for 18–39 TRs. That is 344 of the 380 hit TRs. No pre-specified selection step could have guaranteed zero hits, so the frozen pipeline was bound to fail this rule.
- **What the check is for.** The purpose is "each family moves its own regressor and no other" (design_v2 §1.5). Outside events, LOC and LOC_SCR show the same scramble frames at the same TRs, so their twin difference in `face_area_crop_frac` is zero by construction. Hits there are a property of the detector and do not contaminate the twin-subtracted readout (D-071 (d)).
- **Minimal fix: an owner D-entry with no change to stimuli, detector, seeds or thresholds.**
  - **(i) Gating:** a twin-identity check. On every TR outside [onset−4, onset+8], LOC and LOC_SCR frames are pixel-identical (twin difference = 0).
  - **(ii) Reported, not gating:** the scramble-period and LOC_SCR-swap hits.
  - **(iii) Intact body/place hits** (10 TRs, 8 clips): D-075 B3/P2 stays the authoritative no-face gate, since those images passed it. The video hits are disclosed TR by TR.
- **face_00 miss.** The frozen text says "≥ 90% of LOC face-event TRs" (family level). The builder checks it *per clip*, which is stricter. Family-pooled, 19 of 20 face events are detected. Interpreting the frozen text after the result is known is a forking path, so the owner must rule on it in the same D-entry, and face_00's 0% is disclosed.
- **Rejected options:**
  - new seeds: that is seed-hunting, and it does not fix the intact hits;
  - dropping or replacing exemplars: "no substitution" rules it out;
  - a different detector: it would no longer match the analysis FFC regressor, and the choice would be chosen post hoc;
  - a tolerance picked after seeing "10 TRs": a tuned threshold.
- **D-071 (h).** If the stimuli are bit-identical (step 0), this is a pre-run QC correction like D-074/D-075 and does *not* consume (h). Any change to the stimuli is p4b_ref/v2 under (h), with its own cost cap.

## 2. SPK/BURST/TALKFACE speech corpus: a missing spec (blocking for AUD)
- **Proposed spec:** select the text deterministically, with no hand-writing.
  - **Source:** a frozen public-domain list (IEEE/Harvard sentences for BURST and TALKFACE; SPK 2–3-word phrases taken from those sentences or from a frozen word list).
  - **Exclusions:** filter out YC, startup and pitch vocabulary.
  - **Order:** ascending sha256(text); take the first N that pass a duration gate (SPK 1.0–1.5 s, BURST 4–6 s, TALKFACE 1–6 s). Rejects are logged with reason codes.
  - **Engine:** espeak-ng with the version pinned, voice en-us, default rate, fixed in config.
- **Freeze:** the file goes to `controls.refclips_artifacts.speech_corpus_sha256` before synthesis.
- **Who decides:** the council writes the spec; the owner ratifies the source and licence, because SPK gates a hard STOP (AUD).

## 3. SHINE choices: council-only ratification
The choices were fixed in 82aa000 before the build ran (per-image phase and DC, target = mean amplitude of all 60, 128/32, uint8 rounding at each step). Ratify them, on one condition: a test confirming the decoded intact frame equals the locimg patch within the x264 tolerance. On the contact sheet several frames look ghosted (for example loc_10 k1 and loc_17 k0). That may just be how specMatch looks, but it should be checked, not assumed.

## 4. Contact sheet: place_07 logo and body_03 jacket print. Council-only, no action.
D-075 replaced human judgement with the frozen OCR rules P3 and B5, and both images passed them. Acting on a visual impression now would be an unfrozen human override, which is a forking path. Disclose both in the v1 report.

## 5. BUG-044: council-only. Accept the workaround.
- **Recovery:** sources are recovered by content sha256 and uploaded to the frozen `s3_key`. Keep the names that carry the query string, since renaming changes the frozen manifest sha; disclose it.
- **Still to do:** add a regression test that `finalise` uploads the sources, for any v2. Pin or record the libx264 build alongside ffmpeg 6.1.1, as D-071 (d) asks.

## Owner vs council
- **Owner:** the D-entry for item 1 (the QC amendment, the per-clip vs family reading, and the ruling that it does not consume (h)); item 2 (corpus source).
- **Council-only:** items 0, 3, 4 and 5.
