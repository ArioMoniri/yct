# TRIBE v2 — verified requirements and pipeline facts

Fact-find date: 2026-11-17. Every item is tagged:

- **VERIFIED**: read in an official source (file and line, or URL).
- **VERIFIED-CODE**: follows directly from the released code path, but the official docs do not state it and we have not yet run it.
- **UNVERIFIED**: estimate or third-party report. Must be checked in the P0 smoke test.

## 0. Pinned sources (put these in config.yaml)

| Item | Value | Status |
|---|---|---|
| Code repo | https://github.com/facebookresearch/tribev2, commit `af58661791a351a448a489042a28f6c37e1c14b7` (HEAD on 2026-06-23, "Update README.md") | VERIFIED (git clone) |
| Weights repo | https://huggingface.co/facebook/tribev2, revision `f894e783020944dcd96e5568550afe2aa9743f9f` | VERIFIED (HF API `sha`) |
| `best.ckpt` | 708,856,138 bytes, sha256 `9c79ffff6b642b7b0c71d558c935fb3fa33f2788bfb509feead94fafbba2f321` | VERIFIED (HF LFS oid) |
| `config.yaml` | 18,041 bytes, git oid `767ba38f2fa96b47382a1b6ad84df160cabcfc12` | VERIFIED |
| Paper | d'Ascoli et al. 2026, arXiv:2605.04326 (https://arxiv.org/abs/2605.04326) | VERIFIED |
| License | CC-BY-NC-4.0 for code (`LICENSE`, README l.111-113) and weights (HF card front matter `license: cc-by-nc-4.0`) | VERIFIED |

## 1. Install

| Item | Fact | Status / source |
|---|---|---|
| Python | `requires-python = ">=3.11"` | VERIFIED `pyproject.toml` l.11. The HF card badge says 3.10+, which conflicts. GitHub issue #2 reports that 3.10 fails. **Use 3.11 or 3.12.** |
| Torch | `torch>=2.5.1,<2.7`, `torchvision>=0.20,<0.22` | VERIFIED `pyproject.toml` |
| Hard pins | `neuralset==0.0.2`, `neuraltrain==0.0.2`, `exca==0.5.20`, `numpy==2.2.6`, `x_transformers==1.27.20`, `moviepy>=2.2.1`; `transformers` is unpinned | VERIFIED `pyproject.toml`. GitHub issue #65 reports that neuralset 0.0.2 breaks with exca 0.5.26, so **keep exca==0.5.20 exactly**. |
| Install command | `pip install -e .` for inference, or `pip install -e ".[plotting]"` (adds nilearn, nibabel, pyvista, …). Colab uses `uv pip install "tribev2[plotting] @ git+https://github.com/facebookresearch/tribev2.git"` | VERIFIED README l.38-53, `tribe_demo.ipynb` cell 2 |
| Hidden system deps | (a) **`uv`/`uvx` must be on PATH**: transcription shells out to `uvx whisperx …` (`tribev2/eventstransforms.py` l.111-135), and `uvx` downloads the *latest* whisperx at run time unless it is pinned, so the run needs network access. (b) `ffmpeg` for moviepy. (c) `mne` arrives through neuralset and is used for HCP-MMP labels (`tribev2/utils.py` l.13, 214-244). | VERIFIED-CODE |
| HF token | **Required.** The text extractor is `meta-llama/Llama-3.2-3B`, which is gated with manual approval (HF API `gated: "manual"`). The notebook says: "you will have to request access to the Llama-3.2 model using your HuggingFace account" (cell 7). The HF card says: "The text encoder requires access to the gated LLaMA 3.2-3B model … huggingface-cli login". The other backbones are not gated: `facebook/vjepa2-vitg-fpc64-256` (apache-2.0), `facebook/w2v-bert-2.0` (mit), `facebook/dinov2-large` (apache-2.0, configured but not used, see §3). | VERIFIED |
| GPU memory | No official inference figure. The paper ran feature extraction on 128 × V100 32 GB and training on one V100 32 GB (paper §5.3 "Implementation"). The extractors load **one at a time** and each is freed after its features are cached (`main.py` l.59-79, 214-217). Llama-3B and V-JEPA2-g load in **float16** with `device_map="auto"` (neuralset `extractors/text.py` l.336, `extractors/video.py` l.383-385). w2v-BERT loads in fp32 (`audio.py` l.541). WhisperX large-v3 fp16 runs first, as a separate process. GitHub issue #28 reports an OOM on a 14.56 GiB Colab GPU (stage not given). **Measured in P0: peak 13,411 MiB (nvidia-smi), torch max allocated 10,373 MiB on A100-40GB, for 10 s and 40 s clips.** A 24 GB GPU (A10) has headroom; 16 GB is plausible but untested. With `device_map="auto"` a small GPU can silently spill to CPU, which makes runs slower and less reproducible. | VERIFIED (run `smoke_20261117T142354Z`) |
| CPU-only | WhisperX is called with `--compute_type float16` hard-coded, even when `device=cpu` (`eventstransforms.py` l.107-124). CTranslate2 generally rejects fp16 on CPU. **Expect a CPU-only run to fail at transcription unless the transcripts are supplied in advance (§2.4).** | UNVERIFIED |

## 2. Inference API and internal pipeline

### 2.1 Calls (VERIFIED: README l.21-29; `tribev2/demo_utils.py` l.150-392)

```python
from tribev2 import TribeModel
model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache", device="cuda")
df = model.get_events_dataframe(video_path="x.mp4")   # exactly one of text_path / audio_path / video_path
preds, segments = model.predict(events=df)            # preds: (n_kept_TRs, 20484) float32
```

- Accepted suffixes: video `.mp4 .avi .mkv .mov .webm`; audio `.wav .mp3 .flac .ogg`; text `.txt` (`demo_utils.py` l.42-46).
- `from_pretrained` sets `average_subjects=True`, so the model uses the "unseen subject" head (`demo_utils.py` l.218; `main.py` l.356-363).
- `from_pretrained(config_update=...)` accepts config overrides (l.223-224). This is the hook for modality ablation (§5).

### 2.2 What `get_events_dataframe(video_path=…)` does (VERIFIED `demo_utils.py` l.66-95, l.312-320)

1. `ExtractAudioFromVideo`: writes `<video_stem>.wav` **next to the video**, using moviepy defaults (44.1 kHz). **If that .wav already exists, it is reused without checking** (neuralset `events/transforms/audio.py` l.44-51).
2. `ChunkEvents` for Audio and Video: events longer than 60 s are split into chunks of 30–60 s.
3. `ExtractWordsFromAudio` (English is hard-coded): runs **WhisperX large-v3** through `uvx whisperx <wav> --model large-v3 --language en --device cuda|cpu --compute_type float16 --batch_size 16 --align_model WAV2VEC2_ASR_LARGE_LV60K_960H --output_format json` (`eventstransforms.py` l.86-137).
4. The transcript is cached as **`<wav_stem>.tsv` next to the wav**, with columns `text, start, duration, sequence_id, sentence`. **If that .tsv exists, WhisperX is skipped and the file is used** (l.172-184). If `Word` events are already in the dataframe, the whole step is skipped (l.162-164). Words that lack an aligned `start` are dropped (l.147-148).
5. `AddText`, `AddSentenceToWords(max_unmatched_ratio=0.05)`, `AddContextToWords(max_context_len=1024)`, `RemoveMissing`.

**So TRIBE does its own audio extraction and its own ASR.** Our own WhisperX step must either *be* this step (same model, arguments and version) or feed it through the `<stem>.tsv` injection point.

### 2.3 Feature extractors (VERIFIED: HF `config.yaml` `data.*_feature`; paper §5.2)

| Modality | Backbone | Rate | What it sees |
|---|---|---|---|
| Text | `meta-llama/Llama-3.2-3B` (gated), layers [0.5, 0.75, 1.0], group-mean | 2 Hz | Each word with up to 1,024 preceding words of context. Embeddings of the words overlapping each 0.5 s bin are summed. |
| Audio | `facebook/w2v-bert-2.0`, layers [0.5, 0.75, 1.0] | 50 Hz → 2 Hz | Stereo is mean-mixed to mono and resampled to 16 kHz with julius. **Each chunk is z-scored (`norm_audio: true`)** (neuralset `audio.py` l.68-74, 99-110). The features are bidirectional within a chunk (paper §5.2). |
| Video | `facebook/vjepa2-vitg-fpc64-256`, layers [0.5, 0.75, 1.0] | 2 Hz | For each 0.5 s bin, **64 frames sampled by time over the preceding 4 s** (`clip_duration: 4.0`; neuralset `video.py` l.269-292). That is 16 frames/s, so any source of 16 fps or more is fine. The V-JEPA2 processor **resizes the shortest edge to 292 px and center-crops 256×256** (HF `video_preprocessor_config.json`). For 16:9 input the model sees only the central ~49% of the width. Patch tokens are mean-pooled, so spatial position is discarded (paper §5.2). |
| (Image) | `facebook/dinov2-large` is in the config, but `features_to_use: [text, audio, video]` | — | Not used by the released checkpoint. The notebook text claiming "DINOv2 + V-JEPA2" is inaccurate. VERIFIED config. |

Released checkpoint width: video 1408, text 3072. The paper text says 1280 and 2048 (GitHub issue #78). This is cosmetic.

### 2.4 Preprocessing implications for our pipeline

- **fps**: the frame sampling is time-based, so CFR at 30 fps is acceptable. Source frame rate must be at least 16 fps. VERIFIED-CODE.
- **Resolution**: anything with a short edge of 292 px or more gives the backbone its full input. Letterbox/pillarbox bars **enter the 256×256 center crop**. Sides beyond the central square are **never seen** (e.g. a co-founder sitting at the frame edge). VERIFIED-CODE.
- **Audio level**: the audio features are z-scored per chunk, so LUFS normalisation has almost no effect on them. It does affect WhisperX. VERIFIED-CODE.
- **Audio rate**: any integer rate works, because it is resampled internally to 16 kHz. VERIFIED-CODE.
- **Transcript injection**: write our pinned-WhisperX output as `<stem>.tsv` (tab-separated, columns `text,start,duration,sequence_id,sentence`; seconds relative to the file start) beside `<stem>.wav` and `<stem>.mp4` *before* calling `get_events_dataframe`. VERIFIED-CODE.
- **Cache hazard**: features are cached in `cache_folder`, keyed on `study_relative_path + offset + duration` (neuralset `audio.py` l.89-92, and the equivalent in video/text). The sidecar `.wav` and `.tsv` are reused by filename. **If a video file is overwritten under the same name, stale features, audio or transcripts will be used without warning.** Use content-hash filenames (`<sha256[:16]>.mp4`), or one cache folder per input hash. VERIFIED-CODE.

## 3. Output

| Item | Fact | Status / source |
|---|---|---|
| TR | **1.0 s** (measured: T = duration/TR exactly, run `smoke_20261117T142354Z`). `TR = 1/neuro.frequency` and `neuro.frequency: 1.0`. Internally the model runs at 2 Hz and is average-pooled to 1 Hz (`model.py` l.104, l.174-175). | VERIFIED `main.py` l.145-147; config; notebook cell 5 "1 TR = 1 second" |
| Shape | `(n_kept_TRs, 20484)` float32 | VERIFIED notebook output `(53, 20484)`; measured (10, 20484) for 10 s and (40, 20484) for 40 s clips, all finite (run `smoke_20261117T142354Z`) |
| Mesh | **fsaverage5, 20,484 vertices = 10,242 left followed by 10,242 right** (left/right `vstack`) | VERIFIED paper §5.1; `utils_fmri.py` l.200-226 |
| Medial wall | **Predicted, not masked.** The output includes medial-wall vertices. Schaefer-400 fs5 labels 870 left-hemisphere vertices as `Background+FreeSurfer_Defined_Medial_Wall` (checked locally). | VERIFIED (annot inspected) |
| Subject | Average or "unseen" subject only. Per-subject heads are not released (GitHub issue #62). **Correction (v2.4 G-D032):** a subcortical checkpoint *is* released as `facebook/tribev2-subcortical` (sha `214a5d9`, 2026-05-13, cc-by-nc-4.0; maintainer closed #23 on 2026-05-21; issue #79 is out of date), see `docs/tribe_known_issues.md` #12. We do not use it: ENH-003 is DEFERRED (DECISIONS, G-D032 PI resolution; re-proposable after P4 as its own exploratory gate with ≤ 6 pre-fixed bilateral structures, a pinned checkpoint, never in M-models). P9 limitation: "cortical model only; a subcortical checkpoint exists but is not used". | VERIFIED `demo_utils.py` l.218; issues; HF API (#12 in tribe_known_issues.md) |
| Units | Training targets were **z-scored per session and detrended per vertex** (config `neuro.cleaning: standardize: zscore_sample, detrend: true`; paper §5.8 "Rescaling and detrending"). Predictions are therefore in relative z-units: there is no physical BOLD scale and no meaningful absolute baseline. | VERIFIED |
| HRF / lag | **Built in.** "Predictions … are offset by 5 seconds in the past, in order to compensate for the hemodynamic lag" (README l.32). The config sets `neuro.offset: 5.0`. Paper §5.8: "to predict a window [0,T] of fMRI, TRIBE takes as input a window [−5, T−5] of stimuli". A third-party lag scan against real BOLD peaked at 0 s (GitHub issue #78). However, the paper's visual localiser (§5.9 "Contrast maps") reads the response at **t = 5 s** after a 1 s image flash. **Measured in P0 (impulse − control): peak at lag 0 TR in output time for a 1 s flash (early visual) and a 1 s speech burst (auditory), i.e. BOLD at ≈ +5 s real time; responses spread up to ~4 s before onset (non-causal).** See "Measured in P0". | VERIFIED (run `smoke_20261117T142354Z`) |
| Context window | `duration_trs: 100`, so clips are processed in independent 100 s windows. TRs past the end of the stimulus are dropped (`remove_empty_segments=True`, `demo_utils.py` l.366-378). Clips longer than 100 s are split into windows that share no context. Clips longer than 60 s are also chunked for audio/video features. **Expect onset and offset transients, and discontinuities at 60/100 s boundaries in T2.** | VERIFIED-CODE |

## 4. Accuracy and reliability maps

- No per-vertex accuracy, noise-ceiling or reliability map ships with the code or the weights. HF repo files: `.gitattributes, LICENSE, README.md, best.ckpt, config.yaml`. VERIFIED.
- The paper reports encoding scores by HCP-MMP parcel (Fig. 2A, Fig. 8) and per dataset. These are figures only, not data. The paper also reports group-level R ≈ 0.4 on HCP 7T movies. VERIFIED (paper §2.1–2.3).
- TRIBE's own ROI helper uses **HCP-MMP1 (Glasser)**, fetched with `mne.datasets.fetch_hcp_mmp_parcellation`. It is defined on fsaverage and subsampled to fs5 by taking the first 10,242 vertices per hemisphere (`tribev2/utils.py` l.214-244). The paper (§5.9 "Regions of interest") says, verbatim: "FFA, EBA, PPA, VWFA, A5, 45, STS, TPJ, MTG respectively correspond to the following ROI labels: FFC, V4t, PH, A5, 45, STSv, PGi, TE1a". That is 9 names for 8 labels, so the list is misaligned in the source. Use FFA = FFC, EBA = V4t, PPA = PH, STS = STSv, TPJ = PGi, MTG = TE1a, Broca = 45, A5 = A5. VWFA is unresolved: check `tribev2/plotting/cortical_pv.py` usage. VERIFIED (text; the mapping inconsistency is in the source).
- **A reliability mask therefore has to be built by us.** Options: (a) run TRIBE on a public held-out naturalistic dataset with real fMRI (HCP 7T movie or NNDb, both zero-shot test sets in the paper) and compute per-vertex r; (b) use the coarse paper-figure HCP-parcel scores. UNVERIFIED (to do).
  **Resolved for the localisation outputs (D-053, G-D032 c3 Neuro G2):** neither option is available before the lock ((a) needs a GPU run on real-fMRI data; (b) are figures, not data), so the unreliable-vertex set is fixed anatomically and label-free as config `localize.reliability_mask`: bilateral HCP-MMP1 OFC, pOFC, 11l, 13l, TGd, TGv (susceptibility signal-dropout cortex in gradient-echo BOLD) minus the union medial wall = 732 fs5 vertices, sha256 pinned and tested (`tests/test_reliability_mask.py`). Option (a) remains a possible post-P4 exploratory replacement, by a DECISIONS entry only.

## 5. Modality ablation

- **Training used modality dropout**: p = 0.3 per modality, implemented by zeroing the *projected* features (`model.py` l.211-213; config `modality_dropout: 0.3`; paper §5.3).
- **At inference, a modality missing from the batch is replaced by zeros of the same projected shape** (`model.py` l.188-193). That is exactly the training dropout state, so ablation is in-distribution for the model. VERIFIED-CODE.
- Ways to ablate:
  - Drop an extractor: `TribeModel.from_pretrained(..., config_update={"data.features_to_use": ["audio","video"]})`. The checkpoint projectors are still built from `model_build_args`, so the dropped modality becomes zeros. VERIFIED-CODE; run in P0.
  - Remove event types: drop `Word` rows from `df` (no text), or pass `audio_path=` (no Video events). The notebook log shows "Removing extractor video as there are no corresponding events" (cell 14). `get_audio_and_text_events(audio_only=True)` skips ASR (`demo_utils.py` l.66-91). VERIFIED.
- Caveats:
  - The paper's Fig. 7 unimodal results come from *retrained* unimodal models, not from inference-time zeroing. Our ablations are a different estimand. VERIFIED (paper §2.8).
  - `text_path` input is not "text-only": it goes through gTTS speech synthesis and then ASR, so audio features are present (`demo_utils.py` l.98-130).
  - "Text-removed" still carries speech content in the w2v-BERT features.

## 6. Determinism

- `seed: 33` is applied only in `run()`/training (`main.py` l.638-641). `predict()` uses `torch.inference_mode()` and eval mode, and the model has no stochastic layers active at inference. VERIFIED-CODE.
- Possible sources of run-to-run difference:
  - fp16 backbones on GPU (non-deterministic cuBLAS/cuDNN kernels);
  - `device_map="auto"` placement;
  - **unpinned WhisperX through `uvx`**, plus pyannote VAD;
  - unpinned `transformers`.

  A third-party report finds encoding scores identical to within about 3e-4 across 7 configurations, and transformers 4.57 vs 5.16 give Δ < 1e-5 (GitHub issue #78). **Measured in P0 (run `smoke_20261117T142354Z`): two fresh-cache runs of the same 10 s clip differ by max abs 3.57e-3 (r = 0.999994; prediction SD 0.14) — fails a 1e-4 tolerance. Re-predicting from cached features is bit-identical (diff 0.0), so all run-to-run variation comes from GPU feature extraction (fp16 backbones).** VERIFIED.
- **Features are disk-cached, so a "rerun" that hits the cache only tests the 1.1 B-parameter head.** A determinism test must clear the cache (or use a fresh `cache_folder`) and delete the `.wav`/`.tsv` sidecars. VERIFIED-CODE.

## 7. Licensing implications

- CC-BY-NC-4.0 covers the code and weights: **non-commercial research use only, with attribution** (cite arXiv:2605.04326). The GitHub issue tracker contains several commercial-licence inquiries (#25, #45, #49, #66, #82) and one claimed violation (#48). Any use for investment or startup-screening purposes, or a commercial "pitch-scoring" tool built from this study, is **not licensed**. VERIFIED.
- Llama 3.2 Community License and Acceptable Use Policy apply to the text backbone. The gated access terms must be accepted per user. VERIFIED (gated: manual).
- The HCP-MMP atlas requires accepting its terms (`accept=True` in mne). Schaefer/Yeo (CBIG) are MIT-style. VERIFIED (CBIG URLs reachable).

## 8. Atlases on fsaverage5

| Atlas | How to get it on fs5 | Status |
|---|---|---|
| Destrieux (a2009s) | `nilearn.datasets.fetch_atlas_surf_destrieux()`, native fsaverage5 (nilearn 0.14.1 `datasets/atlas.py` l.2020-2057). Label 0 / "Medial_wall" is the medial wall. | VERIFIED |
| Schaefer-400 (7Net) | **Not on surface in nilearn**: `fetch_atlas_schaefer_2018` is MNI volumetric only (nilearn 0.14.1 l.2372+). Use the CBIG FreeSurfer annot `stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/FreeSurfer5.3/fsaverage5/label/{lh,rh}.Schaefer2018_400Parcels_7Networks_order.annot` (HTTP 200). It has 201 labels per hemisphere including medial wall; 870 medial-wall vertices on the left. | VERIFIED |
| Yeo-7 | nilearn `fetch_atlas_yeo_2011` is MNI volumetric only. Derive Yeo-7 from the Schaefer-400-7Net label names (`7Networks_LH_Vis_1` → Vis), or use the CBIG fs5 annot `…/Yeo_JNeurophysiol11_SplitLabels/fsaverage5/label/?h.Yeo2011_7Networks_N1000.split_components.annot` (HTTP 200). | VERIFIED |
| HCP-MMP1 (Glasser) | `tribev2.utils.get_hcp_labels(mesh="fsaverage5")`, the same ROI definitions the paper uses | VERIFIED |
| Mesh nesting | **fsaverage5 vertices are exactly the first 10,242 vertices of each fsaverage hemisphere.** We checked locally that the Schaefer fs7 annot `[:10242]` equals the fs5 annot at 100%. TRIBE uses the same trick (`utils_fmri.py` l.240-243). **Nearest-vertex resampling is unnecessary** for fsaverage-family annots. | VERIFIED |

## 9. Built-in positive controls (paper)

The model reproduces the following in silico (paper §2.5–2.6, Figs 4–5; "unseen subject" mode):

- Visual IBC localisers: faces → FFC, places → PH, bodies → V4t/EBA, characters → VWFA.
- Speech vs non-speech segments ("Bang"), using Algonauts segments.
- Sentences vs word lists, complex vs simple sentences.
- Emotional vs physical pain → TPJ and MTG.

Contrast methods: for images, the response at t = 5 s minus the other categories; for language, a nilearn `FirstLevelModel` GLM on the predictions. VERIFIED.

## 10. Measured in P0 (run `smoke_20261117T142354Z`)

Source: `outputs/runs/smoke_20261117T142354Z/smoke_report.md` and `metrics.json`; full artifacts on the pod at `/work/yct/runs/smoke_20261117T142354Z/`.

| Item | Measured | Status |
|---|---|---|
| Hardware / stack | Lambda gpu_1x_a100_sxm4 (A100-SXM4-40GB, driver 570.148.08); Python 3.11.18; torch 2.6.0+cu124; exca 0.5.20; neuralset/neuraltrain 0.0.2; numpy 2.2.6; transformers 5.17.0 (unpinned upstream) | VERIFIED |
| Weights | `snapshot_download(revision=f894e783…)`, `best.ckpt` sha256 matches §0; TRIBE loaded from the local snapshot dir | VERIFIED |
| Backbone revisions actually used (HF `main` on 2026-11-17) | vjepa2-vitg-fpc64-256 `875c192b7b704b87d1e1d99345769632dd5f739a`; w2v-bert-2.0 `da985ba0987f70aaeb84a80f2851cfac8c697a7b`; Llama-3.2-3B `13afe5124825b4f3751f836b40dafda64c1ed062` | VERIFIED |
| Offline inference | With these in the HF cache, `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` runs end to end (fresh feature cache) | VERIFIED |
| Transcript injection | `<stem>.tsv` beside the video is used; with `uvx` removed from PATH and the ASR entry point patched to raise, ASR is never called | VERIFIED |
| Peak VRAM | 13,411 MiB (nvidia-smi, 1 s sampling); torch max allocated 10,373 MiB | VERIFIED |
| Runtime | ~59 s for a 10 s clip, ~200 s for a 40 s clip (≈5 s wall per s of video; V-JEPA2 dominates); model load 2 s; first run +26 s for backbone downloads | VERIFIED |
| Shape / TR | (T, 20484) float32, T = duration / 1.0 s, finite | VERIFIED |
| Latency | impulse − control, Destrieux ROIs: visual (Pole_occipital + S_calcarine) peak at output t = 15 s for flash at 15 s; auditory (G_temp_sup-G_T_transv + S_temporal_transverse) peak at t = 25 s for speech at 25 s → **L = 0 TR**. Visual response rises from t ≈ 11 s (pre-onset leakage via the temporal transformer). The auditory ROI responds to the flash too, and more strongly. The speech response is a single-TR spike, likely carried by the text features. | VERIFIED |
| Output-time semantics | In training the neuro extractor reads BOLD at `start + 5 s` (neuralset `extractors/neuro.py` l.358), so prediction at output time t ≈ BOLD at t + 5 s | VERIFIED-CODE |
| Determinism | fresh cache: max abs 3.6e-3 (fails 1e-4); cached features: 0.0 | VERIFIED |
| Pitfall | Driving the box with `ssh … bash -s`: `ffmpeg` reads stdin and eats the script; always use `-nostdin` | VERIFIED |
| Not measured | CPU-only behaviour; 16 GB GPUs; clips > 60 s (chunking) and > 100 s (windowing) | UNVERIFIED |

