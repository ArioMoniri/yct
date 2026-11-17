# P0 GPU re-run `p0rerun_20261117T155528Z` (FIX-C3-ENG item F)

Instance `e1c5cf0525cd4f5f8406bceee3a19aba` (gpu_1x_a100_sxm4), spent $1.2035, alive after: [], instance heartbeats in ledger: 63.
Steps (rc): {'setup': 0, 'smoke': 0, 'long70': 0, 'long110': 0}.

## Cached-feature determinism (D-038 gate: exact)

- smoke A extracted (cache_reused=False); B and C re-predicted from the cache (cache_reused=True, True).
- predictions bit-identical A==B: **True**, A==C: **True** (sha256 3de2734cd5173f7c); feature sha256 equal: True.

- reliability runs, cached rerun bit-identical: {}

## Fresh re-extraction reliability (D-038 gate: >= 0.99 per feature)

- smoke_c: reliability_min **0.9997712780907566** over 17 arrays, gate pass **True**; predictions max|diff| 0.0008518733084201813, r 0.9999994413684343, reliability 0.9999994401001876.
  - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999988231553192, max|diff| 0.25 (17 arrays)
- long70: reliability_min **0.9995636471626658** over 172 arrays, gate pass **True**; predictions max|diff| 0.001068606972694397, r 0.9999991357248218, reliability 0.9999991339910336.
  - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999921966658522, max|diff| 0.3125 (172 arrays)

## Clips (shape, T, chunk/context boundaries, VRAM)

| run | dur s | shape | T ok | segments first..last | Audio/Video chunks [start, dur] | words (min..max start, >dur) | peak VRAM MiB (smi / torch alloc) | extract s |
|---|---|---|---|---|---|---|---|---|
| smoke_a | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 12889 / 10297 | 62.2 |
| smoke_b | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 1179 / 734 | None |
| smoke_c | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 12901 / 10300 | 58.9 |
| long70 | 70.0 | [70, 20484] | True | 70: 0.0..69.0 | {'Audio': [[0.0, 70.0]], 'Video': [[0.0, 70.0]]} | 172 (0.5..67.984, 0) | 12931 / 10301 | 364.4 |
| long110 | 110.0 | [229, 20484] | False | 229: 0.0..228.0 | {'Audio': [[0.0, 60.0], [60.0, 50.0]], 'Video': [[0.0, 60.0], [60.0, 50.0]]} | 552 (0.5..228.57, 276) | 12889 / 10297 | 591.0 |

## Offline / pins

- offline=True, env {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'}
- backbone revisions (refs/main == pinned, checked before running): {'facebook/vjepa2-vitg-fpc64-256': '875c192b7b704b87d1e1d99345769632dd5f739a', 'facebook/w2v-bert-2.0': 'da985ba0987f70aaeb84a80f2851cfac8c697a7b', 'meta-llama/Llama-3.2-3B': '13afe5124825b4f3751f836b40dafda64c1ed062', 'en_core_web_lg': '3.8.0'}

Artifacts: pod `/work/yct/runs/<run_id>/` (res/, fc/, clips/) and feature cache entries under `/work/yct/cache/`; sha256 in SHA256SUMS, FC_SHA256SUMS and cache_manifest.json here.

## Corrections (BUG-026)

Appended by `scripts/p0_rerun_report.py --append-corrections BUG-026`; the text above is the original report, unchanged. Corrected summary: `summary_bug026.json` (the original summary.json is kept).

- the run exited with code **1** (NON-ZERO); the original 'Steps (rc)' line lists only the per-step return codes and did not disclose it.
- summary/report were produced by a `--collect-only` recovery at 86fcddae72e6951cfbecc5bd2970de4bb21c89c1, not at the run sha 0e3ed3ee313c1c252f6bcdfc950957280f264494 (SHA MISMATCH).
- the run started from a dirty working tree (git_dirty True).

### Regenerated report (fixed labels)

> # P0 GPU re-run `p0rerun_20261117T155528Z` (FIX-C3-ENG item F)
>
> Instance `e1c5cf0525cd4f5f8406bceee3a19aba` (gpu_1x_a100_sxm4), spent $1.2035, alive after: [], instance heartbeats in ledger: 63.
> Steps (rc): {'setup': 0, 'smoke': 0, 'long70': 0, 'long110': 0}.
>
> ## Provenance (BUG-026)
>
> - run exit code **1** (NON-ZERO: the run did not finish cleanly; see stdout.log); git_sha 0e3ed3ee313c1c252f6bcdfc950957280f264494, git_dirty: **True**.
> - summary/report produced by a separate `--collect-only` recovery at git sha 86fcddae72e6951cfbecc5bd2970de4bb21c89c1 (cmd ["env", "YCT_RUN_DIR=<this run dir>", "python", "scripts/gpu_p0_rerun.py", "--collect-only"]); **SHA MISMATCH** with the run sha 0e3ed3ee313c1c252f6bcdfc950957280f264494.
>
> ## Cached-feature determinism (D-038 gate: exact)
>
> - smoke A extracted (cache_reused=False); B and C re-predicted from the cache (cache_reused=True, True).
> - predictions bit-identical A==B: **True**, A==C: **True** (sha256 3de2734cd5173f7c); feature sha256 equal: True.
>
> - reliability runs, cached rerun bit-identical: not run
>
> ## Fresh re-extraction reliability (D-038 gate: >= 0.99 per feature)
>
> - smoke_c: reliability_min **0.9997712780907566** over 17 arrays, gate pass **True**; predictions max|diff| 0.0008518733084201813, r 0.9999994413684343, reliability 0.9999994401001876.
>   - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999988231553192, max|diff| 0.25 (17 arrays)
> - long70: reliability_min **0.9995636471626658** over 172 arrays, gate pass **True**; predictions max|diff| 0.001068606972694397, r 0.9999991357248218, reliability 0.9999991339910336.
>   - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999921966658522, max|diff| 0.3125 (172 arrays)
>
> ## Clips (shape, T, chunk/context boundaries, VRAM)
>
> | run | dur s | shape | T ok | segments first..last | Audio/Video chunks [start, dur] | words (min..max start, >dur) | peak VRAM MiB (smi / torch alloc) | extract s |
> |---|---|---|---|---|---|---|---|---|
> | smoke_a | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 12889 / 10297 | 62.2 |
> | smoke_b | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 1179 / 734 | None |
> | smoke_c | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 12901 / 10300 | 58.9 |
> | long70 | 70.0 | [70, 20484] | True | 70: 0.0..69.0 | {'Audio': [[0.0, 70.0]], 'Video': [[0.0, 70.0]]} | 172 (0.5..67.984, 0) | 12931 / 10301 | 364.4 |
> | long110 | 110.0 | [229, 20484] | False | 229: 0.0..228.0 | {'Audio': [[0.0, 60.0], [60.0, 50.0]], 'Video': [[0.0, 60.0], [60.0, 50.0]]} | 552 (0.5..228.57, 276) | 12889 / 10297 | 591.0 |
>
> ## Offline / pins
>
> - offline=True, env {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'}
> - backbone revisions (refs/main == pinned, checked before running): {'facebook/vjepa2-vitg-fpc64-256': '875c192b7b704b87d1e1d99345769632dd5f739a', 'facebook/w2v-bert-2.0': 'da985ba0987f70aaeb84a80f2851cfac8c697a7b', 'meta-llama/Llama-3.2-3B': '13afe5124825b4f3751f836b40dafda64c1ed062', 'en_core_web_lg': '3.8.0'}
>
> Artifacts: pod `/work/yct/runs/<run_id>/` (res/, fc/, clips/) and feature cache entries under `/work/yct/cache/`; sha256 in SHA256SUMS, FC_SHA256SUMS and cache_manifest.json here.
