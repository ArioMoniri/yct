# Watchdog Review: Prompt v1 (A/B/C)

Reviewer: Watchdog (independent integrity and governance auditor)
Target: `docs/prompts/v1_original.md` (82 lines)
Scope: how the agents work and are governed, not the science.

## Verdict: FIX

The science plan is strong. The governance is not. As written, one LLM grades its own work, writes the labels it later analyses, can unblind itself (C§6 "unanimous GO; then unblind"), and can rent GPUs with no spending limit. None of these flaws is fatal, but the prompt must not run until items 1–8 are merged. Items 6 and 7 must be in place before any download (P1 Step 4) and before any GPU rental (P4). They are hard blockers.

## Required changes

**1. [CRITICAL] The council can rubber-stamp itself (C§2).** One model is told to play nine or more roles. Each role sees the author's summary. A majority GO passes the gate. No evidence is required.
Drop-in (replace the gate protocol):
> Each reviewer runs as a separate subagent with fresh context. Its input is only the gate packet: file paths, commit SHA, test output and metric tables. It never sees the author's narrative, conclusions or other reviews. A review must list ≥3 concrete defects, each citing `path:line`, a metric or a command output. Alternatively it must say "Searched: <X, Y, Z>; found none" and list the checks it ran. A review with neither counts as missing, not as GO. Each gate has a red-team reviewer, assigned by rotation from `reviews/rotation.txt`, whose instructions are to break the result. GO needs every required review present, no STOP, and Watchdog evidence-complete status.

**2. [CRITICAL] Agents can unblind themselves (C§3, P6).** `data/manifest.csv` holds `outcome`, and every analyst reads the manifest. The shuffled labels are produced by the same agents that hold the real ones.
Drop-in:
> True labels live only in `data/sealed/labels.csv.age`, encrypted to the human owner's key. The analysis manifest has no outcome column. During blinded phases, `src/stats` reads `labels_blinded.csv`: a permutation made with a seed that is withheld from agents. Unblinding needs an `UNBLIND_TOKEN` that the human issues after verifying the prereg hash. Only `src/stats/unblind.py` reads it. Curation (P1) writes labels straight to the sealed file. After P1, curators do not take analyst roles.

**3. [CRITICAL] Labels and evidence can be fabricated (A Step 2).** `evidence_quote` is free text with nothing to check it against. "B: founder states outcome" can be invented.
Drop-in:
> For every `evidence_url`, store a snapshot at `data/evidence/<sha256>.{html,png,txt}`. Record `evidence_sha256`, `fetched_at_utc` and an archive.org URL if one exists. `scripts/verify_labels.py` must find each `evidence_quote` verbatim in the stored text and recompute the A-rule from a stored YC-directory snapshot. CI fails on any mismatch. At each P1 gate, a fresh agent with no curation context re-derives the labels for a random 15% (≥10 rows) of the manifest from the URLs alone. Any disagreement on more than 1 row sends the gate back to FIX. A human spot-checks 10 rows.

**4. [CRITICAL] Goalposts can move with no guard (C§3 "QA vote to change", P6).** QA is also an agent. Nothing enforces the prereg hash or keeps DECISIONS.md append-only.
Drop-in:
> CI blocks a merge if any of these fail: (a) `prereg/PREREG.md` sha256 ≠ the hash in `prereg/PREREG.sha256` after the lock tag `prereg-lock`; (b) `DECISIONS.md` and `reviews/watchdog/audit_log.jsonl` are not strict prefix-extensions of their previous versions; (c) a `tests/` diff deletes or loosens an assertion (lower `assert` count, wider tolerance, new `skip`/`xfail`) without a `TEST-CHANGE:` entry in DECISIONS.md approved by Watchdog; (d) a threshold key in `config.yaml` (listed in `config_frozen_keys.txt`) changes after it is frozen. `.github/CODEOWNERS` (or `infra/protected_paths.txt` plus a pre-receive hook) names the human owner for `prereg/`, `config_frozen_keys.txt`, `tests/` and the CI config.

**5. [MAJOR] Test results can be invented.** An agent can report "tests green" without running the tests.
Drop-in:
> A claim of a test result or metric is valid only with a link to `outputs/runs/<run_id>/` holding the command, exit code, stdout, git SHA and env hash, written by `make` and never typed by hand. A claim about TRIBE v2 must cite a file and line in the pinned TRIBE commit, otherwise it is labelled UNVERIFIED.

**6. [CRITICAL] GPU spending has no limits (P4; no rental text at all).**
Drop-in:
> GPUs come only from Lambda Cloud, through `infra/gpu.py`. The default is an A10 ($1.29/h). An A100 needs a DECISIONS.md entry that justifies the extra cost. Hard cap: $150 total per project (`GPU_BUDGET_USD`). The ledger `infra/gpu_ledger.jsonl` updates every 5 min. At 80% of the cap, the Watchdog is alerted. At 100%, everything terminates. Each instance gets a max-lifetime tag (default 4 h) and is killed when the tag expires. The job sends a heartbeat every 2 min, and 10 min without one means terminate. GPU use below 5% for 15 min means terminate. Instances are created with `try/finally` termination, and the orchestrator lists all instances at the start of every session and at every gate. An instance not in the ledger is terminated and reported as an incident. Never launch EC2: the vCPU quota is exhausted. Never run TRIBE on the t3.large pod.

**7. [CRITICAL] The legal and data position is unresolved (A RULES).** "Follow platform ToS" contradicts "yt-dlp best quality": YouTube ToS forbids downloading except through YouTube's own features. Founders' faces and voices are personal data. The pod is in eu-central-1, so GDPR applies. TRIBE v2 is licensed CC-BY-NC-4.0.
Drop-in:
> Before P1 Step 4, the human owner signs `docs/legal/DATA_DECISION.md`. It must state: ToS risk accepted or not; the legal basis (Art. 6(1)(f) plus Art. 89 research safeguards); a one-page DPIA-lite; the retention period (default: raw video deleted 90 days after P4 QC, keeping only hashes, features and evidence text); that the use is non-commercial (CC-BY-NC). If the owner's use is commercial, STOP. Raw media and evidence stay encrypted at rest on the pod and in an S3 bucket in eu-central-1, never git, never a public bucket, never sent to Lambda except an ephemeral copy that is deleted on termination. Outputs carry pseudonymous `video_id`s. No company or founder name appears in figures or reports. No per-video brain map is published. On a takedown or erasure request, delete within 72 h and log it.

**8. [MAJOR] Secrets have no rules.**
Drop-in:
> Keys come only from env (`LAMBDA_API_KEY`, `HF_TOKEN`), loaded from `~/.config/yct/env` with mode 600. Never pass keys on the command line, put them in config or notebooks, or echo them. A logging filter redacts `[A-Za-z0-9_\-]{24,}` that matches known key prefixes. `gitleaks` runs in pre-commit and CI. A leak means: rotate the key, record an incident, and hold the gate until the human confirms the rotation.

**9. [MAJOR] Debug and enhance loops have no bound (C§4); "stuck" is undefined.**
Drop-in:
> Stuck means any of these: 3 fix attempts on one BUGS.md item without a new failing test turning green; 2 hours wall-clock on one item; the same error signature 3 times; no new commit in 90 min while active. Stuck triggers an escalation file `reviews/escalations/<id>.md` (what was tried, evidence, options) and pauses that work stream. Each phase may raise at most 5 enhancement tickets. Enhancements are frozen after the prereg lock except as EXPLORATORY.

**10. [MAJOR] Pressure to inflate labels.** The STOP rule "<15 conf-A per group" gives agents a reason to upgrade B labels to A, and the pilot findings in C§0 prime curators.
Drop-in:
> Curators do not see C§0 or the hypotheses. Upgrading a confidence level needs a new evidence snapshot. The Watchdog checks the history of A/B/C changes in git.

**11. [MAJOR] B12 "two coders κ≥0.7" is not independent if both coders are the same LLM.** Require one human coder on ≥20% of rows, or two different model families with no shared context. Report κ against the human coder.

**12. [MAJOR] Some actions are human-only, and the prompt does not say so.** List them as HUMAN-ONLY: unblinding; any prereg edit after the lock; budget increases; Prolific or IRB (Phase 9b); signing the legal decision; making the repository or report public; deleting raw data early or late. Agents prepare a request in `reviews/escalations/` and continue other unblocked work. They never wait idle and never proceed on assumption.

**13. [MINOR] "Majority GO" with 12+ roles lets the core roles be outvoted.** Each gate names required roles (as in C§5). Every required role must vote GO.

**14. [MINOR] Gate packets have no fixed format.** Require `reviews/<phase>/packet.md` with: SHA, run IDs, changed files, open BUGS, deviations, and the checklist from the phase DoD.

**15. [MINOR] The global DoD (C§6) lacks an integrity line.** Add: "Watchdog final audit GO; zero running GPU instances; ledger reconciled with Lambda invoices; retention schedule active."

---

## Section 2b: Watchdog & Integrity Rules (ready to paste after C§2)

**2b.1 Independence.** The Watchdog is a separate subagent with fresh context at every invocation. It holds no other role, writes no project code, and never sees the sealed labels. Its inputs are the repository at a given SHA, the run directories, the GPU ledger and the Lambda instance list. It never sees author narratives.

**2b.2 Powers.** The Watchdog may (a) VETO any gate whose evidence is missing, unverifiable or inconsistent. A veto overrides any council vote. (b) Terminate any GPU instance immediately. (c) Freeze a work stream pending human review. (d) Require a re-derivation by a fresh agent. (e) Open incidents. It may not change code, data, tests or prereg, and it may not unblind. Only the human owner can lift a veto, and only in writing in DECISIONS.md.

**2b.3 Cadence.** The Watchdog runs (1) after every gate packet, before the vote is counted; (2) at random spot audits, at least one per working day, timed by `random.Random(date_seed)` and unannounced to other roles; (3) on any trigger: budget at 80%, a stale heartbeat, CI red on main, a change to a protected path, a STOP vote, or a stuck escalation.

**2b.4 Checklist (every run).**
1. Provenance: every claimed metric or test result links to a `outputs/runs/<run_id>/` with a matching SHA and exit code. Re-run 1 random test file and 1 random metric. Mismatch = VETO.
2. Labels: `verify_labels.py` passes. Every evidence hash resolves to a stored snapshot. After P1, label rows are re-derived blind for a random sample of ≥10.
3. Goalposts: prereg hash unchanged since the lock; DECISIONS.md and the audit log are append-only; no test assertions loosened; frozen config keys unchanged; every deviation listed.
4. Blinding: there is no outcome column in any analyst-readable file. Search the repository for `outcome`, `accepted` and `rejected` outside `data/sealed/` and the curation code. The unblind token is absent before P6 GO.
5. Council: every required review exists, ran in an independent context (subagent ID logged), and cites evidence or lists its searches. Copied phrasing across reviews (>40% shared 8-grams) = review invalid.
6. Cost: Lambda instances listed. Each one is in the ledger, has a heartbeat under 10 min, and is within its lifetime and budget. An orphan is terminated now.
7. Secrets: gitleaks is clean on full history, and logs contain no key-like strings.
8. Data/legal: `DATA_DECISION.md` is signed before any download. Retention deadlines are honoured. No names or faces appear in outputs. The NC licence is respected.
9. Loops: no item is over its stuck bound without an escalation file.
10. Fabrication spot check: pick 3 factual claims at random (a TRIBE spec, a URL, a citation) and verify them against their source.

**2b.5 Outputs.** Each audit writes `reviews/watchdog/<YYYYMMDD>_<gate|spot>_<n>.md`, containing the verdict (PASS / VETO / INCIDENT), each check with the command run and its result, and the defects found or "searched X, Y, Z; found none". It also appends one JSON line to `reviews/watchdog/audit_log.jsonl` (ts, sha, scope, verdict, findings_count, hash of the report). CI enforces that the log is append-only. Incidents go to `reviews/watchdog/incidents/<id>.md`. On CRITICAL incidents (leak, orphan instance, unblinding, fabrication), the human owner is notified within 1 h.

**2b.6 Integrity rules for all agents.**
- No claim without an artifact. "I checked" without a run ID counts as not checked.
- Never invent a URL, video, label, quote, citation, TRIBE parameter or test result. If unsure, write UNKNOWN and open a ticket.
- Never edit tests, thresholds, prereg or logs to make a check pass. Fix the code or escalate.
- Never read `data/sealed/`. Never compute group statistics on real labels before the human-issued unblind token exists.
- Never leave a GPU instance running without a heartbeat. When in doubt, terminate.
- Report your own mistakes immediately in BUGS.md. Concealment is the only unrecoverable error.

**2b.7 Watchdog fallibility.** The human owner reviews the audit log weekly. Every 3rd gate, a second independent Watchdog instance audits the same SHA. A disagreement goes to the human.
