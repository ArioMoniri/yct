"""D-075 runner (yct pod CPU only): fetch the pinned model artifacts, then run the frozen automatic image
filters over the frozen D-074/D-078 snapshots and write the append-only D-079 v2 logs, the manifests
and LICENSES.md.

  artifacts MODEL_DIR          download the pinned artifacts; print their sha256 (refclips_auto_artifacts)
  run MODEL_DIR SCRATCH        evaluate face, body, place in loc_categories order (resumes from the v2 logs:
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
    """The library reader (D-079 re-check: one-retry rule for a moving revision, C4 revision check)."""
    return rs.page_meta_c4(titles)


def installed() -> dict[str, str]:
    return {k: metadata.version(k) for k in load_config()["controls"]["refclips_auto"]["env"]["packages"]}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def _head() -> str:
    import subprocess

    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


def _git_changed(a: str, b: str, paths) -> list[str]:
    """Files under `paths` (git pathspecs) that differ between commits a and b."""
    import subprocess

    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", a, b, "--", *paths], check=True,
                         capture_output=True, text=True).stdout
    return [x for x in out.splitlines() if x.strip()]


def parse_targets(argv: list[str], cats) -> dict[str, int]:
    """D-087 draft continuation: --target <category>=<n passes> (repeatable)."""
    out: dict[str, int] = {}
    it = iter(argv)
    for a in it:
        if a != "--target":
            raise SystemExit(f"unknown argument {a!r}")
        c, _, n = next(it, "").partition("=")
        if c not in cats or not n.isdigit():
            raise SystemExit(f"--target needs <category>=<n> with category in {list(cats)}")
        out[c] = int(n)
    return out


def parse_run_args(argv: list[str], cats) -> tuple[dict[str, int], str]:
    """`run` options: [--purpose loc|talkface] then --target <category>=<n> ... (D-087 / D-085 part 2)."""
    purpose, rest = "loc", list(argv)
    if rest[:1] == ["--purpose"]:
        if len(rest) < 2 or rest[1] not in ("loc", "talkface"):
            raise SystemExit("--purpose must be loc or talkface")
        purpose, rest = rest[1], rest[2:]
    return parse_targets(rest, cats), purpose


def assert_byte_prefix(prefix_sha256: str, prefix_len: int, log: Path) -> None:
    """Continuation append-only rule: the log's first prefix_len bytes must hash to the pre-run sha."""
    import hashlib

    head = Path(log).read_bytes()[:prefix_len]
    if len(head) != prefix_len or hashlib.sha256(head).hexdigest() != prefix_sha256:
        raise SystemExit(f"{Path(log).name}: existing rows changed during the continuation: "
                         "STOP to the owner")


TALKFACE_SKIPS = Path("data/refstim/talkface_skips.jsonl")   # committed s3fd/Wav2Lip skip log (watchdog)


def _frozen_key(cfg: dict, key: str) -> bool:
    return any(key == f.get("key") or key.startswith(f.get("key", "") + ".") for f in cfg.get("frozen", []))


def effective_need(cat: str, targets: dict[str, int], need: int, cfg: dict, purpose: str = "loc",
                   skips: list[dict] | None = None) -> int:
    """Passes to reach in `cat`: the frozen loc_per_category, or a continuation target past it (the same v4
    log, same order, same frozen rules; only a larger stop count). purpose "loc": D-087 (frozen) and its cap.
    purpose "talkface": D-085 part 2 `talkface.face_continuation` (frozen), face only, its own budget:
    first_target + up to max_skips, within max_extra_passes; beyond that a STOP to the owner."""
    t = targets.get(cat, need)
    if t < need:
        raise SystemExit(f"{cat}: target {t} < loc_per_category {need}")
    if t == need:
        return need
    if purpose == "talkface":
        if cat != "face":
            raise SystemExit(f"{cat}: the TALKFACE continuation is face only")
        if not _frozen_key(cfg, "controls.refclips_d085.talkface"):
            raise SystemExit("controls.refclips_d085.talkface is not frozen: no TALKFACE face continuation")
        fc = cfg["controls"]["refclips_d085"]["talkface"]["face_continuation"]
        top = min(fc["first_target"] + fc["max_skips"], need + fc["max_extra_passes"])
        if t > top:
            raise SystemExit(f"face: target {t} > {top} (first_target + max_skips): STOP to the owner")
        allowed = set(cfg["controls"]["refclips_d085"]["talkface"]["face_rule"]["skip_on"])
        sk = list(skips or [])
        extra = t - fc["first_target"]
        if extra > 0 and (len(sk) != extra or any(x.get("reason") not in allowed or not x.get("title")
                                                  for x in sk)):
            raise SystemExit(f"face: target {t} needs {extra} logged skip(s) with a skip_on reason: STOP")
        if sk:
            print("talkface skips:", json.dumps(sk), flush=True)
        return t
    if not _frozen_key(cfg, "controls.refclips_d087"):
        raise SystemExit("controls.refclips_d087 is not frozen: no continuation past the frozen count")
    cap = cfg["controls"]["refclips_d087"]["continuation"]["max_extra_per_category"]
    if t - need > cap:
        raise SystemExit(f"{cat}: {t - need} extra passes > the D-087 cap {cap}: STOP to the owner")
    return t


def run(model_dir: Path, scratch: Path, targets: dict[str, int] | None = None, purpose: str = "loc") -> None:
    """D-079: evaluate face, body, place (category_order) into the v2 logs only, from rank 1, resuming from
    the v2 logs. The superseded v1 logs are read only by the determinism audit (audit_v2)."""
    import cv2

    cfg = rs.effective_cfg(load_config())     # D-080: v3 routing when controls.refclips_d080 is present
    a, rc = cfg["controls"]["refclips_auto"], cfg["controls"]["refclips"]
    d9 = cfg["controls"]["refclips_d079"]
    ra.check_frozen(cfg)
    ra.check_frozen_d079(cfg)
    if cfg["controls"].get("refclips_d080"):
        ra.check_frozen_d080(cfg)
    if cfg["controls"].get("refclips_d081"):   # D-081: frozen keys + recomputed post-download re-audit
        ra.check_frozen_d081(cfg, rs.post_download_reaudit_cfg(load_config(), ROOT))
    rs.check_d079_routing(cfg)
    ra.check_env(cfg, installed())
    p = artifact_paths(model_dir)
    for k in a["image_artifacts"]:
        ra.check_artifact(p[k], cfg["controls"]["refclips_auto_artifacts"][k])
    snapdir = rs.REFSTIM / "snapshots"
    want_snap = cfg["controls"]["refclips_artifacts"]["image_snapshot_sha256"]
    if rs.image_snapshot_sha_d074(snapdir, cfg) != want_snap:
        raise ra.StopError("D-074 image snapshots differ from the frozen sha")
    d078 = rs.d078_categories(cfg)
    ra.check_frozen_d078(cfg)
    for cat in d078:
        if rs.file_sha(snapdir / rs.snapshot_name_d078(cat, cfg)) != \
                cfg["controls"]["refclips_d078_artifacts"]["body_snapshot_sha256"]:
            raise ra.StopError("D-078 snapshot differs from the frozen sha")
    flips = rs.load_flips(ROOT / d9["audit"]["flip_file"],
                          cfg["controls"]["refclips_d079_artifacts"]["flip_sha256"], d9["flip_logs"])
    exempt, c1 = tuple(d9["audit"]["exempt_reasons"]), tuple(d9["audit"]["c1_reasons"])
    run_commit = _head()
    dry = None
    if cfg["controls"].get("refclips_d080"):    # D-080 launch rule, enforced before rank 1
        dry = ra.check_dry_audit(cfg, ROOT, run_commit, _git_changed)
    det = RealDetectors(cfg, model_dir)
    keys, longest = ra.manifest_key_hashes()
    st = ra.State()
    targets = targets or {}
    ran: list[str] = []
    for cat in d9["category_order"]:
        sk_path = ROOT / TALKFACE_SKIPS
        skips = _read_jsonl(sk_path) if purpose == "talkface" and sk_path.exists() else []
        need = effective_need(cat, targets, rc["loc_per_category"], cfg, purpose, skips)
        log_path = ROOT / rs.image_log_v2(cat, cfg)
        pre = log_path.read_bytes() if log_path.exists() else b""   # append-only: checked after the category
        priors = [(Path(q).name, {r["title"]: r for r in _read_jsonl(ROOT / q)})
                  for q in d9["superseded_logs"][cat]]
        dry_revids = ((dry["categories"].get(cat) or {}).get("read_revids") or {}) if dry else None
        done = ra.preload_v2(st, cat, cfg, ROOT, ran=ran)     # C3 state: v2 logs only, face -> body -> place
        n_pass = sum(r["decision"] == "pass" for r in done)
        snap = json.loads((snapdir / rs.snapshot_name_eff(cat, cfg)).read_text())
        if cat in d078:
            rs.check_header_d078(snap, cfg, snapdir)
        else:
            rs.check_header_d074(snap, cfg)
        order = rs.ordered(snap)
        d = scratch / cat
        d.mkdir(parents=True, exist_ok=True)
        i = len(done)
        if done and [r["title"] for r in done] != [e["title"] for e in order[:len(done)]]:
            raise ra.StopError(f"{log_path.name}: log is not a prefix of the sha256(title) order")
        while n_pass < need and i < len(order):
            batch = order[i:i + 50]
            meta = rs.page_meta_c4([e["title"] for e in batch])   # revid moving: one batch retry, then STOP
            for e in batch:
                if n_pass >= need:
                    break
                m = meta[e["title"]]   # BUG-036: never a silent empty-licence default
                lic, tpl = rs.licence_of(m["templates"], m.get("license_short"))
                key = rs.title_key(e["title"])

                def load(m=m, key=key, d=d, e=e):
                    if not m.get("url"):
                        raise ra.StopError(f"no download url for {e['title']!r} ({key})")
                    src = d / f"{key[:16]}{Path(m['url']).suffix.lower()}"

                    def dl_polite(url, dest):
                        _dl(url, dest)
                        time.sleep(1.0)
                    # sign-off referee B1: bytes differing from the agreed sha1 = download defect:
                    # one re-download, then STOP naming the title (never an identity_changed reject)
                    ra.fetch_verified(src, m["url"], e["sha1"], e["title"], dl_polite)
                    bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
                    if bgr is None:
                        raise ra.StopError(f"decode failed for BITMAP file {e['title']!r} ({key})")
                    return np.ascontiguousarray(bgr[..., ::-1])

                adm = rs.admissible(lic, rc["image_licences"])
                c = ra.Candidate(e["title"], key, e, m, lic, tpl, adm, load)
                if ra.identity_ok(e.get("sha1"), m.get("commons_sha1"), title=e["title"]):
                    row = ra.evaluate_image(cat, c, det, cfg, st, keys, longest)
                else:                  # D-079 re-check B1: re-uploaded since the snapshot -> D1 reject
                    row = ra.identity_reject_row(cat, c)
                row.update(sha1=e.get("sha1"), commons_sha1=m.get("commons_sha1"), pageid=e["pageid"],
                           **ra.revid_fields(e, m), licence=lic, licence_template=tpl,
                           templates=m["templates"], templates_sha256=ra.templates_digest(m["templates"]),
                           url=m.get("url"), descriptionurl=m.get("descriptionurl"),
                           artist=m.get("artist", ""), credit=m.get("credit", ""), source=e.get("source"),
                           log_version=d9["log_version"], run_commit=run_commit)
                if row["decision"] == "pass":
                    src = next(d.glob(f"{key[:16]}.*"))
                    row["source_sha256"] = hashlib.sha256(src.read_bytes()).hexdigest()
                    n_pass += 1
                try:
                    notes = ra.audit_v2(row, priors, flips, exempt, c1,
                                        c1_equiv=d9["audit"].get("c1_equivalence", False),
                                        dry_revids=dry_revids)
                except ra.StopError as exc:    # BUG-038: the evaluated row (templates, rule) is kept
                    ra.write_stop_evidence(log_path, row, exc)
                    raise
                eq = {n: b for n, k, b in notes if k == "c1_equivalent"}
                if eq:                         # D-080: both C1 reasons are logged
                    row["audit_c1_equivalent"] = eq
                drift = ra.revid_drift_rows(row, priors, notes, dry_revids or {})
                if drift:                      # D-080 audit_revid_drift: both revids logged, disclosed
                    row["audit_revid_drift"] = drift
                ra.append_jsonl(log_path, row)
                i += 1
            print(cat, "evaluated", i, "passes", n_pass, flush=True)
        if n_pass < need:
            raise ra.StopError(f"{cat}: {n_pass} passes < {need} in the full snapshot: STOP to the owner")
        if log_path.exists():
            assert_byte_prefix(hashlib.sha256(pre).hexdigest(), len(pre), log_path)
        ran.append(cat)


def source_counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Per snapshot source: rows evaluated and passes (D-079 disclosure; the realised source mix)."""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        c = out.setdefault(str(r.get("source")), {"evaluated": 0, "passes": 0})
        c["evaluated"] += 1
        c["passes"] += r["decision"] == "pass"
    return out


def finalise(scratch: Path) -> None:
    cfg = rs.effective_cfg(load_config())     # D-080: v3 routing when controls.refclips_d080 is present
    rc = cfg["controls"]["refclips"]
    ra.check_frozen_d079(cfg)
    if cfg["controls"].get("refclips_d080"):
        ra.check_frozen_d080(cfg)
    if cfg["controls"].get("refclips_d081"):
        ra.check_frozen_d081(cfg, rs.post_download_reaudit_cfg(load_config(), ROOT))
    ver = cfg["controls"]["refclips_d079"]["log_version"]
    need, sections, counts, ident, drift = rc["loc_per_category"], {}, {}, {}, {}
    for cat in cfg["controls"]["refclips_d079"]["category_order"]:
        lp = ROOT / rs.image_log_v2(cat, cfg)
        rows = _read_jsonl(lp)
        if any(r.get("log_version") != ver for r in rows):
            raise ra.StopError(f"{lp.name}: a row without log_version {ver}")
        snap = json.loads((rs.REFSTIM / "snapshots" / rs.snapshot_name_eff(cat, cfg)).read_text())
        log = [{"title": r["title"], "sha256_title": r["sha256_title"], "decision": r["decision"],
                "reason": r["reason"] or ""} for r in rows]
        rs.check_log(log, snap, cfg, need,
                     extra_reasons=cfg["controls"]["refclips_d079"]["extra_reject_reasons"])
        counts[cat] = source_counts(rows)
        ident[cat] = ra.identity_disclosure(rows)
        drift[cat] = ra.revid_drift_disclosure(rows)
        man = []
        for r in rows:
            if r["decision"] != "pass":
                continue
            fname = f"{cat}_{len(man):02d}{Path(r['url']).suffix.lower()}"
            man.append({"file": fname, "category": cat, "url": r["descriptionurl"], "download_url": r["url"],
                        "pageid": r["pageid"], "revid": r["revid"], "snapshot_revid": r["snapshot_revid"],
                        "licence": r["licence"], "licence_template": r["licence_template"],
                        "attribution": rs.attribution(r["artist"], r["credit"]), "sha256": r["source_sha256"],
                        "crop_box": r["crop_box"], "title": r["title"], "source": r.get("source"),
                        "s3_key": f"sources/images/{cat}/{fname}"})
        rs.check_manifest(man, cfg, need)
        rs.write_json(rs.REFSTIM / f"image_{cat}_manifest.json", man)
        src = "D-078" if cat in rs.d078_categories(cfg) else "D-074"
        sections[f"Localiser images: {cat} ({src} source, D-075 filters, D-079 v2 logs)"] = man
    names = {"v2": ("image_source_counts_v2.json", "image_identity_changed_v2.json"),
             "v3": ("image_source_counts_v3.json", "image_identity_changed_v3.json"),
             "v4": ("image_source_counts_v4.json", "image_identity_changed_v4.json")}[ver]   # BUG-039
    rs.write_json(rs.REFSTIM / names[0], counts)
    rs.write_json(rs.REFSTIM / names[1], ident)   # D-079 §A disclosure
    if ver in ("v3", "v4"):   # D-080 audit_revid_drift disclosure, carried over to v4 (D-081; BUG-039)
        rs.write_json(rs.REFSTIM / f"image_revid_drift_{ver}.json", drift)
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
        _cfg = load_config()
        _t, _p = parse_run_args(sys.argv[4:], _cfg["controls"]["refclips"]["loc_categories"])
        run(Path(sys.argv[2]), Path(sys.argv[3]), _t, _p)
    elif cmd == "finalise":
        finalise(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
