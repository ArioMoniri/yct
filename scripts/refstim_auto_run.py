"""D-075 runner (yct pod CPU only): fetch the pinned model artifacts, then run the frozen automatic image
filters over the frozen D-074 snapshots and write the append-only logs, the manifests and LICENSES.md.

  artifacts MODEL_DIR          download the pinned artifacts; print their sha256 (refclips_auto_artifacts)
  run MODEL_DIR SCRATCH        evaluate face, body, place in loc_categories order (resumes from the logs:
                               a logged candidate is never re-evaluated)
  finalise SCRATCH             write data/refstim/image_<cat>_manifest.json + docs/stimuli/LICENSES.md
Downloads stay out of the repo (SCRATCH, then S3 under controls.refclips.s3_root/sources/images/)."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from importlib import metadata
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import refstim as rs  # noqa: E402
from yct.curate import refstim_auto as ra  # noqa: E402


def _dl(url: str, dest: Path) -> Path:
    """Owner-approved UA, >= 1 s per host, Retry-After, backoff; a 429 beyond the limit is a STOP."""
    try:
        dest.write_bytes(rs.http_get(url))
    except rs.CurationError as exc:
        raise ra.StopError(f"download failed: {url}: {exc}") from exc
    return dest


def artifact_paths(model_dir: Path) -> dict[str, Path]:
    import cv2

    return {"yunet_sha256": model_dir / "face_detection_yunet_2023mar.onnx",
            "frcnn_sha256": model_dir / "fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth",
            "clip_sha256": model_dir / "open_clip_pytorch_model.bin",
            "tessdata_eng_sha256": Path("/usr/share/tesseract-ocr/5/tessdata/eng.traineddata"),
            "haar_face_sha256": Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml",
            "haar_eye_sha256": Path(cv2.data.haarcascades) / "haarcascade_eye.xml"}


def artifacts(model_dir: Path) -> None:
    a = load_config()["controls"]["refclips_auto"]
    model_dir.mkdir(parents=True, exist_ok=True)
    fd, cl = a["face_detector"], a["clip"]
    p = artifact_paths(model_dir)
    srcs = {"yunet_sha256": f"https://media.githubusercontent.com/media/{fd['repo']}/{fd['revision']}/{fd['file']}",
            "frcnn_sha256": a["person_detector"]["url"],
            "clip_sha256": f"https://huggingface.co/{cl['hf_repo']}/resolve/{cl['revision']}/{cl['file']}"}
    for k, url in srcs.items():
        if not p[k].exists():
            _dl(url, p[k])
    print(json.dumps({k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in p.items()}, indent=1))


class RealDetectors:
    def __init__(self, cfg: dict, model_dir: Path):
        import cv2
        import open_clip
        import torch
        import torchvision

        a = cfg["controls"]["refclips_auto"]
        torch.manual_seed(a["determinism"]["torch_seed"])
        torch.set_num_threads(a["determinism"]["threads"])
        cv2.setNumThreads(a["determinism"]["threads"])
        self.cv2, self.torch, self.cfg, self.a = cv2, torch, cfg, a
        p = artifact_paths(model_dir)
        self.yunet_path = str(p["yunet_sha256"])
        m = torchvision.models.detection.fasterrcnn_resnet50_fpn_v2(weights=None, weights_backbone=None,
                                                                    num_classes=91)
        m.load_state_dict(torch.load(p["frcnn_sha256"], map_location="cpu", weights_only=True))
        self.frcnn = m.eval()
        self.clip, _, self.prep = open_clip.create_model_and_transforms(a["clip"]["model"],
                                                                        pretrained=str(p["clip_sha256"]))
        self.clip.eval()
        self.tok = open_clip.get_tokenizer(a["clip"]["model"])
        self.face_cc = cv2.CascadeClassifier(str(p["haar_face_sha256"]))
        self.eye_cc = cv2.CascadeClassifier(str(p["haar_eye_sha256"]))
        if self.face_cc.empty() or self.eye_cc.empty():
            raise ra.StopError("Haar cascade failed to load")

    def yunet(self, bgr640, score_threshold):
        fd = self.a["face_detector"]
        h, w = bgr640.shape[:2]
        det = self.cv2.FaceDetectorYN.create(self.yunet_path, "", (w, h), score_threshold,
                                             fd["nms_threshold"], fd["top_k"])
        _, faces = det.detect(bgr640)
        out = []
        for r in ([] if faces is None else faces):
            out.append({"box": [float(t) for t in r[:4]], "lm": [float(t) for t in r[4:14]],
                        "score": float(r[14])})
        return out

    def persons(self, rgb):
        lim = self.a["person_detector"]["input_long_side"]
        img, s = (ra.resize_long(rgb, lim) if max(rgb.shape[:2]) > lim else (rgb, 1.0))
        t = self.torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1).float() / 255.0
        with self.torch.no_grad():
            o = self.frcnn([t])[0]
        out = []
        for b, sc, lab in zip(o["boxes"].tolist(), o["scores"].tolist(), o["labels"].tolist(), strict=True):
            if lab == self.a["person_detector"]["person_class"]:
                x1, y1, x2, y2 = (v / s for v in b)
                out.append({"box": [x1, y1, x2 - x1, y2 - y1], "score": float(sc)})
        return out

    def clip_probs(self, rgb, prompts):
        from PIL import Image

        with self.torch.no_grad():
            im = self.prep(Image.fromarray(rgb)).unsqueeze(0)
            f = self.clip.encode_image(im)
            t = self.clip.encode_text(self.tok(prompts))
            f, t = f / f.norm(dim=-1, keepdim=True), t / t.norm(dim=-1, keepdim=True)
            logits = self.clip.logit_scale.exp() * f @ t.T
            return logits.softmax(dim=-1)[0].tolist()

    def ocr_boxes(self, rgb):
        import pytesseract
        from PIL import Image

        o = self.a["ocr"]
        d = pytesseract.image_to_data(Image.fromarray(rgb), config=f"--psm {o['psm']} --oem {o['oem']}",
                                      output_type=pytesseract.Output.DICT)
        return [{"box": [d["left"][i], d["top"][i], d["width"][i], d["height"][i]],
                 "conf": float(d["conf"][i]), "text": d["text"][i]} for i in range(len(d["text"]))]

    def haar_faces(self, grey):
        f = self.cfg["confounds"]["face"]
        m = int(round(f["min_size_frac"] * min(grey.shape)))
        r = self.face_cc.detectMultiScale(grey, scaleFactor=f["scale_factor"],
                                          minNeighbors=f["min_neighbors"], minSize=(m, m))
        return np.array(r).reshape(-1, 4)

    def haar_eyes(self, grey):
        e = self.a["eye_detector"]
        return np.array(self.eye_cc.detectMultiScale(grey, scaleFactor=e["scale_factor"],
                                                     minNeighbors=e["min_neighbors"])).reshape(-1, 4)


def page_meta_c4(titles: list[str]) -> dict[str, dict]:
    """rs.page_meta + the description and category text needed by C4 (read only through the metadata rule)."""
    out = rs.page_meta(titles)
    for i in range(0, len(titles), 50):
        d = rs._get({"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "imageinfo",
                     "iiprop": "extmetadata",
                     "iiextmetadatafilter": "ImageDescription|Categories|ObjectName"})
        for p in d.get("query", {}).get("pages", []):
            em = ((p.get("imageinfo") or [{}])[0]).get("extmetadata", {})
            out.setdefault(p["title"], {}).update(
                description=" ".join(em.get(k, {}).get("value", "")
                                     for k in ("ImageDescription", "ObjectName")),
                categories=em.get("Categories", {}).get("value", "").replace("|", " "))
    return out


def installed() -> dict[str, str]:
    return {k: metadata.version(k) for k in load_config()["controls"]["refclips_auto"]["env"]["packages"]}


def run(model_dir: Path, scratch: Path) -> None:
    import cv2

    cfg = load_config()
    a, rc = cfg["controls"]["refclips_auto"], cfg["controls"]["refclips"]
    ra.check_frozen(cfg)
    ra.check_env(cfg, installed())
    p = artifact_paths(model_dir)
    for k in a["image_artifacts"]:
        ra.check_artifact(p[k], cfg["controls"]["refclips_auto_artifacts"][k])
    snapdir = rs.REFSTIM / "snapshots"
    want_snap = cfg["controls"]["refclips_artifacts"]["image_snapshot_sha256"]
    if rs.image_snapshot_sha_d074(snapdir, cfg) != want_snap:
        raise ra.StopError("D-074 image snapshots differ from the frozen sha")
    det = RealDetectors(cfg, model_dir)
    keys, longest = ra.manifest_key_hashes()
    st = ra.State()
    need = rc["loc_per_category"]
    for cat in rc["loc_categories"]:
        log_path = ROOT / a["logs"]["image"].replace("<cat>", cat)
        done = [json.loads(x) for x in log_path.read_text().splitlines()] if log_path.exists() else []
        for r in done:
            if r["decision"] == "pass":
                st.pass_sha1.add(r["sha1"])
                st.pass_dhash.append(int(r["values"]["dhash"], 16))
        n_pass = sum(r["decision"] == "pass" for r in done)
        snap = json.loads((snapdir / rs.snapshot_name_d074(cat, cfg)).read_text())
        rs.check_header_d074(snap, cfg)
        order = rs.ordered(snap)
        d = scratch / cat
        d.mkdir(parents=True, exist_ok=True)
        i = len(done)
        if done and [r["title"] for r in done] != [e["title"] for e in order[:len(done)]]:
            raise ra.StopError(f"{log_path.name}: log is not a prefix of the sha256(title) order")
        while n_pass < need and i < len(order):
            batch = order[i:i + 50]
            meta = page_meta_c4([e["title"] for e in batch])
            for e in batch:
                if n_pass >= need:
                    break
                m = meta.get(e["title"], {})
                lic, tpl = rs.licence_of(m.get("templates", []), m.get("license_short"))
                key = rs.title_key(e["title"])

                def load(m=m, key=key, d=d):
                    if not m.get("url"):
                        raise ra.StopError(f"no download url for {key}")
                    src = d / f"{key[:16]}{Path(m['url']).suffix.lower()}"
                    if not src.exists():
                        _dl(m["url"], src)
                        time.sleep(1.0)
                    bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
                    if bgr is None:
                        raise ra.StopError(f"decode failed for BITMAP file {key}")
                    return np.ascontiguousarray(bgr[..., ::-1])

                adm = rs.admissible(lic, rc["image_licences"])
                c = ra.Candidate(e["title"], key, e, m, lic, tpl, adm, load)
                row = ra.evaluate_image(cat, c, det, cfg, st, keys, longest)
                row.update(sha1=e.get("sha1"), pageid=e["pageid"], revid=e["revid"], licence=lic,
                           licence_template=tpl, url=m.get("url"), descriptionurl=m.get("descriptionurl"),
                           artist=m.get("artist", ""), credit=m.get("credit", ""))
                if row["decision"] == "pass":
                    src = next(d.glob(f"{key[:16]}.*"))
                    row["source_sha256"] = hashlib.sha256(src.read_bytes()).hexdigest()
                    n_pass += 1
                ra.append_jsonl(log_path, row)
                i += 1
            print(cat, "evaluated", i, "passes", n_pass, flush=True)
        if n_pass < need:
            raise ra.StopError(f"{cat}: {n_pass} passes < {need} in the full snapshot: STOP to the owner")


def finalise(scratch: Path) -> None:
    cfg = load_config()
    a, rc = cfg["controls"]["refclips_auto"], cfg["controls"]["refclips"]
    need, sections = rc["loc_per_category"], {}
    for cat in rc["loc_categories"]:
        lp = ROOT / a["logs"]["image"].replace("<cat>", cat)
        rows = [json.loads(x) for x in lp.read_text().splitlines()]
        snap = json.loads((rs.REFSTIM / "snapshots" / rs.snapshot_name_d074(cat, cfg)).read_text())
        log = [{"title": r["title"], "sha256_title": r["sha256_title"], "decision": r["decision"],
                "reason": r["reason"] or ""} for r in rows]
        rs.check_log(log, snap, cfg, need)
        man = []
        for r in rows:
            if r["decision"] != "pass":
                continue
            fname = f"{cat}_{len(man):02d}{Path(r['url']).suffix.lower()}"
            man.append({"file": fname, "category": cat, "url": r["descriptionurl"], "download_url": r["url"],
                        "pageid": r["pageid"], "revid": r["revid"], "licence": r["licence"],
                        "licence_template": r["licence_template"],
                        "attribution": rs.attribution(r["artist"], r["credit"]), "sha256": r["source_sha256"],
                        "crop_box": r["crop_box"], "title": r["title"],
                        "s3_key": f"sources/images/{cat}/{fname}"})
        rs.check_manifest(man, cfg, need)
        rs.write_json(rs.REFSTIM / f"image_{cat}_manifest.json", man)
        sections[f"Localiser images: {cat} (D-074 source, D-075 filters)"] = man
    text = rs.licenses_md(sections)
    for man in sections.values():
        rs.check_licenses_md(text, man)
    rs.LICENSES_MD.parent.mkdir(parents=True, exist_ok=True)
    rs.LICENSES_MD.write_text(text)
    h = hashlib.sha256()
    for cat in rc["loc_categories"]:
        h.update((rs.REFSTIM / f"image_{cat}_manifest.json").read_bytes())
    print("image_manifest_sha256", h.hexdigest())


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "artifacts":
        artifacts(Path(sys.argv[2]))
    elif cmd == "run":
        run(Path(sys.argv[2]), Path(sys.argv[3]))
    elif cmd == "finalise":
        finalise(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
