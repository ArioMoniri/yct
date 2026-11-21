"""BUG-038 diagnostic replay (yct pod, CPU). Writes NO refstim log, selects nothing.

  meta OUT_DIR      re-read the exact in-run body batch (rs.ordered(body snapshot)[100:150]) through
                    rs.page_meta_c4 with a recording `get`: every raw Commons response (including every
                    continuation page) is saved to OUT_DIR/raw_NNN.json; prints, per title, whether the merged
                    templates hold Template:Personality rights, and compares the merged templates with the
                    templates logged in the v3 body log for the logged rows of that batch.
  rule MODEL_DIR SCRATCH TITLE
                    replay ra.evaluate_image for one body title with the frozen detectors and an EMPTY C3
                    state; prints the firing rule, reason and values. Diagnostic only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402
from yct.curate import refstim_auto as ra  # noqa: E402

BATCH = slice(100, 150)


def _runner():
    spec = importlib.util.spec_from_file_location("refstim_auto_run",
                                                  ROOT / "scripts" / "refstim_auto_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _body_order(cfg: dict) -> list[dict]:
    snap = json.loads((rs.REFSTIM / "snapshots" / rs.snapshot_name_eff("body", cfg)).read_text())
    return rs.ordered(snap)


def meta(out: Path) -> None:
    cfg = rs.effective_cfg(load_config())
    batch = _body_order(cfg)[BATCH]
    out.mkdir(parents=True, exist_ok=True)
    n = [0]

    def rec(params: dict) -> dict:
        d = rs._get(params)
        (out / f"raw_{n[0]:03d}.json").write_text(json.dumps({"params": params, "response": d}))
        n[0] += 1
        return d

    m = rs.page_meta_c4([e["title"] for e in batch], get=rec)
    logged = {json.loads(x)["title"]: json.loads(x) for x in
              (ROOT / "data/refstim/image_body_auto_log_v3.jsonl").read_text().splitlines() if x.strip()}
    same = diff = 0
    for e in batch:
        t = e["title"]
        pr = rs.PERSONALITY in m[t]["templates"]
        row = logged.get(t)
        if row is not None:
            eq = ra.templates_digest(m[t]["templates"]) == row["templates_sha256"]
            same += eq
            diff += not eq
            if not eq:
                print("TEMPLATES DIFFER from v3 log:", t)
        if pr or row is None:
            print(json.dumps({"title": t, "personality_rights_template": pr, "read_revid": m[t]["read_revid"],
                              "logged": row is not None,
                              "logged_reason": row and row["reason"], "logged_rule": row and row["rule"]}))
    print(json.dumps({"responses": n[0], "logged_rows_compared": same + diff, "templates_equal": same,
                      "templates_differ": diff}))


def rule(model_dir: Path, scratch: Path, title: str) -> None:
    import cv2
    import numpy as np

    run_mod = _runner()
    cfg = rs.effective_cfg(load_config())
    e = next(x for x in _body_order(cfg) if x["title"] == title)
    m = rs.page_meta_c4([title])[title]
    lic, tpl = rs.licence_of(m["templates"], m.get("license_short"))
    key = rs.title_key(title)
    scratch.mkdir(parents=True, exist_ok=True)

    def load():
        src = scratch / f"{key[:16]}{Path(m['url']).suffix.lower()}"
        ra.fetch_verified(src, m["url"], e["sha1"], title, run_mod._dl)
        return np.ascontiguousarray(cv2.imread(str(src), cv2.IMREAD_COLOR)[..., ::-1])

    adm = rs.admissible(lic, cfg["controls"]["refclips"]["image_licences"])
    c = ra.Candidate(title, key, e, m, lic, tpl, adm, load)
    det = run_mod.RealDetectors(cfg, model_dir)
    keys, longest = ra.manifest_key_hashes()
    row = ra.evaluate_image("body", c, det, cfg, ra.State(), keys, longest)
    print(json.dumps({"title": title, "licence": lic, "licence_template": tpl, "admissible": adm,
                      "decision": row["decision"], "rule": row.get("rule"), "reason": row.get("reason"),
                      "values": row.get("values")}, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "meta":
        meta(Path(sys.argv[2]))
    elif sys.argv[1] == "rule":
        rule(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        raise SystemExit(__doc__)
