# T-NAT0 readiness (D-075 §3, item 5): status 2026-11-21

**Status: NOT ready to launch.** Session 0 is blocked by BUG-040: the pinned pyannote 3.1 does not load offline under pyannote.audio 4.1.0, and the next step is a council/owner STOP. The NAT CPU stage is running on the pod, and its buffer is not yet full. The driver refuses to launch until both are resolved.

## 1. CPU stage (pod, no GPU)

- **Code:**
  - `src/yct/curate/natstim.py` (metadata rules and buffer fill);
  - `scripts/natstim_cpu_run.py` (pod runner);
  - `tests/test_natstim.py`.
- **Order:** the frozen NAT snapshot (sha aab68a55…, frozen row) in ascending sha256(title) order. The header is checked against config.
- **Rules, in order (one row per candidate in `data/refstim/nat_auto_log.jsonl`, stage `cpu`, append-only):**

  | Rule | When | Check | Reject reason |
  |---|---|---|---|
  | C1 | metadata | personality rights; licence in `image_licences` (D-071 b) | `personality_rights`, `licence` |
  | T58 | metadata | Commons duration ≥ `stimulus.t1_trim_s` (58 s) | `too_short` |
  | C4 | metadata | the frozen metadata rule on title, description and categories | `yc_link` |
  | — | metadata | URL hash in data/manifest.csv or data/wave2_pool/pool_manifest.csv | STOP (D-071 c disjointness) |
  | P2 | after normalising | trimmed duration ≥ 58 s | `too_short` |

  - The P2 step downloads the file (owner-approved UA; sha1 must equal Commons, with one re-download and then a STOP) and runs `yct.normalize.normalize_video`, unchanged, identical to the analysis T1.
  - The optional CPU-stage P3 is not run. N3 runs after N1/N2 (D-075 permits either).
- **Buffer:** the first 40 passes, in order (`cpu_buffer`).
- **Fail-closed:** a download, decode or normalise error is a STOP, never a reject.
- **Outputs (S3, `controls.refclips.s3_root`):**
  - `sources/nat/` (downloaded source; the local copy is deleted);
  - `nat_t1/<t1>.mp4`, `nat_t1/audio16k/<t1>.wav`, `nat_t1/records/`.
- **Run:** pod `/work/yct/natcpu.sh` at 7d3fb66 (nohup; log `/work/yct/natcpu.log`, rc `/work/yct/natcpu.rc`). It resumes from the log, so it is safe to restart.
- **Throughput:** the source files are long lectures (up to about 1 h, about 570 MB). The analysis-identical black and silence detection decodes the whole file on the pod's 2 vCPUs, about 20–30 min per downloaded candidate, so the 40-candidate buffer needs many hours. Metadata-stage rejects cost no download.

## 2. pyannote setup (pod): BUG-040, STOP

- **Downloaded and mirrored:** the three pinned repos, downloaded with the owner-accepted gates (token piped SSM → umask-077 file → shredded; never printed). Mirrored to `s3_root/models/pyannote/`.
- **Mirror shas** (`yct.curate.nat0_box.dir_sha`; computed, **not set or frozen**):
  - diarization 0f66ffc1…05af2
  - segmentation 702a51c6…e7733
  - embedding 519a3249…f84e
- **Verify (synthetic espeak-ng two-voice fixture, CPU) fails.** In 4.1.0, `SpeakerDiarization` always loads a PLDA from the unpinned `pyannote/speaker-diarization-community-1`, even with AgglomerativeClustering. Offline, that is a `LocalEntryNotFoundError`.
- **Rule:** per D-075 this is a STOP to the council; there is no silent switch. The options are in BUGS.md BUG-040. Once one is decided by a D- entry and the verification passes, the shas are set in one commit and frozen in the next.

## 3. Session 0 (one gpu_1x_a100_sxm4): driver `scripts/gpu_p4b_nat0.py`, tests `tests/test_gpu_p4b_nat0.py`

**Preconditions, all checked before any launch (exit 1 if refused, nothing launched):**
- **Frozen:** `controls.refclips_auto`, `nat_snapshot_sha256` and the three pyannote shas (set and frozen).
- **Limits:**
  - `--max-hours` ≤ `p4.launcher_max_hours` (1.75);
  - `--usd-limit` ≤ 8;
  - price × hours ≤ the limit.
- **Terminator:**
  - `--external-terminator-at` is required, inside [planned deadline + 900 s, + 1 h more];
  - it must be a fire time no earlier session used.
- **Commit:** HEAD == `--ci-green-sha` (the orchestrator checks the CI run first), and HEAD is on the remote.
- **Buffer:** 1 to 40 CPU passes, and no session-0 row already logged.
- **One instance at a time.**
- **Campaign baseline:** `entries/campaign_baseline.json` is written once, before the first `yct-p4b-ref*` launch. It is refused if one predates it.
- **Cap:** the $75 cap guard (`ref_campaign.guard_launch`) must pass.

**Box steps (only these; no TRIBE job):**
1. `setup_wx`: the pinned WhisperX env, installed from the committed freeze file.
2. `push_buffer`: the 40 T1 16 kHz wavs plus the pyannote mirror from S3.
3. `nat0` (`python -m yct.curate.nat0_box`):
   - It refuses unless faster-whisper is 1.2.1 and pyannote.audio is 4.1.0, and the mirror shas equal the frozen values.
   - N1: faster-whisper large-v3 `detect_language` on samples [0, 30 s).
   - N2: pyannote 3.1 offline. Only numbers leave the box.
4. `asr`: P2b, the pinned WhisperX on the buffer wavs. The JSON goes to the pod `/work/yct/nat_asr` and S3 `nat_asr/`.

The instance is always terminated (finally), and the box carries the dead-man switch.

**Pod after the session:**
- N3: `face_present_crop` (yct.confounds `video_features`, unchanged) averaged over W = [5, 45) TR, ≥ 0.5, else `low_face_present`.
- Selection with `natstim.session0_rows`: N1 → N2 → N3 per candidate, in buffer order, up to the 15th pass (`nat_select`).
- The rows are appended to the NAT log (stage `session0`). Fewer than 15 passes logs the rows and exits 1 (STOP to the owner).

**Exit codes:**
- 0: 15 passes logged.
- 75: no capacity, or the box failed before any result (nothing logged; re-run with a new terminator).
- 1: a human decides.

**Cost estimate:**
- About 45 min of A100 time (env install about 15 min, model downloads, N1/N2 on 40 × 58 s about 5 min, P2b about 10 min), about $1.5.
- The cap guard's planned charge is 1.99 $/h × 1.75 h = $3.48.
- Campaign spend so far is $0: no `yct-p4b-ref` launch yet, and the baseline is not written yet.
- After session 0, the D-071 (k) projection is about $63 of $75.

## 4. Still to do after session 0

- `nat_manifest` (`natstim.nat_manifest`) → `data/refstim/nat_manifest.json`.
- LICENSES.md NAT section.
- `nat_manifest_sha256` set, then frozen.
- P2b ingest of the 15 transcripts to TRIBE .tsv (pod).
- The clip manifest (T-STIM) and its frozen sha.
- Then reference session 1 (`--limit 3`, watched).
