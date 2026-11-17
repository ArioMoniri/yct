# Watchdog — gate G-D032

- Subagent: watchdog, fresh context, session_011NAQ1mksc4Ea1mJcrGfTSd. Audit date 2026-11-17.
- Audited SHA: 529652d. Packet says "e9b891c + packet". HEAD has since moved: aaf6cd3, then 6e93ac0 on origin, with agents working concurrently.
- Not read: data/sealed/ and the other reviews in reviews/gate_D032/.

**VERDICT: VETO** (fixable). The gate's CI is red, and the project's own test-weakening guard fails on a commit in this gate. The red Lint step hides that guard failure. Nothing qualifies as an INCIDENT: no leak, no orphan GPU, no fabrication.

## Checks

**1. Provenance**
- Commands:
  - `git archive 529652d | tar -x` into scratchpad, then `pytest -q tests/test_photometric.py` (file picked with `random.Random(20261117)`). Result: **6 passed**, exit 0.
  - Full suite: `python -m pytest -q`. Result: **151 passed in 79.76s**, matching the packet. `pytest -rs` on the atlas, network and localize tests: 18 passed, 0 skipped.
- Defect: the packet's test claim has no `outputs/runs/<run_id>/` with SHA and exit code (§3 Provenance, §2b.4.1). `outputs/` is untracked and holds only `smoke_20261117T142354Z`. That smoke run directory has CSVs and metrics.json, but no command, SHA, config hash or exit code.
- Defect: CI. `gh run view 44102933915` (headSha 529652d) and `gh run view 44102143125` (e9b891c) both show **conclusion failure at the Lint step**: ruff E702/E501 in `src/yct/tribe_run/latency.py:6,45` and `run_clip.py:71`. So the Tests and Integrity-guards steps never ran in CI for this gate.

**2. Goalposts**
- `scripts/check_append_only.py --base 4c194c7`: OK, 5 files. `check_frozen_config`: OK. `check_prereg`: OK, no lock tag yet.
- **`scripts/check_test_weakening.py --base 4c194c7`: rc=1, "FAIL c35c53c: tests/_atlas.py: 1 skip/xfail marker(s) added".** The marker is `tests/_atlas.py:17` (`pytest.skip(...)` in `load_or_skip`). No BUGS or ENHANCEMENTS ticket exists for it (`grep -i skip|_atlas BUGS.md ENHANCEMENTS.md`: none). §3 requires a ticket, a QA vote and Watchdog sign-off. The effect: offline CI would silently skip every real-atlas assertion. That includes the medial-wall count of 870, the 360 HCP labels and the Yeo mapping.
- Assertion diff: I AST-diffed every assert and `approx` between each test file's first commit and 529652d (normalize, transcribe, confounds, photometric, atlas_*, localize). The only removed asserts are the `A.`→`atl.` renames in e9b891c, which reappear unchanged. Searched, no tolerance widened.
- BUG-001 history:
  - 8005ceb edited D-030 in place.
  - e1ad4fe restored it. `diff <(git show 8005ceb^:DECISIONS.md) <(head … e1ad4fe)` gives RESTORED_EXACT.
  - e1ad4fe:DECISIONS.md is an exact prefix of the current file.
  - Every removed line in DECISIONS, BUGS and ENHANCEMENTS history (`git log -p | grep '^-'`) is that one D-030 edit and its revert.
- Note, outside this gate: 8005ceb dropped the SSH-signature tests in `test_guards_human_signed.py` when D-030 moved to SSM. That needs its own sign-off trail. v2.md §2 still describes signed commits.

**3. Blinding**
- Command: `git grep -niE 'outcome|accepted|rejected' 529652d -- . ':!data/sealed' ':!src/yct/curate'`.
- None of the hits are in the gate code (src/yct/normalize, features, interpret, config). The rest are in prompts, reviews, guard tests and protocol text.
- **Defect (minor):** `data/curation/search_log.csv` has 44 hits, for example line 5 `YC video accepted,40,11` and line 44. The file is outside the allowed paths. It logs per-query candidate counts split by outcome-labelled query strings, which leaks class-conditional pool sizes at aggregate level only. No video IDs. `check_blinding.py` passes, because it checks columns only.
- No `UNBLIND_TOKEN`, now or anywhere in `git log --all`.

**4. Secrets**
- gitleaks is not installed here. Instead: `git log -p --all | grep -E 'hf_[A-Za-z0-9]{30,}|AKIA…|sk-…|ghp_…|BEGIN … PRIVATE KEY|AGE-SECRET-KEY'`. The only hit is a grep pattern in owner_setup.sh. No keys found.
- `grep -rn 'hf_token|get_parameter|ssm' src infra scripts/*.py`: nothing reads `/yct/hf_token`. `owner_actions.py` reads `/yct/owner/*`, and only `owner_setup.sh` writes hf_token.
- `infra/lambda_gpu.py:56` uses `LAMBDA_API_KEY` only inside the request header. None of its print calls (lines 46, 109, 144, 174, 176) output the key or headers.

**5. Licence and data**
- **Defect:** `config.yaml:118,122`. The Schaefer annots are fetched from `ThomasYeoLab/CBIG/master` and pinned only by sha256. A change upstream fails closed but is not reproducible. Pin a commit SHA in the URL.
- HCP-MMP:
  - Downloaded directly from figshare 5528816/5528819. This bypasses mne's `accept=True` terms prompt.
  - The terms are covered only by `DATA_DECISION.md:13`, which records chat-signed interim owner acceptance (H-002).
  - Acceptable, but record that the figshare route needs that acceptance.
- No atlas files are committed (`git ls-files | grep annot|gii|nii`: none).
- nilearn is pinned `==0.14.1` in pyproject `[neuro]`. `requirements.lock` does not exist, although §3 requires it.
- CC-BY-NC is recorded in DATA_DECISION and tribe_requirements. ENH-003 subcortical is also cc-by-nc-4.0 (verified below), so the licence position is unchanged.

**6. Fabrication** (claims from docs/tribe_known_issues.md)
1. Row 12, "facebook/tribev2-subcortical sha 214a5d9, 2026-05-13, cc-by-nc-4.0". Checked with HF API: sha `214a5d93…`, lastModified 2026-05-13T12:54Z, licence cc-by-nc-4.0. **TRUE.**
2. Row 1, "PR #81 open, unmerged; 119 s clip → 239 rows not 120; sum doubles text". Checked github.com/facebookresearch/tribev2/pull/81: open, same numbers. **TRUE.** The line numbers were not on the page, so the `eventstransforms.py l.188-205` reference is not verified there.
3. Row 18, "HF #2 corrected cc-by-4.0→cc-by-nc-4.0 on 2026-03-27". The discussion was merged on "Mar 27", and the API lastModified for tribev2 is 2026-03-27 with sha f894e78, matching the "HF sha still f894e78" claim. **TRUE.**

**7. Cost**
- `python infra/lambda_gpu.py list`: one instance, `yct-smoke` 06e217…, status **terminating**.
- `infra/gpu_ledger.jsonl` (uncommitted change) has launch at 1794924323, deadline +2 h, and terminate at 1794925717, about 23 min later.
- `spent`: **$0.77** of BUDGET_USD 200, 0.4%.
- No orphan. Defect: the ledger has no heartbeat events (§3 requires one every 2 min). I cannot confirm heartbeat compliance for the smoke run.

## Defects (summary)
1. `tests/_atlas.py:17`: a skip was added with no ticket, and the guard fails (rc=1).
2. CI red on 529652d and e9b891c (Lint, `src/yct/tribe_run/*.py`), so tests and guards were never verified in CI.
3. The 151-pass claim has no run directory. The smoke run directory lacks SHA, command and exit code.
4. `config.yaml:118,122`: CBIG pinned to `master`.
5. `data/curation/search_log.csv`: outcome-labelled per-query counts outside the allowed paths.
6. No `requirements.lock`, and no heartbeat records in the GPU ledger.

## Required fixes to lift the VETO
- Open a ticket for the `load_or_skip` skip, get the QA vote, and either justify it or make CI fail when atlases are unavailable (for example `YCT_REQUIRE_ATLAS=1`). Re-run `make guards` green.
- Fix the ruff errors so CI runs Tests and Guards green on the gate SHA, and link that run ID.
- Write `outputs/runs/<id>/` for the test run, containing SHA, command and exit code.
- Pin the CBIG URLs to a commit.
- Move or annotate search_log, or have the Curator confirm the outcome-labelled counts are acceptable.

Items 4 and 5 may be fixed in the FIX cycle; the first three block GO.
