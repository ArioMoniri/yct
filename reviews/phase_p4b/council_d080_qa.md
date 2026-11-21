# Council D-080 — QA review (BUG-037 audit amendment, v3 logs)

Reviewed: reviews/phase_p4b/d080_draft.md, commits 8148366 + 4118fa2, data/refstim/d080_dry_audit.json.
Not read: data/sealed/*, labels, transcripts, outputs/ predictions.

**Verdict: APPROVE** (no blocking items).

Tests: `pytest -q tests/test_refstim_d080.py tests/test_refstim_d079_signoff.py tests/test_refstim_d079_recheck.py` → 58 passed.
Checked by hand: sha256(d080_dry_audit.json) = 35bb0b95…e6fe7, the same as config; v2 run-1 log sha = cdd7d3e2…1d00, the same as BUG-037.

**C1 ≡ C1 is outcome-blind and safe.** `audit_pair` returns `c1_equivalent` only when both sides are `reject` and both reasons are in the frozen `c1_reasons`. The file is rejected before the download either way, so the selection outcome cannot change. The rule is checked after the flip branch, so a flipped title that is still a C1 reject still STOPs. It is also checked after equal/duplicate. Admissibility changes in either direction still STOP. The only v2 information used is the STOP row's two reasons. Both reasons are logged (`audit_c1_equivalent`). The schema pins `audit_c1_equivalence: Literal[True]`, and `effective_cfg` deep-copies the config without mutating the frozen D-079 key.

**The dry audit is adequate for what it claims to cover.** It runs the frozen `evaluate_image` itself, stopped at the download, so it uses no second implementation. Every row is counted: face 948 = 451+2+260+235, v2 18 = 12+6, body 568 = 346+9+108+105, d078 15 = 9+1+3+2. The flip counts match the committed BUG-036 list (260/108/3). would_stop = 0, and the 12 c1_equivalent pairs size the BUG-037 class that BUGS.md left uncounted.

**Residual STOP risk (not blocking; disclosed or inherited from D-079).**
1. There are 348 `reaches_download` pairs. The audit still compares their post-download decisions (C5/F*/B*/P*) for equality. A different detector or download would STOP the run, which is the correct fail-closed result. Some evidence it will not happen: the v2 run reproduced its 6 v1 post-download rows before rank 19.
2. A Commons edit made between the dry audit and the run could change C1 or identity. That case is covered by the in-run audit or identity_changed.
3. C3 duplicates can't be predicted in a dry run. The B2 duplicate rule already handles them.

**Selection bias.** None found. Snapshots, order, filters, thresholds, the first 20 passes and C3 state (from the v3 logs only) are unchanged. Superseded logs are read only by the audit, and preload/finalise reject any row that is not v3.

**Non-blocking nits.** These would harden the launch but are optional before the freeze.
- `check_frozen_d080` checks that `dry_audit_sha256` is frozen and non-null. It does not re-hash `dry_audit_file` or assert `would_stop == []` at launch.
- The runner does not re-verify the sha of the superseded v2 log (cdd7d3e2…) before the audit reads it.
