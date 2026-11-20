"""D-075: frozen automatic filters for the P4b localiser images (face, body, place) and the NAT clips.

Every rule reads its threshold from config `controls.refclips_auto` (frozen). Rules are evaluated in the
listed order; the first failing rule gives the logged reason; each evaluated candidate (pass or reject) is
appended once to an append-only JSONL log with its rule id and every value computed so far. A model-load
error, a download/decode error of a BITMAP file, or a NaN in any score is a STOP (exit 1, human), never a
reject. Detectors are injected (`Detectors`), so tests run on fakes; `load_detectors` builds the real ones.

This module never opens data/wave2_pool/ (D-069, D-071 (c); test_refstim_auto checks it).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_CSV = ROOT / "data" / "manifest.csv"
IMAGE_RULES = {
    "face": ["C0", "C1", "C2", "C3", "C4", "C5", "F1", "F2", "F6", "F3", "F4", "F5", "F5b", "F7", "F8"],
    "body": ["C0", "C1", "C2", "C3", "C4", "C5", "B1", "B2", "B3", "B4", "B5"],
    "place": ["C0", "C1", "C2", "C3", "C4", "C5", "P1", "P2", "P3"],
}
NAT_RULES = ["N1", "N2"]
LANDMARK_ORDER = ["right_eye", "left_eye", "nose_tip", "right_mouth_corner", "left_mouth_corner"]


class StopError(RuntimeError):
    """Fail-closed STOP (exit 1, human decision): never turned into a reject."""


class Detectors(Protocol):
    def yunet(self, bgr640: np.ndarray, score_threshold: float) -> list[dict]: ...      # [{box, score, lm}]
    def persons(self, rgb: np.ndarray) -> list[dict]: ...                                # [{box, score}]
    def clip_probs(self, rgb: np.ndarray, prompts: list[str]) -> list[float]: ...
    def ocr_boxes(self, rgb: np.ndarray) -> list[dict]: ...                              # [{box, conf, text}]
    def haar_faces(self, grey: np.ndarray) -> np.ndarray: ...                            # (n, 4) x, y, w, h
    def haar_eyes(self, grey: np.ndarray) -> np.ndarray: ...


# ---------------------------------------------------------------- small pure helpers
def finite(*xs: float) -> None:
    for x in xs:
        if x is None or (isinstance(x, float) and not math.isfinite(x)):
            raise StopError(f"non-finite score {x!r} (fail-closed STOP)")


def resize_long(img: np.ndarray, long_side: int):
    import cv2

    h, w = img.shape[:2]
    s = long_side / max(h, w)
    out = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))),
                     interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    return out, s


def dhash64(grey: np.ndarray) -> int:
    import cv2

    small = cv2.resize(grey, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def argmax_is(probs: list[float], i: int) -> bool:
    finite(*[float(p) for p in probs])
    return int(np.argmax(probs)) == i


# ---------------------------------------------------------------- C4 metadata (hashed n-grams)
def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def manifest_key_hashes(path: Path = MANIFEST_CSV) -> tuple[set[str], int]:
    """sha256 of the normalised token strings of data/manifest.csv company_key / company_id (wave 1 only).
    Only these two columns are read; the hashes, never the keys, are kept."""
    out, longest = set(), 1
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for col in ("company_key", "company_id"):
                toks = _tokens(row.get(col) or "")
                if toks:
                    out.add(_h(" ".join(toks)))
                    longest = max(longest, len(toks))
    return out, longest


def metadata_hit(text: str, terms: list[str], regex: str, key_hashes: set[str], longest: int) -> bool:
    low = text.lower()
    for t in terms:
        if re.search(r"\b" + re.escape(t.lower()) + r"\b", low):
            return True
    if re.search(regex, text, flags=re.IGNORECASE):
        return True
    toks = _tokens(text)
    for n in range(1, longest + 1):
        for i in range(len(toks) - n + 1):
            if _h(" ".join(toks[i:i + n])) in key_hashes:
                return True
    return False


# ---------------------------------------------------------------- head pose (F4)
def head_pose(lm: np.ndarray, image_wh: tuple[int, int],
              model_points: np.ndarray) -> tuple[float, float, float]:
    """(yaw, pitch, roll) in degrees from the 5 YuNet landmarks (LANDMARK_ORDER, pixels of the image the
    landmarks were taken on). SQPNP (no initial guess); camera: f = image width, principal point at the
    centre, no distortion. Model frame: x right, y down, z away from the camera; a frontal face = 0, 0, 0.
    Angles from cv2.RQDecomp3x3(R): pitch = about x, yaw = about y, roll = about z."""
    import cv2

    w, h = image_wh
    cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    ok, rvec, _ = cv2.solvePnP(np.asarray(model_points, np.float64),
                               np.asarray(lm, np.float64).reshape(-1, 1, 2), cam, np.zeros(4),
                               flags=cv2.SOLVEPNP_SQPNP)
    if not ok:
        raise StopError("solvePnP SQPNP failed")
    rmat = cv2.Rodrigues(rvec)[0]
    angles = cv2.RQDecomp3x3(rmat)[0]
    pitch, yaw, roll = (float(a) for a in angles)
    finite(yaw, pitch, roll)
    return yaw, pitch, roll


def project(model_points: np.ndarray, yaw: float, pitch: float, image_wh: tuple[int, int],
            dist_mm: float = 600.0) -> np.ndarray:
    """Synthetic landmarks: rotate the model by (pitch about x, yaw about y) and project (tests only)."""
    import cv2

    w, h = image_wh
    cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
    rx = cv2.Rodrigues(np.array([math.radians(pitch), 0, 0]))[0]
    ry = cv2.Rodrigues(np.array([0, math.radians(yaw), 0]))[0]
    rvec = cv2.Rodrigues(ry @ rx)[0]
    pts, _ = cv2.projectPoints(np.asarray(model_points, np.float64), rvec,
                               np.array([0, 0, dist_mm], np.float64), cam, np.zeros(4))
    return pts.reshape(-1, 2)


# ---------------------------------------------------------------- per-candidate evaluation
@dataclass
class Candidate:
    title: str
    sha256_title: str
    entry: dict                       # D-074 snapshot entry (mediatype, mime, width, height, sha1, ...)
    meta: dict                        # page_meta + description/categories text
    licence: str | None
    licence_template: str | None
    admissible: bool
    load_rgb: Callable[[], np.ndarray]   # downloads + decodes; raises StopError on failure


@dataclass
class State:
    pass_sha1: set = field(default_factory=set)
    pass_dhash: list = field(default_factory=list)


class RejectError(Exception):
    def __init__(self, rule: str, reason: str):
        super().__init__(rule)
        self.rule, self.reason = rule, reason


def grey709(rgb: np.ndarray) -> np.ndarray:
    return ((0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
            .round().clip(0, 255).astype(np.uint8))


def crop_info(rgb: np.ndarray, cat: str, det: Detectors) -> dict | None:
    """The existing T-LIC crop, unchanged (scripts/refstim_inspect.py crop_box + processed): Haar on the
    BT.709 greyscale image scaled to a long side <= 1600 px; face = centred on the largest detection with
    face = 50% of the side, min 316 px, clipped; body/place = largest centred square; processed = crop +
    BT.709 grey + INTER_AREA 256 px. Returns box (original px), the Haar detections on the processed crop,
    and the centre of the crop-defining Haar face in original px (face only)."""
    import cv2

    g = grey709(rgb)
    h, w = g.shape
    scale = 1600 / max(g.shape) if max(g.shape) > 1600 else 1.0
    gs = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    hs, ws = gs.shape
    centre = None
    if cat == "face":
        d = np.asarray(det.haar_faces(gs)).reshape(-1, 4)
        if not len(d):
            return None
        x, y, fw, fh = max(d, key=lambda b: b[2] * b[3])
        side = int(min(min(hs, ws), max(fh / 0.5, CROP_MIN_SIDE)))
        cx, cy = x + fw / 2, y + fh / 2
        x0 = int(np.clip(cx - side / 2, 0, ws - side))
        y0 = int(np.clip(cy - side / 2, 0, hs - side))
        box = (x0, y0, side)
        centre = (cx / scale, cy / scale)
    else:
        side = min(hs, ws)
        box = ((ws - side) // 2, (hs - side) // 2, side)
    box = tuple(int(round(t / scale)) for t in box)
    x, y, s = box
    proc = cv2.resize(grey709(rgb[y:y + s, x:x + s]), (256, 256), interpolation=cv2.INTER_AREA)
    return {"box": box, "proc": proc, "proc_faces": np.asarray(det.haar_faces(proc)).reshape(-1, 4),
            "haar_centre": centre}


CROP_MIN_SIDE = 316


def evaluate_image(cat: str, c: Candidate, det: Detectors, cfg: dict, st: State,
                   key_hashes: set[str], longest: int) -> dict:
    """Run IMAGE_RULES[cat] in order. Returns the log row (decision pass|reject, rule, reason, values)."""
    a = cfg["controls"]["refclips_auto"]
    rr = a["rule_reasons"]
    v: dict[str, Any] = {}
    row = {"title": c.title, "sha256_title": c.sha256_title, "category": cat}

    def rej(rule: str, which: int = 0):
        reasons = rr[rule] if isinstance(rr[rule], list) else [rr[rule]]
        raise RejectError(rule, reasons[which])

    try:
        # C0 mediatype / mime (metadata, before download)
        if (c.entry.get("mediatype") != cfg["controls"]["refclips_d074"]["bitmap_mediatype"]
                or (c.entry.get("mime") or "") not in a["common"]["mimes"]):
            rej("C0")
        # C1 licence / personality rights
        if c.licence_template == "Template:Personality rights":
            rej("C1", 1)
        if not c.admissible:
            rej("C1", 0)
        # C2 size
        v["short_side"] = min(c.entry.get("width") or 0, c.entry.get("height") or 0)
        if v["short_side"] < a["common"]["min_short_side_px"]:
            rej("C2")
        # C3 exact duplicate (sha1) before download
        if c.entry.get("sha1") in st.pass_sha1:
            rej("C3")
        # C4 metadata
        text = " ".join([c.title, c.meta.get("description", ""), c.meta.get("categories", "")])
        com = a["common"]
        if metadata_hit(text, com["metadata_terms"], com["metadata_regex"], key_hashes, longest):
            rej("C4")
        rgb = c.load_rgb()
        grey_full = grey709(rgb)
        dh = dhash64(grey_full)
        v["dhash"] = f"{dh:016x}"
        if any(hamming(dh, o) <= a["common"]["dhash_max_hamming"] for o in st.pass_dhash):
            rej("C3")
        # C5 photograph (argmax)
        p = det.clip_probs(rgb, a["clip"]["photo_prompts"])
        v["clip_photo"] = [round(float(x), 6) for x in p]
        if not argmax_is(p, 0):
            rej("C5")
        bgr = rgb[..., ::-1].copy()
        b640, s640 = resize_long(bgr, a["face_detector"]["input_long_side"])
        h, w = rgb.shape[:2]
        box = None

        def text_rule(rule: str):
            lim = a["ocr"]["image_long_side"]
            r1600 = resize_long(rgb, lim)[0] if max(h, w) > lim else rgb
            boxes = det.ocr_boxes(r1600)
            area = sum(b["box"][2] * b["box"][3] for b in boxes
                       if b["conf"] >= a["ocr"]["min_conf"] and (b.get("text") or "").strip())
            v["text_area_frac"] = round(area / (r1600.shape[0] * r1600.shape[1]), 6)
            if v["text_area_frac"] >= a["ocr"]["max_text_area_frac"]:
                rej(rule)

        def adult_rule(rule: str):
            pa = det.clip_probs(rgb, a["clip"]["adult_prompts"])
            v["clip_adult"] = [round(float(x), 6) for x in pa]
            if not argmax_is(pa, 1):
                rej(rule)

        def persons():
            ps = [q for q in det.persons(rgb) if q["score"] >= a["person_detector"]["score_threshold"]]
            for q in ps:
                finite(float(q["score"]))
            v["persons"] = [round(float(q["score"]), 4) for q in ps]
            return ps

        if cat == "face":
            fs = det.yunet(b640, a["face_detector"]["score_threshold"])
            v["yunet_n"] = len(fs)
            if len(fs) == 0:
                rej("F1", 0)
            if len(fs) > 1:
                rej("F1", 1)
            f = fs[0]
            finite(float(f["score"]))
            ps = persons()
            if len(ps) > 1:
                rej("F2")
            box = crop_info(rgb, cat, det)
            if box is None or not len(box["proc_faces"]):
                rej("F6")
            v["face_height_frac"] = round(max(int(b[3]) for b in box["proc_faces"]) / 256, 4)
            if v["face_height_frac"] < a["face_rules"]["min_face_height_frac_crop"]:
                rej("F3", 0)
            fx, fy, fw, fh = (float(t) for t in f["box"])
            cx, cy = (t * s640 for t in box["haar_centre"])
            if not (fx <= cx <= fx + fw and fy <= cy <= fy + fh):
                rej("F3", 1)
            lm = np.asarray(f["lm"], np.float64).reshape(5, 2)
            yaw, pitch, roll = head_pose(lm, (b640.shape[1], b640.shape[0]),
                                         np.asarray(a["headpose"]["model_points_mm"], np.float64))
            v.update(yaw=round(yaw, 3), pitch=round(pitch, 3), roll=round(roll, 3))
            if abs(yaw) > a["headpose"]["max_abs_yaw_deg"] or abs(pitch) > a["headpose"]["max_abs_pitch_deg"]:
                rej("F4")
            re_, le_ = lm[0], lm[1]
            inside = all(fx <= x <= fx + fw and fy <= y <= fy + fh for x, y in (re_, le_))
            v["interocular_frac"] = round(float(np.hypot(*(re_ - le_))) / fw, 4)
            if not inside or v["interocular_frac"] < a["face_rules"]["min_interocular_frac_box"]:
                rej("F5")
            # F5b eye cascade on the original image, inside the YuNet box (scaled back)
            x0, y0 = int(fx / s640), int(fy / s640)
            x1, y1 = int((fx + fw) / s640), int((fy + fh) / s640)
            roi = grey_full[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
            eyes = det.haar_eyes(roi) if roi.size else np.zeros((0, 4))
            upper = [e for e in np.asarray(eyes).reshape(-1, 4) if e[1] + e[3] / 2 <= roi.shape[0] / 2]
            v["eyes_upper"] = len(upper)
            if len(upper) < a["eye_detector"]["min_count"]:
                rej("F5b")
            adult_rule("F7")
            text_rule("F8")
        elif cat == "body":
            ps = persons()
            if len(ps) == 0:
                rej("B1", 0)
            if len(ps) > 1:
                rej("B1", 1)
            bx, by, bw, bh = ps[0]["box"]
            v["person_area_frac"] = round(bw * bh / (w * h), 4)
            if v["person_area_frac"] < a["body_rules"]["min_person_area_frac"]:
                rej("B2")
            fs = det.yunet(b640, a["face_detector"]["exclusion_score_threshold"])
            box = crop_info(rgb, cat, det)
            v["yunet_n_excl"], v["haar_n"] = len(fs), int(len(box["proc_faces"]))
            if fs or len(box["proc_faces"]):
                rej("B3")
            adult_rule("B4")
            text_rule("B5")
        else:
            ps = persons()
            if ps:
                rej("P1")
            fs = det.yunet(b640, a["face_detector"]["exclusion_score_threshold"])
            box = crop_info(rgb, cat, det)
            v["yunet_n_excl"], v["haar_n"] = len(fs), int(len(box["proc_faces"]))
            if fs or len(box["proc_faces"]):
                rej("P2")
            text_rule("P3")
        row.update(decision="pass", rule=None, reason=None, values=v, crop_box=list(box["box"]))
        st.pass_sha1.add(c.entry.get("sha1"))
        st.pass_dhash.append(dh)
    except RejectError as r:
        row.update(decision="reject", rule=r.rule, reason=r.reason, values=v)
    return row


# ---------------------------------------------------------------- NAT rules (session 0; fakes in tests)
def nat_decide(lang_probs: dict[str, float], segments: list[tuple[float, float, str]], cfg: dict) -> dict:
    """N1 English then N2 single speaker on the trimmed 58-s T1 audio. lang_probs from
    faster_whisper detect_language on samples [0, 30 s); segments = diarization (start, end, speaker)."""
    n = cfg["controls"]["refclips_auto"]["nat"]
    p_en = float(lang_probs.get("en", 0.0))
    finite(p_en)
    v = {"p_en": round(p_en, 6)}
    if p_en < n["lang_id"]["min_prob_en"]:
        return {"decision": "reject", "rule": "N1", "reason": "not_english", "values": v}
    per: dict[str, float] = {}
    for s, e, spk in segments:
        finite(float(s), float(e))
        per[spk] = per.get(spk, 0.0) + max(0.0, float(e) - float(s))
    total = sum(per.values())
    v["speech_s"] = round(total, 3)
    if total <= 0:
        return {"decision": "reject", "rule": "N2", "reason": "not_single_speaker", "values": v}
    main = max(per.values())
    others = sorted(per.values())[:-1]
    v.update(main_frac=round(main / total, 4), max_other_s=round(max(others, default=0.0), 3))
    d = n["diarization"]
    if main / total < d["min_main_speaker_frac"] or any(o > d["max_other_speaker_s"] for o in others):
        return {"decision": "reject", "rule": "N2", "reason": "not_single_speaker", "values": v}
    return {"decision": "pass", "rule": None, "reason": None, "values": v}


def nat_select(ordered_ids: list[str], decide: Callable[[str], dict],
               cfg: dict) -> tuple[list[str], list[dict]]:
    """First nat_n passes, in order, among the CPU-stage buffer (cpu_buffer candidates). < nat_n -> STOP."""
    n = cfg["controls"]["refclips_auto"]["nat"]
    need, buf = cfg["controls"]["refclips"]["nat_n"], n["cpu_buffer"]
    if len(ordered_ids) > buf:
        raise StopError(f"NAT buffer holds {len(ordered_ids)} > cpu_buffer {buf}")
    passes, log = [], []
    for i in ordered_ids:
        r = {"id": i, **decide(i)}
        log.append(r)
        if r["decision"] == "pass":
            passes.append(i)
            if len(passes) == need:
                break
    if len(passes) < need:
        raise StopError(f"{len(passes)} NAT passes < {need} in the {buf}-candidate buffer: STOP to the owner")
    return passes, log


# ---------------------------------------------------------------- frozen/artifact preconditions
def check_frozen(cfg: dict) -> None:
    """The first detector call is refused unless controls.refclips_auto and every image artifact key are
    frozen (config `frozen:` rows) and every image artifact sha is set."""
    rows = {r["key"] for r in cfg.get("frozen") or []}
    need = ["controls.refclips_auto"] + [f"controls.refclips_auto_artifacts.{k}"
                                         for k in cfg["controls"]["refclips_auto"]["image_artifacts"]]
    missing = [k for k in need if k not in rows]
    if missing:
        raise StopError(f"not frozen: {missing}")
    arts = cfg["controls"]["refclips_auto_artifacts"]
    unset = [k for k in cfg["controls"]["refclips_auto"]["image_artifacts"] if not arts.get(k)]
    if unset:
        raise StopError(f"artifact shas not set: {unset}")


def check_artifact(path: Path, want_sha256: str) -> None:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if h != want_sha256:
        raise StopError(f"{Path(path).name}: sha256 {h} != frozen {want_sha256}")


def check_env(cfg: dict, installed: dict[str, str]) -> None:
    """Installed package versions must equal the frozen env pins before the first detector call."""
    want = cfg["controls"]["refclips_auto"]["env"]["packages"]
    bad = {k: (installed.get(k), v) for k, v in want.items() if installed.get(k) != v}
    if bad:
        raise StopError(f"environment differs from the frozen pins: {bad}")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
