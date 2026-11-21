"""D-080 pre-launch dry audit (BUG-037): metadata reads only, no download, no detector, no log write.

For every title in the superseded logs of each category (D-079 v1 logs + the v2 run-1 evidence log), the
frozen client reads the current Commons metadata; the identity rule (metadata stage) and the frozen
evaluate_image up to the download (rules C0-C4, C3 inert) predict the v3 decision before the download; and
ra.dry_pair compares it with each superseded row under the D-080 audit rule. Output: counts of each pair
kind per log and every would_stop pair (sha256(title) keys, decisions and rules; no image content).

    python scripts/refstim_d080_dry_audit.py OUT.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]


def _rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def predict(cat: str, e: dict, m: dict, cfg: dict, keys: set[str], longest: int) -> tuple:
    """Metadata-stage prediction for one snapshot entry `e` with fixed-client metadata `m`."""
    if not e.get("sha1") or not m.get("commons_sha1"):
        return ("missing_sha1", None, None)
    if not ra.identity_ok(e.get("sha1"), m.get("commons_sha1"), title=e["title"]):
        return ("reject", "D1", ra.IDENTITY_REASON)
    lic, tpl = rs.licence_of(m["templates"], m.get("license_short"))
    adm = rs.admissible(lic, cfg["controls"]["refclips"]["image_licences"])
    c = ra.Candidate(e["title"], rs.title_key(e["title"]), e, m, lic, tpl, adm, None)
    return ra.metadata_stage(cat, c, cfg, keys, longest)


def audit_category(cat: str, priors: list[tuple[str, list[dict]]], entries: dict[str, dict],
                   meta: dict[str, dict], flips: dict[str, set[str]], cfg: dict, keys: set[str],
                   longest: int) -> dict:
    d9 = cfg["controls"]["refclips_d079"]
    exempt, c1 = tuple(d9["audit"]["exempt_reasons"]), tuple(d9["audit"]["c1_reasons"])
    eq = d9["audit"].get("c1_equivalence", False)
    out: dict = {"logs": {}, "would_stop": [],
                 "read_revids": {rs.title_key(t): meta[t].get("read_revid") for t in sorted(meta)}}
    preds: dict[str, tuple] = {}
    for name, rows in priors:
        n: dict[str, int] = {}
        for r in rows:
            t = r["title"]
            if t not in preds:
                preds[t] = predict(cat, entries[t], meta[t], cfg, keys, longest)
            p = preds[t]
            if p[0] == "missing_sha1":
                kind = "would_stop"
            else:
                kind = ra.dry_pair(p, r, r["sha256_title"] in flips.get(name, set()), exempt, c1, eq)
            n[kind] = n.get(kind, 0) + 1
            if kind == "would_stop":
                out["would_stop"].append({"log": name, "sha256_title": r["sha256_title"],
                                          "v1": [r["decision"], r.get("rule"), r.get("reason")],
                                          "pred": list(p)})
        out["logs"][name] = dict(sorted(n.items()))
    return out


def _code_state() -> tuple[str, list[str]]:
    """HEAD and any uncommitted change under ra.DRY_AUDIT_CODE_PATHS (D-080 council biostat c)."""
    import subprocess

    git = ["git", "-C", str(ROOT)]
    head = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    st = subprocess.run([*git, "status", "--porcelain", "--", *ra.DRY_AUDIT_CODE_PATHS], check=True,
                        capture_output=True, text=True).stdout
    return head, [x for x in st.splitlines() if x.strip()]


def main(argv: list[str]) -> int:
    out_path = Path(argv[0])
    cfg = rs.effective_cfg(load_config())
    d9 = cfg["controls"]["refclips_d079"]
    flips = rs.load_flips(ROOT / d9["audit"]["flip_file"],
                          cfg["controls"]["refclips_d079_artifacts"]["flip_sha256"], d9["flip_logs"])
    keys, longest = ra.manifest_key_hashes()
    commit, dirty = _code_state()
    if dirty:
        raise ra.StopError(f"dry audit: uncommitted changes in {dirty}: commit first")
    doc = {"decision": "D-080", "source": "scripts/refstim_d080_dry_audit.py (fixed client, metadata only)",
           "code_commit": commit, "categories": {}}
    for cat in d9["category_order"]:
        if not d9["superseded_logs"][cat]:
            continue
        priors = [(Path(q).name, _rows(ROOT / q)) for q in d9["superseded_logs"][cat]]
        snap = json.loads((rs.REFSTIM / "snapshots" / rs.snapshot_name_eff(cat, cfg)).read_text())
        entries = {e["title"]: e for e in rs.ordered(snap)}
        titles = sorted({r["title"] for _, rows in priors for r in rows})
        missing = [t for t in titles if t not in entries]
        if missing:
            raise ra.StopError(f"{cat}: {len(missing)} logged titles not in the snapshot")
        meta = rs.page_meta_c4(titles)
        doc["categories"][cat] = audit_category(cat, priors, entries, meta, flips, cfg, keys, longest)
        print(cat, json.dumps(doc["categories"][cat]["logs"]), "would_stop",
              len(doc["categories"][cat]["would_stop"]), flush=True)
    out_path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
