# D-078 draft: second Commons category for the body localiser images (amends D-074)

**Owner decision (2026-11-21, in-session AskUserQuestion):** "Add 2nd category". The licence rule (`image_licences`, CC0/CC-BY) is unchanged.

**Trigger:** T-LIC run 2 (9f38eb1). Body STOPped at 10/20 passes after the complete 568-member D-074 snapshot was evaluated. This is the D-074 STOP path, which hands the decision to the owner. Face is 20/20 and place has not been evaluated. No reference output exists, and no image has been processed beyond the filter log.

## 0. Category choice (rule stated before the snapshot)
- Rule: among existing Commons categories whose name denotes people seen from behind, take the one with the most files.
- Excluded by name, before counts were read for selection: costume, art, nude, child, military, clothing or club, and body-part categories (Rear views of cosplayers, Motorcycle club colors, Nape, Rear views of people in art, Rear views of nude people, Rear views of children, Rear views of military people, Handkerchief code, Shoulder blade tattoos, Human backs).
- Counts (Commons `categoryinfo`, 2026-11-21, read with the frozen curation client):
  - **Rear views of men 399**
  - Rear views of women 324
  - People walking seen from behind 205
  - Standing people seen from behind 123
  - Rear views of people sitting 95
  - Rear views of female people 47
  - Rear views of male people 25
  - Rear views of adults 20
- Selected: **Category:Rear views of men**, depth 0.
- No filter outcome, thumbnail or licence of any member was looked at to choose it.

## 1. Source and snapshot
- `controls.refclips_d078.image_sources.body` = [Rear views of people (D-074, depth 0), Rear views of men (depth 0)].
- The D-078 body snapshot `data/refstim/snapshots/image_body_d078_snapshot.json` is built as follows:
  - **Base:** the entries of the frozen D-074 body snapshot `image_body_d074_snapshot.json`, byte-for-byte as recorded (2026-11-19). The base is NOT re-enumerated, so the original membership stays exactly the one already frozen.
  - **Added source:** a complete depth-0 enumeration of Category:Rear views of men, read with the same API string, limit and `require_complete` rule.
  - **Union:** deduplicated by title, with base entries first (first source wins, as in D-074 place). Each entry keeps its `source`.
- Header: decision D-078, amends D-074, category, sources, the base file name and its sha256, namespace, api, limit, utc_date, complete, n_members.
- `controls.refclips_d078_artifacts.body_snapshot_sha256` = sha256 of the D-078 body snapshot file. It is set in the commit that adds the snapshot and frozen in the next commit, before any filter call.
- These files stay byte-identical and remain the record:
  - the D-074 snapshots (face, body, place);
  - `image_snapshot_sha256`;
  - the D-074 body log `image_body_auto_log.jsonl` (568 rows).

## 2. Selection rule (a priori, does not use filter outcomes)
- The body selection is the **first 20 passes in ascending sha256(title) order over the D-078 union**, evaluated from the start into a new append-only log `data/refstim/image_body_d078_auto_log.jsonl`.
- Every candidate, old or new, is evaluated by the same frozen D-075 filters (`controls.refclips_auto`, unchanged).
- The 10 earlier passes have no special status. Each is selected only if it falls among the first 20 passes of the union order; otherwise it is not used. No earlier outcome is used to include, exclude or rank anything.
- Cross-category duplicate state (C3) is preloaded from the face log, then the D-078 body log, exactly as D-075. The D-074 body log is not preloaded, because it is superseded.
- Place runs after body, unchanged (D-074 snapshot, D-074 log name).

## 3. Determinism audit (fail-closed)
- For each candidate in both the D-074 body log and the new log, (decision, reason) must be equal.
- The one exception is a pair where either reason is `duplicate` (C3 depends on the passes before it, and the order changed).
- Any other mismatch is a STOP to the owner, never silently accepted. It would mean the frozen pipeline is not reproducible.

## 4. STOP rules (unchanged in kind)
- Fewer than 20 body passes after the complete union is exhausted is a STOP to the owner. No further category is added without a new owner decision.
- The STOP rules for HTTP 429 beyond 30 min, model, env or sha mismatch, decode failure and NaN are unchanged.
- Fewer than 20 place passes is a STOP.

## 5. Unchanged
- D-075 rules and thresholds;
- the image licences and LICENSES.md attribution;
- ordering by ascending sha256(title);
- loc_per_category 20;
- processing (greyscale, SHINE);
- the $75 cap;
- the K rules;
- face (20/20, D-074 log);
- `controls.refclips.version` v1.

## 6. Disclosure
- The v1 report discloses the D-074 body STOP at 10/568, the owner's decision and the added category.
- The selected category is male-only, so the body set may skew male relative to D-074. Gender is not a filter variable. Body-selective (EBA/FBA) responses are not expected to depend on gender, and this is disclosed as a limitation.
- The category rule in §0 was written after the subcategory list and file counts had been read. No member image, licence or filter result had been seen. The selection uses names and counts only.
- Expected yield, stated before the run: the D-074 body pass rate was 10/568 ≈ 1.8%. At that rate, 399 added files give about 7 passes, which would leave the union short of 20. The owner chose one added category, so a STOP at fewer than 20 is the pre-stated outcome if yield follows D-074. There is no fallback category.

## 7. Review record
- Council cycle 1 (Watchdog, Referee, Biostat, Neuro, QA), recorded in reviews/phase_p4b/signoff_d078.md.
- REVISE items applied:
  - W1: the order in which counts were read is now disclosed.
  - B1: the pre-stated yield expectation and the no-fallback rule are added.
  - Q1: the test list is added (§8).

## 8. Tests (TDD, tests/test_refstim_d078.py)
- The config key exists and validates.
- The D-078 header matches config, with the base file sha recorded.
- Base entries are carried over verbatim and come first. Union dedupe is by title.
- An incomplete or over-limit added source is refused.
- The D-078 snapshot and log names are used for body only, never for face or place.
- The committed D-078 snapshot matches `refclips_d078_artifacts.body_snapshot_sha256` once set.
- The run refuses unless `controls.refclips_d078` and `refclips_d078_artifacts.body_snapshot_sha256` are frozen.
- Determinism audit: an equal pair passes. A duplicate-exempt pair passes. Any other mismatch is a StopError.
- The D-074 body snapshot and log stay byte-identical to their committed versions.

## Addendum (2026-11-21, append-only; council cycle council_d078_d079_*)

- **§6 yield expectation withdrawn.** The 10/568 ≈ 1.8 % rate, and the "STOP is the pre-stated outcome" statement, were produced under BUG-036: 108 D-074 body C1 rejects were wrong. No new expectation is made.
- **D-078 is kept.** On 2026-11-21 the owner re-decided "Keep it as frozen", by the outcome-blind principle that a frozen amendment is not revisited on later knowledge.
- **§3 and §5 are proposed for amendment by D-079** (draft v2, `d079_v2.md`). The audit would compare against every v1 log of the category, with a committed BUG-036 flip list, and routing would go to the v2 logs.
- **Sex skew:** the male-only addition can skew body towards male. Body enters the gated FFC contrast. The report gives per-source counts. Sex is never labelled.
