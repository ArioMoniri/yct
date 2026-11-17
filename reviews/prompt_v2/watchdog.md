# Watchdog review: prompt v2 (fresh auditor; repo HEAD f7b2e59)

Scope: the 8 listed artifacts; reviews/prompt_v1/* not read.
Ran: `cat -n` each file; `ls -a` (no `.github/`, `.pre-commit-config.yaml`, `config.yaml`, `docs/owner_age.pub`); `pytest -q tests` (4 passed).

**Vote: FIX.** Items 1–4 block the P0 gate.

## Required changes

**1 [CRITICAL] Blinding fails because the Curator is the PI.** v2.md:83 makes the PI the Curator, contradicting v2.md:191 ("Curator subagent") and ROADMAP.md:8. The agent that reads plaintext outcomes and the permutation seed (v2.md:190) also runs the analysis; `age` sealing does not blind it.
Replace v2.md:83 with: "The executing agent is the PI/Orchestrator. It runs Preprocessing, Modeling and Reporter itself. **Curation runs in a separate subagent with fresh context.** That subagent receives only §4, §5-P1 and the curation spec. It writes only `data/sealed/` and `data/manifest.csv`, and it generates the permutation seed inside the sealed file. It returns only counts by confidence level. These roles do not vote."

**2 [CRITICAL] The human-only actions cannot be enforced as written.** UNBLIND_TOKEN (v2.md:190), veto lifts in DECISIONS.md (v2.md:132) and budget raises (v2.md:114) are all files or env vars the agent can write (lambda_gpu.py:31-32).
Add to v2.md §2 after line 118: "Each human-only action is valid only as a commit or tag signed with the owner's GPG/SSH key `docs/owner_signing.pub`. CI verifies the signature for any change to `UNBLIND_TOKEN`, to `DECISIONS.md` lines tagged `[HUMAN]`, and to `config.yaml:budget`. `BUDGET_USD` and the max-hours cap are read from the signed `config.yaml`, never from the environment."

**3 [CRITICAL] Every governance guard v2 depends on is missing.** The repo has no CI and no pre-commit configuration, so none of these exist: append-only checks (v2.md:109, 153), gitleaks (v2.md:207), the prereg hash check, the frozen-key check (v2.md:175), the 8-gram overlap check (v2.md:101), the spot-audit scheduler (v2.md:136) and the heartbeat agent (ROADMAP.md:28).
Add to ROADMAP.md P0 DoD (after line 43): "- Each mechanism below exists, and a fixture shows it failing on a violation: `.github/workflows/ci.yml` (pytest, ruff, gitleaks full history); `scripts/check_append_only.py` (DECISIONS.md, audit_log.jsonl, gpu_ledger); `scripts/check_prereg.py`; `scripts/check_frozen.py`; `scripts/review_overlap.py`; `infra/heartbeat.py`; `.pre-commit-config.yaml` with gitleaks. Until then those v2 §2–3 rules are ASPIRATIONAL."

**4 [CRITICAL] The GPU ledger is gitignored and only local, so the budget cap can be bypassed.** LEDGER is `outputs/infra/gpu_ledger.jsonl` (lambda_gpu.py:29), and `outputs/infra/` is ignored (.gitignore:6). A fresh checkout starts at `spent_usd()=0` (lambda_gpu.py:57-64): the cap is per working copy.
Fix: "Commit the ledger after each launch/terminate (un-ignore it); `launch` reconciles against `GET /instances` and refuses if any `yct-` instance is unledgered."

**5 [MAJOR] lambda_gpu.py does not implement v2 §3 (v2.md:196-202).**
- 4 h max: the cap defaults to 6 and can be overridden from the environment (lambda_gpu.py:13, 32). The test is tautological (tests/test_infra_guards.py:181-183 uses the module's own cap). Set `BUDGET_MAX_HOURS = 4.0` as a constant and assert `launch(..., 4.01, ...)` raises.
- Instance type: the default is `gpu_1x_a10` (lambda_gpu.py:5, 126), but v2.md:197 forbids the A10 until P0 measures VRAM. Change the default to `gpu_1x_a100`, and refuse `*a10*` unless `config.yaml:p0.peak_vram_gb < 20`.
- 80% alert: absent. lambda_gpu.py:83-84 only blocks at 100%. Add: "if spent ≥ 0.8·BUDGET_USD, append an `alert` event and write `reviews/escalations/budget80.md`".
- Heartbeat (2 min / 10 min kill) and idle kill (15 min <5% GPU): absent from lambda_gpu.py.
- Deadline is enforced only by a manual `reap` (lambda_gpu.py:109-118); a dead session leaks forever. Add an on-instance dead-man switch: `user_data` with `shutdown -h +<max_hours*60>`, plus a watchdog powering off after 10 min without heartbeat or 15 min below 5% `nvidia-smi` utilisation.
- Nothing invokes `reap` at session start or gates; add it to the Makefile and gate job.
- Orphans: `list_ours()` only sees `yct-*` names (lambda_gpu.py:104-106). v2.md:145 requires "every Lambda instance is in the ledger". `reap` must report non-prefixed instances as INCIDENT, without terminating them.
- An instance terminated outside the tool accrues in `spent_usd` forever and never reconciles (lambda_gpu.py:61-62; v2.md:342).
- SSH key fallback `keys[0]` may be a teammate's, or `[None]` (lambda_gpu.py:86). Require `LAMBDA_SSH_KEY_NAME`.
- No tests cover reap, the 80% alert or the heartbeat.

**6 [MAJOR] Gate quorum contradicts the per-phase reviewer lists.** v2.md:106 requires at least 4/5 GO. ROADMAP.md:7, 8, 10, 11, 13, 15-17 list only 3 reviewers for those phases, and ROADMAP.md:9 lists 4, so 4/5 is unreachable. Replace v2.md:106 with: "GO requires no STOP, no Watchdog VETO, and GO from every listed gate reviewer in ROADMAP.md (all 5 at P4b, P6 and P10)."

**7 [MAJOR] The phase order is inconsistent.**
- (a) ROADMAP.md:100 time-averages M0b over W in P3, but W is set only in P4 (v2.md:33, ROADMAP.md:116). Fix: in P3, store per-TR M0b embeddings; average over W in P5.
- (b) The permuted-label validation is "before unblinding" in P7 (v2.md:305, ROADMAP.md:155), but the token is issued in P6 (v2.md:302). Move it to the P6 gate packet: "P6 requires the passing null-FPR, planted-effect, shuffled-AUC and leakage runs (run-ids) before the human issues UNBLIND_TOKEN."

**8 [MAJOR] Path and ignore drift.** .gitignore:3 ignores `data/labels_sealed/`, but v2.md:188 uses `data/sealed/`. `docs/owner_age.pub` does not exist. Nothing ignores TRIBE sidecars or the cache (`*.tsv`, `cache/`, `*.ckpt`). Replace .gitignore:3 with `data/sealed/*.csv` and `!data/sealed/*.age`, and add `cache/`, `*.ckpt`, `data/**/*.tsv`, `*.pem`, `.env.*`.

**9 [MAJOR] Legal gaps in DATA_DECISION (v2.md:231-239).**
Founder faces/voices move from the EU pod (v2.md:195) to US-hosted Lambda: an uncovered international transfer. Llama 3.2 licence/AUP and HCP-MMP terms (tribe_requirements.md:125-126) are not listed.
Add to v2.md:239: "- GDPR transfer to Lambda (US): legal basis, deletion on terminate; - Llama 3.2 licence + AUP and HCP-MMP terms accepted."

**10 [MAJOR] No rule for handling secrets on remote hosts.** HF_TOKEN must reach Lambda (tribe_requirements.md:29); pod_exec.sh:151-152 sends raw commands via SSM, logged in CloudTrail. Add to v2.md:206: "Never put a secret in an SSM command string, user_data, or a CLI argument. Copy HF_TOKEN to Lambda over SSH into a 0600 file, and delete it on terminate."

**11 [MAJOR] The Watchdog re-derivation step contradicts its own blindness.** v2.md:141 requires the Watchdog to re-derive 10 label rows, but v2.md:126 says it never sees the labels. Replace with: "the Watchdog re-derives 10 rows; the human compares them against the sealed file and records agree/disagree counts only."

**12 [MAJOR] v2 overstates tribe_requirements.md.**
- (a) v2.md:34-35 states as fact that no HRF shift is needed and that the early TRs reflect context warm-up. The source marks latency in practice as UNVERIFIED, and the paper reads the localiser at t = 5 s (tribe_requirements.md:88). Prepend to v2.md:34: "Provisional until the P0 impulse clip; if the measured peak latency is above 2 s, W and the no-shift rule are re-decided before P5."
- (b) v2.md:264 says the short side should be "256 (or more)". The source says full input needs a short edge of at least 292 px (tribe_requirements.md:64, 72). Change it to "≥292".
- (c) v2.md:266's "backbone samples at 2 Hz" is wrong: 64 frames per 4 s = 16 frames/s; require source ≥16 fps (tribe_requirements.md:64, 71).
- (d) `[N-fact n]` tags (v2.md:18, 34, 197, 272, 281, 290) have no anchor in tribe_requirements.md; cite § numbers.
- (e) v2.md:272-273 purges `.tsv` "before every run", which can delete the injected transcript so TRIBE silently calls unpinned `uvx` (tribe_requirements.md:53). Specify "purge → inject → run"; remove `uvx` from PATH so it fails closed.

**13 [MINOR]** D-008 (DECISIONS.md:13) omits v2.md:76's "≥80 per class"; κ ≥ 0.9 (ROADMAP.md:69) is missing from v2.md:257; DECISIONS.md:5-18 lack the evidence field required at line 3; the grep at v2.md:143 matches v2.md itself, so restrict it to `src/ analysis/ outputs/`.
