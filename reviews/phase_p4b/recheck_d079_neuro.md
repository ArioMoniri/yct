# Re-check D-079 v2 — Neuroscientist

Date: 2026-11-21. Read: council_d078_d079_neuro.md (my cycle 1), d079_v2.md, d079_v2_response.md,
`git show d46d6b5 2370c0e` (config, refstim.py, refstim_auto.py, runner, tests). I did not read
data/sealed/*, labels, transcripts, outputs/ predictions, images or log rows.

**Verdict: APPROVE.** No blocking items.

## My cycle-1 items
1. **Body enters the gated FFC contrast; male-only skew; no sex control; sex never labelled.** Resolved.
   d079_v2 §5.4 and the DECISIONS "D-078 note" both say body enters face − mean(place, body) (D-071 d),
   that neither source is sex-controlled, that the expected gating effect is negligible and why (hair/back
   of head regardless of sex; B3 removes detected faces). "Never labelled, counted or used for selection"
   is the pre-stated choice. The per-source counts and the source of each body pass are written by
   `finalise` (`image_source_counts_v2.json`, manifest `source`), as required (§5.3).
2. **File-identity rule, pre-chosen, tested.** Resolved. `identity_rule: stop` is in config.
   `ra.check_identity` runs before `licence_of` on every candidate (snapshot sha1 == imageinfo
   `commons_sha1`, taken from `iiprop=...|sha1` in page_meta). It runs again inside `load()` on the sha1 of
   the downloaded bytes, so a cached scratch file is checked too. Missing values fail closed.
   `test_identity_rule` covers equal, Commons mismatch, bytes mismatch and a missing snapshot or Commons
   sha1. The source-routing test asserts that the runner calls it. `commons_sha1` is logged in every row.
3. **Contact sheet applies to v2; content will differ from v1.** Resolved (§5.5, §5.6). The wording
   matches mine: it only verifies B1–B5/F1–F8/P1–P3, a failure is a STOP to the council and never a swap,
   and clothing and bare skin are recorded descriptively.

## Open question (a): should the 2 revid-drift face files stay non-exempt?
Yes, they should stay non-exempt. A page revision that is not a re-upload changes the wikitext, not the
pixels. Every non-C1 rule (C0, C2–C5, F/B/P) runs on pixels or on deterministic pinned detectors, so the
v1 non-C1 decision must reproduce. If it does not, the result is either nondeterminism or a re-upload, and
both need a STOP. A re-upload is caught earlier by the identity STOP. If either title is in the committed
`inadm_to_adm` list, the flip exemption already covers it on the C1 path, which is consistent. Exempting
drift would add a run-time exemption that was not committed. Keep STOP.

## Open question (b): STOP or reject on a file-identity mismatch?
STOP is right. A pre-stated reject would make the selected set depend on the state of Commons on the
day of the run, and a re-upload is often the same photograph re-cropped or re-processed. Rejecting it
silently would drop it at its rank, and admitting it would judge it under the old rank. Both need a human
to look. The cost is a possible halt, and it is small: identity drift since 2026-11-19/21 should be rare.
Non-blocking: when the owner resolves such a STOP, the resolution should be a rule applied from rank 1 under
§2.8 (a v3 for every category, disclosed), not a decision for that one title.

## Non-blocking
- Contact sheet: no code enforces it. It is a launch-note item, so record its outcome in the launch note.
