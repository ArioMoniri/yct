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

## Round 4 (2026-11-19, append-only)

Data Curator, blind to study hypotheses. Appended 18 new pool rows `yct_0692`..`yct_0709` (wave=2, collected_after_lock=PENDING). Every company is disjoint from `data/manifest.csv` and from all earlier pool rows (checked by company_id, by fuzzy company-name match against all existing company_ids, and by video id / LinkedIn activity id). One wave-1 duplicate was found only through a manual check (the wave-1 company_id was a generic word, not the company name) and was dropped before writing. One video per company: 18 rows = 18 companies. No outcome breakdowns appear in this file. Labels and evidence are only in `data/sealed/sealed_w2pool_part3.tar.age` (yct_0692..0699) and `data/sealed/sealed_w2pool_part4.tar.age` (yct_0700..0709). The plaintext was shredded after encryption.

### Counts by label confidence x era (round-4 rows, one per company)

| confidence | E1 | E2 | E3 | UNKNOWN | total |
|---|---|---|---|---|---|
| A (in_primary=True) | 2 | 0 | 7 | 6 | 15 |
| not A (B) | 0 | 0 | 3 | 0 | 3 |
| total | 2 | 0 | 10 | 6 | 18 |

The one-per-company counts are the same (18 distinct companies, 15 conf-A). claimed_batch is UNKNOWN whenever the uploader or founder stated no batch, even when the YC directory gives one. This produces 6 UNKNOWN-era rows.

### Sources used
- **YouTube Data API v3** (new phrasings only):
  - search.list with season-word batch forms ("Y Combinator Winter 2021 application" and similar, 2016–2027), "YC founders intro", "top 10%", "waitlisted", "early decision" and "not selected for interview" phrasings.
  - order=viewCount year slices for "YC application video", "Y Combinator application", "YC founder video" and "founders video for Y Combinator".
  - videos.list for metadata.
  - commentThreads.list on about 745 candidate videos.
  - playlistItems.list on 686 applicant channels.
- **Exa web search** (about 50 queries), aimed mainly at LinkedIn founder posts with native video:
  - "shared on deadline day" posts by YC founders.
  - "throwback / found our application video" posts.
  - Rejection posts that attach the founder video.
  - X/Twitter mirrors and TikTok.
  - Founder blogs that publish their full application.
- **Public LinkedIn post pages** (VideoObject JSON-LD: author, date, duration) and lnkd.in shortlink resolution.
- **YC directory**: the yc-oss companies dump (batch, former names) and ycombinator.com/companies founder lists.
- **Other**: Vimeo oEmbed for one founder-blog video, and Hacker News Algolia (16 new phrasings, comment and story).
- **Strict founder rule applied**: rows uploaded or posted only by a company account with no founder post claiming them are B, or were skipped.

### YouTube API units
About 9,400 units used of the daily ~10,000. No 403 quotaExceeded was hit, and searching stopped with about 600 units left. About 110 search.list calls were made, plus videos.list, commentThreads.list, playlistItems.list and channels.list calls.

### Exclusions
1,321 reviewed candidates were appended to `exclusions.csv`, with reason categories only. URLs whose text contains an outcome word are written as `sha256:` prefixes. The main reasons were:
- no stated outcome (C)
- not an application video
- over 3 min
- YC-channel uploads
- non-English metadata
- LinkedIn posts without native video
- company already in a manifest
- video unavailable

One LinkedIn post (Panta) was appended as an exclusion (C) early in this round, before the directory cross-check. It is superseded by pool row yct_0701, and the exclusion row was left in place under the append-only rule.

### Blockers / caveats
- **Low yield**: the obvious YouTube and LinkedIn phrasings were largely harvested by wave 1 and round 3. Many Exa hits were companies or URLs already in the manifests. Most new applicant videos and posts state no outcome, and most rejection posts carry no video.
- **Target not reached**: ≥ 25 conf-A per outcome was not reached.
- **Reddit**: the reddit.com JSON search returned HTTP 403. It was not retried or worked around.
- **LinkedIn metadata**: LinkedIn rows have language UNKNOWN. One conf-A LinkedIn video is a 33 s clip that the founder presents as the application video.
- **Wave-1 company_id quality**: some wave-1 company_ids are generic words, not company names. Disjointness by company_id alone is therefore not fully reliable, and future rounds should also match on founder name and video duration.
