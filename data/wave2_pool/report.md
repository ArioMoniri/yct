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

## Round 5 (2026-11-20, append-only)

Data Curator, blind to study hypotheses. Appended 9 new pool rows `yct_0710`..`yct_0718` (wave=2, collected_after_lock=PENDING). Every company is disjoint from `data/manifest.csv` and from all earlier pool rows. Disjointness was checked by company_id, by fuzzy company-name match (including YC-directory former names), and by video id / Vimeo id / X status id / LinkedIn activity id against both manifests and `exclusions.csv`. One video per company: 9 rows = 9 companies. No outcome breakdowns appear in this file. Labels and evidence are only in `data/sealed/sealed_w2pool_part5.tar.age` (yct_0710..0716) and `data/sealed/sealed_w2pool_part6.tar.age` (yct_0717..0718). The plaintext was shredded after encryption.

### Counts by label confidence x era (round-5 rows, one per company)

| confidence | E1 | E2 | E3 | UNKNOWN | total |
|---|---|---|---|---|---|
| A (in_primary=True) | 2 | 1 | 2 | 2 | 7 |
| not A (B) | 0 | 1 | 1 | 0 | 2 |
| total | 2 | 2 | 3 | 2 | 9 |

The one-per-company counts are the same (9 distinct companies, 7 conf-A). claimed_batch is UNKNOWN when the uploader or founder stated no batch, which gives the 2 UNKNOWN-era rows. New platform values this round: `x` (a native video in a founder's own X post, checked through the public tweet-embed endpoint) and `web` (an mp4 self-hosted on a founder's personal blog). Language is UNKNOWN for the non-YouTube rows.

### Sources used
- **YouTube Data API v3**:
  - videos.list on about 480 YC-titled uploads that were left unreviewed in the round-4 applicant-channel upload lists. This needed no new searches.
  - search.list with `type=playlist`, about 22 queries. playlistItems.list then read 54 curated application-video playlists made by third-party curators, but every video still had to come from a founder's own channel.
  - playlists.list on the curator channels.
  - search.list with new parameters only: `videoDuration=short` combined with order=date windows before application deadlines for 2016–2026, regionCode and relevanceLanguage variants, and about 15 new phrasings.
  - channels.list and playlistItems.list on about 240 new applicant channels.
- **Exa web search** (about 25 queries):
  - Old-era founder blogs (tumblr, posterous, personal sites).
  - Curated lists of application videos.
  - threadreaderapp and nitter mirrors of X posts.
  - New LinkedIn phrasings.
  - Exa fetch for Medium pages.
- **Founder blogs and curated lists via web fetch**: a GitHub founder-story README, personal founder blogs and guide pages that embed founder videos.
- **Other**:
  - The X public tweet-embed endpoint for author, date and native-video duration.
  - Vimeo oEmbed.
  - Hacker News Algolia: new phrasings, item threads and one author listing.
  - The YC directory (yc-oss dump plus ycombinator.com company pages) for batch, founders and former names.
- **Strict founder rule applied**: rows uploaded only by a company channel, with no founder post claiming them, are B. YC-hosted application videos (directory video URLs, YC channel) were not used.

### YouTube API units
About 7,700 units used of the daily ~10,000 (about 52 search.list calls, plus videos/playlistItems/playlists/channels/commentThreads calls). No 403 quotaExceeded was hit.

### Exclusions
833 reviewed candidates were appended to `exclusions.csv`, with reason categories only and no outcome words in any written URL. The main reasons were:
- no stated outcome / no directory match (C)
- non-English metadata
- over 3 min
- launch/demo videos
- YC-channel uploads
- posts without native video
- unclear whether the clip is the submitted video

Founder videos whose metadata declares a non-English audio language were excluded under the round-3/4 convention (3 such cases).

### Blockers / caveats
- **YouTube saturated**: standard and new phrasings return mostly already-seen videos. regionCode/relevanceLanguage variants returned almost no new results. Deadline-window searches yielded about 1 directory match per ~1,500 units.
- **LinkedIn via Exa saturated**: nearly every relevant post had already been reviewed in earlier rounds.
- **Dead links**: many old-era (2010–2015) curated application-video links are now private, deleted or on defunct hosts.
- **web.archive.org**: requests timed out after the first success and were not retried.
- **Blocked or unreadable sources**: one founder blog sits behind a JavaScript bot challenge and was skipped, not worked around. Medium and LinkedIn pages often hide embedded video ids.
- **Unverified fields**: some non-YouTube rows have unverified audio language. One row's poster is a co-founder who is not in the directory's founder list. Details are in the sealed notes.

## Round 6 (2026-11-21, append-only)

Data Curator, blind to study hypotheses. Appended 9 new pool rows `yct_0719`..`yct_0727` (wave=2, collected_after_lock=PENDING). Every company is disjoint from `data/manifest.csv` and from all earlier pool rows. Disjointness was checked by company_id, by fuzzy company-name match (including YC-directory former names), and by video id / LinkedIn activity id against both manifests and both exclusion lists. One candidate was dropped because its name fuzzy-matched a wave-1 company. One video per company: 9 rows = 9 companies. No outcome breakdowns appear in this file. Labels and evidence are only in `data/sealed/sealed_w2pool_part7.tar.age` (yct_0719..0727). The plaintext was shredded after encryption.

### Counts by label confidence x era (round-6 rows, one per company)

| confidence | E1 | E2 | E3 | UNKNOWN | total |
|---|---|---|---|---|---|
| A (in_primary=True) | 0 | 1 | 3 | 2 | 6 |
| not A (B) | 0 | 0 | 2 | 1 | 3 |
| total | 0 | 1 | 5 | 3 | 9 |

The one-per-company counts are the same (9 distinct companies, 6 conf-A). claimed_batch is UNKNOWN when the uploader or founder stated no batch, which gives the 3 UNKNOWN-era rows. Three conf-A rows were matched through a YC-directory former name (the application used the company's earlier name). The B rows were uploaded by company accounts with no founder post claiming them.

### Sources used
- **YouTube Data API v3**:
  - About 70 search.list calls with new phrasings only, checked against both search logs before running. These included "YC pitch <batch>", "<batch> founder video" for batch codes not tried before (W17–W21, S17–S22, F26), "YC Application <year>", "1 minute for YC", "the video we sent to YC", "YC ED application video", and non-English-title variants (Chinese, Korean, French, Turkish). They also included `ycombinator` with `videoDuration=short` and order=date windows around 12 application deadlines from 2016 to 2022.
  - Re-review of about 3,000 earlier-seen candidates and the earlier 240-channel upload dump against a fresh yc-oss directory dump, including former names. This used no new API calls and produced 2 of the conf-A rows.
  - commentThreads.list on about 1,100 application-like candidates, looking for uploader replies that state an outcome.
  - playlistItems.list on founder channels to keep one video per company.
- **Exa web search** (6 queries): Spanish-language LinkedIn posts, Instagram/TikTok reels, X posts, and founder sites that publish their application. Exa fetch was used for a 2016 Medium application.
- **LinkedIn**: public post pages, checked through their VideoObject metadata.
- **Web fetch**: founder blogs and docs, plus one application PDF.
- **Other**:
  - Hacker News Algolia (8 new phrasings, no application videos).
  - The YC directory (yc-oss dump plus ycombinator.com company pages) for batch, founders and former names.
  - Founder identity was cross-checked through LinkedIn profiles and investor pages where the channel name differed from the directory name.

### YouTube API units
About 8,300 units used of the daily ~10,000 (about 70 search.list calls plus about 1,100 commentThreads calls and small videos/playlistItems/channels calls). No 403 quotaExceeded was hit.

### Exclusions
297 reviewed candidates were appended to `exclusions.csv`, with reason categories only and no outcome words in any written URL. The main reasons were:
- no stated outcome / no directory match (C)
- non-English metadata
- not an application video
- launch/demo videos
- dead or unavailable links
- one possible duplicate company (fuzzy name match to a wave-1 company)

### Blockers / caveats
- **YouTube is saturated**: most searches returned fewer than 15 unseen videos, nearly all with no stated outcome and no directory match. New rows came mainly from former-name re-matching of already-seen candidates.
- **Exa/LinkedIn is saturated**: most relevant posts had already been reviewed. Several promising posts had no native video, a dead short link (404 target), or a demo rather than a founder video.
- **Old published applications**: some founder videos are now private or deleted, and some application PDFs omit the video URL.
- **Unverified fields**: two of the conf-A rows rest on a directory batch match for the upload's application window, with no batch stated by the founder. One founder match goes through a channel name that differs from the directory's short form, and that name was confirmed via LinkedIn and an investor page. Details are in the sealed notes.

## Round 7 (2026-11-22, append-only)

Data Curator, blind to study hypotheses. Appended 6 new pool rows `yct_0728`..`yct_0733` (wave=2, collected_after_lock=PENDING). Every company is disjoint from `data/manifest.csv` and from all earlier pool rows. Disjointness was checked by company_id, by fuzzy company-name match (including YC-directory former names), and by video id / LinkedIn activity id / X status id against both manifests and both exclusion lists. Three fuzzy name hits were checked by hand and are different companies. One video per company: 6 rows = 6 companies. No outcome breakdowns appear in this file. Labels and evidence are only in `data/sealed/sealed_w2pool_part8.tar.age` (yct_0728..0732) and `data/sealed/sealed_w2pool_part9.tar.age` (yct_0733). The plaintext was shredded after each encryption.

### Counts by label confidence x era (round-7 rows, one per company)

| confidence | E1 | E2 | E3 | UNKNOWN | total |
|---|---|---|---|---|---|
| A (in_primary=True) | 0 | 0 | 5 | 1 | 6 |
| not A | 0 | 0 | 0 | 0 | 0 |
| total | 0 | 0 | 5 | 1 | 6 |

The one-per-company counts are the same (6 distinct companies, 6 conf-A). The UNKNOWN-era row has no batch stated by the poster. Platforms: 4 rows from X (native video in a founder's own post) and 2 from LinkedIn (native video in a founder's own post). No YouTube row qualified this round.

### Sources used
- **X (new source this round)**:
  - Candidate posts were found through Exa searches over X mirror pages (24vids, nitter-style mirrors, twstalker).
  - Status ids were resolved from mirror profile and media pages. The mirrors' search page requires an interactive check, so it was not used.
  - Each post was verified through the public `cdn.syndication.twimg.com` tweet-result JSON: author handle, date, native-video presence and duration, and post text.
- **Exa web search**: about 25 queries, including LinkedIn founder posts, X mirror pages, Loom/Vimeo, and founder blogs.
- **LinkedIn**: public post pages, checked through their VideoObject metadata (duration, author, text).
- **YouTube Data API v3**:
  - 14 order=date `Y Combinator` windows around 2022–2026 application deadlines (`videoDuration=short`).
  - 11 order=date `application video` windows around 2024–2026 deadlines.
  - 12 new phrasings, for example "Founders Video YCombinator", "Y-Combinator intro video" and "YC submission video".
  - commentThreads.list on 144 new application-like candidates.
  - Small videos/channels/playlistItems checks.
  - All candidates were matched against the yc-oss directory dump, including former names. None reached conf-A: application-like uploads had no directory match and no founder-stated outcome.
- **Other**:
  - ycarena.com's public curated list (102 video ids). All were already in a manifest or an exclusion list.
  - Hacker News Algolia (1 item lookup).
  - YC directory company pages for batch and founders.
  - Founder blogs (web fetch).

### YouTube API units
About 3,900 units used (about 37 search.list calls plus 144 commentThreads calls and small detail calls). No 403 quotaExceeded was hit.

### Exclusions
80 reviewed candidates were appended to `exclusions.csv`, with reason categories only and no outcome words in any written URL. The main reasons were:
- no stated outcome / no directory match (C)
- no native video in post
- company already in a manifest
- non-English metadata
- unclear whether the attached clip is the submitted video

### Blockers / caveats
- **YouTube is saturated**: deadline-window and new-phrasing searches surfaced about 25 application-like uploads, and none had a directory match or a stated outcome.
- **LinkedIn via Exa is saturated**: almost every relevant post had already been reviewed in earlier rounds.
- **X**: posts are not indexed by the standard web search. Discovery depends on Exa coverage of mirror sites. Old status ids could only be resolved by paging a founder's mirror profile.
- **Unverified fields**:
  - Three conf-A rows rest on the founder presenting the clip as their YC founder video, plus a directory batch match. The batch is not stated in the post text; for two rows it comes from the founder's profile bio.
  - One row's format is unusual: a sung video that the founder says they applied with.
  - Audio language of the X/LinkedIn rows is recorded as UNKNOWN, following the earlier convention.
  - Details are in the sealed notes.
