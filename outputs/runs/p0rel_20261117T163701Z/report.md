# P0 GPU re-run `p0rel_20261117T163701Z` (FIX-C3-ENG item F)

Instance `daa44e473dd8454bb8a8a8ebdcc639a0` (gpu_1x_a100_sxm4), spent $1.7382, alive after: [], instance heartbeats in ledger: 95.
Steps (rc): {'setup': 0, 'rel_smoke': 0, 'rel_long70': 0, 'rel_long110': 0}.

## Cached-feature determinism (D-038 gate: exact)

- smoke A extracted (cache_reused=None); B and C re-predicted from the cache (cache_reused=None, None).
- predictions bit-identical A==B: **False**, A==C: **False** (sha256 None); feature sha256 equal: True.

- reliability runs, cached rerun bit-identical: {'smoke': {'bit_identical': True, 'rerun_cache_reused': True}, 'long70': {'bit_identical': True, 'rerun_cache_reused': True}, 'long110': {'bit_identical': True, 'rerun_cache_reused': True}}

## Fresh re-extraction reliability (D-038 gate: >= 0.99 per feature)

- rel_smoke: reliability_min **0.9997097081718677** over 19 arrays, gate pass **True**; predictions max|diff| 0.001660376787185669, r 0.999999069855893, reliability 0.9999990667989792.
  - `neuralset.extractors.audio.Wav2VecBert._get_data,release/frequency=2,name=Wav2VecBert,cache_n_layers=20,infra.version=release-69924142`: reliability 1.0, max|diff| 0.0 (1 arrays)
  - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999991796535215, max|diff| 0.21875 (17 arrays)
  - `neuralset.extractors.video.HuggingFaceVideo._get_data,release/frequency=2,clip_duration=4,infra.version=release,name=HuggingFaceVideo,image={cache_n_layers=20,name=HuggingFaceImage,model_nam...33-23256cbb`: reliability 1.0, max|diff| 0.0 (1 arrays)
- rel_long70: reliability_min **0.9995379950056881** over 174 arrays, gate pass **True**; predictions max|diff| 0.0016425549983978271, r 0.9999986892593727, reliability 0.9999986773466241.
  - `neuralset.extractors.audio.Wav2VecBert._get_data,release/frequency=2,name=Wav2VecBert,cache_n_layers=20,infra.version=release-69924142`: reliability 1.0, max|diff| 0.0 (1 arrays)
  - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999918742208835, max|diff| 0.375 (172 arrays)
  - `neuralset.extractors.video.HuggingFaceVideo._get_data,release/frequency=2,clip_duration=4,infra.version=release,name=HuggingFaceVideo,image={cache_n_layers=20,name=HuggingFaceImage,model_nam...33-23256cbb`: reliability 1.0, max|diff| 0.0 (1 arrays)
- rel_long110: reliability_min **0.9913476551699258** over 556 arrays, gate pass **True**; predictions max|diff| 0.009696274995803833, r 0.9999681117883004, reliability 0.999967745523739.
  - `neuralset.extractors.audio.Wav2VecBert._get_data,release/frequency=2,name=Wav2VecBert,cache_n_layers=20,infra.version=release-69924142`: reliability 1.0, max|diff| 0.0 (2 arrays)
  - `neuralset.extractors.text.HuggingFaceText._get_data,release/cache_n_layers=20,name=HuggingFaceText,infra.version=release,model_name=meta-llama-Llama-3.2-3B-57aba842`: reliability 0.9999540086339564, max|diff| 1.0625 (552 arrays)
  - `neuralset.extractors.video.HuggingFaceVideo._get_data,release/frequency=2,clip_duration=4,infra.version=release,name=HuggingFaceVideo,image={cache_n_layers=20,name=HuggingFaceImage,model_nam...33-23256cbb`: reliability 1.0, max|diff| 0.0 (2 arrays)

## Clips (shape, T, chunk/context boundaries, VRAM)

| run | dur s | shape | T ok | segments first..last | Audio/Video chunks [start, dur] | words (min..max start, >dur) | peak VRAM MiB (smi / torch alloc) | extract s |
|---|---|---|---|---|---|---|---|---|
| rel_smoke | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 12931 / 10301 | 58.9 |
| rel_smoke_rerun | 10.0 | [10, 20484] | True | 10: 0.0..9.0 | {'Audio': [[0.0, 10.0]], 'Video': [[0.0, 10.0]]} | 17 (0.5..5.984, 0) | 1179 / 734 | None |
| rel_long70 | 70.0 | [70, 20484] | True | 70: 0.0..69.0 | {'Audio': [[0.0, 70.0]], 'Video': [[0.0, 70.0]]} | 172 (0.5..67.984, 0) | 12931 / 10301 | 361.7 |
| rel_long70_rerun | 70.0 | [70, 20484] | True | 70: 0.0..69.0 | {'Audio': [[0.0, 70.0]], 'Video': [[0.0, 70.0]]} | 172 (0.5..67.984, 0) | 1179 / 734 | None |
| rel_long110 | 110.0 | [229, 20484] | False | 229: 0.0..228.0 | {'Audio': [[0.0, 60.0], [60.0, 50.0]], 'Video': [[0.0, 60.0], [60.0, 50.0]]} | 552 (0.5..228.57, 276) | 12925 / 10300 | 608.7 |
| rel_long110_rerun | 110.0 | [229, 20484] | False | 229: 0.0..228.0 | {'Audio': [[0.0, 60.0], [60.0, 50.0]], 'Video': [[0.0, 60.0], [60.0, 50.0]]} | 552 (0.5..228.57, 276) | 1179 / 782 | None |

## Offline / pins

- offline=True, env {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'}
- backbone revisions (refs/main == pinned, checked before running): {'facebook/vjepa2-vitg-fpc64-256': '875c192b7b704b87d1e1d99345769632dd5f739a', 'facebook/w2v-bert-2.0': 'da985ba0987f70aaeb84a80f2851cfac8c697a7b', 'meta-llama/Llama-3.2-3B': '13afe5124825b4f3751f836b40dafda64c1ed062', 'en_core_web_lg': '3.8.0'}

Artifacts: pod `/work/yct/runs/<run_id>/` (res/, fc/, clips/) and feature cache entries under `/work/yct/cache/`; sha256 in SHA256SUMS, FC_SHA256SUMS and cache_manifest.json here.
