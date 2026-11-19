"""T-LIC step 2 (D-071 b): inspect localiser candidates in ascending sha256(title) order.

  auto   CATEGORY N   automatic checks (personality rights, licence, too_small, duplicate, cascade on the
                      processed 256-px greyscale crop) for the first N ordered candidates; downloads survivors
                      to the scratch dir and writes numbered contact sheets for the visual check.
  final  CATEGORY     merge auto + visual decisions (scratch visual_<cat>.json: {title: reason|""}) in order,
                      stop at the 20th pass, write data/refstim/<cat>_reject_log.json + manifest rows.
Downloads stay out of the repo (scratch, then S3 under controls.refclips.s3_root/sources/)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402

SCR = Path(os.environ.get("REFSTIM_SCRATCH", "/tmp/refstim"))
CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
MIN_SIDE = 316
FACE_FRAC = 0.4


def grey709(rgb: np.ndarray) -> np.ndarray:
    return (
        (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
        .round()
        .clip(0, 255)
        .astype(np.uint8)
    )


def faces(g: np.ndarray, cfg: dict) -> np.ndarray:
    f = cfg["confounds"]["face"]
    m = int(round(f["min_size_frac"] * min(g.shape)))
    r = CASCADE.detectMultiScale(
        g, scaleFactor=f["scale_factor"], minNeighbors=f["min_neighbors"], minSize=(m, m)
    )
    return np.array(r).reshape(-1, 4)


def crop_box(g_full: np.ndarray, cat: str, cfg: dict) -> tuple[int, int, int] | None:
    """Square (x, y, side). face: centred on the largest detection, face = 50% of the side, clipped to the
    image; body/place: the largest centred square."""
    h, w = g_full.shape
    if cat == "face":
        d = faces(g_full, cfg)
        if not len(d):
            return None
        x, y, fw, fh = max(d, key=lambda b: b[2] * b[3])
        side = int(min(min(h, w), max(fh / 0.5, MIN_SIDE)))
        cx, cy = x + fw / 2, y + fh / 2
        x0 = int(np.clip(cx - side / 2, 0, w - side))
        y0 = int(np.clip(cy - side / 2, 0, h - side))
        return x0, y0, side
    side = min(h, w)
    return (w - side) // 2, (h - side) // 2, side


def processed(rgb: np.ndarray, box) -> np.ndarray:
    x, y, s = box
    g = grey709(rgb[y : y + s, x : x + s])
    return cv2.resize(g, (256, 256), interpolation=cv2.INTER_AREA)


def download(url: str, dest: Path) -> Path:
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": rs.USER_AGENT})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    dest.write_bytes(r.read())
                break
            except Exception:  # noqa: BLE001
                time.sleep(15 * 2**attempt)
        time.sleep(1.0)
    return dest


def auto(cat: str, n: int) -> None:
    cfg = load_config()
    snap = json.loads((rs.REFSTIM / "snapshots" / f"image_{cat}_snapshot.json").read_text())
    order = rs.ordered(snap)[:n]
    meta = rs.page_meta([e["title"] for e in order])
    d = SCR / cat
    d.mkdir(parents=True, exist_ok=True)
    allowed = cfg["controls"]["refclips"]["image_licences"]
    seen_sha1, rows, sheet = set(), [], []
    for e in order:
        m = meta.get(e["title"], {})
        lic, tpl = rs.licence_of(m.get("templates", []), m.get("license_short"))
        row = {
            "title": e["title"],
            "sha256_title": rs.title_key(e["title"]),
            "pageid": e["pageid"],
            "revid": e["revid"],
            "licence": lic,
            "licence_template": tpl,
            "url": m.get("url"),
            "descriptionurl": m.get("descriptionurl"),
            "artist": m.get("artist", ""),
            "credit": m.get("credit", ""),
            "auto": "",
        }
        if tpl == rs.PERSONALITY:
            row["auto"] = "personality_rights"
        elif not rs.admissible(lic, allowed):
            row["auto"] = "licence"
        elif (m.get("mime") or "") not in ("image/jpeg", "image/png", "image/tiff", "image/webp"):
            row["auto"] = "not_photo"
        elif min(m.get("width") or 0, m.get("height") or 0) < MIN_SIDE:
            row["auto"] = "too_small"
        elif m.get("commons_sha1") in seen_sha1:
            row["auto"] = "duplicate"
        else:
            seen_sha1.add(m.get("commons_sha1"))
            ext = Path(m["url"]).suffix.lower()
            src = download(m["url"], d / f"{row['sha256_title'][:16]}{ext}")
            row["source_sha256"] = hashlib.sha256(src.read_bytes()).hexdigest()
            bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
            if bgr is None:
                row["auto"] = "not_photo"
            else:
                rgb = bgr[..., ::-1]
                gfull = grey709(rgb)
                scale = 1600 / max(gfull.shape) if max(gfull.shape) > 1600 else 1.0
                gs = cv2.resize(gfull, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                box = crop_box(gs, cat, cfg)
                if box is None:
                    row["auto"] = "no_face_detected"
                else:
                    box = tuple(int(round(v / scale)) for v in box)
                    p = processed(rgb, box)
                    fd = faces(p, cfg)
                    row["crop_box"] = box
                    if cat == "face":
                        if not len(fd):
                            row["auto"] = "no_face_detected"
                        elif max(b[3] for b in fd) < FACE_FRAC * 256:
                            row["auto"] = "too_small"  # face height < 40% of the crop
                    elif len(fd):
                        row["auto"] = "face_detected"
                    if not row["auto"]:
                        cv2.imwrite(str(d / f"proc_{row['sha256_title'][:16]}.png"), p)
                        sheet.append(row)
        rows.append(row)
    (d / "auto.json").write_text(json.dumps(rows, indent=1))
    # contact sheets of 12 for the visual check (processed greyscale crop + colour crop)
    for s in range(0, len(sheet), 12):
        tiles = []
        for j, row in enumerate(sheet[s : s + 12]):
            src = next(d.glob(f"{row['sha256_title'][:16]}.*"))
            bgr = cv2.imread(str(src))
            x, y, side = row["crop_box"]
            col = cv2.resize(bgr[y : y + side, x : x + side], (256, 256), interpolation=cv2.INTER_AREA)
            p = cv2.cvtColor(
                cv2.imread(str(d / f"proc_{row['sha256_title'][:16]}.png"), 0), cv2.COLOR_GRAY2BGR
            )
            t = np.hstack([col, p])
            cv2.putText(t, str(s + j), (6, 28), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            tiles.append(t)
        while len(tiles) % 3:
            tiles.append(np.zeros_like(tiles[0]))
        grid = np.vstack([np.hstack(tiles[k : k + 3]) for k in range(0, len(tiles), 3)])
        cv2.imwrite(str(d / f"sheet_{s // 12:02d}.jpg"), cv2.resize(grid, None, fx=0.6, fy=0.6))
    (d / "sheet_index.json").write_text(json.dumps([r["title"] for r in sheet], indent=1))
    n_auto = sum(1 for r in rows if not r["auto"])
    print(cat, "inspected", len(rows), "auto-pass", n_auto, "sheets", (len(sheet) + 11) // 12)


def final(cat: str) -> None:
    cfg = load_config()
    need = cfg["controls"]["refclips"]["loc_per_category"]
    d = SCR / cat
    rows = json.loads((d / "auto.json").read_text())
    visual = json.loads((d / f"visual_{cat}.json").read_text())
    log, manifest = [], []
    for r in rows:
        reason = r["auto"] or visual.get(r["title"])
        if reason is None:
            raise SystemExit(f"no visual decision for {r['title']!r}: review it before finalising")
        dec = "reject" if reason else "pass"
        log.append(
            {"title": r["title"], "sha256_title": r["sha256_title"], "decision": dec, "reason": reason}
        )
        if dec == "pass":
            k = len(manifest)
            manifest.append(
                {
                    "file": f"{cat}_{k:02d}{Path(r['url']).suffix.lower()}",
                    "category": cat,
                    "url": r["descriptionurl"],
                    "download_url": r["url"],
                    "pageid": r["pageid"],
                    "revid": r["revid"],
                    "licence": r["licence"],
                    "licence_template": r["licence_template"],
                    "attribution": rs.attribution(r["artist"], r["credit"]),
                    "sha256": r["source_sha256"],
                    "crop_box": list(r["crop_box"]),
                    "title": r["title"],
                }
            )
            if len(manifest) == need:
                break
    snap = json.loads((rs.REFSTIM / "snapshots" / f"image_{cat}_snapshot.json").read_text())
    rs.check_log(log, snap, cfg, need)
    rs.check_manifest(manifest, cfg, need)
    rs.write_json(rs.REFSTIM / f"image_{cat}_reject_log.json", log)
    rs.write_json(rs.REFSTIM / f"image_{cat}_manifest.json", manifest)
    print(cat, "logged", len(log), "passes", len(manifest))


if __name__ == "__main__":
    {"auto": lambda: auto(sys.argv[2], int(sys.argv[3])), "final": lambda: final(sys.argv[2])}[sys.argv[1]]()
