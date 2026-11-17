#!/usr/bin/env python3
"""Blinding guard (v2.md §3 Blinding, §2b.4 item 4).

Fails if
  * any tracked .csv/.tsv file outside data/sealed/ and src/yct/curate/ has a header column named
    `outcome` (case-insensitive), or any tracked .jsonl/.json file there has an `outcome` key;
    data/manifest.csv is covered by this and named explicitly in the report;
  * UNBLIND_TOKEN exists (tracked or in the working tree) while the prereg-lock tag is absent.

Files under the excluded directories are never opened.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402

EXCLUDED = ("data/sealed/", "src/yct/curate/")
FORBIDDEN = {"outcome"}
MANIFEST = "data/manifest.csv"


def _norm(name: object) -> str:
    return str(name).strip().strip('"').strip().lower()


def header_hits(path: str, text: str) -> list[str]:
    if path.endswith((".csv", ".tsv")):
        first = text.splitlines()[0] if text.strip() else ""
        delim = "\t" if path.endswith(".tsv") or ("\t" in first and "," not in first) else ","
        row = next(csv.reader(io.StringIO(first), delimiter=delim), [])
        return [c for c in row if _norm(c) in FORBIDDEN]
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
                    hits += [k for k in o if _norm(k) in FORBIDDEN]
        return sorted(set(hits))
    return []


def main() -> int:
    ap = g.base_parser(__doc__)
    ap.parse_args()
    root = Path(g.git("rev-parse", "--show-toplevel").strip())
    tracked = [p for p in g.git("ls-files", "-z").split("\0") if p]
    bad = []
    for p in tracked:
        if p.startswith(EXCLUDED) or not p.endswith((".csv", ".tsv", ".jsonl", ".json")):
            continue
        f = root / p
        if not f.is_file():
            continue
        hits = header_hits(p, f.read_text(errors="replace"))
        if hits:
            label = "manifest has an outcome column" if p == MANIFEST else "outcome column/key"
            bad.append(f"{p}: {label} {hits} outside {', '.join(EXCLUDED)}")
    if ("UNBLIND_TOKEN" in tracked or (root / "UNBLIND_TOKEN").exists()) and not g.tag_exists():
        bad.append(f"UNBLIND_TOKEN exists but tag {g.PREREG_TAG} is absent")
    for b in bad:
        print(f"FAIL {b}")
    if not bad:
        print(f"OK blinding: {len(tracked)} tracked files scanned")
    return 1 if bad else 0


if __name__ == "__main__":
    g.run(main)
