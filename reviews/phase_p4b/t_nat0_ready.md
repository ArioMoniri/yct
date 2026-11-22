# T-NAT0 readiness (D-075 §3, item 5): status 2026-11-22 (after D-082 and the council, wf_f6c3f08d-716)

**Status: launch-ready, pending only the $0 pod CPU rehearsal at the launch commit (§5) and the
orchestrator's launch checks (CI-green, terminator).** Nothing has been launched.

- **BUG-040 resolved by D-082** (DECISIONS; frozen at 0c3057c → f4211ea): the community-1 PLDA is pinned
  and mirrored, and the four pyannote mirror shas are set and frozen.
- **NAT CPU stage done** on the pod (`natcpu.rc` 0, 2026-11-22 07:29Z): 68 rows, buffer **40/40**
  (rejects: licence 14, yc_link 8, too_short 6). The committed log
  (`data/refstim/nat_auto_log.jsonl`, sha 4d1cd61f…) is the pod's log byte for byte.
- **L4 ledger reconciliation:** `data/refstim/ledger_reconcile_nat0.json` (driver `--reconcile-only`,
  2026-11-22): 2807 ledger lines (sha 4261f62b…), no open launch, no live yct-* instance, spent $51.86 of
  the $200 budget cap, campaign spend $0.

## 1. CPU stage (pod, no GPU): done
Code `src/yct/curate/natstim.py`, `scripts/natstim_cpu_run.py`; rules C1 (licence, personality rights),
T58 (Commons duration ≥ 58 s), C4 (YC metadata), the D-071 (c) URL-hash STOP, P2 (trimmed duration ≥ 58 s),
fail-closed on download/decode/normalise errors. A short buffer now writes a terminal
`{"stage": "cpu_end", "reason": "snapshot_exhausted", ...}` record (not needed here: the buffer is full).

## 2. pyannote (D-082)
- Pins: speaker-diarization-3.1@84fd2591…, segmentation-3.0@e66f3d3b…, wespeaker-voxceleb-resnet34-LM@837717dd…
  (D-075), speaker-diarization-community-1@3533c8cf… `plda/` only (D-082).
- Frozen mirror shas: diarization 0f66ffc1…, segmentation 702a51c6…, embedding 519a3249…, plda 53df9c18….
- Verify (pod CPU): 3.1 loads offline under pyannote.audio 4.1.0; 2 speakers on the A-B-A fixture
  (78d09e3); the verify now also requires 1 speaker on a single-voice fixture.
- BUG-042 (rehearsal run 1): the embedding is passed as `{checkpoint: path}` so 4.1.0 always takes the
  pyannote Model loader; `load_pipeline` refuses any other embedding loader.
- Disclosure: the verify ran on CPU; N2 in session 0 runs on CUDA (A100).

## 3. Session-0 preconditions (all checked before any launch; exit 1 if refused, nothing launched)
- **Frozen:** `controls.refclips_auto`, `controls.refclips_d082`, `nat_snapshot_sha256` and the four
  pyannote shas (set and frozen).
- **Limits:** `--max-hours` ≤ 1.75 (`p4.launcher_max_hours`); `--usd-limit` ≤ 8; price × hours ≤ limit.
- **Terminator:** `--external-terminator-at` required, in [planned deadline + 900 s, + 1 h more], a fire
  time no earlier session used.
- **Commit:** HEAD == `--ci-green-sha` (the orchestrator checks CI first), and HEAD is on the remote.
- **L4 (new):** the committed reconciliation record matches the ledger at launch (line count and sha), with
  no open launch and no live instance. Re-run `--reconcile-only` and commit if the ledger moved. The
  D-071 (k) $ tolerance (max($0.50, 1%)) needs an external invoice, which no API here exposes; the record
  carries the ledger-side figures only.
- **CPU stage (new):** the pod CPU stage has ended (`natcpu.rc` present, no `natstim_cpu_run` process) and
  the pod's NAT log sha equals the committed log.
- **Buffer (new):** exactly 40 CPU passes, or a short buffer with the matching logged
  `snapshot_exhausted` record; no session-0 row logged yet.
- **One instance at a time; campaign baseline** written once before the first `yct-p4b-ref*` launch; the
  **$75 cap guard** passes.

## 4. Box steps (no TRIBE job)
1. `setup_wx`: waits for apt locks; installs ffmpeg if missing; installs uv into `~/.uvbin` (as
   tribe_run's setup script does); the pinned WhisperX env from the committed freeze; nltk `punkt_tab`.
2. `push_buffer`: the exact mirror sync (`mirror_sync_cmd`) and the 40 T1 wavs to the box.
3. `nat0`: `yct.curate.nat0_box` in the activated env with the P2b cudnn/cublas `LD_LIBRARY_PATH`;
   faster-whisper large-v3 is resolved online (its HF snapshot hash is recorded), then HF offline is
   enforced (module constant, not just the env var) before pyannote loads from the frozen mirror. Output
   is compact JSON, copied box → pod over ssh and read with the chunked `pod_file` (SSM stdout truncates at
   24 kB).
4. `asr`: P2b (pinned WhisperX) on the 40 wavs, same `LD_LIBRARY_PATH`.
- **Ship list:** `gpu_p0_rerun.SHIP` (copied, not mutated) + `infra/gpu_deadman.sh`,
  `src/yct/curate/{__init__,nat0_box}.py` and the freeze file; a test checks the import closure of every
  box-step module against the real tarball.
- **No masked failure:** the selection is logged only when every step is ok; any step failure → exit 75,
  nothing logged, instance terminated (finally), dead-man switch on the box.
- **Pod after the session:** N3 (`face_present_crop` over W ≥ 0.5) via the same `n3_cmd` the rehearsal
  ran; `natstim.session0_rows` up to the 15th pass; fewer than 15 → rows logged, exit 1 (STOP to the owner).

## 5. Pod CPU rehearsal ($0, `scripts/nat0_rehearsal.py`, records in outputs/runs/nat0_rehearsal_20261122/)
Steps: (a) every buffer t1 has its mp4 + wav, wav sha == logged, `read_wav` accepts it; (b) the exact ship
tarball untarred into a fresh dir, fresh uv, fresh venv from the freeze, punkt_tab; (c) the exact mirror
sync + `check_mirror` on the four frozen shas; (d) `nat0_box --device cpu` on 3 buffer wavs with the exact
`--shas` JSON; (e) HF offline enforced after faster_whisper's import; (f) `yct.transcribe` on 1 wav (cpu/int8
for the rehearsal only); (g) N3 via `n3_cmd` on 1 mp4; (h) `session0_rows` dry (log unchanged).
- Run 1 (f4211ea): a, b, c, g ok; d, e, f failed → BUG-042 (fixed in 2954f7f).
- Run 2 (2954f7f): d OOM-killed on the 7 GB pod (both models held at once) → BUG-043 (fixed in 72bd29d);
  e, f, g ok.
- **Run 3 (72bd29d): all 8 steps ok, exit 0** (run3_72bd29d.json). Ship tarball from the exact ship list;
  fresh uv and venv from the freeze; mirror sync reproduces the four frozen shas; `nat0_box --device cpu`
  on 3 buffer wavs returns finite lang_probs and segments (large-v3 snapshot edaa852e…); HF offline
  refuses a download; `yct.transcribe` writes its JSON; N3 = 0.2 on one mp4; `session0_rows` dry leaves the
  log unchanged. The full suite passes at 72bd29d (1222).
- **Early warning (rehearsal numbers only, CPU int8, not decisions):** all 3 rehearsed candidates would be
  rejects (two N1 p(en) 0.20 and 0.69 < 0.9; one N2), and N3 on the one mp4 tried is 0.2 < 0.5. If this rate
  holds, session 0 may yield fewer than 15 of 40 passes, which the frozen rule makes a STOP to the owner
  (rows logged, no relaxation). The council may want to weigh this before spending the session.

## 6. Cost
About 45 min of A100 time, about $1.5; the cap guard plans $3.48 (1.99 $/h × 1.75 h). Campaign spend so
far $0. After session 0, the D-071 (k) projection is about $63 of $75.

## 7. Still to do after session 0
`nat_manifest` → `data/refstim/nat_manifest.json`; LICENSES.md NAT section; `nat_manifest_sha256` set,
then frozen; P2b ingest of the 15 transcripts to TRIBE .tsv (pod); the clip manifest (T-STIM) and its
frozen sha; then reference session 1 (`--limit 3`, watched).
