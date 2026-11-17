#!/usr/bin/env python3
"""Recompute the confidence-A rule on DECRYPTED sealed label tables (v2.md §5 P1, §2b.4 check 2; BUG-022;
DECISIONS D-053). OWNER-SIDE ONLY: it reads labels, so it refuses to run without --owner-side, and it is
never run by an agent. Pure stdlib (runs where scripts/owner_label_qc.sh runs).

A-rule (docs/prompts/v1_original.md, Prompt A STEP 2):
  * A accepted = in the YC directory with the matching batch AND >= 1 founder match;
  * A rejected = the founder explicitly says THIS video was rejected AND the company is not listed for
    that batch.
Machine checks per sealed row with label_confidence A (founder match is not machine-checkable here):
  1. batch: taken from the MANIFEST claimed_batch (BUG-022: round-2 sealed CSVs lack it). Manifest batch
     UNKNOWN -> NEEDS_RECHECK(batch_unknown); a sealed claimed_batch that differs -> FAIL(batch_mismatch);
  2. directory URL present: accepted -> evidence_url or directory_url is a YC directory company URL;
     rejected -> directory_url (the directory listing consulted) present. Missing -> NEEDS_RECHECK(
     a_rule_evidence); an accepted row whose only evidence is not a directory URL -> FAIL(a_rule_evidence);
  3. quote present (evidence_quote | quote): missing -> NEEDS_RECHECK(quote_missing), never auto-A
     (BUG-022). With --snapshots and an evidence_sha256 column, the snapshot <sha256>.* must exist, hash to
     that value, and contain the quote verbatim (whitespace-normalised) -> else FAIL(snapshot_missing |
     snapshot_hash | quote_not_verbatim).
Status per row = worst of FAIL > NEEDS_RECHECK > PASS. Reason codes are outcome-neutral.

Output hygiene (BUG-021): stdout carries COUNTS ONLY. Per-id results go to --out (a file in the owner's
private temp dir), or to stderr after a "DO NOT PASTE" banner when SHOW_LABELS=1. Exit 0 = all PASS,
1 = any FAIL, 2 = only NEEDS_RECHECK.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

DIRECTORY_RE = re.compile(r"^https?://(www\.)?ycombinator\.com/companies/[^/?#]+", re.I)
_POS = {"accepted", "accept", "acc", "a", "1", "true", "yes", "admitted"}
_NEG = {"rejected", "reject", "rej", "r", "0", "false", "no"}
BANNER = "=" * 72 + "\nDO NOT PASTE BELOW THIS LINE (owner eyes only; per-id label-QC detail)\n" + "=" * 72


def outcome_class(v) -> str:
    s = str(v or "").strip().lower()
    return "pos" if s in _POS else ("neg" if s in _NEG else "")


def read_tables(root: Path) -> list[list[dict]]:
    out = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".csv", ".tsv", ".json", ".jsonl"):
            continue
        text = p.read_text(encoding="utf-8-sig")
        if p.suffix.lower() in (".csv", ".tsv"):
            delim = "\t" if p.suffix.lower() == ".tsv" else ","
            rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
        elif p.suffix.lower() == ".json":
            obj = json.loads(text)
            obj = obj.get("rows", obj.get("data", [obj])) if isinstance(obj, dict) else obj
            rows = [o for o in obj if isinstance(o, dict)]
        else:
            rows = [json.loads(x) for x in text.splitlines() if x.strip()]
        rows = [{str(k).strip().lower(): ("" if v is None else str(v).strip()) for k, v in r.items()}
                for r in rows]
        if rows:
            out.append(rows)
    return out


def load_sealed(root: Path) -> dict:
    """{video_id: merged row} over every table with video_id + outcome; conflicts abort (ids only)."""
    merged: dict = {}
    conflicts = set()
    for rows in read_tables(root):
        if not {"video_id", "outcome"} <= set(rows[0]):
            continue
        for r in rows:
            cur = merged.setdefault(r.get("video_id", ""), {})
            for k, v in r.items():
                if v and cur.get(k) and cur[k] != v and not (k == "outcome"
                                                              and outcome_class(cur[k]) == outcome_class(v)):
                    conflicts.add(r["video_id"])
                elif v:
                    cur[k] = v
    merged.pop("", None)
    if conflicts:
        raise SystemExit(f"CONFLICT: sealed tables disagree for {len(conflicts)} video_ids: "
                         f"{sorted(conflicts)}")
    return merged


def read_manifest(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["video_id"]: r for r in csv.DictReader(fh)}


def _norm(s: str) -> str:
    return " ".join(str(s).split()).lower()


def check_row(vid: str, row: dict, man: dict, snapshots: Path | None = None) -> tuple[str, list[str]]:
    fails: list[str] = []
    recheck: list[str] = []
    batch = (man.get(vid, {}).get("claimed_batch") or "").strip().upper()
    if vid not in man:
        fails.append("not_in_manifest")
    elif not batch or batch == "UNKNOWN":
        recheck.append("batch_unknown")
    sb = (row.get("claimed_batch") or "").strip().upper()
    if sb and batch and batch != "UNKNOWN" and sb != batch:
        fails.append("batch_mismatch")
    cls = outcome_class(row.get("outcome"))
    ev, dirurl = row.get("evidence_url", ""), row.get("directory_url", "")
    if cls == "pos":
        if DIRECTORY_RE.match(ev) or DIRECTORY_RE.match(dirurl):
            pass
        elif ev or dirurl:
            fails.append("a_rule_evidence")
        else:
            recheck.append("a_rule_evidence")
    elif cls == "neg":
        if not dirurl:
            recheck.append("a_rule_evidence")
    else:
        fails.append("outcome_unparseable")
    quote = row.get("evidence_quote") or row.get("quote") or ""
    if not quote:
        recheck.append("quote_missing")
    elif snapshots is not None and row.get("evidence_sha256"):
        sha = row["evidence_sha256"].lower()
        cands = sorted(Path(snapshots).glob(f"{sha}*"))
        if not cands:
            fails.append("snapshot_missing")
        elif hashlib.sha256(cands[0].read_bytes()).hexdigest() != sha:
            fails.append("snapshot_hash")
        elif _norm(quote) not in _norm(cands[0].read_text(encoding="utf-8", errors="replace")):
            fails.append("quote_not_verbatim")
    if fails:
        return "FAIL", fails + recheck
    if recheck:
        return "NEEDS_RECHECK", recheck
    return "PASS", []


def verify(sealed: dict, man: dict, snapshots: Path | None = None) -> dict:
    res = {}
    for vid in sorted(sealed):
        if str(sealed[vid].get("label_confidence", "")).strip().upper() != "A":
            continue
        res[vid] = check_row(vid, sealed[vid], man, snapshots)
    return res


def summary(res: dict) -> str:
    n = {s: sum(1 for v in res.values() if v[0] == s) for s in ("PASS", "NEEDS_RECHECK", "FAIL")}
    return (f"verify_labels: conf-A rows checked = {len(res)}; PASS = {n['PASS']}; "
            f"NEEDS_RECHECK = {n['NEEDS_RECHECK']}; FAIL = {n['FAIL']}")


def detail(res: dict) -> str:
    return "\n".join(f"{vid}\t{st}\t{','.join(r) or '-'}" for vid, (st, r) in res.items() if st != "PASS")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--sealed", required=True, help="directory of DECRYPTED sealed tables (owner temp dir)")
    ap.add_argument("--snapshots", help="directory of evidence snapshots named <sha256>.<ext>")
    ap.add_argument("--out", help="write per-id results here (owner temp dir); never to the repo")
    ap.add_argument("--owner-side", action="store_true",
                    help="required: confirms this is the owner's machine")
    a = ap.parse_args(argv)
    if not a.owner_side:
        print("refusing: verify_labels reads sealed labels and runs OWNER-SIDE only (--owner-side)",
              file=sys.stderr)
        return 3
    res = verify(load_sealed(Path(a.sealed)), read_manifest(Path(a.manifest)),
                 Path(a.snapshots) if a.snapshots else None)
    print(summary(res))
    if a.out:
        Path(a.out).write_text(detail(res) + "\n")
        print(f"per-id results written to {a.out} (owner-side; DO NOT PASTE)")
    if os.environ.get("SHOW_LABELS") == "1":
        print(BANNER, file=sys.stderr)
        print(detail(res) or "(no flagged rows)", file=sys.stderr)
    states = {v[0] for v in res.values()}
    return 1 if "FAIL" in states else (2 if "NEEDS_RECHECK" in states else 0)


if __name__ == "__main__":
    sys.exit(main())
