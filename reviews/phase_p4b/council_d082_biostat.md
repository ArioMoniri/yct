# Council D-082 + T-NAT0 session-0 readiness: biostat (2026-11-22)

**Verdict: REVISE.** D-082 itself can be approved as drafted. Three blocking items must be fixed before session 0 launches. Tests run: 42 passed (test_gpu_p4b_nat0, test_nat0, test_nat0_d082). I read no sealed data, labels, transcripts or predictions.

## (1) D-082: pin the community-1 PLDA, refuse VBx. Acceptable.
- The pin is an immutable 40-hex revision, mirrored as `plda/*` only and covered by `pyannote_plda_sha256`. The two-commit freeze is checked by `check_frozen`, which also needs the `controls.refclips_d082` row. The analysis is reproducible whether or not the PLDA is applied.
- The 3.1 N2 parameters (Agglomerative clustering, centroid linkage, threshold 0.7046, min_cluster_size 12) and the frozen N2 thresholds (0.95, 3 s, min_prob_en 0.9) are unchanged. Inference is therefore unaffected, and the D-075 pass set is the same as intended.
- Verifying that the fixture returns exactly two speakers is a real improvement: before, any non-empty output passed. The `read_wav` fix matches the CPU-stage wav format (`pcm_s16le`, 16 kHz mono, normalize/core.py:660).
- Non-blocking: "loaded, never applied" rests on reading the code. A cheap empirical check would be to verify again with zeroed PLDA arrays (outside the frozen mirror) and get identical segments. That would support the §5 disclosure.

## (2) Session-0 readiness: blocking items
- **B1. The driver accepts a partial buffer.** `check_buffer`/`ns.buffer_ids` accept 1..40 CPU passes. The log holds 39 passes right now and the CPU stage is still running. A launch today would select from 39, could raise a spurious "< 15" STOP, and would lock the buffer at 39, because a later 40th CPU row would follow the session-0 rows.
  - Fix: refuse unless the CPU passes == `cpu_buffer` (40), or a logged terminal "snapshot exhausted" record exists.
  - Also refuse while the pod CPU run is alive (`natcpu.rc` absent).
  - Add a test for a 39-pass buffer.
- **B2. An ASR failure after nat0 reports exit 0 "done".** If `asr` (or a later step) raises after `nat0` returned, `gpu` is already set. The rows are logged, status is overwritten to "done", and rc is 0. Session 0 can then never run again ("rows already logged"), and the P2b transcripts are missing with no path to regenerate them.
  - Fix: log the selection only when every STEP is "ok". Otherwise return 75 with nothing logged.
  - Add the test `Box(fail="asr")` → rc 75, no rows, instance terminated.
- **B3. The real PodBox path is untested (fakes only).** Minimum check before launch, on the pod, at the launch commit:
  - (a) For all 40 buffer ids, `/work/yct/nat_scratch/t1/audio16k/<id>.wav` exists, and its sha256 equals the logged `wav_sha256`. The box does not check this.
  - (b) Sync the mirror with the exact `aws s3 sync …/models/pyannote/` command that push_buffer uses.
  - (c) Run `venv_wx/bin/python -m yct.curate.nat0_box --device cpu --wavs <3 real buffer wavs> --mirror <synced> --shas '<JSON built exactly as PodBox.step("nat0") builds it from config>' --out …`. It must exit 0 and return `lang_probs`, plus segments with a finite total, for each of the 3.
  - (d) Feed that JSON through `ns.session0_rows` in a dry run on a temp log copy, with N3 run by the PodBox.n3 command on one real T1 mp4.
  - This exercises the real wavs, the mirror layout, the shas key mapping (`plda`), faster-whisper load and N3 at no GPU cost. The P2b precedent covers `setup_wx` and GPU float16.

## Non-blocking
- `t_nat0_ready.md` is stale (dated 2026-11-21, lists three shas, BUG-040 shown as open). Update it to D-082 before launch.
- **Yield risk.** I estimated this from CPU-pass titles only; no rule is changed by it.
  - About 6 of the 39 look non-English: French, Russian ×3, Thai.
  - Several clips probably have no speech or several speakers: a walk-through video, archival footage, bodycam, a cartoon, and about 13 talk-show episodes.
  - Some are animations or screencasts that are at risk at N3.
  - So P(< 15 passes in 40) is not small. Ask the owner now about the D-075 continuation buffer. The driver's "rows already logged" refusal means any continuation also needs a D- entry and a code path.
