"""D-074: write the three image candidate snapshots from Commons categories, before any filter.
Writes data/refstim/snapshots/image_{face,body,place}_d074_snapshot.json ONLY (the D-071 image snapshots
and the NAT snapshot are never touched) and prints the concatenated-bytes sha256 for
controls.refclips_artifacts.image_snapshot_sha256.
Usage: python scripts/refstim_snapshot_d074.py"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402


def run(snapshot_dir: Path, cfg: dict, fetch_members, utc_date: str) -> str:
    for cat in cfg["controls"]["refclips"]["loc_categories"]:
        s = rs.build_category_snapshot(rs.header_for_d074(cfg, cat, utc_date), fetch_members)
        sha = rs.write_json(Path(snapshot_dir) / rs.snapshot_name_d074(cat, cfg), s)
        print(rs.snapshot_name_d074(cat, cfg), len(s["entries"]), sha, flush=True)
    return rs.image_snapshot_sha_d074(snapshot_dir, cfg)


def main() -> None:
    day = dt.datetime.now(dt.UTC).date().isoformat()
    print("image_snapshot_sha256", run(rs.REFSTIM / "snapshots", load_config(), rs.fetch_category, day))


if __name__ == "__main__":
    main()
