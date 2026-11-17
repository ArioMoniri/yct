# Curation report: public YC application videos

Generated 2026-11-17 by the Data Curator agent (blind to study hypotheses). This file intentionally contains no label breakdowns; labels live only in `data/sealed/labels_pending.csv`.

## Counts by label confidence x era

| confidence | E1 | E2 | E3 | UNKNOWN | total |
|---|---|---|---|---|---|
| A | 2 | 3 | 34 | 0 | 39 |
| B | 0 | 1 | 20 | 11 | 32 |
| C | 23 | 90 | 441 | 2 | 556 |
| total | 25 | 94 | 495 | 13 | 627 |

Era strata are assigned from the batch claimed in the video title/description: E1 <= W2016, E2 S2016-W2020, E3 >= S2020. `UNKNOWN` = no batch stated by the uploader.

Confidence definitions (per curation protocol): A = founder statement and/or YC directory cross-check fully consistent (directory batch matches claimed batch and a founder name matches the uploader/description, or explicit founder statement with directory consistent); B = founder statement not fully cross-checkable (company or founder not identifiable, batch not stated, or uploader is a company channel); C = label implied only (no explicit founder statement; inferred from YC directory status for the claimed cycle or from indirect statements).

## Duration distribution (seconds)

n=627; min 35, Q1 60, median 66, Q3 80, max 180.

| bin | n |
|---|---|
| 0-44 | 5 |
| 45-59 | 141 |
| 60-74 | 287 |
| 75-89 | 97 |
| 90-119 | 81 |
| 120-180 | 16 |

## Other manifest fields

- upload_date known for 111/627 rows; language verified from YouTube metadata for 109/627 rows.
- Platform: {'youtube': 627}.
- discovery_method: {'keyword_search': 625, 'directory_sweep': 2} (directory_sweep = found only via per-company YouTube search over the YC directory; rows first found by keyword search keep keyword_search even if later cross-checked against the directory).
- Distinct company_id values: 604 (some companies appear in several application cycles; each cycle is its own row).

## Search coverage

- Queries logged: 660 (youtube_search(yt-dlp): 178, websearch: 22, webfetch: 9, youtube_search(yt-dlp) directory_sweep: 451).
- Unique YouTube candidates returned by searches: 2278; title pre-filter (mentions YC/Y Combinator, <=300 s) kept the set that was reviewed; 627 retained, 1025 excluded with reasons in `data/curation/exclusions.csv`.
- Batch sweep: YouTube searches were run for batch codes W2012-F2026 (W/S/F/X and the P26 code used by some Spring 2026 uploaders), plus year-based and phrase-based queries. YC batch naming verified against the YC directory: Winter, Spring (X; uploaders also write P26), Summer, Fall.
- YC directory cross-check used the public yc-oss mirror of ycombinator.com/companies (6,398 companies incl. former names) and individual ycombinator.com/companies/<slug> pages for batch and founder names.

- Directory sweep (owner instruction): one YouTube query "<company name> YC application video" (top 8 results) per YC company in batches S2015-F2024 (4,202 companies in the directory mirror; W2015 was not included). Completed for 451 companies (~11%) before YouTube rate-limiting (HTTP 403 / bot checks) blocked further queries; companies after the first ~360 were processed in random order, so the swept subset after that point is a random sample. Hits required the company (or former) name and an application/founder-video keyword in the title, then a manual identity check (batch and founder names).
- No Vimeo/X/LinkedIn per-company sweep was possible (no usable search endpoint); founder-name queries were not run because the directory mirror lacks founder names and per-company page fetches for all companies were out of budget.

### Exclusion reasons

| reason | n |
|---|---|
| no claimed batch and no outcome evidence | 386 |
| not identified as an application video from title | 193 |
| company not identifiable; outcome not checkable | 82 |
| promo/launch video | 73 |
| duration >3 min | 60 |
| product demo/promo | 35 |
| YC Fellowship (different program) | 31 |
| tutorial/commentary about YC videos | 17 |
| demo day | 16 |
| batch decisions not final (W27) | 12 |
| duplicate/re-upload (same company and batch) | 10 |
| ambiguous: no batch stated and founder not matched | 10 |
| ambiguous name match with YC company (short name, founder not matched) | 8 |
| posted by Y Combinator channel (YC-made/YC-posted, not founder-posted) | 7 |
| non-application YC program content | 7 |
| interview/talk/podcast | 6 |
| draft/alternate take or bloopers | 6 |
| third-party re-upload of YC example video | 5 |
| claimed outcome conflicts with YC directory (company not found) | 4 |
| non-English (metadata language=hi) | 4 |
| hiring/recruiting video | 4 |
| outcome pending per uploader | 4 |
| product demo, not founder application video | 2 |
| ambiguous identity: same name as a different-batch YC company | 2 |
| ambiguous identity (name matches YC company; no batch, founder unverified) | 2 |
| third-party re-upload of YC-posted video | 2 |
| two different videos with identical title; cannot tell which was submitted | 2 |
| commentary video about the outcome, not the application video | 2 |
| commentary video | 2 |
| commentary about the interview process | 1 |
| product demo clip, not founder application video | 1 |
| duplicate upload of same video (kept founder-channel copy) | 1 |
| claimed outcome conflicts with YC directory (company not found); no batch | 1 |
| not identified as the application video (meet-the-founders intro) | 1 |
| compilation of two application videos (original uploads used instead where found) | 1 |
| company not identifiable; outcome not stated | 1 |
| non-English (metadata language=nl) | 1 |
| non-English (metadata language=de) | 1 |
| not identified as the application video (product tagline title) | 1 |
| not identified as the application video (intro addressed to a YC partner) | 1 |
| ambiguous identity: name and batch match a YC company but uploader is not a listed founder | 1 |
| partial video (part 2 of multi-part upload) | 1 |
| vlog about the outcome, not the application video | 1 |
| cannot verify it is an application video (no title/description detail) | 1 |
| earlier version marked OLD by uploader (not the final submitted video) | 1 |
| announcement video, not application video | 1 |
| bloopers/outtakes, not the submitted video | 1 |
| multiple batches claimed in title | 1 |
| not identified as the application video (interview-stage video) | 1 |
| interview highlights, not application video | 1 |
| YC-partner content | 1 |
| interview/event digest | 1 |
| tutorial/advice video | 1 |
| vlog | 1 |
| third-party upload (Startup Grind), not founder-posted | 1 |
| parody performance, not application video | 1 |
| commentary video about feedback, not application video | 1 |
| commentary video, not application video | 1 |
| commentary/promo video | 1 |
| event coverage | 1 |

## Sources that failed or yielded nothing

- YouTube watch-page metadata (yt-dlp `--dump-json`) was repeatedly blocked by YouTube bot checks ("Sign in to confirm you are not a bot") after a burst of parallel requests; retried slowly. Rows without full metadata use the YouTube search-result record (title, channel, duration, description snippet); their upload_date/language are UNKNOWN.
- Several yt-dlp search queries intermittently returned 0 results (logged as 0); most were retried.
- General web search (Hacker News, Reddit, LinkedIn, X, Medium, Substack, Indie Hackers, Product Hunt, Vimeo) produced founder write-ups but almost no links to identifiable application videos; site: operators for x.com/linkedin.com/reddit were not honored by the search backend. WebFetch of YouTube pages returned no content. Indie Hackers returned HTTP 403.
- Third-party compilations (e.g. alexanderjarvis.com list, ycombinator.com/video examples) mostly lacked direct URLs or pointed to YC-posted copies, which are excluded.
- No YC founder-name search index was used (only name-based directory matching), so pivots/renames not recorded as former names cannot be detected.

## Known biases and caveats

- Selection: only videos founders chose to make public and title with YC/application keywords; strongly skewed to recent batches (E3) and to English-titled uploads. Founders who post publicly may differ systematically from those who do not.
- Public statements of outcome are uncommon; most rows carry implied (C) labels. The label_confidence column is therefore NOT outcome-neutral: the inference route differs by outcome, so confidence tiers are correlated with the sealed label. Treat label_confidence (and evidence_url, whose page titles often state the outcome) as potentially unblinding; do not use them as model features.
- Name-based directory matching can miss companies that renamed without the old name being recorded, which would mislabel some C rows; generic names were reviewed manually and ambiguous matches excluded.
- Several channels upload multiple cycles for the same company or founder (separate rows, shared company_id); analyses should cluster by company_id/channel.
- Titles/notes containing the word "pitch" were included only where the uploader framed them as the YC application video; is_original_application_video could not be verified by watching (no media was downloaded).
- Language and presence of audio were not verified for rows lacking YouTube metadata.
- Applications for W27 were excluded unless decisions were public, since decisions were not final at curation time (2026-11-17).

## Shortfall statement

Total retained: 627 rows (39 confidence-A). The target of >=40 confidence-A per label was not reached; see the orchestrator hand-off for per-label stop-rule counts (kept out of this file to preserve blinding). Main limits: scarcity of explicit public outcome statements and YouTube metadata rate-limiting.
