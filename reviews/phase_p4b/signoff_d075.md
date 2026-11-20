# D-075 sign-off: Strict Referee, Neuroscientist, Biostatistician, QA

Reviewed: reviews/phase_p4b/d075_draft.md at 8cebc2d, against D-071 (b)/(c)/(d)/(k) and D-074 (DECISIONS.md), config.yaml (`controls.refclips*`, `frozen:`), scripts/check_frozen_config.py, scripts/check_append_only.py, scripts/gpu_p4b_ref.py, src/yct/tribe_run/ref_campaign.py, scripts/refstim_inspect.py, tests/test_guards_frozen_config.py, and the WhisperX run record outputs/runs/wave1p2b_20261117T234829Z/.
Method: read-only (git, grep, pytest). No AWS, no decryption, no sealed or pool data, no labels, predictions or candidate images. data/manifest.csv: header only. data/refstim/ has only snapshots, so no filter has run (confirmed from git history).
pytest: tests/test_guards_frozen_config.py, test_d074_config.py, test_ref_campaign_cap.py and test_config_schema.py give 104 passed. No D-075 test files exist yet.

**Verdicts: Referee REVISE, Neuroscientist REVISE, Biostatistician REVISE, QA REVISE.** The rule set is close. Its structure, its use of library defaults for YuNet and Haar, its one-shot and STOP discipline, and the fact that it does not consume D-071 (h) are all sound. Four blockers need fixing before commit 1:
- B1, NAT session placement;
- B2, the wave-2 pool read;
- B3, the solvePnP call and the missing 3-D points;
- B4, the freeze and test mechanics.

---

## Blocking findings (shared by the roles named)

**B1. NAT GPU stage "inside `p4b_ref` session 1" breaks D-071 (d)/(k) and the wrapper.** Referee, QA, Biostat.
- D-071 (k) "Before launch: … the image, NAT and clip manifests are frozen".
- D-071 (k) "Session 1: `--limit 3` (GREY-CTRL s0, SPK_00, MOT_00) … watched".
- D-071 (d): the clip manifest holds the NAT shas and is frozen before upload.
- scripts/gpu_p4b_ref.py refuses any session unless the clip manifest sha equals the frozen `manifest_sha256` and `job_order` covers every manifest clip, NAT included.
- So the NAT set must exist before session 1. A filter stage inside session 1 cannot run, and running it there would move the frozen session-1 scope.
- Fix: a separate NAT-filter launch, "session 0", ahead of session 1. See the edits under Referee. This needs the owner to confirm that it matches "Automatic on 1st GPU run".

**B2. C4 reads `company_key`/`company_id` from data/wave2_pool/pool_manifest.csv.** Referee.
- D-071 (c): "The disjointness test compares URL and video-id hashes only, never any other data/wave2_pool/ field."
- D-069: "Until then no pool row is analysed."
- Fix: drop the pool file from C4, or get explicit owner authorisation (see the OWNER list).

**B3. Head pose (F4) cannot run as written, and its parameters are not reviewable.** QA, Neuro.
- `cv2.solvePnP(..., SOLVEPNP_ITERATIVE)` without an extrinsic guess needs ≥ 6 points for non-planar object points: the DLT initialisation asserts `count >= 6`. A 5-point face model with the nose off the eye/mouth plane is non-planar. The rule as frozen would raise on every face, or would force an unreviewed solver change after the freeze.
- `headpose.model_points: [[0.0, 0.0, 0.0]]` is a placeholder inside the subtree that commit 2 freezes. The council would be signing numbers it has not seen.
- The planned test (recover ±10°/±25° from landmarks projected with the same model) is circular. It checks only the solver, not the fit of the generic model to YuNet's landmark definitions (eye centres, nose tip, mouth corners).

**B4. Freeze and test mechanics are mis-stated.** QA.
- (a) "One row per `refclips_auto_artifacts.<name>`, in the commit that sets it" (§4, §6.3) is impossible. `frozen_at` must name a commit whose config.yaml already holds the value, and a commit cannot name itself. The precedent is 3ca6b2e (set) → 59b6e87 (freeze).
- (b) "New files only; no existing test edited" is impossible. tests/test_guards_frozen_config.py::test_repo_config_has_v22_defaults_and_only_the_d063_freeze asserts the exact `frozen:` list. Every D-075 freeze commit must append to it, as 7a312b4, 1b15837 and 59b6e87 did.
- (c) "The one-shot rule … is enforced by `check_frozen_config`" is false. That script compares only config.yaml values at `frozen_at` and HEAD, never logs. Append-only reject logs need scripts/check_append_only.py: add the paths to `APPEND_ONLY` and write the logs as JSONL, appended once per evaluated candidate.

---

## STRICT REFEREE: REVISE

Faithfulness to D-071 (b)/(c), rule by rule:
- C1, C3, F1, F2, F3 (40% crop), F6 (Haar on the processed 256-px crop), B1, B3, P1, P2: faithful, or stricter in the fail-closed direction.
- C4 (YC imagery): acceptable as a stated proxy. Founder imagery is not covered (see the OWNER list).
- C5 (real photo): acceptable.
- F4/F5 (frontal, eyes visible): acceptable only after B3 and the Neuro edits.
- F7/B4 (adult): acceptable. Mapping minors to `personality_rights` is a reasonable reading. Log the rule id so the mapping can be audited.
- P3 "no text": the 1% area bound is an operationalisation of D-071's "no text", not a literal implementation. That is acceptable if it is disclosed as such.
- NAT: the D-071 (c) filter order (English, ≥ 58 s, single speaker, face, YC link) is permuted: ≥ 58 s and YC link move to the CPU stage. The pass set is unchanged because the rules form a deterministic conjunction, but the logged first-failing reason changes. Disclose this.

Exact edits:
1. **§3 (B1).** Replace "GPU stage, as the first jobs of reference session 1" and the first bullet under "Cost and cap" with:
   > GPU stage: a dedicated NAT-filter launch (session 0), named with prefix `controls.refclips.ledger_name_prefix` (so it counts toward the $75 cap), run before reference session 1. Its driver applies the same every-session rules as D-071 (k): `--max-hours ≤ p4.launcher_max_hours`, `--usd-limit 8`, a new external terminator re-armed on each retry, the dead-man switch, exit 75/1 semantics, the ledger reconciled (L4), and launch only from a pushed, CI-green commit. `entries/campaign_baseline.json` is written once before session 0, not session 1, so that no prefixed instance predates the baseline. Session 0 runs no TRIBE job. Session 1 stays `--limit 3` (the D-038 clips) and `job_order` is unchanged. Session 1 launches only after the NAT manifest sha and the clip manifest sha (T-STIM) are frozen.

   Change §3's last bullet and §6.5 to match. Fix the "documentation of the baseline" in scripts/gpu_p4b_ref.py and ref_campaign.py ("before session 1" → "before the first `yct-p4b-ref` launch"). That fix is a code and docstring change with tests, not a change to frozen config.
2. **§2 C4 (B2).** Delete "or data/wave2_pool/pool_manifest.csv". Keep data/manifest.csv `company_key`/`company_id`, matched as hashed lowercase word n-grams (n = 1 … the longest key's token count).
   - Replace the literal terms "YC W", "YC S" with the regex `\bYC ?[WSF]\d{2}\b`. As written, a word-bounded "YC W" does not match "YC W21".
3. **§2 P3.** Append: "Operationalises D-071 'no text'. OCR noise makes a literal zero-word rule unusable; the 1% bound is stated a priori. A textless logo is not detected."
4. **§3.** Append: "The D-071 (c) filter order is permuted for cost. The resulting set is identical (deterministic conjunction, same sha256(title) order); only the first logged reason can differ. Disclosed in v1."
5. **§2 log.** "Each pass is logged with every rule value" becomes "Each evaluated candidate, pass or reject, is logged with its rule id (C1…P3, N1…N3), its reason code and every rule value computed so far."
6. **§1.** Delete "or this container". Name one image environment (the pod) and record it.

## NEUROSCIENTIST: REVISE

- F5 does not implement "eyes visible". YuNet regresses eye landmarks even behind sunglasses, so both checks pass on occluded eyes.
  - Edit: add F5b, the OpenCV `haarcascade_eye.xml` at the `confounds.face` parameters (scaleFactor 1.1, minNeighbors 5), with ≥ 2 detections whose centres lie in the upper half of the YuNet face box on the original image. Reason `face_not_frontal`. These are documentation and config defaults, not tuned.
  - Otherwise, disclose "eyes visible approximated; occlusion by sunglasses not detected".
- F6 is not an occlusion check. It restates F1 and the D-071 Haar rule.
  - Edit: rename it "F6 Haar on processed crop (D-071)". Add to the disclosures: "occlusion (hands, masks, hair) is detected only through detector confidence".
- F3 "face box": state which detector and which crop. The current builder (scripts/refstim_inspect.py `crop_box`) centres on the largest Haar detection on the ≤ 1600-px greyscale image, with face = 50% of the side, minimum 316, clipped. It measures face height with Haar on the processed crop.
  - Edit: "F3 uses the existing `crop_box`/`processed` definitions unchanged. Face height = the largest Haar box on the processed 256-px crop ≥ 0.40 × 256. The Haar crop centre must lie inside the single YuNet box (otherwise `multi_subject`)."
- "Processed" means crop + BT.709 greyscale + 256-px resize, before SHINE (SHINE is joint over all 60 images, so it cannot run per candidate).
  - Edit: "If the post-SHINE stimulus QC (D-071 (a)) fails for an image, that is a STOP to the owner. No replacement image is drawn."
- F4 model points must follow YuNet's landmark semantics: eye centres, not eye corners. The common 6-point "generic face" uses outer eye corners and a chin, and does not fit. See QA for the solver.
- N1: specify the audio segment.
  - Edit: "first 30 s of the trimmed 58-s T1 audio (`stimulus.t1_trim_s`), the same samples that enter the clip".
  - Call `faster_whisper.WhisperModel.detect_language` (faster-whisper 1.2.1 in the pinned env), which returns all language probabilities. The `whisperx` CLI with `--language en` (config `transcribe.whisperx.language`) skips detection.
- N2 on the trimmed 58-s T1 audio: good. Add "zero diarized speech → `not_single_speaker`".
- N3 (optional, saves GPU time and buffer): `face_present_crop` is a visual P3 feature and does not depend on P2b, so it can move to the CPU stage. If it stays on the GPU stage, no change is needed.

## BIOSTATISTICIAN: REVISE

Threshold provenance:
- **True documentation or config defaults:**
  - YuNet 0.9 / 0.3 / 5000 (the `FaceDetectorYN.create` defaults);
  - Haar 1.1 / 5 (frozen `confounds.face`);
  - the CLIP logit scale as released;
  - 40% (D-071) and ±20° (D-071).
- **Stated a priori, which is allowed, but labelled wrongly in the draft:**
  - F2/B1/P1 person 0.5: "torchvision's documented reference visualisation threshold" is not verified. torchvision's own model default is `box_score_thresh = 0.05`, and its visualisation gallery uses 0.8 for boxes (0.5 is its mask-probability cut).
  - C5 0.5: in a 6-way softmax, p ≥ 0.5 is not the argmax convention. It is stricter.
  - F5 0.25: not "from the YuNet landmark definition".
  - F8 conf 60: "pytesseract usage convention" is folklore.
- **No source given:** C2 512, C3 Hamming 4, B2 15%, B3/P2 YuNet 0.5, N1 0.9, N2 95% / 3 s, and the 40-candidate buffer.
- None of these could have been tuned (git history shows no filter output), so relabelling is enough.

Exact edits:
1. **F2 source** becomes "0.5, stated a priori (not a library default; torchvision's default box_score_thresh is 0.05)".
2. **C5** becomes "pass if argmax over the six prompts is 'a photograph'". That is the actual argmax convention and leaves no free number. Otherwise keep p_photo ≥ 0.5 and relabel it "stated a priori, stricter than argmax". The config `clip.min_prob` must then match whichever is chosen.
3. **C2:** use 316 px, the frozen stimulus patch (`PATCH = 316` in refclips58.py, `MIN_SIDE` in refstim_inspect.py), which is derived and not tuned. Otherwise label 512 "stated a priori (≥ 1.6 × the 316-px patch)".
4. Add one line to §0: "Thresholds without a library or D-071 source are stated a priori in this entry: C2, C3, F2, F5, F8, B2, B3/P2 (0.5), N1, N2, cpu_buffer."
5. **§3 buffer:** append "A continuation buffer (the next 40 in the same order) needs an owner decision. If one is approved, the selected set is identical to D-071's 'first 15 that pass', so the continuation is not a design change."
6. **Fail-closed.**
   - Add to §2 and §3: "A model-load error, a decode error, or a NaN in any score is a STOP (exit 1, human), never a reject, so no candidate is silently swapped."
   - Disclose: "pyannote on GPU is not bit-deterministic. Each candidate is evaluated once and its values are logged; there is no rerun."

## QA: REVISE

Exact edits:
1. **F4 (B3).**
   - Replace `SOLVEPNP_ITERATIVE` with `cv2.SOLVEPNP_SQPNP`: ≥ 3 points, no initial guess, deterministic.
   - Define the angles: `R = cv2.Rodrigues(rvec)[0]`, then yaw, pitch and roll from `cv2.RQDecomp3x3(R)` in a model frame with x right, y down and z away from the camera, with the sign convention written out.
   - The camera matrix uses the width of the 640-px-long-side image on which the landmarks were taken.
   - Put the five 3-D points (eye centres, nose tip, mouth corners, in mm, with a cited source) in the draft before sign-off. Commit 1 must not carry a placeholder.
   - Tests:
     - SQPNP on the 5 frozen points does not raise;
     - a synthetic projection at yaw/pitch ∈ {±19°, ±21°} decides correctly;
     - the decisions are stable when the points are perturbed by 5 mm (shows the rule is not fitted to its own model).
2. **§4/§6 (B4a).** Replace "one row per `refclips_auto_artifacts.<name>`, in the commit that sets it" and §6.3 "commit each artifact sha with its frozen row" with "set in commit k; its `frozen:` row, with `frozen_at` = k, in commit k+1, before any detector call (precedent 3ca6b2e → 59b6e87)". Do the same for the image and NAT manifest shas in §6.4.
3. **§5 (B4b).** Replace "new files only; no existing test edited" with "new test files, plus an append-only extension of the expected list in tests/test_guards_frozen_config.py in each freeze commit (precedent 7a312b4, 1b15837, 59b6e87); check_test_weakening must pass".
4. **§5 (B4c).** Replace "enforced by `check_frozen_config`" with: "reject logs are data/refstim/<cat>_auto_reject_log.jsonl and data/refstim/nat_auto_reject_log.jsonl. Their paths are added to `APPEND_ONLY` in scripts/check_append_only.py. `check_frozen_config` enforces only that thresholds do not change."
5. **§6, new step 0.** Set `controls.refclips_artifacts.nat_snapshot_sha256` to the sha of the committed `nat_nat_snapshot.json` (D-074 records aab68a55…). Freeze it in the next commit, before the NAT CPU stage. D-071 (c) requires this; the draft asserts it as done, but it is null at HEAD.
6. **§2, new rule C0** before C2: "Commons `mediatype` ≠ BITMAP, or a file that does not decode → `not_photo`" (D-074). Without it the first-failing order is underspecified.
7. **Version pins (§1).** "Pinned at T-ENV" or "recorded" is not reproducible. Before commit 1, state exactly:
   - torch and torchvision CPU wheels (the WhisperX GPU env has torch 2.8.0 / torchvision 0.23.0; the CPU pod env must be pinned separately in requirements.lock);
   - `open_clip_torch==<x>`;
   - `pytesseract==<x>`;
   - the tesseract binary (`tesseract --version` and the apt package version, frozen in config, not only recorded);
   - which traineddata: `tessdata_fast` or `tessdata_best`, with its repo commit.

   Artifact sources need a URL and an immutable revision, not trust on first download:
   - YuNet: the opencv_zoo commit;
   - CLIP: the HF repo `laion/CLIP-ViT-B-32-laion2B-s34B-b79K` revision;
   - the torchvision weights URL (it already has a built-in hash prefix, `dd69338a`);
   - pyannote: the revisions of `speaker-diarization-3.1`, `segmentation-3.0` and the embedding model.

   Add a test that the installed versions equal the frozen values before the first detector call.
8. **pyannote under the pinned WhisperX env.** The pinned P2b env (run wave1p2b_20261117T234829Z) has pyannote-audio 4.1.0 and whisperx 3.8.6. The draft's "pyannote.audio pinned at T-ENV" would create a second pin. The project's WhisperX path (src/yct/transcribe/core.py) has never diarized.
   - Edit: "pyannote.audio = the version in the pinned WhisperX env (4.1.0). The loading of `pyannote/speaker-diarization-3.1` under it is verified on a synthetic two-voice fixture in a setup step before the artifact freeze. If it does not load, that is a STOP to the council; there is no silent switch to another default pipeline."
9. **Tests to add** (beyond §5):
   - every rule id maps to exactly one code in `reject_reasons`, and the mapping table is exhaustive;
   - the C4 regex catches "YC W21" and multi-word keys;
   - a test that the module never opens data/wave2_pool/;
   - F3 Haar crop centre inside the YuNet box;
   - fail-closed STOP on a model or decode error;
   - N2 with zero speech gives `not_single_speaker`;
   - N1 uses exactly samples [0, 30 s) of the trimmed T1 audio;
   - session-0 preconditions (baseline before the first prefixed launch, cap guard, terminator, `--max-hours`, `--usd-limit`, CI-green);
   - determinism across two separate processes, not two calls in one process.

### NAT GPU session against the $75 cap and the D-071 launch rules
- Cost:
  - The P2b precedent is $0.53 for 57 wavs including setup, at $1.99/h, A100.
  - 40 trimmed 58-s clips with language ID, diarization and transcription is ≈ $1–2.
  - The guard's planned charge is 1.99 × 1.75 = $3.48 against a spend of $0 now.
  - The D-071 (k) estimate of ≈ $61 rises to ≈ $63, which is under the $75 cap. The $60 `--ack-cap-80` threshold is reached about $2 earlier.
- Cost and cap are compliant. Placement and preconditions are not compliant until B1 and QA edit 9 (session-0 preconditions) are done.

### pyannote gated-model token
- Facts from the repo:
  - The GPU box is fresh for each launch. The draft's "token already provisioned there" is inaccurate.
  - The driver (gpu_wave1_p2b.py, gpu_wave1_p4.py) pipes SSM `/yct/hf_token` from the pod straight into `~/.cache/huggingface/token` on the box with `umask 077`. Only `wc -c` is echoed.
  - owner_setup.sh checks only the Llama-3.2-3B gate.
- Assessment:
  - The pipe pattern keeps the token out of agent output and is acceptable. Agents must not run any command that echoes, cats, greps or logs the token, `~/.cache/huggingface/token`, or the environment, and must not test gate access with the token themselves.
  - `speaker-diarization-3.1` and `segmentation-3.0` are gated separately. Gate acceptance for them on the owner's HF account is unverified (OWNER item).
- Is a non-gated alternative needed? **Not needed if the owner accepts both gates.** For reproducibility and to remove the run-time dependency:
  - download the pinned revisions once, in the setup step;
  - record the file shas as `refclips_auto_artifacts.pyannote_*` and freeze them;
  - mirror the files under `controls.refclips.s3_root/models/`;
  - load offline (`HF_HUB_OFFLINE=1`) in session 0.
- If the owner declines the gates, a non-gated diarizer is needed. Candidates: NeMo MSDD or ECAPA with the released clustering defaults. The `community-1` pipeline is believed to be gated too and is not a way around this. A replacement would be a new D-075 revision with its own council pass, never a run-time fallback.

### Head-pose 3-D point placeholder
Not acceptable for sign-off.
- The solver choice is invalid with 5 points.
- The frozen subtree would hold numbers the council never saw.
- The test is circular.

QA edit 1 resolves all three. The points must be written into the draft (with a source, in YuNet landmark semantics) and re-checked by QA before commit 1. That re-check can be a one-line QA confirmation; a full council round is not needed if only the points and solver change.

---

## Needs the OWNER
1. **"Automatic on 1st GPU run"**:
   - Confirm that it means a dedicated NAT-filter launch (session 0, `yct-p4b-ref` prefix, counted in the $75 cap) before reference session 1. Inside session 1 is incompatible with D-071 (k) and the frozen wrapper.
   - Say whether session 0 must be watched, like session 1.
2. **pyannote gates**:
   - Accept the conditions for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` on the HF account whose token is in SSM, and check access yourself as owner_setup.sh does for Llama. Agents must not test it with the token.
   - Approve the one-time S3 mirror for offline loading.
   - If you decline, a non-gated diarizer needs a new council pass.
3. **C4 and data/wave2_pool/**: approve removing the pool's `company_key`/`company_id` from C4 (recommended). The alternative is to authorise explicitly that reading, which D-069 and D-071 (c) currently forbid.
4. **Founder imagery residual risk**: no automatic rule can detect a YC founder's face without names, and names are not available to agents. Accept the metadata + OCR proxy as a disclosed residual risk.
5. Any later STOP: fewer than 20 image passes, fewer than 15 NAT passes in the 40-candidate buffer, a model-load failure, or a post-SHINE QC failure. Each comes to you, as D-071 (b) and D-074 already require.
