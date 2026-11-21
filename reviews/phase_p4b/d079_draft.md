# D-079 draft — supersede the v1 image logs after BUG-036 (council review pending)

Status: DRAFT for the council (Watchdog, Strict Referee, Biostatistician, Neuroscientist, QA). Nothing in this
draft is frozen or recorded in DECISIONS.md until all five sign off. No image run happens before that.

## Why

BUG-036: `refstim.page_meta` queried 50 titles per request with `prop=templates&tllimit=max` and never
followed `tlcontinue`. The 500-template cap is shared across the batch, so files late in a batch came back
with no templates and were read as having no licence. A C1 decision therefore depended on which other files
shared the batch. That is not a property of the file. Every C1 decision in the v1 logs is unreliable.

## Fix (code, already committed; see BUGS.md BUG-036 FIXED)

- `refstim.query_pages` follows every `continue` key until `batchcomplete`, merging pages by requested
  title.
- It fails closed (CurationError, a STOP, never a licence reject) when:
  - a response has neither `continue` nor `batchcomplete`;
  - a requested title is absent;
  - a page is missing or invalid;
  - imageinfo is absent.
- `page_meta` uses it and refuses a file page that has no templates after complete paging.
- The C4 extmetadata query in `scripts/refstim_auto_run.py` uses the same helper.
- The runner no longer defaults a missing title to `{}`.
- Tests are in `tests/test_refstim_bug036.py`:
  - paging to batchcomplete;
  - missing batchcomplete, title, imageinfo and templates each raise;
  - decisions are identical for batch sizes 1, 7 and 50 at template caps 3 and 500.

## Proposed rule

1. **v1 logs superseded, not deleted:**
   - `data/refstim/image_face_auto_log.jsonl`, `image_body_auto_log.jsonl` and
     `image_body_d078_auto_log.jsonl` are kept byte-identical, as the append-only record.
   - They are marked superseded by D-079 and are never read for selection, the manifest or any statistic.
2. **v2 logs:**
   - New files `data/refstim/image_{face,body,place}_auto_log_v2.jsonl`, each evaluated from rank 1 with
     the fixed client.
   - face: the D-074 face snapshot.
   - body: the D-078 union snapshot (D-074 body plus Rear views of men).
   - place: the D-074 place snapshot.
3. **Unchanged:**
   - every frozen filter (D-075 `controls.refclips_auto`, its artifacts and environment);
   - the ascending-sha256(title) ordering;
   - the first-20-passes rule and the STOP on fewer than 20;
   - `image_licences`, `reject_reasons`, processing and LICENSES.md.
   - No v1 decision is carried over. No category, threshold, licence set or ordering is changed.
4. **Selection rule unchanged:**
   - The rule is the one frozen in D-074/D-075/D-078.
   - No filter outcome was used to choose anything in D-079. The only new inputs are the corrected API
     reading and the file names.
   - The read-only re-check below is reported for disclosure. It does not select anything.
5. **D-078 stays.**
   - Body uses the D-078 union, as frozen.
   - Dropping D-078 now, after seeing that body might reach 20 from D-074 alone, would be a choice made on
     filter outcomes.
6. **Disclosure (v1 report):**
   - BUG-036 and the v1 → v2 log supersession;
   - the re-check counts;
   - that the face passes in v1 are not the face set used.
7. **Before the v2 run:**
   - Add a `log_version: v2` config key, frozen in the next commit as the two-commit pattern requires.
   - The runner refuses to append to a v1 log.

## Read-only re-check (for disclosure, not selection)

`scripts/refstim_bug036_recheck.py` reads the C1 decision for every logged title with the fixed client. It
makes metadata API calls only: no download, no detector, no log write. Counts are reported in the commit and
fork report:

- RECHECK_COUNTS_PLACEHOLDER

## Questions for the council

- Watchdog: is any element of D-079 chosen with knowledge of v1 filter outcomes beyond C1?
- QA: are fail-closed coverage and the batch-independence test sufficient? Should a live probe test be
  added (one known multi-template batch, asserting complete paging)?
- Biostatistician: a fresh evaluation from rank 1 versus reusing the non-C1 v1 decisions.
- Referee and Neuroscientist: is any change to reference-clip content expected? None is intended.
