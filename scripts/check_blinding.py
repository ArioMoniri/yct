#!/usr/bin/env python3
"""Blinding guard (v2.md §3 Blinding, §2b.4 item 4).

Fails if
  * any tracked .csv/.tsv file outside data/sealed/ and src/yct/curate/ has a header column named
    `outcome` (case-insensitive), or any tracked .jsonl/.json file there has an `outcome` key;
    data/manifest.csv is covered by this and named explicitly in the report;
  * UNBLIND_TOKEN exists (tracked or in the working tree) while the prereg-lock tag is absent;
  * (FIX-P1, BUG-016) any URL in a tracked text file outside those directories, or any value of a
    url-like column (header containing "url") of a tracked .csv/.tsv, contains an outcome word
    (reject/rejected/rejection, accepted, got-in, into-yc, didnt-get; case-insensitive, URL-decoded,
    "-", "_" or space as separator). For tables with a video_id column the offending video_ids are listed,
    otherwise path:line (the matched word is never printed). A URL that must stay out of the analyst
    view is replaced by `sealed:<id>` and
    the real URL is kept in an owner-encrypted archive under data/sealed/.

Files under the excluded directories are never opened.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402

EXCLUDED = ("data/sealed/", "src/yct/curate/")
FORBIDDEN = {"outcome"}
# BUG-024: sealed-only columns (label proxies) must never appear in tracked tables or stored diffs.
SEALED_COLS = {"label_confidence", "discovery_method", "evidence_url", "evidence_quote", "route"}
MANIFEST = "data/manifest.csv"
OUTCOME_WORDS = re.compile(r"reject|accepted|got[-_ ]in|into[-_ ]yc|didn'?t[-_ ]get", re.IGNORECASE)
URL_RE = re.compile(r"(?:https?://|sealed:)[^\s\"'<>()\[\]{}|\\^`,]+", re.IGNORECASE)


def outcome_words(value: str) -> list[str]:
    """Outcome words in one URL/value (URL-decoded, lower-cased)."""
    v = unquote(unquote(str(value))).lower()
    return sorted({m.group(0) for m in OUTCOME_WORDS.finditer(v)})


def url_hits(path: str, text: str) -> list[str]:
    """Outcome words in URLs (any text file) and in url-like columns (.csv/.tsv)."""
    hits: list[str] = []
    if path.endswith((".csv", ".tsv")) and text.strip():
        first = text.splitlines()[0]
        delim = "\t" if path.endswith(".tsv") or ("\t" in first and "," not in first) else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        header = [_norm(c) for c in rows[0]]
        url_cols = [i for i, c in enumerate(header) if "url" in c]
        id_col = header.index("video_id") if "video_id" in header else None
        for n, row in enumerate(rows[1:], start=2):
            cells = [row[i] for i in url_cols if i < len(row)]
            cells += [u for c in row for u in URL_RE.findall(c)]
            words = sorted({w for c in cells for w in outcome_words(c)})
            if words:
                where = row[id_col] if id_col is not None and id_col < len(row) else f"line {n}"
                hits.append(where)  # never print the word itself: it would state the outcome
        return hits
    for n, line in enumerate(text.splitlines(), start=1):
        words = sorted({w for u in URL_RE.findall(line) for w in outcome_words(u)})
        if words:
            hits.append(f"line {n}")
    return hits


def _norm(name: object) -> str:
    return str(name).strip().strip('"').strip().lower()


def header_hits(path: str, text: str) -> list[str]:
    if path.endswith((".csv", ".tsv")):
        first = text.splitlines()[0] if text.strip() else ""
        delim = "\t" if path.endswith(".tsv") or ("\t" in first and "," not in first) else ","
        row = next(csv.reader(io.StringIO(first), delimiter=delim), [])
        return [c for c in row if _norm(c) in FORBIDDEN | SEALED_COLS]
    if path.endswith((".jsonl", ".json")):
        hits = []
        docs = text.splitlines() if path.endswith(".jsonl") else [text]
        for line in docs:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            for o in obj if isinstance(obj, list) else [obj]:
                if isinstance(o, dict):
                    hits += [k for k in o if _norm(k) in FORBIDDEN | SEALED_COLS]
        return sorted(set(hits))
    if path.endswith((".patch", ".diff")):
        return sorted({c for c in SEALED_COLS | FORBIDDEN
                       if re.search(rf"(^|[,\t\s\"]){re.escape(c)}([,\t\s\"]|$)", text, re.M)})
    return []


def main() -> int:
    ap = g.base_parser(__doc__)
    ap.parse_args()
    root = Path(g.git("rev-parse", "--show-toplevel").strip())
    tracked = [p for p in g.git("ls-files", "-z").split("\0") if p]
    bad = []
    for p in tracked:
        f = root / p
        if p.startswith(EXCLUDED) or not f.is_file():
            continue
        raw = f.read_bytes()
        if b"\0" in raw[:8192]:
            continue  # binary
        text = raw.decode("utf-8", errors="replace")
        if p.endswith((".csv", ".tsv", ".jsonl", ".json")):
            hits = header_hits(p, text)
            if hits:
                label = "manifest has an outcome column" if p == MANIFEST else "outcome column/key"
                bad.append(f"{p}: {label} {hits} outside {', '.join(EXCLUDED)}")
        uhits = url_hits(p, text)
        if uhits:
            bad.append(f"{p}: outcome word in URL ({len(uhits)}): " + "; ".join(uhits))
    if ("UNBLIND_TOKEN" in tracked or (root / "UNBLIND_TOKEN").exists()) and not g.tag_exists():
        bad.append(f"UNBLIND_TOKEN exists but tag {g.PREREG_TAG} is absent")
    for b in bad:
        print(f"FAIL {b}")
    if not bad:
        print(f"OK blinding: {len(tracked)} tracked files scanned")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
