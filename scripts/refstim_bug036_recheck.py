"""BUG-036 read-only re-check: recompute the C1 licence decision for every title in the v1 image logs with
the fixed (fully paged, fail-closed) Commons client. Metadata API calls only: no download, no detector, no
log write. Prints counts only; with --flips OUT it also writes the D-079 flip list (sha256(title) keys per
v1 log: inadm_to_adm, adm_to_inadm, revid_changed), which is committed and frozen by sha before the v2 run.

    python scripts/refstim_bug036_recheck.py [--flips OUT] data/refstim/image_face_auto_log.jsonl ...

What is compared (R5): the C1 reading stored in each v1 row (`licence` non-null = admissible) against the
C1 reading of the same title with the fixed client. That differs from the BUG-036 diagnosis (BUGS.md),
which compared two truncated reads with different batch boundaries against each other.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from yct.curate import refstim as rs


def diff_rows(rows: list[dict], meta: dict[str, dict]) -> tuple[dict, dict]:
    """(counts, lists) for v1 rows (C0 rows excluded) against fixed-client metadata `meta` by title."""
    rows = [r for r in rows if r.get("rule") != "C0"]          # C1 was evaluated on every other row
    n = {"rows": len(rows), "adm_to_inadm": 0, "inadm_to_adm": 0, "template_changed": 0,
         "passes": 0, "passes_now_inadm": 0, "revid_changed": 0}
    lists: dict[str, list[str]] = {"inadm_to_adm": [], "adm_to_inadm": [], "revid_changed": []}
    for r in rows:
        m = meta[r["title"]]
        lic, tpl = rs.licence_of(m["templates"], m["license_short"])
        was, now = r.get("licence") is not None, lic is not None
        if was and not now:
            n["adm_to_inadm"] += 1
            lists["adm_to_inadm"].append(r["sha256_title"])
        if now and not was:
            n["inadm_to_adm"] += 1
            lists["inadm_to_adm"].append(r["sha256_title"])
        n["template_changed"] += was and now and tpl != r.get("licence_template")
        if r.get("decision") == "pass":
            n["passes"] += 1
            n["passes_now_inadm"] += not now
        if m.get("read_revid") != r.get("revid"):
            n["revid_changed"] += 1
            lists["revid_changed"].append(r["sha256_title"])
    return n, {k: sorted(v) for k, v in lists.items()}


def main(argv: list[str]) -> int:
    out_path = None
    if argv[:1] == ["--flips"]:
        out_path, argv = Path(argv[1]), argv[2:]
    doc = {"decision": "D-079", "source": "scripts/refstim_bug036_recheck.py (fixed client, read-only)",
           "logs": {}}
    for path in argv:
        rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
        titles = [r["title"] for r in rows if r.get("rule") != "C0"]
        n, lists = diff_rows(rows, rs.page_meta(titles, batch=10))
        print(Path(path).name, json.dumps(n))
        doc["logs"][Path(path).name] = lists
    if out_path:
        out_path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
