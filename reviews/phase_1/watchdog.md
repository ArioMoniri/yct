# Watchdog — Phase 1 gate (curation, wave 1)
Fresh watchdog subagent, repo HEAD fd08ad9 (packet cites 536e816). Sealed files not decrypted; no label values read.

## VERDICT: INCIDENT (CRITICAL, blinding) + VETO

## Defects
1. **CRITICAL: plaintext labels on disk.** The session scratchpad `/tmp/claude-0/-home-user-yct/796b470d-…/scratchpad/` (the same one every subagent in this session uses) holds:
   - `built.json`: 627 rows with keys `outcome, conf, quote, ev, discovery, yc_url`. This is the plaintext that went into sealed_p1. Timestamp 16:01.
   - `man.json`: the pre-BUG-012 manifest with `label_confidence, evidence_url, discovery_method`.
   - `classified.json` (196 rows), `triage*.json` (up to 1628 rows), `r2/batch_new.json` and `r2/batch_ext.json`: per-id `acc/rej` flags and titles.

   Command: `grep -rlE '"outcome"|"acc"\s*:' scratchpad`, then I printed the key names only. BUG-012 says "plaintext shredded", which is false. `sealed2/` is empty, but that is the only part that was cleaned. Discovery route r (D-040, sealed-only) is also in plaintext (`discovery`). Action for the owner: shred these files, then check whether any analyst or reviewer agent read them.
2. **Outcome-revealing URL in the analyst manifest.** `data/manifest.csv:645` is yct_0644, whose URL contains `…/my-yc-rejection-full-application/…` and the founder's name. Command: grep the manifest URLs for `reject|accept|didnt|got-in|into-yc|admitted|denied`. This is the only hit. `scripts/check_blinding.py` → "OK, 239 files". So the scanner does not check URL contents.
3. **Row-level tally leak in tracked docs.**
   - `reviews/phase_1/packet.md:5` says "FireJet = 4 rejected cycles same team".
   - `DECISIONS.md:70` (D-045) says the same.
   - The manifest has exactly 3 FireJet rows, all `in_primary=True` (yct_0641/0642/0643, S22/W23/S23), so their labels can be deduced. The manifest has 3 rows while the docs say "4", which is a count inconsistency.
   - Aggregate "30/28" is in packet.md and DECISIONS.md. That is tolerable as an orchestrator total, but it should not sit next to company names.
4. **BUG-012 (history leak), severity P1, confirmed but bounded.** `git show f48a331:data/manifest.csv` has label_confidence, evidence_url and notes: A 36, B 31, C 556. Video ids were renumbered, but a URL join still works: 622/661 current rows match. The 58 primary rows map to old A 36, B 1, and new 21. The C rows ("all one outcome", now excluded) are recoverable from history. Notes and evidence_url contain no outcome words, and 64/67 A/B evidence_urls equal the video URL. Primary labels are therefore not directly recoverable from history. The residual risk is procedural. Recommend the owner decide on a history rewrite before Phase 6.
5. **BUG-013 (hf_token via ssm:SendCommand), severity P0.** It is open and owner-only. The renumbering was done append-only, which is correct. It does not block P1 but must be fixed before any further GPU work.
6. **Search-log path and tracking.**
   - ROADMAP.md:53 specifies `data/search_log.csv`. The actual file is `data/curation/search_log.csv`, and it is gitignored (`.gitignore`, BUG-005), so reviewers cannot audit the provenance at a SHA.
   - Columns `timestamp, source, query, n_results, n_new_candidates` comply, with no per-candidate outcome. The query text is outcome-stratified (for example "rejected YC application video"), and the number of new candidates per query hints at the route.
   - Minor: of the 457 `directory_sweep` (YC-directory) queries, 12 match manifest company_ids, 1 of them primary (yct_0310). This is weak evidence of an "accepted" outcome.
7. **Sealed checksum format.** `sealed_p1b_part1.tar.age.sha256` stores the path `data/sealed/…`, so `sha256sum -c` run in data/sealed warns "could not be read". The hashes do match (see below).

## Passed checks (commands)
- **Manifest header:** `video_id,url,platform,upload_date,claimed_batch,era_stratum,company_id,duration_s,language,is_original_application_video,in_primary`. No label columns. Rows: 661, of which 58 have `in_primary=True` (30+28 = 58, consistent). The sha256 is 719080c8…61ea, matching D-045.
- **Sealed hashes:**
  - `sha256sum *.age`: p1 = 46389a8b…364b, p1b = 1ded6ae4…19b1. Both equal their .sha256 files.
  - Git history for paths matching `label|evidence|sealed|outcome` contains only `.age` and `.sha256` files.
- **Duplicates:** exact URL, normalised YouTube id and video_id all give 0. Company+claimed_batch gives 0. 21 companies have 2–3 rows, all in different cycles, which is a within-company pair design. Exclusions overlap the manifest in 0 of 2386 URLs.
- **Fabrication** (seed 20261117, 5 random rows plus 1 LinkedIn row):
  - YouTube oEmbed returned 200 for yct_0150, 0025, 0240, 0208 and 0221.
  - The LinkedIn row yct_0646 returned 200 (og:type article; login wall possible).
  - yct_0644 returned 200 video/mp4.
  - For all 11 LinkedIn rows, the upload_date equals the date decoded from the activity id (id>>22). Titles and outcomes were not inspected.
- **Legal:**
  - SSM `/yct/owner/data_decision` reads "SIGNED 2026-11-17 by arn:aws:iam::…:root", version 1.
  - DATA_DECISION.md was committed in 6c16d89 by an agent and is not SSH-signed (`%G?`=N). This was an interim chat attestation (H-002), which is acceptable only until the signing check is live.
  - No `data/raw` or `data/normalized` directory exists. The only `.mp4` files found are ≤1 MB synthetic test clips (2 s). No media has been downloaded yet.
- **Exclusions and curation report:** reason strings only. The report withholds per-label counts (line 133).

## Required before re-gate
1. Owner shreds the scratchpad plaintext and attests in DECISIONS.md.
2. Remove or replace the yct_0644 URL (use an opaque mirror, or map it in a sealed file).
3. Drop per-company outcome wording from packet.md. D-045 is append-only, so add a superseding note.
4. Extend check_blinding.py to scan URLs and slugs.
5. Fix the p1b .sha256 path.
6. Track a de-outcomed search log, or document why it is untracked.

P1 DoD items still open: κ re-derivation and the 10-row human spot-check, both owner-blind procedures.
