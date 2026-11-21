"""BUG-036 read-only re-check: recompute the C1 licence decision for every title in the v1 image logs with
the fixed (fully paged, fail-closed) Commons client. Metadata API calls only: no download, no detector, no
log write. Prints counts only.

    python scripts/refstim_bug036_recheck.py data/refstim/image_face_auto_log.jsonl ...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from yct.curate import refstim as rs


def main(paths: list[str]) -> int:
    for path in paths:
        rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
        rows = [r for r in rows if r.get("rule") != "C0"]          # C1 was evaluated on every other row
        meta = rs.page_meta([r["title"] for r in rows], batch=10)
        n = {"rows": len(rows), "adm_to_inadm": 0, "inadm_to_adm": 0, "template_changed": 0,
             "passes": 0, "passes_now_inadm": 0, "revid_changed": 0}
        for r in rows:
            lic, tpl = rs.licence_of(meta[r["title"]]["templates"], meta[r["title"]]["license_short"])
            was = r.get("licence") is not None
            now = lic is not None
            n["adm_to_inadm"] += was and not now
            n["inadm_to_adm"] += now and not was
            n["template_changed"] += was and now and tpl != r.get("licence_template")
            if r.get("decision") == "pass":
                n["passes"] += 1
                n["passes_now_inadm"] += not now
        revs = {p["title"]: p.get("lastrevid") for p in _revids([r["title"] for r in rows])}
        n["revid_changed"] = sum(1 for r in rows if revs.get(r["title"]) != r.get("revid"))
        print(Path(path).name, json.dumps(n))
    return 0


def _revids(titles: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(titles), 50):
        d = rs._get({"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "info"})
        if "continue" in d or not d.get("batchcomplete"):
            raise rs.CurationError("prop=info not complete in one response")
        out += d["query"]["pages"]
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
