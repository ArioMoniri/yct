# Phase 0 gate: QA review (fresh context)

Reviewed at b140dd6 (HEAD c287efc adds only reviews). data/sealed/ not read.

**Vote: FIX (merge-blocking until changes 1-3 are done; no STOP).** CI is genuinely green, the lock reproduces, and the feature-cache tests have teeth. Still blocking: one ROADMAP P0 test is missing, the smoke run dir lacks provenance, and one DoD item that matters for real YC clips is neither resolved nor ticketed.

## ROADMAP P0 tests
- **`test_infra_guards`: PASS.** 11 tests: name prefix, hours cap, A10 block, budget from file, 10-min heartbeat, reaper, watch loop.
- **`test_config_schema`: MISSING.** `load_config` is a bare `yaml.safe_load`. pydantic is a dependency but is used nowhere.
- **`test_ci_guards`: PASS (equivalent).** A tampered append-only log fails (modified, deleted or inserted line). A prereg edit or delete after lock fails. Frozen-config, blinding and weakening fixtures exist too.
- **`test_tribe_smoke`: evidence only, no pytest.** smoke metrics.json shows shapes (10, 20484) and (40, 20484), `T_within_1` true, `finite` true, peak VRAM 13,411 MiB, TR 1.0, and latency CSVs.
- 256 passed locally, in a clean clone, and in CI run 44109304890 (0 skipped).

## Feature cache (BUG-006): mutation test
- With `ensure` mutated to re-extract every run, **7 of 14 tests fail** (`ex.calls == 1` and the bit-identity checks).
- With the post-prediction `verify` removed, **2 fail** (the must-not-write and must-not-add tests).
- run_clip.py:95 points exca `cache_folder` at `feat_dir`, so a real re-extraction would write there and raise.
- What is not caught directly: a predictor that recomputes in memory or in another folder. Only bit-identity across reruns would catch that.
- Not GPU-verified: exca might touch `feat_dir` on a cache hit and cause a false `FeatureCacheError`.

## Provenance and lock
- In a clone, `make test RUN_ID=qa_prov` wrote `cmd`, `git_sha`, `config_sha`, `exit_code`, `metrics.json` and `stdout.log` (sha c287efc, dirty=false, 256 passed).
- Fresh `python3.11 -m venv` + `pip install --require-hashes -r requirements.lock` + `-e . --no-deps` installed cleanly, and `pip check` was clean.
- In that venv: 256 passed, ruff clean.
- `uv pip compile` reproduces the lock exactly.

## Defects
1. **`test_config_schema` is missing.** config.yaml has no schema, so a mistyped key read with a `.get()` default cannot fail anywhere.
2. **The smoke run dir breaks v2.md §3 Provenance.** `smoke_20261117T142354Z/` has no `cmd`, `git_sha`, `config_sha`, `exit_code` or logs. It was not run via `run_with_provenance.py`; the commands are a prose summary.
3. **DoD "UNVERIFIED resolved or ticketed" is not met.**
   - tribe_requirements.md:167 lists clips > 60 s (chunking) and > 100 s (windowing) as UNVERIFIED, with no ticket. YC videos are about 60 s, right at that boundary.
   - The CPU-only row (l.31) also has no ticket; mark it N/A.
   - The reliability mask is covered by P4.
4. **The determinism fix is CPU-mock only.** The smoke metrics predate the cache, and P4 `test_determinism` depends on it. The packet discloses this.
5. **The provenance run dir is thin.** It has no package list or lock sha256 (local 3.13 vs CI 3.11 shows only in `python`) and no input hashes (v2.md §3).
6. Minor: Actions are pinned by tag, not SHA, and run under Node-20 deprecation warnings.

## Required changes
1. Add a pydantic schema for config.yaml (`extra="forbid"` on tunable sections) and `tests/test_config_schema.py`. The test must load the repo config and reject a missing key, a wrong type and an unknown key.
2. Add `cmd`, `git_sha`, `config_sha`, `exit_code` and `stdout.log` to the smoke run dir, reconstructed from pod logs and marked as such. Alternatively, re-run the smoke via `run_with_provenance.py` in change 3.
3. Open a ticket, due before P4, for one GPU session:
   - run a 60-75 s clip and a 110 s clip, and assert the shape and T within ±1 of duration/TR;
   - run `run_clip.py --feature-cache` twice plus `--fresh-drift`, and expect `cache_reused` true, bit-identical predictions and no `FeatureCacheError`.
4. `run_with_provenance.py` should also record the requirements.lock sha256 (or `pip freeze`) and the platform.
5. Optional: pin the Actions by SHA.
