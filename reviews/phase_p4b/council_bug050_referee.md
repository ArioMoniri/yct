# Council BUG-050: referee
Verdict: **APPROVE with conditions.** I read bug050_diagnosis.md, BUGS.md BUG-050, 6460da1, 38d32d5 (branch bug050-failing-test), d071_v3.md (a)/(f)/(g), config `controls.refclips.families`, refclips58.py `plan`/`bed`/`flash_frames`, kernels.py `evaluate_mt_plus`, and gpu_wave1_p4.py `restorable`/`do_job`. I read no sealed data, labels, transcripts, predictions or features.

**R1. Root cause: confirmed.** `restorable()` looks entries up only by `job.id` (or `base_id` for ablations). The cache key is content-only. A byte-identical clip that lands on a new box re-extracts (BUG-006 nondeterminism), and the immutable store correctly refuses the different tar. Rejecting (b) and (c) is right: (c) would turn GPU nondeterminism into fake between-clip variance.

**R2. The fix is approved as scoped.**
- Restore by the expected key, computed before staging from the measured mp4/tsv shas and `State.revisions_sha256()`. Use the existing crash-recovery stage path.
- Match only a `gate_pass` entry whose key maps to exactly one tar sha. If the key cannot be computed, behaviour stays as it is today.
- It changes no frozen artifact and no D-063 key scheme. It is outcome-blind: it uses shas only and is decided before any further output.

**R3. The identical clips are correct by design, not a build bug.**
- D-071 (a) has one seeded bed (SEED 20261117), and "visual-only clips carry the control audio bit for bit".
- GREY-CTRL has no events. FLASH varies only by shift s = f(i // 2): i = 0, 1, 4 give s = 0 and i = 2, 3 give s = −1. Neither family takes a per-item seed under D-071 (b), because neither has a random visual draw.
- So the frozen spec determines GREY_CTRL_00 == 01, FLASH_00 == 01 == 04 and FLASH_02 == 03. The builder's one-bed reading is the literal spec, already reported in its docstring and in talkface_ready.md.
- Bit-identical predictions are therefore the correct outcome. The test pins exactly these groups.

**R4. Readout.**
- GREY-CTRL: `plan()` uses only grey_ctrl_00 as the control. GREY_CTRL_01 never enters a kernel, so this has no analytic effect. Report it as a redundant replicate that shows cross-session cache reuse.
- FLASH (K6 only): the frozen rule is `diff > 0` on the 5-clip mean, and the bootstrap CI is reported only. Do not change either; changing a frozen rule now is forking.
- The report must disclose that the 5 FLASH clips are 2 distinct stimuli (3 × s = 0, 2 × s = −1). The point estimate therefore weights s = 0 at 3/5, and the clip-bootstrap CI understates uncertainty (n_eff = 2). A distinct-stimulus CI may be added as a labelled secondary, never as a gate.

**Blocking**
- B1: the fix plus the 38d32d5 test turned green on the campaign branch, with no xfail or skip.
- B2: the manifest row of a key-restored job records `restored_from_job`, and `cache_reused` is True.
- B3: a test that a key match with a conflicting tar sha, or a key from a non-pass entry, STOPs instead of restoring.
- B4: a test that the P4 manifest and its sha (`03322d84…`) stay unchanged and that P4 job selection is unaffected.
- B5: the FLASH disclosure in R4 is added to the report template before the readout.
- B6: BUGS.md BUG-050 goes to FIXED, citing this council.

**Owner questions:** none. R3 and R4 follow from the frozen text.
