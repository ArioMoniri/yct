# D-075 draft: frozen automatic filters for the P4b localiser images and the NAT clips

Status: DRAFT for council sign-off (Referee, Neuroscientist, QA, Biostatistician, Watchdog). Not committed to DECISIONS.md or config.yaml.
Basis: owner decisions of 2026-11-20 (in-session answers):
- "Frozen automatic rules" for the T-LIC visual filters;
- "Automatic on 1st GPU run" for the NAT filters.

This is a pre-run amendment of D-071 (b)/(c) and D-074. No image or clip has been filtered and no reference output exists. It is therefore not the one versioned redesign (D-071 (h)).

## 0. Scope and supersession
- D-071 (b) phrases that need human visual judgement are superseded by the rules in §2:
  - "one real adult face, frontal within about ±20°, eyes visible, no occlusion";
  - "one person with no face visible";
  - "no prominent person, … no text";
  - "No YC, founder or analysis-company imagery".
- Every other D-071 (b)/(c) and D-074 rule is unchanged:
  - sources;
  - licence set and personality-rights exclusion;
  - sha256(title) order;
  - the first 20 (NAT: 15) passes per category;
  - the reject log with reason codes;
  - the face-height ≥ 40% crop rule;
  - the Haar-cascade checks on the processed 256-px greyscale image;
  - the STOP-to-owner rule.
- The reject-reason list `controls.refclips.reject_reasons` is unchanged. Every rule below maps to an existing code.
- Rules are evaluated in the order listed. The first failing rule gives the logged reason. A candidate is never re-evaluated.
- No threshold below was chosen by looking at candidates. Each is a documented library default or a documented convention, stated with its source. None may change after the first detector call on a candidate (§5).

## 1. Toolchain (pinned; where it runs)
- Images run on CPU in the yct pod (i-02dc0aef7260534ee) or this container, with one fixed environment recorded in the run record. They never run on the GPU box.
- Models, pinned by version. Weight files are pinned by sha256: the sha is recorded at download into `controls.refclips_auto_artifacts.<name>_sha256` and frozen by its own `frozen:` row before any candidate is processed.
  - **Face detector + landmarks:**
    - OpenCV `cv2.FaceDetectorYN` (YuNet), opencv-python-headless==4.11.0.86 (already in requirements.lock).
    - Model `face_detection_yunet_2023mar.onnx` from opencv/opencv_zoo, MIT licence.
    - Input: the original image resized so its long side is 640 px.
  - **Person detector:**
    - torchvision `fasterrcnn_resnet50_fpn_v2`, weights `FasterRCNN_ResNet50_FPN_V2_Weights.COCO_V1` (file `fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth`; BSD-3 code, weights from torchvision).
    - torch/torchvision CPU wheels pinned to exact versions in requirements.lock at T-ENV.
    - COCO class 1 = person.
  - **OCR:**
    - Tesseract 5 via `pytesseract`. The apt package version and the `eng.traineddata` sha are recorded.
    - Settings: `--psm 11` (sparse text) and `--oem 1`.
  - **Photo / adult proxy:**
    - open_clip `ViT-B-32`, pretrained `laion2b_s34b_b79k`, CPU float32. MIT code; LAION weights.
  - **NAT language ID:** WhisperX 3.8.6 as already pinned (`transcribe.whisperx`, D-061), model large-v3. Language detection on the first 30 s of the 16-kHz P2 audio.
  - **NAT diarization:**
    - `pyannote/speaker-diarization-3.1` through WhisperX's diarize path (pyannote.audio pinned at T-ENV; model revision sha recorded and frozen).
    - Runs on the GPU box with the gated-model token already provisioned there; the token is never read by the agent.
- Determinism: models run in eval mode with `torch.manual_seed(0)` and single-threaded inference (`torch.set_num_threads(1)`, `cv2.setNumThreads(1)`). A rerun on the same image must give identical decisions. This is tested on fixtures.

## 2. Image rules (per category, in order)
Common to all categories, applied before the category rules:
- **C1 licence:** the existing D-071 (b) licence and personality-rights checks.
  - Reason: `licence`, `personality_rights`.
- **C2 size:**
  - short side ≥ 512 px.
  - Reason: `too_small`.
- **C3 duplicate:**
  - identical sha256, or a 64-bit dHash Hamming distance ≤ 4 to an earlier pass in any category.
  - Reason: `duplicate`.
- **C4 metadata exclusion (replaces "no YC, founder or analysis-company imagery"):**
  - rejected if the file title, description or any category contains (case-insensitive, word-bounded) "Y Combinator", "YCombinator", "YC W", "YC S", "Demo Day", or any company_key or company_id string from data/manifest.csv or data/wave2_pool/pool_manifest.csv;
  - the match is done by sha256 of the normalised token, so the curator never prints those keys;
  - reason: `text_or_logo` (metadata).
  - Justification: the image sources are generic Commons categories. A visual YC-imagery detector cannot be specified without tuning, so a metadata rule plus the OCR rule is the stated proxy.
- **C5 photograph (replaces "real photo"):**
  - pass if p_photo ≥ 0.5, where p_photo comes from a CLIP zero-shot softmax (logit scale as released) over the prompts:
    - "a photograph";
    - "a drawing";
    - "a painting";
    - "a sculpture or statue";
    - "a computer rendering";
    - "a screenshot".
  - Reason: `not_photo`.
  - Source: the 0.5 is the decision boundary of the softmax (the argmax convention), not tuned.

**face**
- F1 YuNet with the library defaults `score_threshold=0.9`, `nms_threshold=0.3`, `top_k=5000`. Exactly 1 face. Reason: 0 → `no_face_detected`, ≥ 2 → `multi_subject`.
- F2 person detector: at most 1 person box with score ≥ 0.5. Reason: `multi_subject`. Source: 0.5 is torchvision's documented reference visualisation threshold.
- F3 face size:
  - face box height ≥ 40% of the square crop used by the clip builder, per D-071 (b) unchanged;
  - reason: `too_small`.
- F4 frontal:
  - yaw and pitch from `cv2.solvePnP` (SOLVEPNP_ITERATIVE) on the 5 YuNet landmarks, using the fixed generic 3-D 5-point face model listed in `controls.refclips_auto.headpose_model_points`;
  - camera matrix focal length = image width, principal point at the centre, no distortion;
  - pass if |yaw| ≤ 20° and |pitch| ≤ 20°;
  - reason: `face_not_frontal`;
  - source: ±20° is the D-071 (b) criterion.
- F5 eyes visible:
  - both eye landmarks lie inside the face box;
  - the inter-ocular distance is ≥ 0.25 × the face box width;
  - reason: `face_not_frontal`;
  - source: geometric, from the YuNet landmark definition.
- F6 occlusion proxy:
  - the YuNet score is ≥ 0.9 (already enforced by F1);
  - the Haar cascade (`confounds.face`, scaleFactor 1.1, minNeighbors 5) detects a face on the processed 256-px greyscale crop, per D-071 (b) unchanged;
  - reason: `no_face_detected`.
- F7 adult proxy:
  - CLIP zero-shot softmax over "a photo of a child" and "a photo of an adult", with p_adult ≥ 0.5;
  - reason: `personality_rights`, because minors are excluded on rights grounds;
  - source: the argmax convention.
- F8 text:
  - total area of Tesseract word boxes with conf ≥ 60 is < 1% of the image area;
  - reason: `text_or_logo`;
  - source: conf 60 follows the pytesseract usage convention; 1% is a fixed small-area bound, stated now.

**body**
- B1 person detector: exactly 1 person box with score ≥ 0.5. Reason: 0 → `not_photo`, ≥ 2 → `multi_subject`.
- B2 person box area ≥ 15% of the image area. Reason: `too_small`. Source: a fixed bound, stated now; it keeps the body as the dominant subject.
- B3 no face:
  - YuNet at score_threshold 0.5 (lower than F1 on purpose, to reject any visible face) finds 0 faces on the original image, and the Haar cascade is negative on the processed image (D-071 (b));
  - reason: `face_detected`.
- B4 adult proxy: as F7.
- B5 text: as F8.

**place**
- P1 person detector: no person box with score ≥ 0.5. Reason: `person_present`.
- P2 no face:
  - YuNet at score_threshold 0.5 finds 0 faces, and the Haar cascade is negative on the processed image;
  - reason: `face_detected`.
- P3 text: as F8. Reason: `text_or_logo`.

Each pass is logged with every rule value: scores, angles and areas. The log is committed together with the manifest. If a category gets fewer than 20 passes in its full snapshot, the build does not start. That goes to the owner (D-071 (b)). No threshold relaxation and no substitute source.

## 3. NAT rules (first reference GPU session)
- Order is unchanged from D-071 (c): sha256(title) over the committed NAT snapshot (`nat_nat_snapshot.json`; its sha is frozen in `controls.refclips_artifacts.nat_snapshot_sha256` before any filter).
- CPU stage on the pod, before the GPU session:
  - licence and personality rights as (b);
  - duration ≥ 58 s (reason `too_short`);
  - no YC link via the C4 metadata rule (reason `yc_link`);
  - P1/P2 normalisation identical to analysis T1.
  - The CPU stage keeps the first 40 candidates by order that pass, a fixed buffer for the GPU rules below.
- GPU stage, as the first jobs of reference session 1, in this order:
  1. N1 English: WhisperX/faster-whisper `detect_language` on the first 30 s, with p(en) ≥ 0.9. Reason: `not_english`. Source: a fixed high-confidence bound, stated now.
  2. N2 single speaker:
     - pyannote 3.1 diarization over the trimmed T1 audio;
     - pass if the largest speaker holds ≥ 95% of the diarized speech time and no other speaker exceeds 3 s in total;
     - reason: `not_single_speaker`;
     - source: fixed bounds, stated now; ≥ 95% follows the D-071 single-speaker intent.
  3. P2b transcription (pinned WhisperX, as analysis), then P3.
  4. N3: face_present_crop ≥ 0.5 over W, from yct.confounds (D-071 (c), unchanged). Reason: `low_face_present`.
- The first 15 that pass all rules, in order, are the NAT set. Fewer than 15 out of the 40-candidate buffer → STOP to the owner. There is no second buffer without an owner decision.
- Cost and cap:
  - The NAT GPU stage runs inside `p4b_ref` session 1, before any SPK/LOC/MOT job. It is a yct-p4b-ref launch, so it counts toward the $75 campaign cap.
  - Estimate: 40 × about 1.5 min (language ID + diarization + transcription) ≈ 1 h ≈ $2.
  - The cap guard (src/yct/tribe_run/ref_campaign.py) runs before the launch as usual.
- The NAT TRIBE predictions run only after the set is fixed. The fixed set is the committed NAT manifest with its sha frozen.

## 4. Config (new sibling key; two-commit freeze as D-071 976e8ab → 7a312b4)
```yaml
controls:
  refclips_auto:               # D-075 (owner decision 2026-11-20): frozen automatic filters
    decision: D-075
    supersedes: "D-071 (b) human-judgement phrases; D-071 (c) English/single-speaker method"
    face_detector: {impl: cv2.FaceDetectorYN, model: face_detection_yunet_2023mar.onnx, input_long_side: 640,
                    score_threshold: 0.9, nms_threshold: 0.3, top_k: 5000, exclusion_score_threshold: 0.5}
    person_detector: {impl: torchvision.fasterrcnn_resnet50_fpn_v2, weights: COCO_V1, person_class: 1, score_threshold: 0.5}
    ocr: {impl: tesseract5, psm: 11, oem: 1, min_conf: 60, max_text_area_frac: 0.01}
    clip: {model: ViT-B-32, pretrained: laion2b_s34b_b79k,
           photo_prompts: ["a photograph", "a drawing", "a painting", "a sculpture or statue", "a computer rendering", "a screenshot"],
           adult_prompts: ["a photo of a child", "a photo of an adult"], min_prob: 0.5}
    headpose: {method: solvePnP_iterative, max_abs_yaw_deg: 20, max_abs_pitch_deg: 20,
               model_points: [[0.0, 0.0, 0.0]] }   # placeholder: the 5 fixed 3-D points are written in commit 1
    face_rules: {min_face_height_frac_crop: 0.40, min_interocular_frac_box: 0.25}
    body_rules: {min_person_area_frac: 0.15}
    common: {min_short_side_px: 512, dhash_bits: 64, dhash_max_hamming: 4,
             metadata_terms: ["Y Combinator", "YCombinator", "YC W", "YC S", "Demo Day"], metadata_manifest_keys: true}
    nat: {cpu_buffer: 40, lang_id: {impl: whisperx_detect_language, seconds: 30, min_prob_en: 0.9},
          diarization: {impl: pyannote/speaker-diarization-3.1, min_main_speaker_frac: 0.95, max_other_speaker_s: 3.0},
          stage: p4b_ref_session_1_first, counts_toward_cap: true}
    determinism: {torch_seed: 0, threads: 1}
  refclips_auto_artifacts:     # filled at download; each value is frozen by its own row before any candidate is processed
    yunet_sha256: null
    frcnn_sha256: null
    clip_sha256: null
    tesseract_eng_sha256: null
    pyannote_revision: null
```
- The `frozen:` rows are:
  - `controls.refclips_auto`, at commit 1;
  - one row per `refclips_auto_artifacts.<name>`, in the commit that sets it.
- No later-filled value sits inside a frozen subtree (QA X2 lesson).
- The schema is a new `RefclipsAuto` model with literal values, extra="forbid".

## 5. Tests (new files only; no existing test edited)
- `tests/test_d075_config.py`:
  - keys and literals equal this entry;
  - frozen rows present;
  - artifacts not frozen while null and frozen once set;
  - `reject_reasons` unchanged and every rule maps to a code in it.
- `tests/test_refstim_auto.py`, on synthetic or fixture images only and never on candidates:
  - rule order: the first failing rule is logged;
  - each rule's boundary, at value = threshold and threshold ± ε;
  - head-pose recovers known yaw/pitch from synthetic landmarks projected at ±10°/±25°;
  - dHash duplicate detection;
  - the metadata rule matches by hashed token and never prints keys;
  - determinism: two runs give byte-identical logs;
  - the build refuses with fewer than 20 passes;
  - artifact shas are checked before the first detector call, and a mismatch refuses;
  - the first detector call is refused unless `controls.refclips_auto` and every artifact row are frozen.
- `tests/test_nat_auto.py`, with fakes for language ID and diarization:
  - thresholds at the boundary;
  - the 40-buffer and first-15 order;
  - STOP below 15;
  - the NAT stage is scheduled before any SPK/LOC/MOT job;
  - spend is counted in the campaign cap.
- The one-shot rule (no re-evaluation of a candidate after the first detector call; no threshold change) is enforced by `check_frozen_config` and a test that the reject log is append-only.

## 6. Order of work
1. Commit 1: the D-075 entry in DECISIONS.md, the config, the schema and the tests.
2. Commit 2: the frozen row.
3. Download models; commit each artifact sha with its frozen row.
4. Run images (CPU). Commit the reject logs and manifests, LICENSES.md, and the image manifest sha with its frozen row.
5. NAT CPU stage, then NAT in reference session 1.
- Each step is a separate commit. No step runs before the previous one is pushed with green CI.
