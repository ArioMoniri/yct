# D-082 draft: pin the pyannote community-1 PLDA for 3.1 under pyannote.audio 4.1.0 (BUG-040)

Status: DRAFT for the council. Not in DECISIONS.md and not frozen. Session 0 stays refused until
D-082 is accepted, `controls.refclips_d082` is frozen and `pyannote_plda_sha256` is set and frozen
(the two-commit pattern).

## 0. Trigger and owner decision
- **BUG-040:** under pyannote.audio 4.1.0 (the pinned WhisperX env), the D-075-pinned
  `speaker-diarization-3.1` pipeline does not load offline. `SpeakerDiarization.__init__` always calls
  `get_plda(plda)`; with `plda=None` it defaults to `pyannote/speaker-diarization-community-1`
  (subfolder `plda`). That repo was not in the D-075 pin list.
- **Owner decision (2026-11-22, in-session):** option (a), "I'll accept the gate". The owner then
  replied "Done gate accepted" for https://huggingface.co/pyannote/speaker-diarization-community-1.
  Options (b), disable the PLDA, and (c), a pyannote 3.x env, were not taken.

## 1. Amendment to D-075 §1 (pins)
- **Added pin:** `pyannote/speaker-diarization-community-1` @ `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`.
  - This is the repo's head commit sha from the HF API on 2026-11-22, an immutable revision.
  - Only `plda/` is mirrored (`allow_patterns=["plda/*"]`): `plda.npz`, `xvec_transform.npz`, `README.md`.
  - community-1's own segmentation and embedding models are never downloaded or loaded.
- **Gate check on the pod:** with the owner's token (piped from SSM to a umask-077 file, shredded, never
  printed), the API returned HTTP 200 and the repo shows `gated: auto`. `plda/plda.npz`,
  `plda/xvec_transform.npz` and `config.yaml` all returned 200 at the pinned sha.
- **Mirror:** `controls.refclips.s3_root/models/pyannote/speaker-diarization-community-1/plda/`.
  - The `dir_sha` of the mirrored dir is
    `pyannote_plda_sha256 = 53df9c188dd21b02cd629aff5f63b1509958aad5251f2fcdea0ef8c02c75835e`.
    It is recorded here and not set in config until the council accepts.
  - The three D-075 mirror shas were re-derived and are unchanged: diarization 0f66ffc1…, segmentation
    702a51c6…, embedding 519a3249…, as in BUG-040.
- **Config (draft):** `controls.refclips_d082` holds the pin, and
  `controls.refclips_auto_artifacts.pyannote_plda_sha256` is a new key, null for now. The frozen
  `controls.refclips_auto` (D-075) is not edited.

## 2. How the PLDA is used (loaded, never applied)
- **Load:** `nat0_box.patched_config` passes the mirrored PLDA explicitly (`params.plda = <mirror>/…/plda`).
  4.1.0 therefore loads it from the local dir with `HF_HUB_OFFLINE=1` and never reaches for the hub
  default.
- **Never applied:** in 4.1.0 (`speaker_diarization.py`, `__init__`), the PLDA is handed to the clustering
  only when `clustering == "VBxClustering"`; otherwise `Klustering.value(metric=metric)` is built without
  it. The pinned 3.1 `config.yaml` sets `clustering: AgglomerativeClustering` (centroid, threshold
  0.7046, min_cluster_size 12).
- **Code guard:** `patched_config` refuses any clustering other than AgglomerativeClustering, and
  refuses an incomplete PLDA mirror.
- **Runtime evidence:** see §4. The verify step logs `plda_loaded` and `clustering`.
- **Effect on N2 decisions:** none expected. The D-075 rules, thresholds and pipeline parameters are
  unchanged.

## 3. Other changes (tested, test-first)
- **`scripts/nat0_pyannote_setup.py`:**
  - `pins()` includes the PLDA, and download is limited to `plda/*`.
  - Verify now requires exactly two speakers on the synthetic A-B-A two-voice fixture (`fixture_ok`);
    before, any non-empty output passed.
- **`scripts/gpu_p4b_nat0.py`:** session 0 also requires `controls.refclips_d082` frozen, and a set,
  frozen `pyannote_plda_sha256`. The shas passed to the box include `plda`.
- **`nat0_box.read_wav`/`write_wav`:** now use stdlib `wave` + numpy.
  - The pinned WhisperX freeze (`wx_pip_freeze.txt`) has no `soundfile`, so the old `read_wav` would
    have failed on the box at N1/N2.
  - The first D-082 pod verify found this, after the pipeline itself had loaded.
- **Tests:** `tests/test_nat0_d082.py` (14 tests). Two existing fixtures gained a PLDA dir, a clustering
  key and the D-082 freeze row; no assertion was changed.

## 4. Pod verification (78d09e3, /work/yct/repo_nat0; the NAT CPU run in /work/yct/repo untouched)
- **Result:** `nat0_pyannote_setup.py verify` exited 0. It loaded 3.1 offline (`HF_HUB_OFFLINE=1`) from
  the mirror under pyannote.audio 4.1.0 on the CPU, and the mirror shas match config/§1.
- **Fixture output:**
  `{"n_turns": 4, "n_speakers": 2, "speech_s": 20.436, "plda_loaded": true, "clustering": "AgglomerativeClustering"}`.
  - The two espeak-ng voices, A-B-A, come back as exactly 2 speakers. The 4th turn is a split of one
    voice's segment, so the turn order was not checked beyond the speaker count.
  - `plda_loaded: true` with `clustering: AgglomerativeClustering`: by the §2 code path, the PLDA is
    loaded and not applied.
- **Log:** `s3://yct-research-235229001983/wave1/derived/p4b_ref/v1/models/pyannote_verify_4.1.0_d082.log`.
- **Warning in the log:** one pyannote UserWarning, "std(): degrees of freedom <= 0", from the embedding
  pooling on a very short chunk. It is benign and also occurs upstream; no NaN reached the output.

## 5. Disclosure (v1 report)
- D-075 pinned three pyannote repos. pyannote.audio 4.1.0 additionally requires a PLDA file, which is
  pinned by D-082 and unused by the 3.1 AgglomerativeClustering pipeline.
- The owner accepted the community-1 gate on 2026-11-22.

## 6. Freeze plan after council acceptance
1. **Commit k:** DECISIONS D-082, and `pyannote_{diarization,segmentation,embedding,plda}_sha256` set in
   config.
2. **Commit k+1:** freeze rows for `controls.refclips_d082` and the four sha keys, with the expected
   rows in `tests/test_guards_frozen_config.py`.
3. **Then:** the T-NAT0 session 0 under D-071 (k) launch rules, once the NAT CPU buffer is full.
