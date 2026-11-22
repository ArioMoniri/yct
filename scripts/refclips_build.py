#!/usr/bin/env python3
"""Pod-side, CPU-only builder of the non-NAT p4b_ref/v1 reference clips (D-071 (a)-(d), T-REF58).

  python scripts/refclips_build.py OUT_DIR [--families F ...] [--sources DIR]

- Refuses unless controls.refclips_artifacts.image_manifest_sha256 is frozen and equals the sha256 of the
  committed data/refstim/image_{face,body,place}_manifest.json concatenated in loc_categories order.
- Source images: fetched from controls.refclips.s3_root + s3_key, sha256-verified against the manifest row,
  decoded as the T-LIC runner does (cv2 IMREAD_COLOR -> RGB); then yct.tribe_run.locimg (crop_box, BT.709,
  INTER_AREA 316 px, SHINE over all 60 jointly).
- NAT is never built here (T-NAT manifest). SPK / BURST / TALKFACE need a frozen speech corpus
  (controls.refclips_artifacts.speech_corpus_sha256); without it they are refused.
- Runs the frozen stimulus QC (refclips58.stimulus_qc, the real yct.confounds code). Any failure is a STOP
  to the council: STOP_NOTE.md + qc.json, exit 1, no manifest, no substitution.
- Writes refclips_partial_manifest.json (per-file sha256, toolchain, sources, builder blob shas). It never
  uploads: D-071 (d) requires the full clip-manifest sha to be frozen before any clip upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.tribe_run import locimg  # noqa: E402
from yct.tribe_run import refclips58 as R  # noqa: E402,N812

SPEECH = {"SPK", "BURST", "TALKFACE"}
DEFAULT = ["GREY_CTRL", "FLASH", "LOC", "LOC_SCR", "MOT", "MOT_STAT"]
TWINS = [("MOT", "MOT_STAT"), ("LOC", "LOC_SCR")]
IMG_KEY = "controls.refclips_artifacts.image_manifest_sha256"
SPEECH_KEY = "controls.refclips_artifacts.speech_corpus_sha256"


def _frozen(cfg: dict, key: str) -> bool:
    return any(f.get("key") == key for f in cfg.get("frozen", []))


def check_image_manifests(cfg: dict, root: Path = ROOT) -> dict[str, list[dict]]:
    if not _frozen(cfg, IMG_KEY):
        raise SystemExit(f"{IMG_KEY} is not frozen")
    cats = cfg["controls"]["refclips"]["loc_categories"]
    paths = [root / "data" / "refstim" / f"image_{c}_manifest.json" for c in cats]
    sha = hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()
    if sha != cfg["controls"]["refclips_artifacts"]["image_manifest_sha256"]:
        raise SystemExit(f"image manifest sha mismatch: {sha} != frozen value")
    return {c: json.loads(p.read_text()) for c, p in zip(cats, paths, strict=True)}


def select_families(cfg: dict, fams: list[str] | None) -> list[str]:
    allf = set(cfg["controls"]["refclips"]["families"])
    out = list(fams) if fams else list(DEFAULT)
    for f in out:
        if f not in allf:
            raise SystemExit(f"unknown family {f}")
        if f == "NAT":
            raise SystemExit("NAT clips come from the T-NAT manifest, never this builder")
        if f in SPEECH and not _frozen(cfg, SPEECH_KEY):
            raise SystemExit(f"{f}: needs a frozen speech corpus ({SPEECH_KEY})")
    for a, b in TWINS:
        if (a in out) != (b in out):
            raise SystemExit(f"{a} and its twin {b} must be built together")
    return out


def toolchain() -> dict[str, str]:
    v = subprocess.run(["ffmpeg", "-nostdin", "-version"], capture_output=True, text=True,
                       check=True).stdout.splitlines()
    x264 = subprocess.run(["dpkg-query", "-W", "-f", "${Package} ${Version}\n", "libx264-*"],
                          capture_output=True, text=True, check=False).stdout.strip()
    return {"ffmpeg": v[0], "ffmpeg_libs": " | ".join(x.strip() for x in v if x.strip().startswith("lib")),
            "libx264": x264 or "unknown"}


def verify_s3_sources(mans: dict[str, list[dict]], get) -> dict[str, str]:
    """D-085 (council, BUG-044): every manifest s3_key exists and its bytes hash to the manifest sha256.
    get(key) -> bytes | None. Returns {s3_key: sha256} for the clip manifest record."""
    out = {}
    for cat in sorted(mans):
        for row in mans[cat]:
            data = get(row["s3_key"])
            if data is None:
                raise SystemExit(f"BUG-044 read-back: {row['s3_key']} missing from S3")
            sha = hashlib.sha256(data).hexdigest()
            if sha != row["sha256"]:
                raise SystemExit(f"BUG-044 read-back: {row['s3_key']} sha256 {sha} != manifest "
                                 f"{row['sha256']}")
            out[row["s3_key"]] = sha
    return out


def build_all(clips: list, out: Path, cfg: dict, images=None, sources: dict | None = None,
              qc: str = "d071", yunet=None) -> int:
    """qc="d071": the original frozen D-071 (a) QC (build 1). qc="d085": the amended QC
    (yct.tribe_run.refclips_qc85), refused until controls.refclips_d085 is frozen; needs the T-LIC YuNet."""
    if qc == "d085":
        from yct.tribe_run import refclips_qc85

        refclips_qc85.require_frozen(cfg)
        if yunet is None:
            raise SystemExit("D-085 QC needs the frozen T-LIC YuNet detector")
    elif qc != "d071":
        raise SystemExit(f"unknown QC rule {qc}")
    out.mkdir(parents=True, exist_ok=True)
    recs, rows = {}, []
    for c in clips:
        recs[c.name] = R.build_clip(c, out, cfg, images=images)
        print(f"built {c.name}", flush=True)
    by = {c.name: c for c in clips}
    if qc == "d085":
        res = refclips_qc85.run_qc(clips, out, cfg, recs, yunet, lambda c: R.clip_frames(c, images))
        (out / "qc.json").write_text(json.dumps(res, indent=1, default=float))
        bad = [r["name"] for r in res["rows"] if not r["pass"]]
        if res["face_hit_family"] is not None and not res["face_hit_family"]["pass"]:
            bad.append("LOC family face_hit_frac")
        rule = "to the owner (D-085, amended D-071 (a); no second amendment, D-071 (h))"
    else:
        for c in clips:
            twin = (by[c.control], out / f"{c.control}.mp4") if c.family == "MOT" else None
            rows.append(R.stimulus_qc(c, out / f"{c.name}.mp4", cfg, twin=twin))
        (out / "qc.json").write_text(json.dumps(rows, indent=1, default=float))
        bad = [q["name"] for q in rows if not q["pass"]]
        rule = "to the council (D-071 (a), no substitution)"
    if bad:
        (out / "STOP_NOTE.md").write_text(
            f"# p4b_ref/v1 build: stimulus QC failed, STOP {rule}\n" + "".join(f"- {n}\n" for n in bad))
        print(f"STOP: QC failed for {bad}", flush=True)
        return 1
    fams = sorted({c.family for c in clips})
    doc_path = out / "refclips_partial_manifest.json"
    R.manifest(list(recs.values()), toolchain(), sources or {}, doc_path)
    doc = json.loads(doc_path.read_text())
    doc.update(partial=True, families_built=fams,
               families_missing=sorted(set(cfg["controls"]["refclips"]["families"]) - set(fams)),
               qc_sha256=hashlib.sha256((out / "qc.json").read_bytes()).hexdigest(),
               builder_blob_sha1={Path(p).name: R.git_blob_sha(Path(p)) for p in
                                  (R.__file__, locimg.__file__, __file__)})
    doc_path.write_text(json.dumps(doc, indent=1, sort_keys=True, default=float))
    return 0


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fetch_sources(mans: dict[str, list[dict]], cfg: dict, d: Path, local: list[Path] | None = None):
    """Loader of the sha-verified source images. BUG-044: the T-LIC finalise wrote s3_key into the frozen
    manifests but never uploaded. So: S3 copy at s3_key if present; else the pod T-LIC scratch file whose
    content sha256 equals the manifest sha256 (matched by content only), which is then uploaded to s3_key."""
    import shutil

    import cv2

    root = cfg["controls"]["refclips"]["s3_root"]
    d.mkdir(parents=True, exist_ok=True)
    index: dict[str, Path] | None = None

    def local_index() -> dict[str, Path]:
        nonlocal index
        if index is None:
            index = {}
            for base in local or []:
                for f in sorted(Path(base).rglob("*")):
                    if f.is_file():
                        index.setdefault(_sha_file(f), f)
        return index

    def load(row: dict) -> np.ndarray:
        p = d / hashlib.sha256(row["s3_key"].encode()).hexdigest()[:16]
        if not p.exists() or _sha_file(p) != row["sha256"]:
            try:
                subprocess.run(["aws", "s3", "cp", "--only-show-errors", root + row["s3_key"], str(p)],
                               check=True)
            except subprocess.CalledProcessError:
                pass
        if not p.exists() or _sha_file(p) != row["sha256"]:
            src = local_index().get(row["sha256"])
            if src is None:
                raise SystemExit(f"no source with the manifest sha256 for {row['title']!r}")
            shutil.copyfile(src, p)
            subprocess.run(["aws", "s3", "cp", "--only-show-errors", str(p), root + row["s3_key"]],
                           check=True)
        if _sha_file(p) != row["sha256"]:
            raise SystemExit(f"source sha256 mismatch for {row['title']!r}")
        bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if bgr is None:
            raise SystemExit(f"decode failed for {row['title']!r}")
        return np.ascontiguousarray(bgr[..., ::-1])
    return load


def contact_sheet(out: Path, clips: list, cfg: dict, png: Path) -> None:
    """One frame per LOC image: the intact image at each LOC event (onset + 0.5 s), decoded from the built
    mp4. Grid rows = clip, columns = event k; labels give category and image index."""
    import cv2

    loc = sorted((c for c in clips if c.family == "LOC"), key=lambda c: c.i)
    cell, pad = R.PATCH // 2, 18
    sheet = np.full((len(loc) * (cell + pad), 3 * (cell + 4)), 255, np.uint8)
    y0 = (R.H - R.PATCH) // 2
    x0 = (R.W - R.PATCH) // 2
    for r, c in enumerate(loc):
        for e in c.events:
            t = e["onset"] + 0.5
            mp4 = str(out / f"{c.name}.mp4")
            raw = subprocess.run([*R.FF, "-ss", f"{t:.3f}", "-i", mp4, "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True,
                                 check=True).stdout
            f = np.frombuffer(raw, np.uint8)[:R.W * R.H].reshape(R.H, R.W)
            p = cv2.resize(f[y0:y0 + R.PATCH, x0:x0 + R.PATCH], (cell, cell), interpolation=cv2.INTER_AREA)
            yy, xx = r * (cell + pad) + pad, e["k"] * (cell + 4)
            sheet[yy:yy + cell, xx:xx + cell] = p
            cv2.putText(sheet, f"{c.name} k{e['k']} {e['category']}_{e['image']:02d}", (xx + 2, yy - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, 0, 1)
    cv2.imwrite(str(png), sheet)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--families", nargs="*")
    ap.add_argument("--sources", type=Path, default=Path("/work/yct/refclips_sources"))
    ap.add_argument("--local", type=Path, nargs="*", default=[Path("/work/yct/refstim_auto_scratch")],
                    help="T-LIC scratch dirs searched by content sha256 (BUG-044)")
    ap.add_argument("--qc", choices=["d071", "d085"], default="d071",
                    help="d085 = the amended QC, refused until controls.refclips_d085 is frozen")
    ap.add_argument("--yunet-onnx", type=Path,
                    default=Path("/work/yct/refstim_models/face_detection_yunet_2023mar.onnx"))
    a = ap.parse_args()
    cfg = load_config()
    fams = select_families(cfg, a.families)
    clips = [c for c in R.plan(cfg) if c.family in fams]
    images, sources = None, {}
    if "LOC" in fams:
        mans = check_image_manifests(cfg)
        base = fetch_sources(mans, cfg, a.sources, local=a.local)
        over: dict[str, int] = {}

        def load(row: dict) -> np.ndarray:
            rgb = base(row)
            if locimg.overrun(rgb, row["crop_box"]):
                over[row["file"]] = locimg.overrun(rgb, row["crop_box"])
            return rgb
        images = locimg.loc_images(mans, load, cfg)
        sources = {"image_manifest_sha256": cfg["controls"]["refclips_artifacts"]["image_manifest_sha256"],
                   "crop_box_edge_overrun_px": over}
    yunet = None
    if a.qc == "d085":
        from yct.tribe_run import refclips_qc85

        refclips_qc85.require_frozen(cfg)
        yunet = refclips_qc85.t_lic_yunet(cfg, a.yunet_onnx)
    rc = build_all(clips, a.out, cfg, images=images, sources=sources, qc=a.qc, yunet=yunet)
    if rc == 0 and "LOC" in fams:
        contact_sheet(a.out, clips, cfg, a.out / "loc_contact_sheet.png")
    return rc


if __name__ == "__main__":
    sys.exit(main())
