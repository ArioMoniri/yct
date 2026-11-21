"""T-NAT0 CPU stage runner (yct pod CPU only; D-075 §3; src/yct/curate/natstim.py).

  run SCRATCH     fill the 40-candidate NAT buffer from the frozen NAT snapshot (resumes from the log)

Downloads + normalised T1 clips stay out of the repo (SCRATCH, then S3 under controls.refclips.s3_root:
sources/nat/<file> and nat_t1/<t1_name>.mp4 + nat_t1/audio16k/<t1_name>.wav). Writes only the append-only
NAT log controls.refclips_auto.logs.nat. Exit 0 = buffer full or snapshot exhausted; STOP -> exit 2."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import natstim as ns  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402
from yct.curate import refstim_auto as ra  # noqa: E402


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _s3(src: Path, key: str, cfg: dict) -> None:
    root = cfg["controls"]["refclips"]["s3_root"].rstrip("/")
    subprocess.run(["aws", "s3", "cp", "--only-show-errors", "--region", "eu-central-1", str(src),
                    f"{root}/{key}"], check=True)


def fetch_normalise_fn(scratch: Path, cfg: dict):
    from yct.normalize.core import normalize_video

    srcd, t1d = scratch / "sources", scratch / "t1"
    srcd.mkdir(parents=True, exist_ok=True)
    t1d.mkdir(parents=True, exist_ok=True)

    def fn(entry: dict, meta: dict) -> dict:
        title, url, want = entry["title"], meta["url"], meta.get("commons_sha1")
        if not want:
            raise ra.StopError(f"Commons returned no sha1 for {title!r} (fail-closed)")
        ext = Path(url).suffix.lower() or ".bin"
        src = srcd / f"{rs.title_key(title)[:16]}{ext}"
        for _ in range(2):        # D-079 byte rule: a mismatch is a download defect -> once more, then STOP
            if not src.exists():
                try:
                    ns.stream_get(url, src)
                except rs.CurationError as exc:
                    raise ra.StopError(f"download failed: {title!r}: {exc}") from exc
            got = ns.sha1_file(src)
            if got == want:
                break
            src.unlink()
        else:
            raise ra.StopError(f"download defect: {title!r} sha1 {got} != Commons {want} "
                               "after one re-download")
        try:
            rec = normalize_video(src, t1d, cfg)
        except Exception as exc:  # noqa: BLE001 - fail-closed: decode/normalise errors are a STOP
            raise ra.StopError(f"normalise failed for {title!r}: {type(exc).__name__}: {exc}") from exc
        wav = Path(rec["wav_path"])
        out = {"trimmed_duration_s": rec["trimmed_duration_s"], "source_sha1": got,
               "source_sha256": _sha256(src), "sha256": rec["sha256"], "video_id": rec["video_id"],
               "wav_sha256": _sha256(wav)}
        _s3(src, f"sources/nat/{src.name}", cfg)
        _s3(Path(rec["path"]), f"nat_t1/{rec['video_id']}.mp4", cfg)
        _s3(wav, f"nat_t1/audio16k/{wav.name}", cfg)
        _s3(t1d / f"{rec['video_id']}.json", f"nat_t1/records/{rec['video_id']}.json", cfg)
        src.unlink()              # kept in S3; sources can be large
        return out

    return fn


def run(scratch: Path) -> int:
    cfg = load_config()
    a = cfg["controls"]["refclips_auto"]
    ra.check_frozen(cfg)          # controls.refclips_auto frozen (D-075)
    order = ns.check_snapshot(cfg, rs.REFSTIM / "snapshots" / "nat_nat_snapshot.json")
    keys, longest = ra.manifest_key_hashes()
    known = rs.known_url_hashes([ROOT / "data" / "manifest.csv",
                                  ROOT / "data" / "wave2_pool" / "pool_manifest.csv"])
    log = ROOT / a["logs"]["nat"]
    try:
        buf = ns.run_cpu(order, cfg, log, rs.page_meta_c4, fetch_normalise_fn(scratch, cfg), keys, longest,
                         known)
    except (ra.StopError, rs.CurationError) as exc:
        print(json.dumps({"status": "STOP", "error": str(exc)[:2000]}))
        return 2
    rows = ns.cpu_rows(ns.load_log(log))
    print(json.dumps({"status": "ok", "buffer": len(buf), "evaluated": len(rows),
                      "rejects": {r: sum(x["reason"] == r for x in rows) for r in
                                  sorted({x["reason"] for x in rows if x["reason"]})}}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    sys.exit(run(Path(sys.argv[2])))
