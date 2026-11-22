# Council, p4b_ref/v1 non-NAT build 1 STOP: Neuro review
**Verdict on build-as-is: REVISE.** The STOP was correct. No reference output exists, so every fix is blind to the reference outcome. The QC outcome is known, so the only fixes allowed are ones that do not depend on which exemplars failed. Sources: refclips_build_v1.md, outputs/runs/refclips_v1_nonnat_build1/*, D-071 (a)(d)(h), d071_v3 (d) readout, D-075, refclips58.stimulus_qc / loc_frames / phase_scramble, locimg.py, confounds/core.py, contact sheet. Not read: sealed data, labels, transcripts, predictions.

## 1. LOC/LOC_SCR face QC is a mis-specified rule (a design defect); the stimuli did not fail
- **What the rule should measure.** The neural question is whether a non-face frame carries face *content* that could drive FFC. D-071 (a) instead gates on `face_area_crop_frac`, a Haar FFC nuisance regressor. Nobody had measured how often it fires on noise.
- **Scrambles are face-free by construction.** After joint SHINE, all 60 images share one amplitude spectrum. phase_scramble then replaces their phase with seeded uniform-random phase. Every scramble is therefore drawn from the same category-free 1/f-like ensemble. A Haar hit on such a frame is a cascade false positive. A 19 to 39 TR run is just one static segment counted repeatedly. Since no frozen selection step screened scrambles, zero tolerance was not achievable by design.
- **No contamination of the gated readout.** The (d) readout is intact − scrambled at lags 0–3, with FFC tested as face − mean(place, body). The twins are identical outside events, so scramble hits cancel. Face-like content in a body or place image would *lower* face − body/place, which is the conservative direction for a hard-STOP gate.
- **Minimal fix (owner D-entry; stimuli, seeds, exemplars and Haar parameters unchanged; (h) not consumed if the clips stay bit-identical):**
  - (i) **Gate on twin identity:** LOC and LOC_SCR frames must be pixel-identical on every TR outside [onset−4, onset+8]. This is the actual requirement of the (d) readout.
  - (ii) **Scramble Haar hits** are reported, not gated. No detector is run on scrambles, because they are face-free by construction and any detector there measures only its own false-positive rate.
  - (iii) **Intact body/place:** the gate is the frozen B3/P2 content detector, YuNet at score ≥ 0.5 (frozen sha), run on the post-SHINE decoded 316-px patch. The 10 Haar TRs are disclosed TR by TR. Freeze this rule before YuNet runs on any built frame. If YuNet fires, STOP to the owner and go to D-071 (h), with no further rule change.
  - (iv) **face_hit_frac:** read at family level, giving 19/20 = 0.95. A per-clip 0.9 on a single face TR is vacuous. Because this reading comes after the outcome, it goes in the same owner D-entry, and face_00's 0% is disclosed. On the sheet, face_00 is a clear frontal face, so this is a Haar sensitivity miss, not a stimulus defect.
- **Rejected:** new seeds (seed shopping), a tolerance (tuned to "10 TRs"), dropping exemplars ("no substitution"), and Haar retuning (it is the frozen analysis regressor).
- **Disclose beyond the refclips:** Haar fires on textures and non-face photos. That is a specificity limit of the FFC × `face_area_crop_frac` pairing used in the NAT/T1 partial-outs, and must be disclosed there too.

## 2. SPK/BURST/TALKFACE speech corpus: a missing spec. Owner D-entry; it is blocking because SPK gates the AUD hard STOP
- **Source.** Deterministic, with no hand-written text: IEEE/Harvard sentences (public domain, phonetically balanced, standard in auditory work), ordered by ascending sha256(text).
  - BURST (15) and TALKFACE (3): whole sentences.
  - SPK (60): the first 2 or 3 words of each sentence, set by a fixed alternating assignment. This gives 2/3-word balance across the even and odd halves.
- **Exclusions, as a frozen word list.** No proper nouns or numbers. No YC, startup or finance words. No face, body, place or motion words, so that the TRIBE language path cannot drive FFC, PH or MT+ and confound AUD > FFC.
- **Engine.** espeak-ng with the version pinned, voice en-us, rate 175, pitch 50, no SSML. Words reach TRIBE through the same transcription path as NAT, never as hand-fed text.
- **Duration gate.** Speech span at −40 dBFS must lie in the family range. Failures are logged with reason codes and the next item in order is taken. No item is chosen by listening.
- **Freeze.** The file sha goes in `speech_corpus_sha256` before synthesis. The TALKFACE face generator is pinned in the same entry.

## 3. SHINE interpretation: council-only, ratify
- **Why ratify.** Joint (not within-category) specMatch is the right choice. It removes amplitude-spectrum cues that differ between categories, such as the place high-SF bias, which could otherwise drive PH and FFC. Keeping each image's own DC, then lumMatch to 128/32, 2 iterations and uint8 rounding at each step is a faithful reading of SHINE.
- **Condition.** Add a test that the decoded intact frame equals the locimg patch within the x264 tolerance. The sheet shows ghosting, for example on body_10 and face_10.
- **Disclosure.** Report residual spectral mismatch descriptively; it does not gate.

## 4. Contact sheet: council-only, no action, disclose
- **place_07:** the logo is text and object content. It has little bearing on the gated ROIs, and P3 passed it.
- **body_03:** the jacket print is a cartoon animal face with lettering. It could weakly drive FFC on a body event, which biases face − body toward the null (conservative). B3 and B5 passed it.
- **Why no action.** Excluding either image after viewing it would be an unfrozen human override, which is a forking path.

## 5. BUG-044: council-only
- **Decision:** accept the content-sha256 recovery and keep the frozen names that carry the query string; renaming them is cosmetic.
- **To add:** a pre-freeze S3 existence and sha check, and a regression test that finalise uploads the sources.

## Owner vs council; forking-path risk
- **Owner:** the item 1 QC amendment (i)–(iv), and that it does not consume (h). The item 2 corpus D-entry: source, word list and TALKFACE.
- **Council-only:** items 3, 4 and 5, plus the step below.
- **Before drafting any D-entry:** commit the sha256 of every build-1 mp4/wav/tsv, so the amended QC provably runs on bit-identical clips.
- **Forking-path risk:** highest in item 1, because the Haar outcome is known. It is mitigated by using only already-frozen detectors at their frozen thresholds, freezing before the YuNet run, and full disclosure. Item 4 carries a risk only if acted on.
