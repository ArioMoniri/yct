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


def check_frozen_d078(cfg: dict) -> None:
    """D-078 body runs are refused unless controls.refclips_d078 and its snapshot sha are frozen and set."""
    rows = {r["key"] for r in cfg.get("frozen") or []}
    need = ["controls.refclips_d078", "controls.refclips_d078_artifacts.body_snapshot_sha256"]
    missing = [k for k in need if k not in rows]
    if missing:
        raise StopError(f"not frozen: {missing}")
    if not cfg["controls"]["refclips_d078_artifacts"].get("body_snapshot_sha256"):
        raise StopError("controls.refclips_d078_artifacts.body_snapshot_sha256 not set")


def audit_prior(row: dict, prior: dict[str, dict], exempt: tuple[str, ...] = ("duplicate",)) -> None:
    """D-078 determinism audit: a candidate already in the superseded D-074 log must get the same
    (decision, reason), unless either reason is exempt (C3 depends on the passes before it)."""
    old = prior.get(row["title"])
    if old is None:
        return
    a, b = (row["decision"], row.get("reason") or None), (old["decision"], old.get("reason") or None)
    if a != b and not ({a[1], b[1]} & set(exempt)):
        raise StopError(f"determinism audit: {row['title']!r} now {a}, D-074 log {b}: STOP to the owner")


# ---------------------------------------------------------------- D-079 (v2 logs after BUG-036)
def check_frozen_d079(cfg: dict) -> None:
    """The v2 run is refused unless controls.refclips_d079 and its flip sha are frozen and set."""
    rows = {r["key"] for r in cfg.get("frozen") or []}
    need = ["controls.refclips_d079", "controls.refclips_d079_artifacts.flip_sha256"]
    missing = [k for k in need if k not in rows]
    if missing:
        raise StopError(f"not frozen: {missing}")
    if not cfg["controls"]["refclips_d079_artifacts"].get("flip_sha256"):
        raise StopError("controls.refclips_d079_artifacts.flip_sha256 not set")


IDENTITY_REASON = "identity_changed"
DEFECT = ("treat as a code defect (D-079 stop_resolution.other_audit_stop): BUG entry, v3 from rank 1 "
          "for every category")


def audit_v2(row: dict, priors: list[tuple[str, dict[str, dict]]], flips: dict[str, set[str]],
             exempt: tuple[str, ...], c1: tuple[str, ...]) -> None:
    """D-079 determinism audit (non-selecting, fail-closed): the v2 row is compared with the row for the same
    title in every superseded v1 log of its category. Equal (decision, reason), or one reason exempt
    (C3 depends on the passes before it) while the other is not a C1 reason (re-check B2: C1 runs before C3,
    so a duplicate means C1 was passed and a duplicate <-> C1 pair is an admissibility change), or the title
    is in that log's committed BUG-036 flip list (v1 C1 reject -> admissible now; the later rules are new
    evaluations). A v2 identity_changed reject is a different file from the one v1 judged: exempt. Anything
    else is a STOP, resolved as a code defect. A listed title that is not a v1 C1 reject, or is still a C1
    reject in v2, contradicts the re-check: STOP."""
    a = (row["decision"], row.get("reason") or None)
    if a[1] == IDENTITY_REASON:
        return
    for name, rows in priors:
        old = rows.get(row["title"])
        if old is None:
            continue
        b = (old["decision"], old.get("reason") or None)
        if row["sha256_title"] in flips.get(name, set()):
            if b[1] not in c1 or a[1] in c1:
                raise StopError(f"flip list contradiction for {row['title']!r}: v2 {a}, {name} {b}: STOP")
            continue
        dup_ok = (a[1] in exempt and b[1] not in c1) or (b[1] in exempt and a[1] not in c1)
        if a != b and not dup_ok:
            raise StopError(f"determinism audit: {row['title']!r} now {a}, {name} {b}: STOP; {DEFECT}")


def identity_ok(snapshot_sha1: str | None, commons_sha1: str | None, data_sha1: str | None = None,
                title: str = "?") -> bool:
    """D-079 identity rule after the re-check (B1, identity_rule reject_identity_changed): True iff the
    snapshot sha1 equals the current Commons imageinfo sha1 and, once downloaded, the sha1 of the bytes.
    False = the file was re-uploaded since the snapshot: the row is a D1 identity_changed reject and the run
    resumes at the next rank. A missing sha1 is not a mismatch but missing data: STOP."""
    if not snapshot_sha1 or not commons_sha1:
        raise StopError(f"file identity: {title!r} snapshot {snapshot_sha1} commons {commons_sha1}: "
                        "sha1 missing: STOP to the owner")
    return snapshot_sha1 == commons_sha1 and (data_sha1 is None or data_sha1 == snapshot_sha1)


def identity_reject_row(cat: str, c: Candidate) -> dict:
    """Metadata-stage D1 reject (snapshot sha1 != current Commons sha1): nothing was downloaded, so
    data_sha1 is None. The byte stage is never a reject (D-079 sign-off referee B1): see fetch_verified."""
    return {"title": c.title, "sha256_title": c.sha256_title, "category": cat, "decision": "reject",
            "rule": "D1", "reason": IDENTITY_REASON, "values": {}, "identity_stage": "metadata",
            "data_sha1": None}


def fetch_verified(src, url: str, expect_sha1: str, title: str, dl) -> str:
    """Byte stage of the identity rule, run only after the snapshot and Commons sha1s agree. Bytes that
    differ are a download defect, not a re-upload: delete, download once more, and STOP naming the title if
    they still differ. A cached file is checked the same way. Returns the sha1 of the verified bytes."""
    import hashlib

    for _attempt in range(2):
        if not src.exists():
            dl(url, src)
        got = hashlib.sha1(src.read_bytes()).hexdigest()
        if got == expect_sha1:
            return got
        src.unlink()
    raise StopError(f"download defect: {title!r} bytes sha1 {got} != snapshot/Commons sha1 {expect_sha1} "
                    "after one re-download: STOP")


def identity_disclosure(rows: list[dict]) -> list[dict] | str:
    """D-079 §A disclosure: every identity_changed row (title, both sha1s, stage, data sha1), or "none"."""
    out = []
    for r in rows:
        if r.get("reason") != IDENTITY_REASON:
            continue
        if "identity_stage" not in r or "data_sha1" not in r:
            raise StopError(f"identity_changed row {r.get('title')!r} without identity_stage/data_sha1")
        out.append({k: r.get(k) for k in ("title", "sha1", "commons_sha1", "identity_stage", "data_sha1")})
    return out or "none"


def check_identity(snapshot_sha1: str | None, commons_sha1: str | None, data_sha1: str | None = None) -> None:
    """D-079 identity rule (STOP): the file judged is the file snapshotted. Snapshot sha1 must equal the
    current Commons imageinfo sha1 and, once downloaded, the sha1 of the bytes."""
    if not snapshot_sha1 or not commons_sha1 or snapshot_sha1 != commons_sha1 or \
            (data_sha1 is not None and data_sha1 != snapshot_sha1):
        raise StopError(f"file identity: snapshot {snapshot_sha1} commons {commons_sha1} bytes {data_sha1}: "
                        "STOP to the owner")


def revid_fields(entry: dict, meta: dict) -> dict:
    """D-079 revid rule (evaluate_current_log_both): templates are read at the current page revision; the
    snapshot revid and the read revid are both logged; revid (manifest, LICENSES.md) = the read revid."""
    if meta.get("read_revid") is None:
        raise StopError(f"no read_revid from Commons (prop=info) for {entry.get('title')!r}: STOP")
    return {"snapshot_revid": entry["revid"], "read_revid": meta["read_revid"], "revid": meta["read_revid"],
            "revid_drift": entry["revid"] != meta["read_revid"]}


def templates_digest(templates: list[str]) -> str:
    return hashlib.sha256(json.dumps(list(templates)).encode()).hexdigest()


def preload_v2(st: State, cat: str, cfg: dict, root: Path, ran: list[str] | None = None) -> list[dict]:
    """C3 state from the v2 log of `cat` only (earlier categories were preloaded when they ran, in
    category_order). `ran` = the categories already processed in this run; it must be exactly the
    categories before `cat` in category_order. v1 logs are never read here."""
    from yct.curate import refstim as rs

    order = cfg["controls"]["refclips_d079"]["category_order"]
    before = order[:order.index(cat)]
    if ran is not None and list(ran) != before:
        raise StopError(f"{cat}: category order {list(ran)} != {before}: STOP")
    p = Path(root) / rs.image_log_v2(cat, cfg)
    done = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
    for r in done:
        if r.get("log_version") != "v2":           # re-check QA B1: no default; real v1 rows carry no key
            raise StopError(f"{p.name}: row with log_version {r.get('log_version')!r}: STOP")
        if r["decision"] == "pass":
            st.pass_sha1.add(r["sha1"])
            st.pass_dhash.append(int(r["values"]["dhash"], 16))
    return done


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
