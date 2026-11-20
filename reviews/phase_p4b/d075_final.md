# D-075 final: frozen automatic filters for the P4b localiser images and the NAT clips

Status: final text for the D-075 DECISIONS entry. It applies every REVISE edit in signoff_d075.md (Referee, Neuroscientist, Biostatistician, QA) and the owner decisions of 2026-11-20. Config `controls.refclips_auto` is the frozen machine form; src/yct/curate/refstim_auto.py and scripts/refstim_auto_run.py are the implementation; tests/test_refstim_auto.py and tests/test_d075_config.py are the tests.

## 0. Basis, scope, provenance
- **Owner decisions (2026-11-20, in-session):**
  1. "Frozen automatic rules" for the T-LIC visual filters.
  2. "Automatic on 1st GPU run" for the NAT filters, confirmed as a dedicated **session 0** (`yct-p4b-ref` prefix, counted in the $75 cap), unattended with the usual terminators.
  3. The owner will accept the pyannote gates (`pyannote/speaker-diarization-3.1`, `pyannote/segmentation-3.0`) on the HF account whose token is in SSM, and approves a one-time weight mirror to S3 for offline load.
  4. Drop data/wave2_pool from C4 (wave-1 manifest only).
  5. Accept the founder-imagery residual risk as disclosed.
- **Pre-run amendment, not the D-071 (h) redesign.** No image or clip had been filtered and no reference output existed when this was frozen.
- **Superseded:** the D-071 (b) human-judgement phrases ("one real adult face, frontal within about ±20°, eyes visible, no occlusion"; "one person with no face visible"; "no prominent person, … no text"; "No YC, founder or analysis-company imagery") and the D-071 (c) method for "English" and "single speaker". Everything else in D-071 (b)/(c) and D-074 is unchanged: sources, licence set, personality-rights exclusion, sha256(title) order, first 20 (NAT 15) passes, reject log with reason codes, the face-height ≥ 40% crop rule, the Haar checks on the processed 256-px crop, STOP to the owner. `controls.refclips.reject_reasons` is unchanged; every rule maps to an existing code (`rule_reasons`).
- **Threshold provenance.** Library or config defaults: YuNet 0.9/0.3/5000 (`FaceDetectorYN.create`), Haar 1.1/5 (`confounds.face`), the eye cascade at the same 1.1/5, the CLIP logit scale as released, argmax decisions (no free number), 40% and ±20° (D-071), 316 px (the frozen stimulus patch, `PATCH`/`MIN_SIDE`). **Stated a priori in this entry** (no library or D-071 source; none could have been tuned because no filter output existed): C3 dHash Hamming 4; F2/B1/P1 person score 0.5 (torchvision's own `box_score_thresh` default is 0.05); F5 inter-ocular 0.25; F8 OCR conf 60 and 1% area; B2 15%; B3/P2 YuNet 0.5; OCR and person input long side 1600; N1 p(en) 0.9; N2 95% / 3 s; the 40-candidate NAT buffer.
- **Fail-closed.** A model-load error, a download or decode error of a BITMAP file, an environment or artifact-sha mismatch, or a NaN in any score is a STOP (exit 1, human), never a reject, so no candidate is silently swapped.

## 1. Environment and artifacts (pinned)
- **Where:** images run only on the yct pod CPU (i-02dc0aef7260534ee), venv /work/yct/venv_refstim, python 3.12.3; full freeze in infra/refstim_env.lock. Pins (config `env.packages`): torch 2.8.0+cpu, torchvision 0.23.0+cpu (download.pytorch.org/whl/cpu), opencv-python-headless 4.11.0.86, open_clip_torch 3.3.0, pytesseract 0.3.13, numpy 2.5.5, pillow 13.0.0. Tesseract: apt `tesseract-ocr=5.3.4-1build5` (binary 5.3.4, leptonica 1.82.0) and `tesseract-ocr-eng=1:4.1.0-2` (Debian packaging of tessdata_fast 4.1.0). `check_env` refuses the first detector call if an installed version differs.
- **Artifacts (immutable sources):**
  - YuNet `face_detection_yunet_2023mar.onnx`, opencv/opencv_zoo at commit f12e12798e8314f7c074a6656816c048dcc95b7a (LFS media URL), MIT.
  - torchvision `fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth` (URL carries torchvision's hash prefix), COCO_V1.
  - CLIP `open_clip_pytorch_model.bin` from HF `laion/CLIP-ViT-B-32-laion2B-s34B-b79K` at revision 1a25a446712ba5ee05982a381eed697ef9b435cf, loaded from the local file (no hub call).
  - `eng.traineddata` from the apt package; `haarcascade_frontalface_default.xml` and `haarcascade_eye.xml` from the pinned opencv wheel.
  - Each file's sha256 is set in `controls.refclips_auto_artifacts.<name>` in commit k and frozen by its own row (`frozen_at` = k) in commit k+1, before any detector call (precedent 3ca6b2e → 59b6e87). `check_frozen` and `check_artifact` refuse otherwise.
  - pyannote (session 0): `speaker-diarization-3.1`@84fd25912480287da0247647c3d2b4853cb3ee5d, `segmentation-3.0`@e66f3d3b9eb0873085418a7b813d3b369bf160bb, embedding `wespeaker-voxceleb-resnet34-LM`@837717ddb9ff5507820346191109dc79c958d614; pyannote.audio = the pinned WhisperX env version 4.1.0. Downloaded once in the session-0 setup step, mirrored to `controls.refclips.s3_root/models/`, shas set then frozen (two commits), loaded with `HF_HUB_OFFLINE=1`. Loading 3.1 under 4.1.0 is verified on a synthetic two-voice fixture in that setup step before the artifact freeze; if it does not load, that is a STOP to the council (no silent switch to another pipeline).
- **Determinism:** eval mode, `torch.manual_seed(0)`, one thread (`torch.set_num_threads(1)`, `cv2.setNumThreads(1)`). A test checks byte-identical decisions across two processes. pyannote on GPU is not bit-deterministic: each NAT candidate is evaluated once and its values are logged; no rerun.

## 2. Image rules (in order; first failure is logged)
Common:
- **C0** Commons `mediatype` ≠ BITMAP, or mime not in {jpeg, png, tiff, webp} (snapshot metadata, before download) → `not_photo`. A BITMAP file that fails to download or decode is a STOP.
- **C1** licence / personality rights, the existing D-071 (b) checks → `licence` / `personality_rights`.
- **C2** short side < 316 px → `too_small`.
- **C3** duplicate: Commons sha1 equal to an earlier pass, or 64-bit dHash Hamming ≤ 4 to an earlier pass in any category (categories run face, body, place) → `duplicate`.
- **C4** metadata (title, ImageDescription, ObjectName, Categories) contains "Y Combinator", "YCombinator", "Demo Day" (word-bounded), matches `\bYC ?[WSF]\d{2}\b` (case-insensitive), or any lowercase word n-gram whose sha256 equals that of a data/manifest.csv `company_key`/`company_id` (n = 1 … the longest key's token count; only those two columns are read; keys are never printed) → `text_or_logo`. data/wave2_pool is never read (owner decision 4).
- **C5** CLIP ViT-B-32 zero-shot over ["a photograph", "a drawing", "a painting", "a sculpture or statue", "a computer rendering", "a screenshot"]: pass iff the argmax is "a photograph" → `not_photo`.

**face**
- **F1** YuNet (defaults 0.9/0.3/5000) on the image resized to long side 640: 0 faces → `no_face_detected`, ≥ 2 → `multi_subject`.
- **F2** person detector (Faster R-CNN v2, score ≥ 0.5, on the image scaled to long side ≤ 1600): > 1 person → `multi_subject`.
- **F6** "Haar on processed crop (D-071)": the existing `crop_box`/`processed` definitions unchanged (scripts/refstim_inspect.py; crop centred on the largest Haar detection on the ≤ 1600-px BT.709 grey image, face = 50% of the side, min 316, clipped; processed = crop + BT.709 grey + INTER_AREA 256 px, before SHINE). No Haar face on the full image or on the processed crop → `no_face_detected`.
- **F3** face height = the largest Haar box on the processed crop ≥ 0.40 × 256, else `too_small`; the crop-defining Haar centre must lie inside the single YuNet box, else `multi_subject`.
- **F4** frontal: `cv2.solvePnP(..., SOLVEPNP_SQPNP)` on the 5 YuNet landmarks (order right eye, left eye, nose tip, right mouth corner, left mouth corner; eye centres, not corners) against the frozen generic 3-D model below; camera f = width of the 640-px image, principal point at the centre, no distortion; R = Rodrigues(rvec); (pitch, yaw, roll) = `cv2.RQDecomp3x3(R)` angles about x, y, z in a model frame x right, y down, z away from the camera (frontal = 0, 0, 0). Pass iff |yaw| ≤ 20° and |pitch| ≤ 20°, else `face_not_frontal`.
  - Model points (mm): right eye (−31.5, 0, 0), left eye (31.5, 0, 0), nose tip (0, 35, −30), right mouth corner (−25, 70, −5), left mouth corner (25, 70, −5). Rounded generic adult values stated a priori: inter-pupillary 63 mm (Dodgson 2004, mean adult IPD 63.4 mm), mouth width 50 mm, pupil-to-nose-tip 35 mm vertical with 30 mm protrusion, pupil-to-mouth-corner 70 mm (Farkas 1994 adult norms, rounded).
  - **Disclosed sensitivity:** with every true landmark 3 mm from the model (random direction) the pose error is ≤ ~11°; at 5 mm it reaches ~18°. Decisions near ±20° are therefore approximate; the test asserts stability at ±5°/±35° under 3 mm (non-circular: landmarks from a perturbed face, estimated with the frozen model).
- **F5** both eye landmarks inside the YuNet box and inter-ocular distance ≥ 0.25 × box width → else `face_not_frontal`.
- **F5b** eyes visible: OpenCV `haarcascade_eye.xml` (1.1 / 5) on the original-resolution grey crop of the YuNet box, ≥ 2 detections with centres in the upper half of the box → else `face_not_frontal`.
- **F7** adult proxy: CLIP argmax over ["a photo of a child", "a photo of an adult"] must be adult → else `personality_rights` (minors excluded on rights grounds; the rule id is logged so the mapping is auditable).
- **F8** text: total area of Tesseract (`--psm 11 --oem 1`) word boxes with conf ≥ 60 and non-empty text, on the image scaled to long side ≤ 1600, must be < 1% of that image's area → else `text_or_logo`.

**body**
- **B1** exactly 1 person (score ≥ 0.5): 0 → `not_photo`, ≥ 2 → `multi_subject`. **B2** person box area ≥ 15% of the image, else `too_small`. **B3** YuNet at 0.5 finds 0 faces on the 640-px image and the Haar cascade is negative on the processed (centred-square) crop, else `face_detected`. **B4** adult proxy as F7. **B5** text as F8.

**place**
- **P1** no person with score ≥ 0.5, else `person_present`. **P2** as B3 → `face_detected`. **P3** text as F8 → `text_or_logo`.

**Logs and outputs.** Each evaluated candidate (pass or reject) is appended once to data/refstim/image_<cat>_auto_log.jsonl with its rule id, reason and every rule value computed so far. These logs are in `APPEND_ONLY` (scripts/check_append_only.py); `check_frozen_config` enforces only that thresholds do not change. A logged candidate is never re-evaluated (a resumed run starts after the last logged row and refuses if the log is not a prefix of the order). Fewer than 20 passes in a category's full snapshot → STOP to the owner; no relaxation, no substitute source. Post-SHINE stimulus QC (D-071 (a)) failing for an image is a STOP to the owner; no replacement is drawn. Outputs: data/refstim/image_<cat>_manifest.json (20 each, with source sha256 and crop box), docs/stimuli/LICENSES.md with attribution, `controls.refclips_artifacts.image_manifest_sha256` = sha256 of the three manifests concatenated in loc_categories order (set in commit m, frozen at m+1). Source images are stored only under `controls.refclips.s3_root/sources/images/<cat>/`.

## 3. NAT rules (session 0)
- Order: sha256(title) over the committed NAT snapshot. Step 0: `controls.refclips_artifacts.nat_snapshot_sha256` = sha256 of data/refstim/snapshots/nat_nat_snapshot.json (the D-074-recorded aab68a55…), set then frozen before the NAT CPU stage. The NAT snapshot file stays byte-identical.
- **CPU stage (pod):** licence and personality rights as D-071 (b); duration ≥ 58 s (`too_short`); no YC link via C4 (`yc_link`); P1/P2 normalisation identical to analysis T1; optionally P3 `face_present_crop` (visual, no P2b dependency). Keeps the first 40 passing candidates in order (fixed buffer). A continuation buffer (the next 40 in the same order) needs an owner decision; if approved, the selected set is identical to D-071's "first 15 that pass", so it is not a design change.
- **GPU stage = session 0**, a dedicated `yct-p4b-ref`-prefixed launch counted toward the $75 cap, before reference session 1. Same every-session rules as D-071 (k): `--max-hours ≤ p4.launcher_max_hours`, `--usd-limit 8`, a new external terminator re-armed on each retry, the dead-man switch, exit 75/1 semantics, ledger reconciliation (L4), launch only from a pushed CI-green commit. `entries/campaign_baseline.json` is written once before session 0 (the first `yct-p4b-ref` launch), so no prefixed instance predates it. Session 0 runs no TRIBE job. Session 1 stays `--limit 3` with `job_order` unchanged and launches only after the NAT manifest sha and the clip manifest sha are frozen.
  1. **N1 English:** `faster_whisper.WhisperModel.detect_language` (faster-whisper 1.2.1, large-v3) on samples [0, 30 s) of the trimmed 58-s T1 audio (`stimulus.t1_trim_s`, the same samples that enter the clip); p(en) ≥ 0.9, else `not_english`.
  2. **N2 single speaker:** pyannote 3.1 on the trimmed T1 audio; pass iff the largest speaker holds ≥ 95% of diarized speech and no other speaker exceeds 3 s in total; zero diarized speech → `not_single_speaker`.
  3. P2b transcription (pinned WhisperX), then P3. 4. **N3** `face_present_crop` ≥ 0.5 over W (D-071 (c), unchanged), else `low_face_present`.
- First 15 passes in order = the NAT set; fewer than 15 in the 40-buffer → STOP to the owner. Log: data/refstim/nat_auto_log.jsonl (append-only). The D-071 (c) filter order is permuted for cost (≥ 58 s and YC link moved to the CPU stage); the pass set is identical (deterministic conjunction, same order), only the first logged reason can differ. Disclosed.
- **Cost:** ≈ $1–2 (P2b precedent $0.53 for 57 wavs); the cap guard's planned charge is 1.99 × 1.75 = $3.48. D-071 (k) estimate rises from ≈ $61 to ≈ $63 < $75; `--ack-cap-80` ($60) is reached ≈ $2 earlier.
- **Token rule:** the driver pipes SSM `/yct/hf_token` from the pod into the box's `~/.cache/huggingface/token` (umask 077, only `wc -c` echoed). Agents never echo, cat, grep or log the token, the token file or the environment, and never test gate access with the token.

## 4. Disclosures (report)
- "Eyes visible" is a Haar eye-cascade proxy; occlusion (hands, masks, hair, sunglasses missed by the cascade) is detected only through detector confidence.
- P3/F8 "no text" is operationalised as < 1% OCR word-box area; OCR noise makes a literal zero-word rule unusable; a textless logo is not detected.
- Head pose uses a generic 5-point model (sensitivity in §2 F4).
- Founder imagery: no automatic rule can detect a YC founder's face without names; the metadata + OCR proxy is a residual risk accepted by the owner.
- The adult proxy and the photo proxy are CLIP zero-shot argmax decisions.

## 5. Order of work (each step a separate pushed commit)
1. Commit 1: this entry in DECISIONS.md, `controls.refclips_auto` + `refclips_auto_artifacts` (nulls), schema, code, tests, infra/refstim_env.lock, APPEND_ONLY paths.
2. Commit 2: frozen row `controls.refclips_auto` (`frozen_at` = commit 1) + the exact-list extension in tests/test_guards_frozen_config.py.
3. Commit 3: image artifact shas + `nat_snapshot_sha256` set. Commit 4: their frozen rows (`frozen_at` = commit 3) + list extension.
4. Pod run of the image filters; commit the logs, manifests, LICENSES.md and `image_manifest_sha256`; then its frozen row.
5. Ticket T-NAT0 (not done here): session-0 driver (dry-run tests for the preconditions above: baseline before the first prefixed launch, cap guard, terminator, `--max-hours`, `--usd-limit`, CI-green), the pyannote setup/verification step, then session 0.

## 6. Changelog (sign-off item → fix)
B1 → §3 session 0; B2 → C4 manifest only; B3 → F4 SQPNP, written points, non-circular test; B4a → §1/§5 set-then-freeze; B4b → guard list extended per freeze commit; B4c → APPEND_ONLY logs; Ref 3 → §4 P3 disclosure; Ref 4 → §3 order disclosure; Ref 5 → §2 log; Ref 6 → pod only; Neuro F5 → F5b eye cascade; Neuro F6 → renamed + disclosure; Neuro F3 → crop definitions + centre rule; Neuro SHINE → STOP rule; Neuro N1/N2 → samples + zero-speech; Biostat 1–4 → §0 provenance, C5/F7 argmax, C2 = 316; Biostat 5 → §3 buffer; Biostat 6 → fail-closed + pyannote disclosure; QA 1 → F4; QA 5 → nat_snapshot_sha256 step; QA 6 → C0; QA 7 → §1 pins + `check_env`; QA 8 → pyannote under 4.1.0; QA 9 → tests in tests/test_refstim_auto.py (session-0 precondition tests move to T-NAT0).
