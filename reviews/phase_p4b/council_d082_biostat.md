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

## Re-check + pre-launch (2026-11-22, at ed1e842, pushed; 77 tests pass in the NAT/D-082/frozen-config suites)
- **B1 fixed.** `check_buffer` refuses unless `buffer_complete` holds (40 passes, or a logged `snapshot_exhausted` record). `check_cpu_stage` refuses while the pod CPU run is alive or the pod log sha differs from the committed log. The 39-pass refusal test exists. The buffer is 40/40 (rehearsal step a: all 40 wav shas match).
- **B2 fixed.** A step exception sets `gpu = None`. Logging requires every STEP to be "ok", otherwise rc 75 with nothing logged, and the terminate runs in `finally`. `Box(fail="asr")` is tested.
- **B3 met.** Rehearsal run 3 at 72bd29d passed all 8 steps: real wavs, ship tarball, fresh venv, the exact mirror sync reproducing the 4 frozen shas, `nat0_box` with the real `--shas`, HF offline, N3, and a dry `session0_rows` that left the log unchanged. BUG-042 (loader) and BUG-043 (OOM) were real box-path defects that the fakes missed. Both are fixed test-first and touch no frozen key. ed1e842 adds only records and docs on top of 72bd29d.
- **L4.** The record has 2807 lines, no open or live instances, and $51.86 spent with campaign spend $0. It must still match the ledger at launch; the driver checks this. `t_nat0_ready.md` is current. Commit d7f2c62 does not exist in this repo; the tests-first commit is 5582611, so this is not blocking.
- **The rehearsal outcome changes no rule.** The 0/3 result (N1 p_en 0.20 and 0.69; N2 on a clip with p_en 0.999; N3 0.2) came from CPU/int8 on 3 non-random clips. It was outcome-exposed. Any change to N1/N2/N3, nat_n 15 or the 40-buffer prompted by it would be a data-dependent rule change and is barred. It is also weak evidence: P(0/3 | p = 0.375, the rate that just reaches 15/40) ≈ 0.24.
- **Disclosure.** 3 buffer candidates were seen pre-session on CPU. The session-0 GPU result alone decides their outcome. The CPU values are never used, and no CPU/GPU discrepancy is to be adjudicated by hand.
- **Verdict: APPROVE launching session 0.** It is the frozen next step: 1×A100, about 45 min, about $1.5, $3.48 planned against the $75 cap, external terminator, watched. If fewer than 15 of 40 pass, the frozen outcome applies: rows logged, exit 1, STOP to the owner, no relaxation. Any continuation buffer then needs a new D- entry, made with the session-0 results in view, which must be disclosed as such. Before launch, commit the two modified council files so that HEAD == CI-green == pushed.
