"""D-085 draft: the amended p4b_ref/v1 stimulus QC (replaces refclips58.stimulus_qc once D-085 is frozen).

Owner decision 2026-11-22 ("Fix the rule"), stimuli byte-identical to build 1:
- LOC / LOC_SCR "no face": the frozen T-LIC YuNet (refclips_auto.face_detector, score >= 0.5, the B3 / P2
  exclusion threshold) on the decoded 316-px patch, resized to long side 640 exactly as T-LIC
  (ra.resize_long), at the Haar sample frames (confounds.face_fps). Gated TRs: every LOC TR except its
  face-event TR, and every LOC_SCR TR. Any detection fails the clip (STOP to the owner, D-071 (h)).
- Haar face_area_crop_frac on LOC / LOC_SCR: reported, never gating.
- face_hit_frac >= 0.9: pooled over the family's face-event TRs.
- Twin identity: LOC and LOC_SCR rendered uint8 frames are equal at every frame outside every window.
Council-only completions of design_v2 §1.5: luminance / contrast constancy (LOC, LOC_SCR, MOT, MOT_STAT),
MOT static level outside events and in the static twin, FLASH luminance_change at the events only, and
"no other regressor moves" (visual families carry the GREY_CTRL audio bit for bit; audio families show
exactly the GREY_CTRL video features).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from yct.tribe_run import refclips58 as R  # noqa: N812

KEY = "controls.refclips_d085"
Yunet = Callable[[np.ndarray, float], list[dict]]


def require_frozen(cfg: dict) -> None:
    if not any(f.get("key") == KEY for f in cfg.get("frozen", [])):
        raise SystemExit(f"{KEY} is not frozen: the D-085 QC rule must be frozen before YuNet runs on any "
                         "built frame")


def face_event_trs(clip: R.Clip, tr: float = 1.0) -> list[int]:
    return [int(e["onset"] // tr) for e in clip.events if e.get("category") == "face"] \
        if clip.family == "LOC" else []


def yunet_trs(clip: R.Clip, n_tr: int, tr: float = 1.0) -> list[int]:
    skip = set(face_event_trs(clip, tr))
    return [t for t in range(n_tr) if t not in skip]


def to_bgr640(patch: np.ndarray, long_side: int = 640) -> np.ndarray:
    from yct.curate.refstim_auto import resize_long

    rgb = np.repeat(np.asarray(patch, np.uint8)[:, :, None], 3, axis=2)
    out, _ = resize_long(rgb, long_side)
    return np.ascontiguousarray(out[:, :, ::-1])


def yunet_gate(clip: R.Clip, patches: Sequence[tuple[float, np.ndarray]], tr: float, yunet: Yunet,
               thr: float, long_side: int = 640) -> dict[str, Any]:
    gated = set(yunet_trs(clip, int(R.DUR / tr), tr))
    hits, n = [], 0
    for t, p in patches:
        k = int(t // tr)
        if k not in gated:
            continue
        n += 1
        for f in yunet(to_bgr640(p, long_side), thr):
            hits.append({"t": round(float(t), 3), "tr": k, "score": float(f["score"])})
    return {"n_frames": n, "hits": hits, "pass": not hits}


def face_hit_family(rows: list[dict], min_frac: float) -> dict[str, Any]:
    ev = [h for r in rows if r["family"] == "LOC" for h in r["face_event_hits"]]
    frac = float(np.mean(ev)) if ev else float("nan")
    return {"n_events": len(ev), "n_hit": int(sum(ev)), "frac": frac, "pass": bool(ev) and frac >= min_frac}


def twin_identity(frames_a: Sequence[np.ndarray], frames_b: Sequence[np.ndarray], clip: R.Clip,
                  cfg: dict) -> dict[str, Any]:
    if len(frames_a) != len(frames_b):
        return {"pass": False, "n_diff_frames": None, "reason": "frame count differs"}
    win = R.windows(clip, cfg)
    diff = []
    for n, (a, b) in enumerate(zip(frames_a, frames_b, strict=True)):
        t = n / R.FPS
        if any(lo <= t < hi for lo, hi in win):
            continue
        if not np.array_equal(a, b):
            diff.append(n)
    return {"pass": not diff, "n_diff_frames": len(diff), "first_diff_frame": diff[0] if diff else None}


def constancy(x: np.ndarray, tol: float) -> dict[str, Any]:
    v = np.asarray(x, np.float64)
    v = v[np.isfinite(v)]
    m = float(v.mean())
    dev = float(np.max(np.abs(v - m)) / m) if m else float("inf")
    return {"mean": m, "max_rel_dev": dev, "pass": dev <= tol}


def mot_checks(mot: np.ndarray, stat: np.ndarray, ev_tr: Sequence[int], ratio_min: float) -> dict[str, Any]:
    m = np.nan_to_num(np.asarray(mot, np.float64))
    s = np.nan_to_num(np.asarray(stat, np.float64))
    ev = list(ev_tr)
    off = np.ones(len(m), bool)
    off[ev] = False
    e_mean = float(m[ev].mean())
    s_ev = float(s[ev].mean())
    ratio = e_mean / s_ev if s_ev > 0 else float("inf")
    off_max = float(m[off].max())
    twin_max = float(s.max())
    ok = ratio >= ratio_min and off_max * ratio_min <= e_mean and twin_max * ratio_min <= e_mean
    return {"motion_event": e_mean, "motion_static": s_ev, "ratio": ratio, "off_event_max": off_max,
            "twin_max": twin_max, "pass": bool(ok)}


def flash_check(lum_crop: np.ndarray, onset_trs: Sequence[int], quiet_frac: float) -> dict[str, Any]:
    lum = np.asarray(lum_crop, np.float64)
    ch = np.abs(np.diff(lum, prepend=lum[0]))
    on = list(onset_trs)
    ev = set(on) | {t + 1 for t in on}
    quiet = [t for t in range(len(ch)) if t not in ev]
    on_min = float(ch[on].min())
    q_max = float(ch[quiet].max()) if quiet else 0.0
    return {"onset_change_min": on_min, "off_event_change_max": q_max, "pass": q_max <= quiet_frac * on_min}


def audio_identity(rec: dict, ctrl_rec: dict) -> dict[str, Any]:
    return {"wav": rec["sha256"]["wav"], "control_wav": ctrl_rec["sha256"]["wav"],
            "pass": rec["sha256"]["wav"] == ctrl_rec["sha256"]["wav"]}


def video_identity(vf: dict, vf_ctrl: dict) -> dict[str, Any]:
    bad = [k for k in sorted(set(vf) | set(vf_ctrl))
           if k not in vf or k not in vf_ctrl
           or not np.array_equal(np.asarray(vf[k], float), np.asarray(vf_ctrl[k], float), equal_nan=True)]
    return {"differs": bad, "pass": not bad}


def haar_descriptive(clip: R.Clip, face_area: np.ndarray) -> dict[str, Any]:
    fa = np.nan_to_num(np.asarray(face_area, np.float64))
    face = set(face_event_trs(clip))
    hit = [t for t in range(len(fa)) if t not in face and fa[t] > 0]
    return {"n_hit_trs": len(hit), "hit_trs": hit, "max_area": float(fa[hit].max()) if hit else 0.0,
            "gating": False}


def decoded_patches(mp4, fps: float) -> list[tuple[float, np.ndarray]]:
    """Decoded central PATCH x PATCH luma patches at native 640 x 360 (BT.709 tv, as every P2 output)."""
    from yct.media import iter_gray_frames

    out = []
    for t, g in iter_gray_frames(mp4, fps, R.H):
        h, w = g.shape
        if (h, w) != (R.H, R.W):
            raise ValueError(f"{mp4}: decoded {w}x{h}, expected {R.W}x{R.H}")
        y0, x0 = (R.H - R.PATCH) // 2, (R.W - R.PATCH) // 2
        out.append((t, g[y0:y0 + R.PATCH, x0:x0 + R.PATCH].copy()))
    return out


def run_qc(clips: list[R.Clip], out_dir, cfg: dict, records: dict[str, dict], yunet: Yunet,
           frames_of: Callable[[R.Clip], list[np.ndarray]], vfeat: Callable | None = None,
           decode: Callable | None = None) -> dict[str, Any]:
    """The whole D-085 QC over a built family set. frames_of(clip) re-renders the uint8 frames (the build
    is deterministic); vfeat(mp4) -> yct.confounds video_features; decode(mp4, fps) -> patches."""
    from pathlib import Path

    require_frozen(cfg)
    q = cfg["controls"]["refclips_d085"]["qc"]
    tr = cfg["tribe"]["tr_s"]
    if vfeat is None:
        from yct.confounds.core import tr_grid, video_features

        grid = tr_grid(R.DUR, tr)

        def vfeat(p):
            return video_features(p, grid, cfg)
    decode = decode or decoded_patches
    out = Path(out_dir)
    by = {c.name: c for c in clips}
    vf = {c.name: vfeat(out / f"{c.name}.mp4") for c in clips}
    ctrl = "grey_ctrl_00"
    rows = []
    for c in clips:
        r: dict[str, Any] = {"name": c.name, "family": c.family, "checks": {}}
        ev_tr = sorted({int(e["onset"] // tr) for e in c.events})
        ck = r["checks"]
        if c.family in ("LOC", "LOC_SCR"):
            fa = np.nan_to_num(vf[c.name]["face_area_crop_frac"])
            r["face_event_hits"] = [bool(fa[t] > 0) for t in face_event_trs(c, tr)]
            ck["haar"] = haar_descriptive(c, fa)
            ck["yunet"] = yunet_gate(c, decode(out / f"{c.name}.mp4", q["yunet_sample_fps"]), tr, yunet,
                                     q["yunet_score_threshold"], q["yunet_input_long_side"])
            if c.family == "LOC":
                ck["twin_identity"] = twin_identity(frames_of(c), frames_of(by[c.control]), c, cfg)
        if c.family in ("LOC", "LOC_SCR", "MOT", "MOT_STAT"):
            ck["luminance"] = constancy(vf[c.name]["luminance_crop"], q["constancy_tol"])
            ck["contrast"] = constancy(vf[c.name]["contrast_crop"], q["constancy_tol"])
        if c.family == "MOT":
            ck["motion"] = mot_checks(vf[c.name]["motion_energy_crop"], vf[c.control]["motion_energy_crop"],
                                      ev_tr, q["mot_ratio"])
        if c.family == "FLASH":
            ck["flash"] = flash_check(vf[c.name]["luminance_crop"], ev_tr, q["flash_quiet_frac"])
        if c.family in R.VISUAL and ctrl in records:
            ck["audio_identity"] = audio_identity(records[c.name], records[ctrl])
        if c.family in R.AUDIO and ctrl in vf:
            ck["video_identity"] = video_identity(vf[c.name], vf[ctrl])
        r["pass"] = all(v.get("pass", True) for k, v in ck.items() if k != "haar")
        rows.append(r)
    fam = face_hit_family(rows, q["face_hit_min"]) if any(c.family == "LOC" for c in clips) else None
    ok = all(r["pass"] for r in rows) and (fam is None or fam["pass"])
    return {"rule": "D-085", "rows": rows, "face_hit_family": fam, "pass": ok}


def t_lic_yunet(cfg: dict, onnx_path) -> Yunet:
    """The frozen T-LIC YuNet (refclips_auto.face_detector): refuses unless the onnx file hashes to the
    frozen controls.refclips_auto_artifacts.yunet_sha256. Same call as
    scripts/refstim_auto_run.RealDetectors."""
    import hashlib
    from pathlib import Path

    want = cfg["controls"]["refclips_auto_artifacts"]["yunet_sha256"]
    got = hashlib.sha256(Path(onnx_path).read_bytes()).hexdigest()
    if got != want:
        raise SystemExit(f"YuNet onnx sha256 {got} != frozen {want}")
    fd = cfg["controls"]["refclips_auto"]["face_detector"]

    def yunet(bgr640: np.ndarray, thr: float) -> list[dict]:
        import cv2

        h, w = bgr640.shape[:2]
        det = cv2.FaceDetectorYN.create(str(onnx_path), "", (w, h), thr, fd["nms_threshold"], fd["top_k"])
        _, faces = det.detect(bgr640)
        return [{"box": [float(t) for t in r[:4]], "score": float(r[14])}
                for r in ([] if faces is None else faces)]
    return yunet
