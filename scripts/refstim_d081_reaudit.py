"""D-081 (council watchdog 2) offline post-download re-audit: no network, no detector, selects nothing.

Every superseded post-BUG-036 log (the D-079 v2 run-1 log, the D-080 v3 logs) is audited again with the
fixed, rule-based audit against all earlier logs of its category (rs.post_download_reaudit_cfg). Writes
data/refstim/d081_reaudit.json (canonical JSON). Its sha is frozen as
controls.refclips_d081_artifacts.reaudit_sha256; the v4 runner recomputes the same document from the
committed logs before rank 1 and refuses to launch unless it hashes to that sha with 0 STOP and 0
same-reason/different-C1-class pairs (ra.check_frozen_d081).

    python scripts/refstim_d081_reaudit.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402


def main() -> int:
    cfg = load_config()
    doc = rs.post_download_reaudit_cfg(cfg, ROOT)
    sha = rs.write_json(ROOT / cfg["controls"]["refclips_d081"]["reaudit_file"], doc)
    for cat, c in doc.items():
        print(cat, json.dumps(c["logs"]), "stops", len(c["stops"]), "same_reason_diff_class",
              c["same_reason_diff_class"])
    print("sha256", sha)
    return 1 if any(c["stops"] or c["same_reason_diff_class"] for c in doc.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
