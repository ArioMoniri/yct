"""BUG-038 offline re-audit (no network, no detectors, selects nothing): every committed v3 face/body row is
audited again against its superseded logs with the fixed (rule-based) audit, and its C1 classification by
rule is compared with the old reason-based reading. Prints counts and the titles whose classification
changes; writes data/refstim/bug038_audit_v3.json. D-081 council B1: also counts
same-reason/different-C1-class reject pairs (a v3 row and a superseded row of the same title, same reason
code, C1 on one side only). The audit is pinned to the D-080 (v3) layer: controls.refclips_d081 is ignored
here (d081_reaudit covers v4)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402
from yct.curate import refstim_auto as ra  # noqa: E402


def _rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def main() -> None:
    raw = load_config()
    raw["controls"].pop("refclips_d081", None)     # the v3 rows are audited against the D-080 superseded logs
    cfg = rs.effective_cfg(raw)
    d9 = cfg["controls"]["refclips_d079"]
    flips = rs.load_flips(ROOT / d9["audit"]["flip_file"],
                          cfg["controls"]["refclips_d079_artifacts"]["flip_sha256"], d9["flip_logs"])
    exempt, c1 = tuple(d9["audit"]["exempt_reasons"]), tuple(d9["audit"]["c1_reasons"])
    dry = json.loads((ROOT / "data/refstim/d080_dry_audit.json").read_text())
    out: dict = {}
    for cat in ("face", "body"):
        rows = _rows(ROOT / f"data/refstim/image_{cat}_auto_log_v3.jsonl")
        priors = [(Path(q).name, {r["title"]: r for r in _rows(ROOT / q)})
                  for q in d9["superseded_logs"][cat]]
        dry_revids = (dry["categories"].get(cat) or {}).get("read_revids") or {}
        kinds, stops, reclass, pr_rules = Counter(), [], [], Counter()
        diff_class = []
        for r in rows:
            for name, prev in priors:
                o = prev.get(r["title"])
                if (o is not None and r["decision"] == o["decision"] == "reject"
                        and (r.get("reason") or None) == (o.get("reason") or None)
                        and (r.get("rule") == ra.C1_RULE) != (o.get("rule") == ra.C1_RULE)):
                    diff_class.append({"title": r["title"], "log": name, "v3_rule": r.get("rule"),
                                       "superseded_rule": o.get("rule"), "reason": r.get("reason")})
            if r.get("reason") == "personality_rights":
                pr_rules[r["rule"]] += 1
            if (r["decision"] == "reject" and r.get("reason") in c1) != ra.is_c1_reject(r, c1):
                reclass.append({"title": r["title"], "rule": r["rule"], "reason": r["reason"],
                                "decision": r["decision"]})
            try:
                notes = ra.audit_v2(r, priors, flips, exempt, c1, c1_equiv=True, dry_revids=dry_revids)
            except ra.StopError as exc:
                stops.append({"title": r["title"], "stop": str(exc)[:200]})
                continue
            for _, k, _ in notes:
                kinds[k] += 1
            logged = {n for n, k, _ in notes if k == "c1_equivalent"}
            if logged != set(r.get("audit_c1_equivalent") or {}):
                stops.append({"title": r["title"], "stop": "c1_equivalent notes differ from the logged ones"})
        out[cat] = {"rows": len(rows), "passes": sum(r["decision"] == "pass" for r in rows),
                    "audit_kinds": dict(kinds), "stops": stops, "personality_rights_by_rule": dict(pr_rules),
                    "reclassified_by_rule": reclass, "same_reason_diff_class": diff_class}
    sha = rs.write_json(ROOT / "data/refstim/bug038_audit_v3.json", out)
    print(json.dumps(out, indent=1))
    print("sha256", sha)


if __name__ == "__main__":
    main()
