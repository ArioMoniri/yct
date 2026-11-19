# Sign-off: D-074 draft (localiser image candidate source)

Reviewed: reviews/phase_p4b/d074_draft.md at be23904. Roles: STRICT REFEREE, NEUROSCIENTIST, QA.
Evidence read: DECISIONS.md D-071 (b), (d), (h); config.yaml `controls.refclips`, `refclips_artifacts`, `frozen:`;
scripts/check_frozen_config.py; src/yct/curate/refstim.py; scripts/refstim_snapshot.py; src/yct/config_schema.py
(RefClips, RefClipArtifacts, Controls); tests/test_{refstim_curation,d071_config,guards_frozen_config,p4_config}.py;
data/refstim/snapshots/image_*_snapshot.json (headers and `entries` only).
Checks run: `pytest tests/test_refstim_curation.py tests/test_d071_config.py tests/test_guards_frozen_config.py
tests/test_p4_config.py` gives 44 passed. `scripts/check_frozen_config.py` gives OK, 25 keys.
No network access was used, so the Commons category counts in the draft are taken as reported and were not
re-checked.

Facts confirmed:
- All three image snapshots committed in d7e9a6a have `"entries": []`. Their headers carry the frozen quoted queries.
- No reference output, image log, manifest or LICENSES.md exists. All `refclips_artifacts` values are null.
- `check_frozen_config` compares exact dotted paths. A new sibling `controls.refclips_d074` therefore leaves
  `controls.refclips` (frozen at 976e8ab) unchanged. A two-commit freeze (key in commit 1, row
  `frozen_at: <commit 1>` in commit 2) passes checks 1 to 3, as long as commit 1 stays an ancestor of HEAD.
  Do not squash or rebase the pair.
- `controls` is not frozen as a whole. `Controls` has extra="forbid", so the schema change in the draft is required.
- D-073 is reserved (`test_d073_reserved_for_the_audio_only_ablation`), so numbering this entry D-074 is correct.

---

## STRICT REFEREE: REVISE

Reasons.
1. **The owner must approve this change.** D-071 (b), last bullet: "If any of face, body or place cannot reach
   20 passes within its snapshot, the build does not start. That goes to the owner, with no synthetic
   substitute." The zero snapshots trigger exactly this case, and d7e9a6a says "owner decision needed".
   The council can propose a new candidate source, but cannot adopt it alone. The draft does not mention
   the owner.
2. **The "counts only" claim needs two fixes.**
   - The row "Human faces … (mixed close-ups and illustrations)" makes a claim about content. A count
     cannot show that. Either its source is disclosed, or the claim goes.
   - The stated rule does not pick a unique category. "Human faces" (338) and "Portraits of men" also meet
     "plain name states the filter, ≥ 100 files". The rule that was actually used has to be written down.
3. **The request record must be complete.** "Unquoted, body gives 5 hits" means at least one search
   request outside the table was made. Every request made while choosing has to be listed, so that a
   reader can confirm nothing else was looked at.
4. **The ruling "not the versioned redesign" is correct.**
   - D-071 (h) covers a `p4b_ref/v2` made after a v1 failure.
   - Here, no v1 stimulus exists, nothing was built or run, and `version: v1` and `s3_root` are unchanged.
     The K rules, thresholds, `on_fail` and cap are untouched.
   - The entry should say all of this explicitly, so that the v1 report discloses the correction.
5. **Ordering, licences and the 20-pass rule are unchanged, and no tuning lever exists.**
   - Ordering is still sha256(title), the licence set is unchanged, and the first 20 passes are still used.
   - Complete enumeration with no truncation is stricter than D-071's "first 2,000 in API order".
   - No outcome exists that the category choice could have been tuned towards.

Exact edits.
- **R1.** In "Entry text", first bullet: after "(pre-run correction of D-071 (b);", insert "owner approval
  <date, quote or H-id> recorded before commit 1, as D-071 (b) requires for a category that cannot reach 20;".
  Also add to the procedure: "0. Owner approval of this entry. Commit 1 does not happen without it."
- **R2.** In the table, replace "no (mixed close-ups and illustrations)" with "no (name does not state
  'photograph')". If that is not the reason actually used, state the actual source of the claim instead
  (for example, the category description page was read), with the date.
- **R3.** Replace the "Rule used to choose" paragraph with: "Rule used: per category, among the categories
  whose count was requested, take the one whose name states the D-071 content filter (face = portrait
  photograph, body = rear view, place = empty), is not split by a demographic attribute, and has ≥ 100
  direct files and ≤ `image_snapshot_limit`. Place keeps D-071's two-source design (indoor room ∪ street),
  so its union must reach ≥ 100." Then add: "The table lists every Commons request made for this choice
  (prop=categoryinfo only), together with the unquoted `list=search` total-hit queries [list them]. No
  titles, file pages or images were returned or read."
- **R4.** Add to "Entry text": "`controls.refclips.version` stays v1 and `s3_root`, cap, K rules and
  `on_fail` are unchanged. The v1 report discloses D-071 → D-074 and the zero snapshots of d7e9a6a.
  D-074 does not consume D-071 (h)."

---

## NEUROSCIENTIST: SIGN-OFF

Reasons.
- **Face (FFC): `Category:Portrait photographs` is suitable.** The frozen filters do the work:
  - one real adult face, frontal within ±20°;
  - face height ≥ 40% of the crop;
  - the cascade must fire on the processed image.
  A portrait category gives the highest prior rate of single-subject, roughly frontal faces among the
  candidates. The gender-split categories were rightly not used.
- **Body: `Category:Rear views of people` is the correct choice for a body-without-face control.** A rear
  view removes the face while keeping body shape and posture. The body filter (cascade negative, no face
  visible) is then a confirmation, not a selection of awkward crops. Any residual FFC response to the back
  of a head or to body shape makes the face contrast conservative, not inflated.
- **Place (PH): `Empty rooms` ∪ `Empty streets` matches the classic parahippocampal place area localiser.**
  Empty rooms drive the PPA through spatial layout without objects or people. Streets keep D-071's
  outdoor half. The union is about 85% indoor. That is acceptable, because PH is tested only as place
  versus its own scramble twin.
- **Low-level differences between sources are controlled by the frozen pipeline.** These differences
  include historical studio portraits for face and modern photos for body and place. The pipeline applies
  BT.709 greyscale and SHINE luminance, RMS and spectrum matching across all 60 images, and pairs each
  image with a phase-scrambled twin that has the same amplitude spectrum. Each kernel is category versus
  its own scramble, so differences in era or texture between categories do not enter it.

Non-blocking notes. These do not change filters and need no edit to sign off.
- **N1.** Statues, mannequins and photos of paintings are likely in "Rear views of people". Under D-071 they
  are not "one person". The curator should reject them under the existing codes (`not_photo` for depicted
  people). No new code is needed.
- **N2.** Excluding CC-BY-SA will remove most modern Commons photographs. The face set will skew towards
  PD-old portraits, and body passes may run low. If body exhausts before 20 passes, the draft's STOP rule
  (no substitute, no relaxation) is the correct response. Do not pre-empt it.
- **N3.** The D-071 "no YC, founder or analysis-company imagery" rule matters more for a portrait category.
  The curator applies it as before.

---

## QA: REVISE

Reasons.
- **The guard fit is correct.** A sibling key leaves the frozen subtree untouched. The new row extends the
  exact-list test (stricter only). The two-commit pattern matches D-071.
- **Five mechanics are under-specified.** Each lets the implementation either drift from D-071 or trip
  `check_test_weakening`:
  - **(a) The bitmap filter is not exact.** D-071 filtered with `filetype:bitmap`, which is Commons
    MEDIATYPE_BITMAP. The draft's "non-bitmap mime → not_photo" leaves "bitmap mime" undefined.
  - **(b) The revision id is dropped.** D-071 (b) snapshots must hold title, page id and revision id
    (`fetch_commons` gets `lastrevid` from `prop=info`). The draft's `prop=imageinfo&iiprop=mime|sha1|size`
    does not return it.
  - **(c) The snapshot sha has no definition and is frozen too late.**
    - `refclips_artifacts.image_snapshot_sha256` is a single key, but there are three image snapshot files.
      The draft does not define what the sha is.
    - Step 4 sets it after the filters. D-071 (b) requires the sha to be committed before any filter.
  - **(d) Re-running the snapshot script would rewrite the NAT snapshot.** `scripts/refstim_snapshot.py`
    rewrites all four snapshots, including `nat_nat_snapshot.json`. A D-074 run must not touch the NAT
    snapshot.
  - **(e) The test plan edits existing tests.** It changes `test_header_matches_config_and_tamper_fails`
    and `test_nat_header_and_place_union`, which assert the D-071 `queries` and `filetype:bitmap`
    behaviour. Rewriting them is a test change that the weakening heuristic may flag. It also loses the
    check that the committed zero snapshots still match D-071.
- **Schema looseness.** A boolean `require_complete` and a free-text suffix can each be set to the weaker
  value. Both should be literals.

Exact edits.
- **Q1.** In "Entry text" and in the config comment, replace "`prop=imageinfo&iiprop=mime|sha1|size`" with
  "`prop=info|imageinfo&iiprop=mime|mediatype|sha1|size`". Each entry records title, pageid, revid
  (= lastrevid), mime, mediatype, sha1, width and height. Then replace "(a non-bitmap mime is rejected as
  `not_photo`)" with "(an entry whose `mediatype` ≠ `BITMAP` stays in the snapshot and is logged as
  `not_photo` when reached, the exact equivalent of D-071's `filetype:bitmap`)".
- **Q2.** Under "Enumeration must be complete", add: "Completion means a response with `batchcomplete` and no
  `continue` key of any kind (`gcmcontinue` and `iicontinue` both followed)."
- **Q3.** Replace procedure step 3 and the last sentence of step 4 with:
  - "3. Take the three image snapshots under the new names. In the same commit, set
    `controls.refclips_artifacts.image_snapshot_sha256` = sha256 of the bytes of
    `image_face_d074_snapshot.json`, `image_body_d074_snapshot.json` and `image_place_d074_snapshot.json`
    concatenated in `loc_categories` order.
  - 3b. In the next commit, add its `frozen:` row (frozen_at = commit 3).
  - 4. Only then the filters, reject log, manifest and LICENSES.md, in the D-071 order."
- **Q4.** In the procedure, add: "The D-074 snapshot run writes image snapshots only. `nat_nat_snapshot.json`
  (d7e9a6a, sha aab68a55…) and the three D-071 image snapshots stay byte-identical."
- **Q5.** In "Tests", replace the bullet "tests/test_refstim_curation.py: the image snapshot header asserts …
  instead of `queries`" with: "Existing tests are not edited, except to add assertions. The D-071
  `header_for`/`build_snapshot` path stays as it is and gains one test: the committed
  `image_{face,body,place}_snapshot.json` pass `check_header` against D-071. D-074 adds separate functions
  (`header_for_d074`, `build_category_snapshot`, `check_header_d074`) with their own tests."
- **Q6.** In "Schema", require `decision: Literal["D-074"]`, `depth: Literal[0]`, `require_complete:
  Literal[True]`, `snapshot_file_suffix: Literal["_d074"]` and `image_snapshot_limit: PosInt`. Validate in
  `Controls` that `set(refclips_d074.image_sources) == set(refclips.loc_categories)` and that every source
  list is non-empty.
- **Q7.** Add these to the tests list:
  - **(i)** A fake API that returns `iicontinue` without `gcmcontinue` refuses the snapshot unless the
    `iicontinue` is followed to `batchcomplete`.
  - **(ii)** Snapshot entries carry title, pageid and revid. A non-BITMAP entry stays in the snapshot and is
    logged as `not_photo` in sha256(title) order.
  - **(iii)** Once set, `image_snapshot_sha256` equals the concatenated-bytes sha of Q3, and its frozen row
    precedes the reject-log commit.
  - **(iv)** The NAT snapshot is byte-identical after a D-074 snapshot run.
  - **(v)** `refclips.version == "v1"` and `s3_root` are unchanged. This is already in test_d071_config; keep it.
  - **(vi)** `test_d073_reserved_for_the_audio_only_ablation` still passes with D-074 appended.

  The draft's other listed tests are sufficient and should stay: schema reject cases, exact frozen list,
  incomplete, over-limit or error refusal, place union dedup and order, new file names, strict-ancestor
  T4(a), and STOP on exhaustion.

---

## Summary
| Role | Verdict | Blocking items |
|---|---|---|
| Strict Referee | REVISE | R1 (owner approval required by D-071 (b)), R2 and R3 (counts-only record and rule), R4 |
| Neuroscientist | SIGN-OFF | none (notes N1 to N3) |
| QA | REVISE | Q1 to Q7 (mediatype, revid, snapshot sha defined and frozen before filters, NAT untouched, no edits to existing tests, literal schema, added tests) |

Once the R and Q edits are applied, the draft can be committed without another full cycle. A diff check by
the Referee and QA is enough.
