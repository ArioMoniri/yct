# D-087 v2: outcome-blind real-path pod smoke (freeze precondition)

Requested by the council re-check (wf_6140ad4f-5e3: Watchdog R1, Referee R1, Biostat, Neuro; QA condition).
Run on the pod (i-02dc0aef7260534ee, CPU, `/work/yct/repo_refclips` at **d7a416c**) on 2026-11-23 by
`/work/yct/d087_smoke.sh`: `scripts/locscreen_v2.py smoke /work/yct/refstim_models /work/yct/refstim_auto_scratch`
then `scripts/refstim_auto_run.py run … --target face=20 --target body=20 --target place=20`.
Outputs: `outputs/runs/d087_smoke/smoke_abc.json` (full record incl. the v1 per-slot patch shas) and
`outputs/runs/d087_smoke/smoke_meta.txt` (env versions, v4 log shas before/after, rcs, run commit).

No v2 screen was run, nothing was frozen, nothing was uploaded (`fetch_sources(upload=False)`; the S3 404s in
the log are read misses of the not-yet-existing v2 keys, after which the loader matched the source in the pod
T-LIC scratch by content sha256), nothing under `data/refstim` changed (checked by sha before/after), and YuNet
was never called on a slot or candidate patch.

| Part | Check | Result |
|---|---|---|
| (a) | every logged pass of the 3 v4 logs loads and sha-checks through the real loader | face 20/20, body 20/20, place 20/20 |
| (b) | v1 selection: real `locimg.patch` + joint SHINE == `locimg.loc_images`; `rendered_loc_patches` == `refclips58.loc_frames` pixel for pixel | equal; 180 entries (20 LOC clips × 3 events × intact/scramble/swap), all 20 LOC clips checked, 316×316 uint8 |
| (c) | sha-pinned `t_lic_yunet` (T-LIC input: full image, `resize_long` 640, BGR) reproduces logged T-LIC counts on non-candidate reject rows; uniform grey patch via `to_bgr640` | 5/5 match: face F1 ×3 at 0.9 (logged 3, 0, 5 → got 3, 0, 5), place P2 ×2 at 0.5 (1, 1 → 1, 1); grey patch 0 detections |
| (d) | `--target <cat>=20` for all 3 categories is a no-op | rc 0; v4 logs byte-identical (face 2ac34e9c…, body 10ec13f1…, place e7e6911f…) |

Versions (recorded): cv2 4.11.0 (both pod venvs), onnxruntime not installed (cv2.dnn runs the onnx),
ffmpeg 6.1.1-3ubuntu5.

## Wiring findings (fixed, wiring only; the rule is unchanged)
1. **v2 file names carried the Commons url query string** (`face_v2_00_r0172.org&utm_campaign=…`): the suffix
   now comes from the url path (`urlparse`), tested (2f7e071). This changes only the v2 file/s3_key names
   (never read by the screen's patch path, which matched by content sha); the smoke's (a)–(c) results do not
   depend on it.
2. **The screen loader uploaded candidates to slot-0 keys** (Watchdog orphan note): the screen now loads with
   `upload=False` (2f7e071); the builder uploads each final v2 source to its manifest `s3_key`.

Both fixes landed after the smoke commit d7a416c; the smoke's patch/SHINE/render and YuNet paths are
untouched by them. Verdict: the real path behaves as the fakes assumed; the freeze precondition is met.
