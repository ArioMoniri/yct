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
Council D-085 (v2): SPK / BURST audio gate is constructive on the RENDERED 48 kHz int16 audio (identical to
GREY_CTRL outside every utterance window; each window reconstructs from the logged utterance at its onset);
speech_envelope is descriptive only. Decoded twin differences and decoded-vs-rendered at event mid-frames
are descriptive only. TALKFACE face rule with a logged technical fallback. Two-part freeze: part 1
(controls.refclips_d085.qc) unlocks the visual rebuild.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from yct.tribe_run import refclips58 as R  # noqa: N812

KEY = "controls.refclips_d085.qc"
Yunet = Callable[[np.ndarray, float], list[dict]]


def _frozen(cfg: dict, key: str) -> bool:
    """A key is frozen if it, or an ancestor of it, has a frozen: row."""
    return any(key == f.get("key") or key.startswith(f.get("key", "") + ".") for f in cfg.get("frozen", []))


def require_frozen(cfg: dict) -> None:
    if not _frozen(cfg, KEY):
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


def pcm16(x: np.ndarray) -> np.ndarray:
    """The int16 samples refclips58._write_wav writes (the rendered 48 kHz audio)."""
    return np.clip(np.rint(np.asarray(x, np.float64) * 32767), -32768, 32767).astype(np.int16)


def speech_gate(clip_pcm: np.ndarray, ctrl_pcm: np.ndarray, bed: np.ndarray,
                placements: Sequence[tuple[float, np.ndarray]], sr: int = R.SR) -> dict[str, Any]:
    """Council D-085 (c), constructive gate on the rendered 48 kHz audio of an SPK / BURST clip:
    (1) outside_identical: every sample outside the utterance windows equals the GREY_CTRL rendering;
    (2) reconstructed: the whole clip equals refclips58.place_speech applied to the bed with each logged
    (onset, utterance), so every utterance sits sample-exact at its logged onset.
    window_rms_ratio (clip / control, per window) is reported, never gating."""
    a, c = np.asarray(clip_pcm), np.asarray(ctrl_pcm)
    if a.shape != c.shape:
        return {"pass": False, "outside_identical": False, "reconstructed": False, "reason": "length differs",
                "gating": ["outside_identical", "reconstructed"]}
    inside = np.zeros(len(a), bool)
    exp = np.asarray(bed, np.float64)
    rms = []
    for t0, u in placements:
        s0 = int(round(t0 * sr))
        inside[s0:s0 + len(u)] = True
        exp = R.place_speech(exp, u, t0)
        seg_a = a[s0:s0 + len(u)].astype(np.float64)
        seg_c = c[s0:s0 + len(u)].astype(np.float64)
        den = float(np.sqrt(np.mean(seg_c ** 2)))
        rms.append(float(np.sqrt(np.mean(seg_a ** 2))) / den if den else float("nan"))
    outside = bool(np.array_equal(a[~inside], c[~inside]))
    recon = bool(np.array_equal(a, pcm16(exp)))
    return {"pass": outside and recon, "outside_identical": outside, "reconstructed": recon,
            "window_rms_ratio": rms, "gating": ["outside_identical", "reconstructed"]}


Patches = Sequence[tuple[float, np.ndarray]]


def twin_decoded_descriptive(dec_a: Patches, dec_b: Patches, clip: R.Clip, cfg: dict) -> dict[str, Any]:
    """Council D-085 (d): decoded LOC vs LOC_SCR patches outside the windows. Descriptive, never gating."""
    win = R.windows(clip, cfg)
    mx, frac, n = 0, [], 0
    for (t, pa), (_, pb) in zip(dec_a, dec_b, strict=False):
        if any(lo <= t < hi for lo, hi in win):
            continue
        d = np.abs(pa.astype(np.int16) - pb.astype(np.int16))
        mx = max(mx, int(d.max()))
        frac.append(float((d > 0).mean()))
        n += 1
    mean_frac = float(np.mean(frac)) if frac else 0.0
    return {"n_frames": n, "max_abs_diff": mx, "mean_frac_pixels_differing": mean_frac, "gating": False}


def decoded_vs_rendered(dec: Patches, rendered: Sequence[np.ndarray], clip: R.Clip) -> dict[str, Any]:
    """Council D-085 (d): decoded vs rendered central patch at each event mid-frame (onset + 0.5 s).
    Descriptive, never gating (no x264 tolerance is ever set)."""
    y0, x0 = (R.H - R.PATCH) // 2, (R.W - R.PATCH) // 2
    out = []
    for o in clip.onsets:
        tm = o + 0.5
        t, p = min(dec, key=lambda tp: abs(tp[0] - tm))
        r = np.asarray(rendered[int(round(tm * R.FPS))])
        rp = r[y0:y0 + R.PATCH, x0:x0 + R.PATCH] if r.shape == (R.H, R.W) else r
        d = np.abs(p.astype(np.float64) - rp.astype(np.float64))
        mse = float(np.mean(d ** 2))
        out.append({"t": round(float(t), 3), "max_abs_diff": int(d.max()),
                    "psnr_db": float("inf") if mse == 0 else float(10 * np.log10(255 ** 2 / mse))})
    return {"frames": out, "max_abs_diff": max((f["max_abs_diff"] for f in out), default=0), "gating": False}


def row_pass(row: dict) -> bool:
    """A row passes iff every gating check passes (checks marked gating False, and haar, never count)."""
    return all(v.get("pass", True) for k, v in row["checks"].items()
               if k != "haar" and v.get("gating", True) is not False)


def talkface_face(passes: Sequence[dict], failures: dict[str, str], rule: dict) -> dict[str, Any]:
    """Council D-085 (e): the TALKFACE face is the first face pass after v4 rank 492 (log order). A pass
    with a technical failure in rule.skip_on is skipped and logged (no visual review); more than
    rule.max_skips skips -> STOP to the owner."""
    if any(p["rank"] <= 492 for p in passes):
        raise ValueError("TALKFACE candidates must come after rank 492 (the 20 LOC faces)")
    skipped = []
    for p in sorted(passes, key=lambda p: p["rank"]):
        why = failures.get(p["title"])
        if why is None:
            return {"face": p, "skipped": skipped}
        if why not in rule["skip_on"]:
            raise SystemExit(f"TALKFACE face {p['title']}: failure {why!r} is not a pre-stated skip: STOP")
        skipped.append({"title": p["title"], "reason": why})
        if len(skipped) >= rule["max_skips"]:
            raise SystemExit(f"TALKFACE: {len(skipped)} skips, STOP to the owner")
    raise SystemExit("TALKFACE: face passes exhausted, STOP to the owner")


def assert_no_yunet_outputs(root) -> None:
    """Watchdog C1: before the D-085 freeze, YuNet has never run on a built frame: no JSON under root carries
    a refclip `yunet` check."""
    import json
    from pathlib import Path

    for p in Path(root).rglob("*.json"):
        if "refclips" not in str(p):
            continue
        try:
            doc = json.loads(p.read_text())
        except (ValueError, UnicodeDecodeError):
            continue
        if '"yunet"' in json.dumps(doc):
            raise SystemExit(f"YuNet output found on built frames: {p}")


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
            dec = decode(out / f"{c.name}.mp4", q["yunet_sample_fps"])
            ck["yunet"] = yunet_gate(c, dec, tr, yunet, q["yunet_score_threshold"],
                                     q["yunet_input_long_side"])
            if c.family == "LOC":
                fr = frames_of(c)
                ck["twin_identity"] = twin_identity(fr, frames_of(by[c.control]), c, cfg)
                ck["twin_decoded"] = twin_decoded_descriptive(
                    dec, decode(out / f"{c.control}.mp4", q["yunet_sample_fps"]), c, cfg)
                ck["decoded_vs_rendered"] = decoded_vs_rendered(dec, fr, c)
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
        r["pass"] = row_pass(r)
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
