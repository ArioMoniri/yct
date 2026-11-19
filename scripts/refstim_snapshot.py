"""T-LIC / T-NAT step 1 (D-071 b/c): write the full Commons candidate snapshots before any filter.
Usage: python scripts/refstim_snapshot.py   (writes data/refstim/snapshots/*.json, prints sha256 each)"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402


def main() -> None:
    cfg = load_config()
    day = dt.datetime.now(dt.UTC).date().isoformat()
    for kind, cat in [("image", "face"), ("image", "body"), ("image", "place"), ("nat", None)]:
        s = rs.build_snapshot(rs.header_for(kind, cfg, cat, day), rs.fetch_commons)
        name = f"{kind}_{cat or 'nat'}_snapshot.json"
        sha = rs.write_json(rs.REFSTIM / "snapshots" / name, s)
        print(name, len(s["entries"]), sha, flush=True)


if __name__ == "__main__":
    main()
