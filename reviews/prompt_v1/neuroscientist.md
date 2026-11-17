# Review: Prompt v1, cognitive neuroscientist (encoding models)

**Verdict: FIX.** The question is fine to ask. However, several v1 steps conflict with how TRIBE v2 actually works (see `docs/tribe_requirements.md`). As written, v1 would either double-shift the HRF or end up comparing different ASR outputs, and the pilot's headline metric (|BOLD|) is not meaningful for this model.

## Required changes

**1. [CRITICAL] Remove the extra HRF shift (N7).** TRIBE already offsets its outputs by 5 s (README l.32; config `neuro.offset: 5.0`). Adding a further 4–6 s lag would double-count it. The paper's visual localiser reads the peak at t = 5 s after the flash, so the effective latency in output time is ambiguous. Drop-in:
> N7 (replaces): Do NOT apply any HRF convolution or lag to TRIBE outputs. In P0, run an impulse test. Take a 40 s clip of a mid-grey screen with silence; at t = 10, 20 and 30 s insert a 1 s face image, and in a separate clip a 1 s spoken word. Record the latency of the peak in FFC (HCP-MMP) and in A1/STSv relative to onset. Store `tribe_latency_s` in config.yaml. Every time-locked analysis (N6 segments, T2 bins, time-to-peak) uses this measured latency. If the latency is outside 0–6 s, escalate.

**2. [CRITICAL] Use TRIBE's own transcription path; replace STEP 3.** `get_events_dataframe` itself runs `uvx whisperx` with large-v3, English, the WAV2VEC2_ASR_LARGE_LV60K_960H aligner, fp16 and batch 16. It caches the result as `<stem>.tsv` and skips ASR if that file exists. `uvx` pulls an unpinned WhisperX at run time. Drop-in:
> STEP 3: Generate transcripts ONCE with a pinned WhisperX (`whisperx==<ver>` in requirements.lock), using exactly TRIBE's arguments (`--model large-v3 --language en --compute_type float16 --batch_size 16 --align_model WAV2VEC2_ASR_LARGE_LV60K_960H`). Convert the output to TRIBE's TSV schema (`text,start,duration,sequence_id,sentence`, with unaligned words dropped). Write it to `<stem>.tsv` beside `<stem>.mp4` before calling TRIBE. Test: `test_tribe_uses_injected_transcript` asserts that the Word events in the events dataframe equal the TSV and that no whisperx subprocess was spawned. Hand-check the WER on 5 videos *from this TSV*. Platform captions are never used.

**3. [CRITICAL] Ban |BOLD|; define the output units correctly.** The training targets were z-scored per session and detrended (config `neuro.cleaning`). Predictions are therefore relative z-units with no physical baseline. Drop-in:
> P5: Never use absolute-value predictions. The primary features are signed network means of the raw TRIBE output (one fixed model, so the scale is comparable across videos), with the global mean over cortex as a covariate. Per-video z-scored features are secondary and test pattern shape only. The pilot's "+12% mean |BOLD|" is reclassified as uninterpretable and is not a hypothesis.

**4. [CRITICAL] Fix the visual normalisation to match V-JEPA2.** The backbone resizes the shortest edge to 292 px and **center-crops 256×256**, and patch tokens are mean-pooled. With 1280×720 letterboxing, bars enter the crop, and 9:16 content shrinks to about 56% of the crop width. For 16:9 video, the left and right ~25% of the frame are never seen. Drop-in:
> STEP 2: Do not pad. Keep the native aspect ratio and scale the short edge to 360 px (giving the same 480p quality floor for all videos). Compute `center_crop_face_fraction`, the share of face-box area inside the central square, and `content_in_crop_fraction`, and add both to confounds.parquet. 9:16 videos remain a separate stratum. CFR 30 fps is kept (V-JEPA samples 64 frames over 4 s, i.e. 16 fps, so the source needs at least 16 fps).

**5. [MAJOR] Loudness normalisation does not reach the model.** w2v-BERT input is mono-mixed, resampled to 16 kHz and z-scored per chunk (`norm_audio: true`). Drop-in:
> STEP 2: Keep −23 LUFS normalisation only because it standardises the WhisperX input. Do not write a sidecar `<stem>.wav`: TRIBE reuses any wav with that name. Let TRIBE extract the audio, or write the wav deliberately and record its hash. Raw loudness, speech-gated loudness and music remain *confounds* in P3, not model inputs.

**6. [MAJOR] Cache and sidecar hygiene.** Features are cached by path + offset + duration, and the `.wav`/`.tsv` sidecars are reused by filename. Drop-in:
> STEP 4: TRIBE input filenames are `<sha256[:16]>.mp4`, with a fresh `cache_folder` per (input hash, config hash). `test_determinism.py` must run with an empty cache and no sidecars (cold run). The tolerance is max abs diff ≤1e-3 for cold reruns on the same GPU type and ≤1e-4 for warm (cached-feature) reruns. Record the GPU model and driver; fp16 backbones are not bit-exact across devices.

**7. [MAJOR] Duration, windowing and edges.** The model sees independent 100 s windows. Audio and video longer than 60 s are chunked into 30–60 s pieces. Onset and offset transients are expected, which is the likely cause of the pilot's "both spike at end". Drop-in:
> T1: crop every video to exactly the first 45 s (drop videos <45 s; report how many). Then drop the first 6 TRs and the last 5 TRs, which leaves an identical 34-TR window for all videos. Confirm the edge counts empirically from the mean time course on the grey/silent impulse clip (change 1). T2 (full length, which crosses the 60/100 s boundaries) is EXPLORATORY only. Mark TRs within ±5 s of a chunk or window boundary and exclude them.

**8. [MAJOR] Atlas sources and medial wall (P5).** nilearn provides only Destrieux on fsaverage5; its Schaefer and Yeo fetchers are volumetric. fsaverage5 is exactly the first 10,242 vertices of fsaverage, so nearest-vertex mapping is unnecessary. Drop-in:
> P5 atlases:
> - Schaefer-400-7Net from the CBIG FreeSurfer5.3 fsaverage5 `.annot` files, pinned by sha256.
> - Yeo-7 derived from the Schaefer label names.
> - Destrieux from `nilearn.datasets.fetch_atlas_surf_destrieux()`.
> - HCP-MMP1 from `tribev2.utils.get_hcp_labels("fsaverage5")` (the paper's ROI convention).
>
> Vertex order is LH 0–10241, then RH 10242–20483. Mask the medial wall (Schaefer label 0, i.e. `Background+FreeSurfer_Defined_Medial_Wall`) before any vertex-, global- or network-level statistic. `test_atlas.py` asserts 20,484 labels, a per-network vertex count matching the reference, medial-wall count >0, and no label crossing hemispheres. Delete "nearest-vertex".

**9. [MAJOR] ROI definitions (N4): use HCP-MMP labels that are fixed in advance.** Drop-in:
> Primary ROIs, defined before seeing data (bilateral unless stated):
> - FFA = FFC
> - OFA = PIT/LO1 (exploratory)
> - pSTS = STSdp + STSvp
> - aSTS/TP = STSda + STSva + TGd
> - L IFG = 44 + 45
> - L MTG = TE1a + TE1p
> - TPJ = PGi + TPOJ1–3
> - dmPFC = 9m + 8BM
> - vmPFC = 10r + s32 + a24
> - AI/dACC = AVI + FOP4 + a24pr + p32pr
> - Control: V1–V3 = V1 + V2 + V3
>
> H2 primary = pSTS, aSTS/TP, L IFG, TPJ, dmPFC; the rest are secondary.

**10. [MAJOR] Reliability mask (N2): no official map exists, so we build one.** Drop-in:
> N2: Before unblinding, run TRIBE (same commit) on the HCP 7T movie clips (a zero-shot test set in the paper, with public fMRI). Compute per-vertex Pearson r against the group-mean BOLD, applying the measured latency. The mask is r > the 95th percentile of a phase-randomised null (FDR q < .05). Report every primary ROI's mean r. An ROI with r < 0.1 is downgraded to exploratory. If the HCP data cannot be accessed, fall back to the paper's Fig. 2A HCP-parcel scores and label the mask "coarse".

**11. [MAJOR] Positive controls must pass before P5 (new P4b gate).** Drop-in:
> P4b. Run the following on our own YC videos, with labels hidden. Each must reproduce at the network level (one-sample t across videos, p < .01, correct sign) or the pipeline STOPs:
> - (a) face present vs absent TRs (from the face detector) → FFC > V1–V3 control;
> - (b) speech vs no-speech TRs (from VAD) → STSv/A5 > V1;
> - (c) scene cut ±2 TR → early visual/MT+;
> - (d) text ablation (`features_to_use=[audio, video]`) lowers the L IFG/TE1a variance more than V1's;
> - (e) video ablation lowers V1–V3 more than A1.
>
>

**12. [MAJOR] OOD check (N8).** Drop-in:
> N8: Reference set = 20 Creative Commons talking-head clips plus 10 movie clips. For each video, compute the Mahalanobis distance of mean backbone features to the reference. Videos above the 99th percentile are flagged and run as a sensitivity exclusion. If OOD flags differ between groups, that difference is itself a confound.

**13. [MAJOR] Modality ablations are supported natively, but the estimand needs care.** Drop-in:
> Ablations use `TribeModel.from_pretrained(config_update={"data.features_to_use": [...]})`. A missing modality is zero-filled at the projector output, which matches training modality dropout (p = 0.3), so the input is in-distribution. Cells: AV (no text), AT (no video), VT (no audio), A, V, T. "T-only" must NOT use `text_path` (that path runs TTS and so adds audio). These are inference-time ablations, not the paper's retrained unimodal models. Speech content is still present in audio-only runs.

**14. [MINOR] Licensing and wording (N9).** Drop-in:
> CC-BY-NC-4.0 plus the gated Llama 3.2 licence: non-commercial research only, and no pitch-scoring tool or ranking is released. Every result is worded as "TRIBE-predicted average-subject cortical response".

**15. [MINOR] Pin everything.** Drop-in:
> config.yaml pins the repo commit, the HF revision, the `best.ckpt` sha256, exca==0.5.20, Python 3.11, torch <2.7, the WhisperX version and the backbone HF revisions, all listed in `docs/tribe_requirements.md` §0–1. GPU ≥24 GB. HF_TOKEN lives in env only and is never committed.

## Claims this design can license

- **Licensed:**
  - "Accepted and rejected videos differ in the *TRIBE-predicted* average-viewer cortical response in network X, beyond the measured A/V/text confounds (or not)."
  - Whether that difference is carried by the text, audio or video channel (ablations).
- **Not licensed:**
  - That real viewers' or YC partners' brains respond differently.
  - That the response *causes* acceptance.
  - Reverse inference, e.g. "more social cognition" or "more engagement".
  - Anything subcortical, such as reward or amygdala.
  - Lateral-frame content (it is outside the crop).
  - Generalisation beyond videos that founders chose to publish.
