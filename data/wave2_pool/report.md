# Wave-2 candidate pool — curation report (round 3)

Generated 2026-11-18 by the Data Curator agent (blind to study hypotheses). This file intentionally contains **no outcome breakdowns**; labels, evidence and discovery routes are only in the encrypted parts `data/sealed/sealed_w2pool_part{1,2}.tar.age` (plaintext shredded).

## Scope
- Separate wave-2 pool: every company is disjoint from all companies (and all URLs) in `data/manifest.csv` (checked by company_id and video id / LinkedIn activity id). Wave-1 files were not modified.
- One video per company (no company has more than one row): pool rows = companies = 30.
- video_ids yct_0662..yct_0691; wave=2; collected_after_lock=PENDING; era_stratum/company_id/company_key follow the wave-1 conventions (E1 <= W2016, E2 S2016-W2020, E3 >= S2020, from the batch stated by the uploader/founder; UNKNOWN when none stated; company_key = sha256("yct-company-key-v1" + company_id)[:12]).

## Counts by label confidence x era (all rows = one per company)

| confidence | E1 | E2 | E3 | UNKNOWN | total |
|---|---|---|---|---|---|
| A (in_primary=True) | 1 | 6 | 12 | 3 | 22 |
| not A (B) | 0 | 2 | 5 | 1 | 8 |
| total | 1 | 8 | 17 | 4 | 30 |

One-per-company counts are identical (30 distinct companies; 22 conf-A).

## Sources used
- YouTube Data API v3: search.list (keyword queries incl. batch-coded forms such as "YC S24 application video", "YC W27 application video", "YC founder video", "Y Combinator application video" with publishedAfter/Before slices, order=date slices with pageToken), videos.list (duration/upload date/language/full description), commentThreads.list (owner replies stating the outcome), playlistItems.list (other uploads of ~1,166 applicant channels).
- YC directory: yc-oss companies dump (batch, former names, website) + ycombinator.com/companies pages (batch, founders) for cross-checks.
- Exa web search (LinkedIn founder posts with native video, founder blogs, X), LinkedIn public post pages (VideoObject metadata for duration/upload date).
- Published-application collections: shizune.co (YC application examples), getintoyc.com; founder blogs (Medium, Substack, personal sites) embedding the submitted video.
- Hacker News Algolia was not re-queried beyond wave-1 coverage (wave 1 already ran 38 HN queries on the same phrasings).

## YouTube API units
- ~9305 units used of the ~10,000 daily quota (no 403 quotaExceeded encountered); 75 search-log rows.

## Exclusions
`exclusions.csv` lists 1,364 reviewed candidates with a reason category. Most common: no verifiable stated outcome and not cross-checkable in the YC directory (skipped as C), non-English metadata language, > 3 min, launch/demo videos, YC-channel uploads, founder/uploader not matching the directory company, company already in the wave-1 manifest.

## Blockers / caveats
- Yield of new conf-A companies is low: wave 1 had already harvested the high-relevance results for the standard phrasings, and the disjoint-company constraint removes those companies. Most new applicant videos state no outcome; only a small fraction carry an explicit founder statement (title, description, owner comment, or founder post) or match the YC directory.
- Several company-channel uploads were labelled A on company identity + directory batch (the uploader is the company account rather than a named founder); rows where the directory lists no founders, or where the uploader is not a listed founder, were kept as B.
- LinkedIn rows have language UNKNOWN (no metadata). Some YouTube rows have language UNKNOWN (no defaultAudioLanguage).
- A query to YC's live Algolia directory index was blocked by the session permission policy; the yc-oss dump and individual company pages were used instead.
- Target (>= 30 conf-A per outcome) was not reached; sources above were worked to diminishing returns within the time budget.
