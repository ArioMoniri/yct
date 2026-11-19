# D-074 draft: localiser image candidate source (pre-run curation-spec correction)

Status: DRAFT for council sign-off (Referee + Neuro + QA, diff only). Not committed to DECISIONS.md.

## Why
The D-071 frozen `controls.refclips.image_queries` are double-quoted exact phrases. Commons search matches a
quoted string only as a consecutive phrase, and no file contains these phrases, so the snapshots committed in
d7e9a6a hold **0 candidates** for face, body and place (`data/refstim/snapshots/image_{face,body,place}_snapshot.json`).
Unquoted, body gives 5 hits, which can never yield 20 passes. No reference output exists and no image has been
downloaded, viewed or filtered, so this is a correction of the candidate *source*. It is **not** the one
versioned redesign (D-071 (h)), which stays unused.

## How the replacement was chosen (counts only)
Only Commons `prop=categoryinfo` file counts were read (2026-11-19). No titles were listed, and no image was
fetched or viewed. Candidates tried, with direct file counts (depth 0):

| Category:… | files | used |
|---|---:|---|
| Portrait photographs | 4,445 | **face** |
| Portraits of men / Portraits of women | 12,645 / 2,634 | no (gender-split, larger than needed) |
| Human faces | 338 | no (mixed close-ups and illustrations) |
| Rear views of people | 568 | **body** |
| People seen from behind / Back views of people | 0 / 0 | no (empty) |
| Empty rooms | 276 | **place** |
| Empty streets | 47 | **place** |
| Frontal portraits, Head and shoulders portraits, Rooms/Streets/Interiors without people, Deserted streets | missing | no |

Rule used to choose: for each category, take the plain-named category whose name states the D-071 content
filter (face = portrait, body = rear view with no face, place = empty), keeping only categories with ≥ 100
direct files (5× the 20-pass target) or, for place, a union of two that reaches it (276 + 47 = 323).

## Entry text (proposed)
- D-074 P4b localiser image candidate source (pre-run correction of D-071 (b); no reference output exists, no
  image downloaded or viewed; D-071 (h) redesign unused). The frozen `controls.refclips.image_queries` return
  0 Commons candidates for every category, because Commons treats them as exact phrases (snapshots d7e9a6a,
  kept as the record). The image candidate source is replaced by Commons category membership, set in the
  new key `controls.refclips_d074` (frozen in its own row):
  - face: `Category:Portrait photographs`; body: `Category:Rear views of people`; place:
    `Category:Empty rooms` ∪ `Category:Empty streets`. Depth 0 (direct file members only, no subcategories),
    namespace 6, via `generator=categorymembers&gcmtype=file` with `prop=imageinfo&iiprop=mime|sha1|size`.
  - Enumeration must be **complete** (follow `continue` to the end). A candidate list larger than
    `image_snapshot_limit` (6000) or any API error refuses the snapshot. Nothing is truncated or sampled.
  - The snapshot is taken and committed (with its sha256) before any filter is applied. Its header records the
    category names, depth, UTC date, member count and the API parameters.
  - Unchanged from D-071: ordering by ascending sha256(file title); the first 20 passes per category; the
    licence set `image_licences`; every filter and `reject_reasons` (a non-bitmap mime is rejected as
    `not_photo`); frontal face detected by the frozen cascade for face; no face for body; no person for
    place; greyscale and SHINE; LICENSES.md with CC-BY attribution. The place union is ordered as one list by
    sha256(title); a file in both place categories appears once.
  - If a category has fewer than 20 passes after the complete list is exhausted, STOP to the owner (no
    substitute source, no relaxed filter).
  - `controls.refclips.image_queries` and `controls.refclips.snapshot_limits.image` stay frozen as record and
    are no longer read for images. `nat_query` and `snapshot_limits.nat` are unchanged and still used.

## Config changes
`controls.refclips` is frozen as a whole subtree (976e8ab) and check_frozen_config forbids editing or
re-pointing it, so nothing inside it changes. Add a new sibling key:

```yaml
controls:
  refclips_d074:               # D-074: image candidate source (replaces refclips.image_queries for images)
    decision: D-074
    image_sources:
      face:  [{category: "Portrait photographs", depth: 0}]
      body:  [{category: "Rear views of people", depth: 0}]
      place: [{category: "Empty rooms", depth: 0}, {category: "Empty streets", depth: 0}]
    image_snapshot_limit: 6000
    require_complete: true
    snapshot_file_suffix: "_d074"   # data/refstim/snapshots/image_<cat>_d074_snapshot.json
```

`frozen:` row added in the commit after the one that introduces the key (two-commit freeze, as in D-071):

```yaml
  - {key: controls.refclips_d074, frozen_at: <commit 1 of D-074>}
```

Schema: add a `RefclipsD074` model to src/yct/config_schema.py (extra="forbid"; image_sources keys are exactly
`loc_categories`; depth = 0; limit > 0) and wire it into the controls model.

## Re-snapshot procedure
1. Commit 1: the D-074 entry, the new config key and schema, and code changes (refstim reads `refclips_d074`
   for images).
2. Commit 2: the `frozen:` row for `controls.refclips_d074`.
3. Commit 3: take the three image snapshots under the new file names
   (`image_{face,body,place}_d074_snapshot.json`) and commit them with their sha256. The old zero snapshots
   stay committed, unchanged, as the record.
4. Later commits: the filters, reject log, manifest and LICENSES.md, in the D-071 order. Then set
   `controls.refclips_artifacts.image_snapshot_sha256` with its own frozen row.

## Tests
Update:
- tests/test_d071_config.py: the `image_queries` assertions stay (record). Add an assertion that the images
  code path does not read `image_queries`.
- tests/test_refstim_curation.py: the image snapshot header asserts category names, depth, completeness and
  member count instead of `queries`. The old snapshots are not overwritten.

Add (tests/test_d074_config.py and the curation tests):
- the schema accepts the key and rejects extra fields, depth ≠ 0, or category keys ≠ `loc_categories`;
- `controls.refclips_d074` is in the exact frozen list (tests/test_guards_frozen_config.py, stricter only);
- an incomplete enumeration (a fake API that stops mid-`continue`), an over-limit list, or an API error
  refuses the snapshot;
- a place union deduplicates by title and orders the merged list by sha256(title);
- a non-bitmap mime → `not_photo` in the log;
- the new snapshot file names are used and the old ones are byte-identical after a run;
- the snapshot commit is a strict ancestor of the commit adding the reject log (T4 (a), new file names);
- fewer than 20 passes after exhaustion → refusal with STOP (no fallback).
