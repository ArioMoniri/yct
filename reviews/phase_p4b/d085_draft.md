# D-085 draft: LOC stimulus-QC amendment, speech corpus, TALKFACE generator (p4b_ref/v1)

Status: DRAFT for the council. Nothing is in DECISIONS.md and nothing is frozen. Config block
`controls.refclips_d085` and `controls.refclips_artifacts.speech_corpus_sha256` are set but not frozen.

Inputs:
- The build-1 STOP (97af7ec; `reviews/phase_p4b/refclips_build_v1.md`, `outputs/runs/refclips_v1_nonnat_build1/`).
- The council reviews `reviews/phase_p4b/council_refclips_{watchdog,referee,biostat,neuro,qa}.md` (all REVISE).
- Owner decisions of 2026-11-22 (in-session AskUserQuestion):
  1. LOC QC: "Fix the rule".
  2. Speech corpus: "Approve".
  3. TALKFACE: "AI lip-sync model".

Pre-step (watchdog blocking item 1, done first): the sha256 of every build-1 mp4/wav/tsv (79 + 79 + 79) plus
qc.json and STOP_NOTE.md is committed in `outputs/runs/refclips_v1_nonnat_build1/build1_sha256.json`
(11507d4, before this text). A copy is at `s3://yct-research-235229001983/refclips/v1_nonnat_build1/build1_sha256.txt`.
The committed qc.json and STOP_NOTE.md hash to the same values.

## 1. LOC / LOC_SCR stimulus QC (owner: "Fix the rule"). Amends D-071 (a); stimuli unchanged

**Disclosure.** This amendment is chosen AFTER the build-1 Haar QC result was seen (31 of 40 LOC/LOC_SCR clips
failed). It changes no stimulus, seed, exemplar, detector parameter or threshold. It does not consume the
single D-071 (h) redesign. Precedent: D-074 and D-075 were pre-run amendments with no reference output in
existence; no TRIBE reference prediction exists here either.

**Diagnosis (council, all five members).** Three reasons, none of them a stimulus failure:
- The frozen rule "`face_area_crop_frac` = 0 on every non-face LOC TR and every LOC_SCR TR" tests the Haar FFC
  nuisance regressor, whose false-positive rate on noise was never measured.
- Phase scrambles are face-free by construction (seeded random phase on the jointly SHINE-matched amplitude
  spectrum). 344 of the 380 hit TRs are scramble periods.
- No frozen selection step ever saw a scramble or the post-SHINE, H.264-decoded patch: D-075 B3/P2/F6 ran on
  the pre-SHINE 256-px crop. A zero-tolerance rule that correctly built stimuli cannot pass is a defect of
  the rule.

**New rule** (`controls.refclips_d085.qc`, implemented in `src/yct/tribe_run/refclips_qc85.py`):

| item | rule |
|---|---|
| No-face gate | The frozen T-LIC YuNet (`refclips_auto.face_detector`, onnx sha = `yunet_sha256`), score ≥ 0.5 (= the B3/P2 `exclusion_score_threshold`), on the decoded 316-px patch. The patch is decoded at native 640×360 with BT.709 tv and resized to long side 640 by `ra.resize_long` exactly as at T-LIC. Frames are sampled at `confounds.face_fps` = 2 (the Haar sample frames). Gated TRs: every LOC TR except its face-event TR, and every LOC_SCR TR. |
| Any YuNet detection | Clip fails. STOP to the owner under D-071 (h). No further QC change. |
| Haar on LOC / LOC_SCR | `face_area_crop_frac` is reported per TR (count, TRs, max area). It never gates. It is disclosed in full in the v1 report as a specificity limit of the FFC × face regressor pairing, which also bears on NAT and T1. |
| face_hit_frac ≥ 0.9 | Pooled over the family's 20 face-event TRs (one per clip). The per-clip reading puts 0.9 on n = 1, which is vacuous. Build 1 pooled: 19/20 = 0.95. face_00 (0 hits) is disclosed. |
| Twin identity | LOC and LOC_SCR rendered uint8 frames are equal at every frame outside every window [o−4, o+8). This is the property the (d) intact − twin readout needs, and it is checked constructively on the deterministic render. Rationale for render rather than decode: x264 inter-frame prediction lets decoded frames after the first event differ slightly between two encodes, so a decoded equality test would fail for reasons unrelated to the stimulus. Open for the council: a decoded max-|Δ| outside windows, reported descriptively. |
| Order | Freeze `controls.refclips_d085` before YuNet runs on any built frame (`refclips_qc85.require_frozen`, `refclips_build --qc d085`). diag.json holds Haar results only, and stays that way. |

**Rejected** (all five members agree): new scramble seeds (seed shopping); biostat's R = 10 re-seed rule (not
adopted, since the owner chose this option); a QC tolerance; dropping or replacing exemplars ("no
substitution"); retuning Haar (it is the frozen analysis regressor); swapping the analysis detector.

**QA assertion (referee R1b).** No frozen computation reads refclip `face_area_crop_frac`. A grep finds it only
in `yct.confounds` and the refclips QC code. This is to be re-asserted in the D-085 freeze commit.

## 2. Incomplete §1.5 QC (QA blocking 1d; council-only, frozen with D-085)

`refclips58.stimulus_qc` checked only the LOC face rule and the MOT ratio. D-071 (a) incorporates all of
design_v2 §1.5, so the reported MOT, FLASH and GREY passes were partial. These checks are added on the built
mp4s, with the real `yct.confounds.video_features`. Each threshold below is either already frozen or derived
from the §1.5 wording; none was fitted to build-1 data.

| family | check | rule |
|---|---|---|
| LOC, LOC_SCR, MOT, MOT_STAT | luminance and contrast constancy | `luminance_crop` and `contrast_crop`: max \|x − mean\| / mean ≤ 0.01 over all TRs ("within 1%"). |
| MOT | event ratio (frozen) | mean event-TR `motion_energy_crop` ≥ 10 × the MOT_STAT twin's. |
| MOT | static level elsewhere | the max over non-event TRs × 10 ≤ the event mean. This uses the same 10× separation. |
| MOT_STAT | no event | the twin's max over all TRs × 10 ≤ the MOT event mean. |
| FLASH | `luminance_change` at the events only | luminance_change = \|Δ luminance_crop\| (config `controls.regressors`). Off the onset and offset TRs it must be ≤ 1% of the smallest onset change. |
| visual families | no other regressor moves (audio) | wav sha256 equals the GREY_CTRL wav. These clips carry the control audio bit for bit, so `speech_envelope` cannot move. |
| SPK, BURST | no other regressor moves (video) | every `video_features` series is exactly equal to GREY_CTRL's. The frames are grey and identical. |
| SPK, BURST | `speech_envelope` follows the events | **Open.** T-ENV (`speech_envelope`) is not implemented yet. Speech replaces the bed at matched local RMS, so a broadband-envelope mean may barely change at events. The council must set this check a priori before the speech families are built; SPK/BURST QC is refused until then. |

## 3. SHINE ratification and ghosting (council-only)

Ratify as built in 82aa000:
- joint specMatch over all 60 images, keeping each image's own phase and DC;
- lumMatch to 128 / 32;
- 2 iterations;
- uint8 rounding after every step.

Also ratify the a-priori 16-px crop-overrun bound, whose criterion is identical pixels to the T-LIC numpy
slice (21a2239). SHINE must never be changed to make QC pass.

Test added: `tests/test_refclips_qc85.py::test_rendered_intact_event_frame_equals_the_locimg_patch`. The intact
patch shown at each LOC event is exactly the normalised locimg patch, so `loc_frames` does not introduce
ghosting. Contact-sheet ghosting (for example body_10, face_10, loc_10, loc_17) is therefore either SHINE
specMatch (expected: phase from the image, amplitude from the 60-image mean) or x264 at the sampled frame.

Open for the council: a decoded-vs-rendered patch difference at event mid-frames, reported descriptively.
Any x264 tolerance must be set a priori before the rebuild if it is to gate.

## 4. Contact sheet: place_07 logo, body_03 jacket print (council-only)

No action. Both passed the frozen automatic rules (P3/B5 OCR, B3). Excluding them on sight would be an unfrozen
human override (D-075 replaced human judgement). Both are disclosed in the v1 report.

The one admissible check is the frozen no-YC/analysis-company rule. If either is YC or analysis-company
imagery, that is a STOP to the owner.

## 5. BUG-044 (council-only)

- Keep the content-sha256 recovery and the frozen `file` / `s3_key` names, including the query-string suffix,
  which is disclosed. Renaming would change the frozen image manifest sha.
- Added `refclips_build.verify_s3_sources`. Before the clip-manifest freeze, every manifest `s3_key` must exist
  and its bytes must hash to the manifest sha256. The {key: sha} record goes into the clip manifest.
- Still open: a regression fix plus test so that T-LIC finalise itself uploads sources. This is outside the
  frozen v4 image manifest; a later ticket.

## 6. Toolchain pin (council-only)

`refclips_build.toolchain()` now also records the libx264 package version (`dpkg-query libx264-*`) next to the
ffmpeg 6.1.1-3ubuntu5 version line. The espeak-ng version is recorded at the speech setup step, before
synthesis.

## 7. Speech corpus (owner: "Approve")

- **Source.** The IEEE/Harvard sentences: IEEE Recommended Practice for Speech Quality Measurements, IEEE Trans.
  Audio Electroacoust. 17(3):225–246, 1969, Appendix C. They were parsed from
  https://www.cs.columbia.edu/~hgs/audio/harvard.html, fetched 2026-11-22; the raw sha256 is in the corpus
  file. The page parses to 72 lists × 10 = 720 sentences.
  - **Licence: open item.** The owner approved this source as "public domain". The page carries no licence
    statement. The source is a 1969 IEEE publication, and whether its copyright was renewed has not been
    checked. Short sentences are generally not copyrightable individually, but the list as a compilation
    might be. The council must record the evidence it relies on before the freeze.
- **Exclusion.** The frozen lexicon is `data/refstim/speech/exclusion_lexicon_v1.json`. It matches exact
  lowercase tokens, with inflections listed explicitly. Categories: yc_startup_finance, face, body, place,
  motion. Two further rules: a capitalised non-initial token other than "I" is a proper noun, and a digit or
  number word is a number.
  - The lexicon was written by category from the approved spec, not tuned to the survivor count.
  - Ambiguous words such as "back", "nail", "look" and "wave" were left out. A sentence-initial proper noun is
    not detected. Both are disclosed.
  - Result: 410 kept and 310 excluded (motion 106, place 99, number 57, finance 52, body 21, face 16, proper
    noun 12; reasons overlap).
- **Order.** Ascending sha256(UTF-8 text) over the kept sentences: the queue.
- **Synthesis.** espeak-ng, voice en-us, 175 wpm, pitch 50, amplitude 100, no SSML; version recorded and pinned
  at setup. There is no synthesis until `speech_corpus_sha256` is frozen (`speech_corpus.require_frozen`).
- **Selection** (`speech_corpus.select`):
  - Families are filled in the order SPK (60), BURST (15), TALKFACE (3).
  - Each slot pops the next queue item. SPK uses its leading words, with `spk_words(i, k) = 2 if (k + i // 2) %
    2 == 0 else 3`, which gives 15 two-word and 15 three-word items in each half. BURST joins two consecutive
    sentences as one text. TALKFACE uses one sentence.
  - An item is kept iff its −40 dBFS speech span (first to last sample with |x| ≥ 0.01 full scale) lies in the
    family range: SPK 1.0–1.5 s, BURST 4–6 s, TALKFACE 1–6 s.
  - A failure is logged with reason "duration", and the next queue item takes the same slot.
  - Exhaustion is a STOP to the owner. Each source sentence is used at most once. Nobody listens to choose
    items.
  - Synthesised wavs are trimmed to the span, so the builder's own duration check (`refclips58.clip_audio`) sees
    the same length.
- **Corpus file.** `data/refstim/speech/speech_corpus_v1.json`, sha256
  ef88b4eb247a3670cd70591c48abbcdd6ea7148bc32e220da7786d23fda8db06 (set, not frozen). It is built by
  `scripts/speech_corpus_build.py` and is deterministic. It holds only (list, item, sha256) per sentence plus
  the raw page sha256 (owner 2026-11-22: no sentence text in the public repo). The raw page is in the private
  yct bucket (`speech.private_raw_s3`); `speech_corpus.resolve_texts` re-parses it at build time and stops on
  any raw or item sha mismatch.
- **Risk for the council, flagged before any synthesis** (estimated only from word counts; nothing has been
  synthesised).
  - At 175 wpm a 2-word span lasts about 2 × 60 / 175 ≈ 0.69 s, below the SPK floor of 1.0 s. A 3-word span
    lasts about 1.03 s, at the floor.
  - If espeak-ng runs near the nominal rate, most 2-word SPK slots will fail the gate, each consuming a queue
    item. The queue holds 410 items, against a need of 60 + 30 + 3 = 93.
  - Exhaustion would be a STOP. It is plausible for the 2-word slots, because the 2/3 balance keeps a failed
    slot at 2 words.
  - Options the council or owner could fix a priori (not adopted here):
    - (i) keep everything and accept a possible STOP;
    - (ii) SPK uses 3-word leads only, dropping the design_v2 2/3 balance;
    - (iii) the owner revisits the 175 wpm rate; biostat's derivation from 2.5 words / 1.25 s gives 120 wpm.

## 8. TALKFACE (owner: "AI lip-sync model")

- **Generator.** Wav2Lip, https://github.com/Rudrabha/Wav2Lip at bac9a81e63ecc153202353372e5724b83d9e6322 (`git
  ls-remote` HEAD, 2026-11-22).
- **Licence.** README "License and Citation": "personal/research/non-commercial purposes" only. Its results
  must "only be used for research/academic/personal purposes"; it is trained on LRS2, and commercial use is
  prohibited. This study is non-commercial research, so the use is permitted. Record the README sha at setup.
- **Weights.** `wav2lip_gan.pth` or `wav2lip.pth` (council to pick one a priori; README default: `wav2lip_gan`
  for visual quality) plus the s3fd face detector. They are downloaded once at a T-TALK setup step,
  sha256-recorded, mirrored to `controls.refclips.s3_root/models/wav2lip/`, set in
  `refclips_d085.talkface.{weights_sha256, face_detector_sha256}` in one commit and frozen in the next (the
  pyannote procedure, D-075 / D-082). The README links are Google Drive and SharePoint, so nothing about them
  is immutable until we mirror them.
- **Face image, fixed rule.** The first pass of the frozen face rules (D-079 / D-080 / D-081: v4 code, the same
  snapshot order) after v4 rank 492, the last row of the v4 face log. That is the 21st face pass. It is
  outcome-blind and disjoint from the 20 LOC face exemplars.
  - It needs a CPU continuation of the face log on the pod into a separate append-only file; the v4 log is
    frozen and is not appended to.
  - Wav2Lip needs a real face, which is why this is not a drawn face.
- **Processing (proposal).**
  - The CC0/CC-BY face uses the T-LIC `crop_box` rule.
  - Wav2Lip at 25 fps on the TALKFACE wav (bed + the 3 corpus utterances).
  - The output is resampled to 30 fps, converted to BT.709 greyscale, and composited into the central 316 px
    on mid-grey 640×360.
  - Encoding uses the D-071 (d) bit-exact flags.
  - TALKFACE stays descriptive. It is never in a gate, and the mouth drives MT+, which is disclosed. The LOC
    QC rule does not apply to it.
- **GPU and cost.** About 1–3 min of A100 time, folded into an existing reference session's time budget:
  D-071 (k) launch rules, `yct-p4b-ref` prefix, counted in the $75 cap. Worst case as its own session: $3.48.
  Projection now: $0.39 spent + $61 main plan + NAT continuation (each session is guarded by D-084
  `check_projection`). If TALKFACE runs as its own session, `main_campaign_plan_usd` rises by its worst case
  before the next NAT projection, which the council should confirm.
- **Licence of the face photo.** It must be admissible under D-071 (b) and is recorded in LICENSES.md.

## 9. Order, after council sign-off (each step tested)

1. DECISIONS D-085 (append-only), then a two-commit freeze of `controls.refclips_d085` and
   `controls.refclips_artifacts.speech_corpus_sha256`, with expected rows in `tests/test_guards_frozen_config.py`.
2. Rebuild the non-NAT visual families once with `scripts/refclips_build.py --qc d085`. The mp4/wav/tsv sha256s
   must equal `build1_sha256.json`; any difference is a STOP.
3. Run the D-085 QC. Any failure is a STOP to the owner under D-071 (h), with no second amendment.
4. Speech families (after T-ENV, and after the envelope check is fixed): espeak-ng setup and version pin; the
   synthesis and selection log; SPK/BURST build and QC.
5. TALKFACE: T-TALK setup, the 21st face pass, the build.
6. NAT freeze, the full clip manifest, then upload.

## Owner vs council

- **Owner (decided 2026-11-22):** items 1, 7 and 8.
- **Owner, open:** the speech-rate risk in §7 (only if the council does not settle it under the approved spec);
  the licence evidence for the Harvard list.
- **Council-only:** items 2, 3, 4, 5 and 6; the open details in §1 (decoded twin diff), §2 (envelope check), §3
  (x264 tolerance) and §8 (weights choice).
