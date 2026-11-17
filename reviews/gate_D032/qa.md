# G-D032 QA review (fresh context, commit 529652d)

**Vote: FIX — merge-blocking (CI is red).** The code works and is deterministic, but "151 passed" is a local run with every extra installed. CI has never run the tests at this commit, and the atlas/localisation claims are untested in CI.

## What I ran (detached worktree at 529652d; data/sealed/ not touched)
- `python -m pytest -q` (local, all extras, atlases cached): **151 passed**, matching the packet.
- `ruff check .`: **red**. Local ruff 0.16.9 finds 3 errors. CI's pinned ruff 0.8.4 finds 4:
  - src/yct/tribe_run/latency.py:6 (E501)
  - latency.py:45 (E702)
  - src/yct/tribe_run/run_clip.py:71 (E702)
  - src/yct/transcribe/core.py:215 (UP038, flagged by 0.8.4 only)
- Actions run 44102933915 (this commit): **failed at Lint**; Tests and guards **skipped**. Same on e9b891c and every later push.
- CI reproduced locally (fresh venv, `pip install -e '.[dev,pre]' ruff==0.8.4`, empty HOME): **collection error**: tests/test_localize.py:4 `import matplotlib` → ModuleNotFoundError. Ignoring that file: 139 passed, **7 skipped** (every real-atlas test, "nibabel is not installed").
- Guards with `--base 56a6705` (the first commit):
  - append_only, prereg, frozen_config, blinding: OK.
  - **check_human_signed FAIL**: 6c16d89 (infra/BUDGET_USD; old history).
  - **check_test_weakening FAIL**: 8005ceb (old) and **c35c53c** (in-window; see D3). `--base b48de78` also fails; `--base c35c53c`/`029f7f3` pass.
- Determinism: two normalize_video runs gave identical T1 and T3 sha256; the T1 file on disk still matched its hash after T3. No RNG in the new modules; tests seed `default_rng`.

## Defects
**D1 (blocking): CI does not install `neuro`.** .github/workflows/ci.yml:26 installs only `.[dev,pre]`, but test_localize.py imports matplotlib at module level, so CI fails at collection even past Lint. Moving the import would still leave real-atlas tests silently skipped via `load_or_skip`:
- tests/_atlas.py:17
- test_atlas_loaders.py:19,27,35,43,55,64
- test_atlas_networks.py:68
- test_localize.py:155,174

These (400 parcels, 870-vertex medial wall, HCP L/R split, Destrieux, rank 6) have never run in CI. Nothing caches ~/.cache/yct/atlases; Destrieux is fetched from NITRC via nilearn at test time.

**D2 (blocking):** lint red at the gate commit (4 findings above); latency.py and run_clip.py are not in `per-file-ignores`.

**D3 (blocking by project rule):** c35c53c adds `pytest.skip` at tests/_atlas.py:17 without the approval trailer; check_test_weakening flags it. It is the mechanism behind D1's silent skips.

**D4: `make guards` checks an empty range locally.** Makefile:4 defaults BASE to `@{upstream}` or `HEAD`: detached gives HEAD..HEAD; here upstream is *ahead* of HEAD, so that range is empty too. Every guard prints OK having checked nothing.

**D5: the "T1 hash unchanged" test cannot fail for the reason it claims.** tests/test_normalize.py:188-195 compares `rec["video_id"]`, which src/yct/normalize/core.py:455-457 sets *before* T3 runs (core.py:525-528). A T3 that overwrote the T1 mp4 would still pass. It never asserts `"t3" in again` (trivial pass if `enabled` defaulted false) and compares a 16-char prefix, not the full sha256.

**D6: photometric targets are only partly checked independently.** tests/test_photometric.py:14-17 avoids the module's covariance shortcut, but it decodes through the module's own `iter_rgb_frames` (photometric.py:26-57): plain swscale `rgb24`, with no colour range or matrix set. Nothing is tagged BT.709 though config says "BT.709 Y", so "target hit" holds only under the module's own decode convention, not necessarily V-JEPA2's. Tolerance ±0.02 on a 0.20 contrast target is ±10%.

**D7:** test_photometric.py:80-85 asserts only a boolean and a suffix; a no-op deflicker passes.

**D8: dependency pins are loose.**
- Runtime dependencies in pyproject.toml:6 are unpinned (pandas, numpy, pyyaml, pydantic>=2).
- In the `dev` extra, pytest and ruff are unpinned, while CI pins ruff==0.8.4. Local ruff 0.16/0.17 gives different findings (UP038 is reported only by 0.8.4).
- There is no lockfile.
- CI uses Python 3.11; local runs used 3.13.
- Actions pinned by tag, not SHA (Node 20 deprecated).

**D9 (provenance):** commit messages do not match contents. The packet names e9b891c (message: P2 work), which only edits atlas/localize files; 529652d ("Atlas/network/localisation modules") only touches latency.py, the curation log and the packet.

**Magic numbers:** grepped numeric literals in photometric, networks, localize, confounds, transcribe; scientific tunables all come from config.yaml. Remaining:
- localize.py:27-28: NV/NH duplicated. These should come from `tribe.n_vertices` and `atlases.n_vertices_per_hemi`.
- localize.py:92, 112, 118, 121: plot defaults (dpi 110, 1e-6 threshold, 0.5 background scale).
- photometric.py:92: 1e-6 gain floor.
- atlas.py:81: 60 s download timeout.

None is load-bearing. **gitleaks**: valid (v8.21.2, full history, `.gitleaks.toml`), green.

## Required changes (for GO)
1. ci.yml: install `.[dev,pre,neuro]`. Add `actions/cache` for `~/.cache/yct/atlases` (key: sha256 values from config.yaml). Set `YCT_REQUIRE_ATLAS=1`, and make `load_or_skip` **fail** instead of skipping when it is set. Add pip caching.
2. Move `import matplotlib` in test_localize.py behind `pytest.importorskip`, so a dev-only install skips those tests cleanly. CI is covered by step 1.
3. Fix the 4 lint findings, or add per-file ignores for the GPU scripts. Pin ruff the same way in pyproject and CI.
4. QA sign-off on the c35c53c skip (`[QA-approved test change]` follow-up) once step 1 makes it unreachable in CI; record the 6c16d89/8005ceb exceptions or document this gate's guard base.
5. Makefile:4: default BASE to `$(git merge-base HEAD origin/main)`, or refuse to run when the range is empty.
6. test_normalize.py:188: assert `"t3" in again`. Re-hash the T1 file on disk *after* T3 and compare it to the full `sha256`. Assert that the T3 path is outside the T1 directory.
7. test_photometric.py: measure the T3 output with an independent decoder: ffmpeg `signalstats` YAVG on the Y plane, plus explicit `-color_range`/`colorspace` tags. Tighten the tolerance to ±0.01. Make the smoothing test assert that frame-to-frame luminance variance drops compared with smoothing off.
8. Pin runtime/dev deps or add a CI constraints file.
9. Re-run CI; attach the green run URL to the packet.
