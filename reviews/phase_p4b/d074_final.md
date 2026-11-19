# D-074 final (applies reviews/phase_p4b/signoff_d074.md R1–R4, Q1–Q7)

Owner approval: 2026-11-19, in-session answer "Approve" to the question "Approve the D-074 category
sources?" (face Portrait photographs, body Rear views of people, place Empty rooms + Empty streets). This
was recorded before commit 1, as D-071 (b) requires when a category cannot reach 20.

## Request record (R3): every Commons request made while choosing
- `prop=categoryinfo` (file counts only; no titles, file pages or images were returned), 2026-11-19, on:
  - Portrait photographs (4,445 files)
  - Portraits of men (12,645) and Portraits of women (2,634)
  - Human faces (338)
  - Rear views of people (568)
  - People seen from behind (0) and Back views of people (0)
  - Empty rooms (276) and Empty streets (47)
  - Frontal portraits, Head and shoulders portraits, Rooms without people, Streets without people, Interiors without people, Deserted streets: all missing.
  - The four chosen categories were re-checked at commit time with the same counts.
- `list=search&srinfo=totalhits`, unquoted copies of the D-071 phrases (T-LIC diagnosis, 2026-11-19):
  - frontal portrait photograph: 289
  - person seen from behind full body photograph: 5
  - empty room interior photograph: 152
  - empty street photograph: 21,527

  These are totals only; no result titles were used.

## Rule used (R2, R3)
Each category's source was chosen by the same rule. Among the categories whose count was requested, take the one whose name states the D-071 content filter (face = portrait photograph, body = rear view, place = empty). It must not be split by a demographic attribute, and must have ≥ 100 direct files and at most `image_snapshot_limit`.

Place keeps D-071's two-source design (indoor room ∪ street), so it is the union of the two place categories and must reach ≥ 100 files in total.

Applying the rule:
- **face:** Portraits of men and Portraits of women are excluded because they are demographic splits. Human faces is excluded because its name does not state "photograph". That leaves only Portrait photographs.
- **body:** Rear views of people is the only non-empty category whose name states rear view.
- **place:** Empty rooms ∪ Empty streets, 323 files.

## Entry text (appended to DECISIONS.md verbatim)

- D-074 P4b localiser image candidate source: a pre-run correction of D-071 (b).
  - **Approval:** the owner approved this on 2026-11-19 (in-session answer "Approve"), recorded before this commit. D-071 (b) requires owner approval when a category cannot reach 20.
  - **Status:** no reference output exists, no image has been downloaded or viewed, and the D-071 (h) redesign is unused. Review record: reviews/phase_p4b/d074_draft.md, signoff_d074.md, d074_final.md.
  - **Why:** the frozen `controls.refclips.image_queries` are double-quoted exact phrases. They return 0 Commons candidates for face, body and place. The d7e9a6a snapshots `image_{face,body,place}_snapshot.json` are kept unchanged as the record.
  - **New source:** the image candidate source is replaced by Commons category membership, in the new sibling key `controls.refclips_d074`, frozen in its own row. `controls.refclips` is not edited.
    - face: `Category:Portrait photographs`
    - body: `Category:Rear views of people`
    - place: `Category:Empty rooms` ∪ `Category:Empty streets`
    - Depth 0: direct file members only, no subcategories, namespace 6.
    - API: `generator=categorymembers&gcmtype=file&gcmnamespace=6&prop=info|imageinfo&iiprop=mime|mediatype|sha1|size`.
    - Each entry records title, pageid, revid (= lastrevid), mime, mediatype, sha1, width and height.
    - An entry whose `mediatype` ≠ `BITMAP` stays in the snapshot and is logged as `not_photo` when reached. This is the exact equivalent of D-071's `filetype:bitmap`.
  - **Complete enumeration:** completion means a response with `batchcomplete` and no `continue` key of any kind; `gcmcontinue` and `iicontinue` are both followed. The snapshot is refused if any of these happens:
    - a source holds more than `image_snapshot_limit` (6000) entries;
    - the enumeration is incomplete;
    - any API error occurs.

    Nothing is truncated or sampled.
  - **Snapshots:** the three image snapshots are written as `data/refstim/snapshots/image_{face,body,place}_d074_snapshot.json`.
    - Each header records categories, depth, namespace, API parameters, UTC date, `complete: true` and the member count.
    - The place union is deduplicated by title.
    - In the commit that adds them, `controls.refclips_artifacts.image_snapshot_sha256` is set to the sha256 of the concatenated bytes of the face, body and place files, in `loc_categories` order.
    - Its `frozen:` row follows in the next commit, before any filter is applied.
    - The D-074 snapshot run writes image snapshots only. `nat_nat_snapshot.json` (d7e9a6a, sha aab68a55…) and the three D-071 image snapshots stay byte-identical.
  - **Unchanged from D-071:**
    - ordering by ascending sha256(file title);
    - the first 20 passes per category;
    - `image_licences`;
    - every category filter and `reject_reasons`;
    - processing (greyscale, SHINE);
    - LICENSES.md with CC-BY attribution;
    - the no-YC/founder/analysis-company imagery rule.
  - **STOP rule:** if a category has fewer than 20 passes after its complete list is exhausted, the build stops and goes to the owner. There is no substitute source and no relaxed filter.
  - **What stays as it was:** `controls.refclips.image_queries` and `snapshot_limits.image` stay frozen as the record, and are no longer read for images. `nat_query`, `snapshot_limits.nat` and the NAT snapshot are unchanged and still used. `controls.refclips.version` stays v1, and `s3_root`, the $75 cap, the K rules and `on_fail` are unchanged.
  - **Disclosure:** the v1 report discloses D-071 → D-074 and the zero snapshots of d7e9a6a. D-074 does not consume D-071 (h).

## Config (commit 1)
```yaml
controls:
  refclips_d074:
    decision: D-074
    image_sources:
      face:  [{category: "Portrait photographs", depth: 0}]
      body:  [{category: "Rear views of people", depth: 0}]
      place: [{category: "Empty rooms", depth: 0}, {category: "Empty streets", depth: 0}]
    namespace: 6
    api: "generator=categorymembers&gcmtype=file&gcmnamespace=6&prop=info|imageinfo&iiprop=mime|mediatype|sha1|size"
    bitmap_mediatype: BITMAP
    image_snapshot_limit: 6000
    require_complete: true
    snapshot_file_suffix: "_d074"
```

The schema uses literals: `decision: Literal["D-074"]`, `depth: Literal[0]`, `require_complete: Literal[True]`, `snapshot_file_suffix: Literal["_d074"]`, `bitmap_mediatype: Literal["BITMAP"]` and `namespace: Literal[6]`. `Controls` checks that `set(image_sources) == set(refclips.loc_categories)` and that every source list is non-empty.

## Frozen rows
- commit 2: `{key: controls.refclips_d074, frozen_at: <commit 1>}`
- commit 4: `{key: controls.refclips_artifacts.image_snapshot_sha256, frozen_at: <commit 3>}`

## Tests
Existing tests are not edited. The one exception is the exact frozen-list assertion in tests/test_guards_frozen_config.py, which is extended with the new rows only, making it stricter.

New tests are in tests/test_d074_config.py and tests/test_refstim_d074.py:
- **schema:** accept and reject cases (extra field, depth ≠ 0, require_complete false, suffix ≠ `_d074`, category keys ≠ `loc_categories`, empty source list);
- **enumeration refusals:** an incomplete enumeration (`gcmcontinue` stop), `iicontinue` not followed (Q7 i), over the limit, or an API error;
- **entries (Q7 ii):** title, pageid and revid are present; a non-BITMAP entry is kept and logged as `not_photo` in order;
- **place union:** deduplicated and ordered by sha256(title);
- **file names:** new names are used, and the D-071 image snapshots plus the NAT snapshot are byte-identical after a run (Q4, Q7 iv);
- **D-071 record:** the committed D-071 image snapshots still pass `check_header` against D-071;
- **snapshot sha (Q7 iii):** `image_snapshot_sha256` equals the concatenated-bytes sha, and its frozen row precedes any reject-log commit;
- **unchanged keys:** version v1 and `s3_root` unchanged (Q7 v); D-073 still reserved (Q7 vi);
- **STOP:** fewer than 20 passes after exhaustion refuses the build.
