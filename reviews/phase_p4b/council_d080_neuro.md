# Council review D-080 (neuro member)

Verdict: **APPROVE** (no blocking items). Read: d080_draft.md, BUGS.md BUG-037, `git show 8148366 4118fa2`,
data/refstim/d080_dry_audit.json. Not read: data/sealed/*, labels, transcripts, outputs/. Tests: 75 passed (d078/d079/d080).

## C1 <-> C1 equivalence: outcome-blind and safe
- Selection reads only the decision. `licence` and `personality_rights` are both C1 rejects from the frozen
  `audit.c1_reasons`, so a reason change between them cannot add or remove any stimulus. Both reasons are logged.
- The rule is generic: it is triggered by the STOP row's identity and reasons, not by any pass or fail outcome.
  The only v2 information it uses is the 18 superseded rows, which had 0 passes.
- `audit_pair` is narrow. It applies only when `a[0]==b[0]=="reject"` and both reasons are C1. It runs after the
  flip check, so a flip-listed title still rejected at C1 still STOPs. Admissibility changes in either direction
  still STOP. The face-stimulus confound from personality rights (identifiable people) is an existing D-079 filter
  and is unchanged.

## Dry audit: adequate for its stated scope
- The sha in config matches the file (35bb0b95...). It contains no image content or outcomes after the download.
  `reaches_download` reveals no pass information.
- Flip counts match the committed BUG-036 list (260/108/3). The 12 c1_equivalent pairs are the whole BUG-037
  class, and there are 0 would_stop and 0 missing_sha1. `dry_pair` also flags the rule-level cases the v2 audit
  would STOP on (C1 vs C2/C4, and v1 passing C1 while v3 now rejects there).

## Residual STOP / bias risks (non-blocking, already disclosed)
1. Rules after the download (C5/F*/B*/P*) cover 348 pairs that the dry audit cannot predict. Detector
   reproducibility rests on the 6 reaches_download rows in v2 run 1 that matched v1. Run on the same pod
   image/hardware as the v1 and v2 runs (`check_env`).
2. Commons drift between the dry audit and the run: template edits that flip admissibility would STOP. Launch soon
   after the freeze.
3. Nit: `check_frozen_d080` checks that the sha is set but does not re-hash the dry-audit file. The two-commit freeze
   covers this.
