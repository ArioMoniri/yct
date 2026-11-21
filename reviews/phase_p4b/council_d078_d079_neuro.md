# Council review: D-078 (independent re-review) and D-079 — Neuroscientist

Date: 2026-11-21. Scope: d078_draft.md, signoff_d078.md, d079_draft.md, BUGS.md BUG-036, commits a18b246,
598ca0e, d420fa2, e768363, feda068, read against d075_final.md (C/B rules) and design_v2.md §4(d).
I did not read data/sealed/*, labels, transcripts, any outputs/ predictions, any image or any filter log row.

**Verdict: REVISE.** "Rear views of men" is an acceptable body-localiser source. The D-078 disclosure
misstates the body category's role, and D-079 has one stimulus-identity gap.

## Is "Rear views of men" a valid body set?
- Category validity holds. C5 (CLIP photograph vs drawing/painting/statue/rendering) removes art. B1–B5 (one person, ≥ 15 % area, no face by YuNet and Haar, adult, < 1 % text) apply unchanged.
  Depth 0 keeps the excluded nude, costume, military, child and art subcategories out. The source is
  appropriate for EBA/FBA: whole, faceless, single human bodies.
- Sex balance. Neither set is balanced. The face source (Portrait photographs) is not split by sex and has
  no sex filter either, so there is no "face balanced, body male" asymmetry by design. A male-only
  addition can only push the body set towards male. Body-selective cortex responds to bodies of either sex.
  Effects of the sex of a seen body (attractiveness, sexual dimorphism, arousal) are small and are reported
  mostly outside EBA/FBA. I accept the limitation as long as it is disclosed accurately (item 1).
- Gating role, misstated. D-078 §6 and the cycle-1 Neuro line treat body as descriptive only. Body is
  descriptive as a family, but it enters the gated FFC contrast face − mean(place, body) in D-071 (d). A
  male-skewed body set therefore feeds a gating test. I expect no harm (rear views show hair or the back
  of the head, which can drive FFC slightly, whatever the sex of the body). The disclosure must say so, not imply that body never matters (item 1).
- Clothing and bare skin: no B rule controls it, and a male category plausibly has more bare backs.
  Greyscale plus joint SHINE removes most low-level effect. Not blocking, and no new filter now (v1 body
  outcomes have been seen). The pre-launch contact sheet (cycle-2 Neuro, artefact ii) covers it.
- The trigger was an artefact. The 10/568 STOP and the 1.8 % yield came from BUG-036 (108 body rows flip
  to admissible). I agree with the Referee: keep D-078 under the outcome-blind principle and disclose that
  the trigger was an artefact. Dropping it now would be chosen on re-check body counts.

## D-079: is the reference-clip content expected to change?
- Yes, as data, though no rule changes. With 260 face and 108 (+3 in the D-078 log) body C1 flips, the v2 first-20 face and
  body sets will almost certainly differ from the v1 passes, and the source mix of the body set is
  unknown in advance. This is correct: the v1 sets were never the sets the frozen rule defines, and no
  image was processed or viewed. D-079 should state "content will differ from v1; the rule does not".
- Stimulus identity gap. The runner evaluates the image it downloads now, but the C3 duplicate check and
  the log use the snapshot `sha1`. Nothing compares the fetched file (`commons_sha1` or the bytes) with the
  snapshot sha1. A file re-uploaded since 2026-11-19/21 would be judged at the old rank as a different
  image. The re-check already shows revid drift on 2 face files (Referee item 3 covers revids; this is the
  file-content case).
- SHINE is joint over all 60 images, so new face/body sets change every processed image; expected.

## Required items (REVISE-blocking)
1. Amend D-078 §6 (as an append-only note) and repeat it in the D-079 disclosure:
   body enters the gated FFC contrast face − mean(place, body); the male-only addition can skew body towards
   male, and neither face nor body source is sex-controlled; the expected FFC-gating effect is negligible,
   with the reason; the v1 report gives the per-source count of the 20 final body images (Referee item 2).
   Sex is not labelled or used for selection. Any descriptive sex count must be pre-stated as report-only,
   or not done at all.
2. Before any v2 call, D-079 must freeze a file-identity rule, with a test: for each candidate, the
   current Commons imageinfo sha1, and the sha1 of the downloaded bytes, must equal the snapshot `sha1`.
   A mismatch is a STOP to the owner, or a pre-stated reject reason (the council picks one now). It must
   never be evaluated silently.
3. D-079 must state that the cycle-2 pre-launch contact-sheet check (one frame per LOC image) applies to
   the v2 sets. It checks only that B1–B5, F1–F8 and P1–P3 held: a visible face in body, a minor, a second
   person, text. Any failure is a STOP to the council and is never a swap for the next pass. Clothing and
   bare skin are recorded descriptively, not filtered.

## Non-blocking
- This file is the independent Neuro pass that signoff_d078.md defers to. A gender-neutral category would
  have been the better a-priori rule; not requested now, as a change would follow seen outcomes.
