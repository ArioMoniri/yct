# P0 TRIBE v2 smoke test — run `smoke_20261117T142354Z`

Date (UTC): 2026-11-17, ~14:05–14:45. Owner: Modeling Engineer. Full artifacts (npy predictions, logs,
clips, code copy, pip freeze, nvidia-smi): pod `/work/yct/runs/smoke_20261117T142354Z/` (10 MB).
This directory holds text summaries only: `metrics.json`, latency CSVs, this report.

## Verdict (ROADMAP P0 `test_tribe_smoke`)

| Check | Result | Value |
|---|---|---|
| Shape (T, 20484) | **PASS** | smoke (10, 20484); impulse (40, 20484); control (40, 20484) |
| T within ±1 of duration/TR | **PASS** | 10 s → T=10; 40 s → T=40 (TR = 1.0 s) |
| Values finite | **PASS** | all runs; dtype float32 |
| Peak VRAM logged | **PASS** | max 13,411 MiB (nvidia-smi 1 s sampling); torch max allocated 10,373 MiB |
| No ASR / no `uvx` | **PASS** | `uvx` absent from PATH, ASR entry point monkeypatched to raise; never triggered; transcripts from our `<stem>.tsv` (17 words smoke, 2 words impulse) |
| Pinned weights | **PASS** | `best.ckpt` sha256 `9c79ffff…f321` matches doc |
| Offline run (`HF_HUB_OFFLINE=1`) | **PASS** | fresh cache, exit 0, same shape; no network fetch needed |
| Determinism ≤ 1e-4 (fresh cache) | **FAIL** | max abs diff 3.57e-3 (run1 vs run2), 2.64e-3 (run1 vs offline run); r = 0.999994; pred std 0.14 |
| Latency measured | **PASS (measured)** | peak at lag 0 TR in output time for both ROIs (see §Latency; caveats) |

Determinism root cause: re-predicting from the **cached** features gives a max abs diff of exactly
0.0 (head-only, twice, and vs run1). The run-to-run difference comes entirely from feature
extraction (fp16 backbones on GPU, non-deterministic kernels). Relative size ≈ 2.5% of one
prediction SD at the worst vertex/TR. Recommendation for P4: extract features once per clip and
cache them by content hash; treat ~4e-3 as the floor of the reproducibility tolerance
(test threshold 1e-4 is not reachable without deterministic backbone kernels). Ticket needed.

## Environment

- GPU: Lambda `gpu_1x_a100_sxm4` — NVIDIA A100-SXM4-40GB, driver 570.148.08; Ubuntu 22.04.5; 30 vCPU, 216 GB RAM.
- Python 3.11.18 (uv venv); torch 2.6.0+cu124 (CUDA 12.4); torchvision 0.21.0; exca 0.5.20;
  neuralset 0.0.2; neuraltrain 0.0.2; numpy 2.2.6; x-transformers 1.27.20; moviepy 2.2.1;
  **transformers 5.17.0 (unpinned upstream)**; huggingface-hub 1.16.1; julius 0.2.8; nilearn 0.14.1; pandas 3.1.1.
- ffmpeg 4.4.2, espeak-ng 1.50.

### Resolved revisions (all recorded; TRIBE loaded from a local snapshot)

| Repo | Revision |
|---|---|
| facebookresearch/tribev2 (code) | `af58661791a351a448a489042a28f6c37e1c14b7` |
| facebook/tribev2 (weights, `snapshot_download(revision=…)`) | `f894e783020944dcd96e5568550afe2aa9743f9f`; best.ckpt sha256 `9c79ffff6b642b7b0c71d558c935fb3fa33f2788bfb509feead94fafbba2f321`; config.yaml sha256 `a17212a257dfd91424e20a5fa8640d107fbbf79e842b6b2d72d17d24399dc9ef` |
| facebook/vjepa2-vitg-fpc64-256 | `875c192b7b704b87d1e1d99345769632dd5f739a` (HF cache refs/main = snapshot) |
| facebook/w2v-bert-2.0 | `da985ba0987f70aaeb84a80f2851cfac8c697a7b` |
| meta-llama/Llama-3.2-3B | `13afe5124825b4f3751f836b40dafda64c1ed062` (gated access OK with project HF token) |

TRIBE itself was loaded with `TribeModel.from_pretrained(<local snapshot dir>)`, so the HF-main
problem in `from_pretrained` is bypassed. The backbones are still fetched at whatever `main` is on
first use; pin them for P4 by pre-populating the HF cache at the revisions above and running with
`HF_HUB_OFFLINE=1` (shown to work in this run).

## Stimuli (generated on the GPU box, `src/yct/tribe_run/make_test_clips.sh`)

- `smoke.mp4`: 10 s, testsrc2 640x360 @30 fps, espeak-ng (en-us, 160 wpm) sentence of 17 words starting at 0.5 s, 16 kHz mono AAC. sha256[:16] `e9ecef6c7a04e828`.
- `impulse.mp4`: 40 s black 640x360 @30; full-white frames for t ∈ [15, 16); 1 s speech burst ("Hello there.") at t = 25 s; digital silence otherwise. sha256[:16] `29940cf2c80cdbc7`.
- `control.mp4` (added): 40 s black, silent, empty transcript — used to subtract the stimulus-independent drift/edge transients from the impulse response.
- The 20 s talking-face clip was skipped (not available).
- Transcripts: hand-made `<stem>.tsv` (text, start, duration, sequence_id, sentence); word times uniform over the espeak utterance (approximate).

## Runtime (A100-40GB, fresh empty cache each)

| Run | Clip | events+predict wall | model load | peak VRAM (smi) |
|---|---|---|---|---|
| smoke1 | 10 s | 84.9 s (includes first-time backbone download) | 2.1 s | 12,889 MiB |
| smoke2 | 10 s | 59.2 s | 2.1 s | 12,889 MiB |
| smoke3 (offline) | 10 s | 58.9 s | 2.1 s | 12,889 MiB |
| impulse | 40 s | 204.3 s | 2.1 s | 12,889 MiB |
| control | 40 s | 199.5 s | 2.1 s | 13,411 MiB |

Roughly 5 s of wall time per second of video, dominated by V-JEPA2-g encoding (~2.4 s per
0.5 s bin… 80 bins for 40 s). Projection for T1 (58 s clips): ~5 min per clip on an A100.
Peak VRAM < 20 GB, so per v2.md §3 an A10 (24 GB) becomes allowed (`A10_ALLOWED=1` needs the human/orchestrator decision).

## Latency (§6)

ROIs: Destrieux a2009s on fsaverage5 (nilearn 0.14.1), both hemispheres. Visual = Pole_occipital +
S_calcarine (655 vertices). Auditory = G_temp_sup-G_T_transv + S_temporal_transverse (130 vertices).
"Output time" = segment start on the stimulus clock. In training, neuralset's neuro extractor reads
BOLD at `start + offset` with `neuro.offset = 5.0` (`neuralset/extractors/neuro.py` l.358), so a
prediction at output time t estimates BOLD at real time t + 5 s.

Primary (impulse − control, `latency_*_ctrlsub.csv`):

| ROI | Event onset | Peak output time | Lag (TR) | Peak − pre-onset baseline |
|---|---|---|---|---|
| Visual (flash) | 15 s | 15 s | **0** | +0.061 (peak 0.092) |
| Auditory (speech burst) | 25 s | 25 s | **0** | +0.253 (peak 0.237) |

Caveats (important for the window W in P4):

- **Lag L = 0 TR in output time** for both events: the 5 s offset already absorbs the hemodynamic
  delay. In real time this is BOLD at about +5 s, which matches the paper's "read at t = 5 s" localiser.
- The visual response is **broad and non-causal**: it starts rising at t = 11–12 s (3–4 s *before*
  the flash), plateaus 13–18 s and decays by ~22 s. TRIBE's temporal transformer sees the whole 100 s
  window, so stimulus effects leak backwards in time by up to ~4 s.
- The auditory ROI also responds strongly to the **flash** (impulse − control 0.20–0.29 at t = 12–17 s,
  larger than its speech response). The ROI is not modality-selective in the predictions.
- The speech-burst response is a **single-TR spike** at t = 25 s, present in both ROIs (visual +0.079
  at 25 s). It is probably driven by the text (Word) features, which exist only in that TR; the
  audio-only contribution is not separable with this design.
- The raw impulse time courses (no control subtraction, `latency_*_raw.csv`) are dominated by slow drift and
  an end-of-clip rise in the auditory ROI (peak at the last TR, 39 s). Window peak picking on the raw
  courses gives +10 s (visual) and +14 s (auditory); these are artifacts, not latencies.
- For `config.yaml` `window.default_start_tr = max(5, 4 + L + 1)` with L = 0 → **5** (unchanged).

## Commands run (summary)

1. Pod: `ssh-keygen -t ed25519 -f /root/.ssh/yct_lambda`; sandbox: `POST /api/v1/ssh-keys {"name":"yct-pod"}`.
2. `python infra/lambda_gpu.py launch --type gpu_1x_a100_sxm4 --name yct-smoke --max-hours 2 --ssh-key yct-pod` (id `06e21786a5a34d8abae33e50a4b0e39b`, us region, $1.99/h); `python infra/lambda_gpu.py watch` in background.
3. HF token piped pod→box from SSM (`/yct/hf_token`) into `~/.cache/huggingface/token` (never echoed).
4. Box: `bash code/remote_setup.sh ~/yct` (apt ffmpeg espeak-ng; uv in `~/.uvbin`; clone + checkout pinned commit; `uv venv -p 3.11`; `uv pip install -e ./tribev2 "torch>=2.5.1,<2.7" exca==0.5.20 nilearn pandas`; `snapshot_download(revision=f894e78…)`; sha256 check → `SETUP_OK`).
5. `bash code/make_test_clips.sh ~/yct/clips`.
6. `python code/run_clip.py --video <clip> --cache <fresh dir> --out res/<name> --weights weights` for smoke1, impulse, smoke2, smoke3 (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`), control.
7. Head-only determinism: `from_pretrained(weights, cache_folder=cache_smoke1/feat)`, predict twice → max abs 0.0.
8. `python code/latency.py res/impulse.npy res/impulse.segments.csv res/raw` and `… res/ctrl res/control.npy`.
9. scp box → pod `/work/yct/runs/smoke_20261117T142354Z/`; `python infra/lambda_gpu.py terminate --id 06e21786…`; `reap`; `list` (terminating → none alive); `spent` = $0.77.

## Cost

GPU instance alive ~23 min; ledger `spent` = **$0.77** (cap for this task $12). Instance terminated.

## Open items / tickets to open

1. Determinism threshold 1e-4 fails (3.6e-3) due to backbone fp16 feature extraction; head is exactly deterministic. Decide the tolerance or enforce cache-once-reuse.
2. `transformers` is unpinned upstream (5.17.0 used) → pin in `requirements.lock`.
3. Backbone revisions must be pinned (cache pre-population + `HF_HUB_OFFLINE=1`).
4. Pitfall: when driving the box with `ssh … bash -s` (script on stdin), every `ffmpeg` call must use `-nostdin` (or `</dev/null`), or ffmpeg eats the rest of the script. `make_test_clips.sh` should add `-nostdin` (done after this run, see code).
