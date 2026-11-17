# Run wave1_p2p3_20261117T202935Z

- cmd: `python /work/yct/scripts/wave1_p2p3.py all`
- git_sha: `b24fc1cf1a697d5345354fe36836c787a98715bb` (dirty: False)
- config_sha: `aa5e39fd4d60e4b028253f10091eff51e6285265ff303573c308edb8212d8b86`
- exit_code: 0
- wall_s: 10650.012
- pytest: None

## Wave-1 P2 normalisation + P3 confounds (CPU only, pod)

Pod: /work/yct/repo at b24fc1c (origin/claude/yc-videos-agent-system-dirk8p), venv /work/yct/venv
(`pip install --require-hashes -r requirements.lock`, then `pip install --no-deps -e '.[pre,neuro]'`).
Driver: `wave1_p2p3.py` (copied here). For each in_primary manifest row it calls
`python -m yct.normalize --in /work/yct/raw/<id>.mp4 --out /work/yct/norm`, moves the T1 mp4 to norm/t1/ and the record
to norm/records/<content_id>.json (the `path` field is updated; `manifest_video_id` is added), then runs
`python -m yct.confounds --mp4 <t1|t3 mp4> --wav norm/audio16k/<content_id>.wav --out confounds/{t1,t3}/<stem>.parquet`.
The confounds stage also ran in a parallel loop on finished videos while normalisation went on; the main run
skipped outputs that already existed, and all 114 parquet files re-read cleanly. Summary: `wave1_summ.py`.

Inputs: 51 YouTube mp4 from s3://.../wave1/raw/ (all OK against s3://.../wave1/SHA256SUMS) plus 6 LinkedIn mp4
from an earlier pod-side download (0635-0638, 0645, 0646; OK against the sha256 in that download's raw_probe.csv).
There were no split-stream pairs, so nothing was merged. yct_0644 has no raw file: sealed URL, needs an owner action.

Results (58 in_primary): 57 normalised, 0 errors, 1 missing (yct_0644).
- T1 exclusion (trimmed < W_end + window.min_tail_s = 45 + 5 = 50 s, D-039; the old +2 s rule gives the same result): 1 (yct_0483, 42.8 s).
- HDR 0; 9:16 stratum 0; upscaled to the 292 px short side 1 (yct_0105); untagged colour 1 (yct_0636);
  source fps < 16: 2 (yct_0626 12.5 fps, yct_0641 15.0 fps); A/V sync 0; mono-phase 0; loudness off target 0;
  T3 clipping flag 12.
- Caption / on-screen text: not implemented in yct.confounds (text_frac is NaN), so caption_flag = not_implemented.
- Speech-rate features (speech_rate_wps, n_words, words_per_min) are empty: there are no WhisperX transcripts yet (P2b needs the GPU).

Outputs: s3://yct-research-235229001983/wave1/derived/{norm/records,norm/runlog,confounds/{t1,t3,summary},summaries}
(records + confounds only, no media). Media stays on the pod under /work/yct/norm/{t1,q480,t3,audio16k}.
Repo: data/wave1_normalize_qc.csv, data/wave1_confounds_summary.csv (label-free; no titles, URLs or outcomes).
