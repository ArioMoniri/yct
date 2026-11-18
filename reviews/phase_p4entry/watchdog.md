# Watchdog: Gate P4-entry (wave-1 full TRIBE inference)
Watchdog subagent, session_011NAQ1mksc4Ea1mJcrGfTSd.
- **Audited:** HEAD 421c7ef. Working tree clean apart from ignored files.
- **Read:** packet.md, DECISIONS D-060..D-062, BUGS BUG-013(2nd)/BUG-018/BUG-027, ENHANCEMENTS ENH-002/ENH-008, the four cited run dirs, `scripts/gpu_wave1_p2b.py`, `scripts/wave1_p2b_pod.py`, `infra/{lambda_gpu.py,gpu_deadman.sh}`, `src/yct/tribe_run/feature_cache.py`, v2.md §5 P2–P4b, ROADMAP P4, and the prior watchdog reviews in final_round.
- **Not done:** I decrypted nothing, made no AWS or Lambda calls, and did not open data/sealed/.

## Re-runs (read-only)
- **All 7 `scripts/check_*.py` pass:**
  - append-only: OK, 5 files;
  - blinding: OK, 389 tracked files;
  - guard_config: OK, 95 commits;
  - human_signed: OK, with 3 BUG-011 exemptions;
  - test_weakening: OK, 3 allowlisted;
  - prereg: no lock yet;
  - frozen_config: "0 frozen keys", which is expected before the lock.
- **`pytest -q`:** 619 passed, 0 skipped, 0 failed (212 s).
- **Blinding grep:** I searched for the sealed column names (label_confidence, discovery_method, evidence_url, evidence_quote, route) in:
  - the four wave-1 run dirs, tracked and untracked files;
  - data/wave1_*.csv;
  - the diff cfeac3d..HEAD (excluding guard code and tests);
  - the commit messages since cfeac3d (I also searched those for outcome words).

  There were 0 hits.
- **Run-dir content:**
  - The run dirs hold no transcript text.
  - The events.csv files are synthetic clips only, with an empty text column.
  - feature_cache_manifest.json holds hashes and clip names only.
  - The real-clip entries in metrics.json are label-free scalars.
  - The manifest URL column is the accepted analyst view (D-052, D-053e).
- **Test weakening:** in cfeac3d..HEAD, the only test edit outside additions is `tests/test_photometric_bt709.py`. It adds the ENH-005 swscale flags to the independent decoder, which brings it in line with the spec. It is not a weakening.
- **GPU spend:**
  - The ledger gives $4.81 for the three wave1p2b launches: 965 s, 1162 s (the orphan, terminated "manual"), and 6577 s at $1.99/h.
  - That matches D-062. The ledger total is $9.23 of $200.
  - The ledger shows no live instance.
  - The last run's `orphans_swept_at_start` was empty, and it ended with `alive_after` [].
- **Provenance:** all three completed runs have git_sha, config_sha, cmd, exit_code, pip_freeze and metrics with `git_dirty: False`. For gaps, see defects M3 and m3.

## Q1: verdict FIX
The determinism gate, the BUG-018 verification and the cache archive are sound, and nothing is unblinded. Inference may start once B1–B3 below are closed. All three are cheap. None needs a new council round: QA can sign off B1, and the coordinator can record B2 and B3 in DECISIONS and BUGS.

## Q2: yct_0644
- **Ruling:** exclude it now, unconditionally. Do not wait for "if not obtained before P4".
- **Reason (source-unavailable):** there is no source file, and its URL is sealed.
- **Reason (blinding, BUG-013 2nd entry):** the orchestrator already knows this video's label, because the URL path carries an outcome word.
- **Why not make it conditional:**
  - Making the exclusion depend on retrieval effort leaves a discretionary, label-aware choice open: whether to keep trying to get the file.
  - Excluding the one analysis video whose label the analyst side knows is the blinding-safe choice in any case.
- **Record:** a DECISIONS entry, dated before the first P4 launch, with N = 52 and T1 = 51 (after yct_0483).
- **Follow-ups:**
  - Restate the v2.md §0 N = 53 MDE line for 52 (Biostat).
  - Report the exclusion in P10 as possibly not missing at random.

## Q3: sub-16 fps sources
- **The packet framing is wrong.** yct_0641 is not in the analysis set: `qc_pass = False`, so it fails `in_primary & qc_pass`. Only **yct_0626** (12.5 fps) matters.
- **The written rule says exclude.** v2.md §5 P2 reads "sources must be at least 16 fps", and config has `normalize.min_source_fps: 16`. The code only flags (`source_fps_below_min`).
- **Watchdog preference:** follow the written rule. Exclude yct_0626 from the primary T1/T3 analysis, still run TRIBE on it, and give a sensitivity analysis that includes it (no α spent).
- **D-060's reverse (keep + flag + sensitivity excluding it) is acceptable only if:**
  - it is ruled as an explicit, reasoned deviation from the protocol's "must";
  - the ruling is recorded before any P4 output exists.
- **Either way, the choice is fixed now.** It is never revisited after P4b or after unblinding.

## Q4: ENH-002 visual control
- **Process requirement:** this is now BLOCKER B2. Choose before any real-data P4 output exists, not only before the P4b lock.
- **Why so early:** P4b is a STOP gate. If wave-1 predictions exist when the ROI is chosen, the choice can be tuned to whether the control passes on the real videos. That is control-outcome peeking, even though it is label-blind.
- **Which option:** use the **MT+ fallback**. It is the only option the protocol already names as the "pre-lock fallback" (v2.md P4b ROIs), so it adds the fewest forking paths.
  - A luminance-only kernel would be a new design element.
  - Keeping V1–V3 knowingly accepts a likely STOP.
  - Neuro owns the scientific merits; this is the process ranking.
- **Record in DECISIONS:**
  - the ENH-002 numbers (V1–V3 0.06, MT+ 0.46, FFC 1.25, standardised);
  - that the kernel is derived from the reference clips only;
  - that there are no further control changes.

## Q5: WER
- **Not blocking for P4.**
- **Blocking for the P4b lock and P6 (prereg),** because v2.md P2b requires it to be reported.
- **Pre-specify the action rule now, before anyone sees a WER value.** For example:
  - WER is report-only;
  - re-transcription happens only for a gross failure (wrong language, or empty output), via a new D- entry.
- **Cost of a late change:** any transcript change alters the cache key. Every affected clip then has to be re-extracted and re-predicted, and that P4 GPU time is spent again.
- **Missing deliverable:** the "accent flag" required by v2.md:396 has no implementation and no ticket. Ticket it (see m5).

## Q6: ENH-008 caption flag
- **Not blocking for P4:** TRIBE does not read it, and `text_frac` is out of M0 by protocol.
- **Blocking for P5 (M0 assembly freeze):** either implement the label-blind proxy or record it as a limitation in DECISIONS, before the P5 features are built and before the lock.

## Q7: BUG-027 fix
**Adequate for one short, watched run. Not adequate for P4.** Here is why:
- **P4 is long.** The measured fresh extraction is about 300 s per 58 s clip. 57 T1 + 57 T3 extractions come to about 9–10 GPU-h, plus ablations and M0b, against `max_hours_per_instance: 4`. That is at least 3 launches.
- **The driver lives in the container.** It and the reaper run in the session container, which has already restarted once.
- **A dead-man halt does not stop billing.** The dead-man only halts the box, and Lambda bills a halted instance.
- **Termination waits for the next driver start.** `sweep()` runs only when a driver next starts. If no one starts one, exposure is unbounded, at $1.99/h (about $48 per day).
- **Required fix (B3):** a terminator that does not live in the container.
  - **Cheapest option:** at each launch, create a one-shot scheduled task (a fresh session in the same environment) at `deadline + 15 min`. It runs `python infra/lambda_gpu.py list` and terminates every live yct-* instance whose ledger deadline has passed (`reap`/`sweep` are safe at that moment, because the box's own hard cap has already halted it).
  - **Result:** exposure is bounded at about max_hours + 0.25 h, or ≤ $8.5 per launch.
  - **Alternative:** the owner-approved pod-side driver under nohup/systemd.
  - **Don't:** never schedule a blind periodic `sweep` while a healthy run is live, because it terminates every yct-* instance.

## Q8: other items to fix before P4
See B1 (no reviewed P4 driver) and M1–M4 below.

## Defects

### BLOCKER
- **B1. There is no P4 driver to approve.**
  - **Problem:** Q1 asks for a GO on code that does not exist. `scripts/` has `gpu_wave1_p2b.py` but nothing that runs T1 + T3 × {full, audio, video, text+TTS} over the analysis set.
  - **Fix:** commit `scripts/gpu_wave1_p4.py` (or the equivalent) with tests, and get QA sign-off before the first launch. The driver must:
    - run as resumable chunks of ≤ 4 h each, skipping clips whose cache entry and predictions already exist (content-addressed);
    - sync each clip to S3 as it finishes, so a restart loses at most one clip;
    - read the analysis set from `manifest.analysis_view` (no company_id/url) and exclude the B2 rulings;
    - write no speech text or events.csv for real clips to `$YCT_RUN_DIR`;
    - record the GPU type per video;
    - write the final feature-cache manifest sha256 into metrics and into a DECISIONS entry. The prereg must later carry that hash (v2.md P4).
- **B2. Label-blind rulings must be recorded before any real-data P4 output.**
  - **Fix:** one DECISIONS entry, dated and committed before the first launch, covering:
    - the yct_0644 exclusion (Q2);
    - yct_0626 (Q3);
    - the motion-control ROI (Q4);
    - the WER action rule (Q5).
  - **Why:** without it, these choices can be made after P4 outputs are seen. Q4 is a STOP-gate choice.
- **B3. There is no container-independent terminator for multi-launch P4** (Q7).
  - **Fix:** a scheduled terminator at each launch's deadline + 15 min (or a pod-side driver), plus a test or dry run of that path.
  - **Also:** record it under BUG-027 as a status line.

### MAJOR (fix before the P4b lock; the ticket goes in now)
- **M1. T2 and M0b are silently out of scope.**
  - **Problem:** ROADMAP P4 says "Run all videos on T1/T2", and v2.md §3 says one GPU type for T1, T2, T3, ablations and M0b. The packet asks only about T1 + T3. T2 is now possible, because BUG-018 is verified for clips over 60 s.
  - **Fix:** either include T2 and M0b extraction in this P4 run (same GPU type, same cache), or defer them with a DECISIONS entry and note that the one-GPU-type rule still binds.
- **M2. An undocumented deviation from a hard P4 prerequisite.**
  - **Problem:** v2.md P4 requires cache key = sha256(video ‖ transcript ‖ revisions ‖ device class). `feature_cache.cache_key()` (`src/yct/tribe_run/feature_cache.py:96-99`) hashes only the video and transcript.
    - Revisions are enforced by refusing a mismatch (:162-165), which is functionally adequate.
    - The device class is neither in the key nor checked.
  - **Fix:** before the P4 cache is built:
    - store the GPU name in the sidecar and refuse a mismatch;
    - record a DECISIONS entry that the revision check plus the device check is equivalent to the keyed form.
- **M3. Tracked data were produced by pod-only, untracked code.**
  - **Problem:** `data/wave1_confounds_summary.csv` was regenerated in the P2b run by `/work/yct/scripts/wave1_summ.py` (`gpu_wave1_p2b.py:401`). That script is not in git. A copy sits only in the older run dir wave1_p2p3_20261117T202935Z, and `wave1_p2p3.py` is the same case. So `git_dirty: False` overstates provenance.
  - **Fix:**
    - commit both scripts under `scripts/` and call them from the repo path;
    - record the sha256 of every pod-side script a run executes in metrics.json;
    - apply the same rule to the P4 driver.
- **M4. The prior watchdog's required changes were never ticketed** (gD032_c3_watchdog.md). None appears in BUGS or ENHANCEMENTS:
  - the guard token is still self-asserted (`check_guard_config.py:36`);
  - `.gitleaksignore` and `.gitleaks.toml` are unfrozen;
  - the residual skip evasions remain;
  - `reviews/watchdog/audit_log.jsonl` is still missing;
  - scratchpad `repair_16837/` (a full history mirror including f48a331), `gl/` and `gl2/` are still present.

  **Fix:**
  - add the BUG and ENH lines now;
  - create audit_log.jsonl with the earlier rounds and this one;
  - `rm -rf` the scratchpad items (do not shred them, per BUG-017).

### MINOR
- **m1. ROADMAP is stale.** The status table still shows P1–P3 as TODO and P0 as WIP. Update it via an R-n entry.
- **m2. The packet mis-frames Q3.** It lists yct_0641, which is not in the analysis set. Correct this in the decision record.
- **m3. A partial run's report is silent about what is valid.**
  - **Problem:** run wave1p2b_20261117T234829Z has exit_code 1, yet its P2b outputs (ingest, plus the confound refresh in the `finally` path) are used. The fact is stated only in the commit message and D-062, and its report.md does not say which steps are valid.
  - **Fix:** append a note to the run dir, as was done with ABORTED_NOTE.md.
- **m4. The D-038 Gate-2 clip rule changed from "seeded sha" to "first 3 sorted ids".**
  - **Problem:** the rule is label-blind and was committed in code (4db5895, 23:48:23) before the run (23:48:45). But the only record is the post-hoc D-062, which attributes it to an "owner/coordinator ruling".
  - **Fix:** append a short D- line that records the deviation itself.
- **m5. The P2b accent flag (v2.md:396) is unimplemented and unticketed.** Fix: add an ENH entry.
- **m6. The GPU ledger lives only in the container and git.**
  - **Problem:** a container restart before a commit loses launch records, and with them `spent_usd()` input. A sweep can also terminate an instance that has no launch record.
  - **Fix:** mirror every ledger event to S3, and have `sweep` log unknown instances with an estimated start time.
- **m7. `sweep()` terminates every yct-* instance.**
  - **Problem:** two concurrent drivers (for example, council or subagent sessions) would kill each other's runs.
  - **Fix:** add a lock object in S3 or SSM that a driver must acquire before launching.
