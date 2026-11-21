"""D-078: write data/refstim/snapshots/image_body_d078_snapshot.json = the frozen D-074 body snapshot's
entries verbatim + a complete enumeration of each added Commons category (union, dedup by title).
Never touches the D-074 snapshots or logs. Prints the file sha256 for
controls.refclips_d078_artifacts.body_snapshot_sha256.
Usage: python scripts/refstim_snapshot_d078.py"""

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402


def run(snapshot_dir: Path, cfg: dict, fetch_members, utc_date: str) -> dict[str, str]:
    want = cfg["controls"]["refclips_artifacts"]["image_snapshot_sha256"]
    if rs.image_snapshot_sha_d074(snapshot_dir, cfg) != want:
        raise rs.CurationError("D-074 snapshots differ from the frozen sha: refusing to build D-078")
    out = {}
    for cat in rs.d078_categories(cfg):
        base_path = Path(snapshot_dir) / rs.snapshot_name_d074(cat, cfg)
        base = json.loads(base_path.read_text())
        rs.check_header_d074(base, cfg)
        hdr = rs.header_for_d078(cfg, cat, utc_date, rs.file_sha(base_path))
        s = rs.build_d078_snapshot(hdr, base, fetch_members)
        out[cat] = rs.write_json(Path(snapshot_dir) / rs.snapshot_name_d078(cat, cfg), s)
        rs.check_header_d078(s, cfg, snapshot_dir)
        print(rs.snapshot_name_d078(cat, cfg), len(s["entries"]), out[cat], flush=True)
    return out


def main() -> None:
    day = dt.datetime.now(dt.UTC).date().isoformat()
    run(rs.REFSTIM / "snapshots", load_config(), rs.fetch_category, day)


if __name__ == "__main__":
    main()
