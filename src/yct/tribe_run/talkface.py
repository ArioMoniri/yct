"""D-085 part 2 step 4: the TALKFACE clip (talkface_00) around one short Wav2Lip GPU session. Pure helpers.

Plan (reviews/phase_p4b/talkface_ready.md; the composition choices below are proposals for the council):
- Face: the frozen TALKFACE face = v4 face-log row `talkface_face_rank` (1-based; 499), a pass whose
  source_sha256 equals the frozen talkface_face_sha256 and whose licence permits adaptation (no ND).
- Static frame: the LOC processing of that image without SHINE (locimg.patch: frozen crop_box, BT.709 luma,
  INTER_AREA 316 px) centred in the 640 x 360 mid-grey frame (refclips58._frame), as every LOC frame.
- Audio: the clip audio exactly as for SPK / BURST (refclips58.clip_audio: one bed, speech replaces the bed
  at matched RMS, TALKFACE rate 175 wpm from the frozen selection). Wav2Lip is driven by that same audio
  (band-limited to 16 kHz), so the mouth follows what TRIBE hears.
- Video: Wav2Lip (pinned bac9a81 code, NOGAN through the frozen loader, s3fd sha-checked, --static, fps 30)
  re-renders the lower face per frame. Only frames inside the utterance windows [onset, onset + span) are
  taken from Wav2Lip; every other frame is the static frame bit for bit, so outside the windows the clip is
  a still face (no mouth motion driven by the noise bed).
- QC (gating): 1740 frames; every frame outside the windows equals the static frame; each window has
  Wav2Lip lip motion (at least one frame differs from the static frame); the constructive speech gate on the
  rendered audio (as SPK / BURST). Descriptive: mean |frame - static| per window.
- Skips (face_rule.skip_on): s3fd finds no face -> s3fd_no_face; any other Wav2Lip error -> wav2lip_error;
  licence not adaptable -> licence_not_adaptable. A skip is logged; the next face pass needs the frozen
  face continuation (max 5 skips, then STOP to the owner).
- Internal only (publish false): the clip and its frames never enter git or the report; numbers + sha only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from yct.tribe_run import refclips58 as R  # noqa: N812

FACE_KEY = "controls.refclips_artifacts.talkface_face_sha256"
SEL_KEY = "controls.refclips_artifacts.speech_selection_sha256"
CONT = "data/refstim/talkface_face_continuation.json"
NEED_FROZEN = ("controls.refclips_d085.speech", "controls.refclips_d085.talkface",
               "controls.refclips_d085.tenv", "controls.refclips_d085.qc", "controls.refclips_d089",
               SEL_KEY, FACE_KEY, "controls.refclips_artifacts.speech_corpus_sha256")
N_FRAMES = int(R.DUR * R.FPS)


def _frozen(cfg: dict, key: str) -> bool:
    return any(key == f.get("key") or key.startswith(f.get("key", "") + ".") for f in cfg.get("frozen", []))


def check_frozen(cfg: dict, root: Path) -> dict:
    """Every key TALKFACE depends on is frozen, publish is false, the loader is the frozen one."""
    miss = [k for k in NEED_FROZEN if not _frozen(cfg, k)]
    if miss:
        raise SystemExit(f"TALKFACE refused, not frozen: {miss}")
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    if tk.get("publish") is not False:
        raise SystemExit("TALKFACE publish must be false (owner 2026-11-22: internal only)")
    ld = tk["loader"]
    if "NOGAN" not in tk["weights_file"] or ld.get("gan_allowed") or ld.get("jit_fallback"):
        raise SystemExit("TALKFACE: only the NOGAN weights via the strict loader (no GAN, no jit fallback)")
    mod = Path(root) / tk["loader"]["module"]
    if R.git_blob_sha(mod) != tk["loader"]["blob_sha1"]:
        raise SystemExit(f"{tk['loader']['module']}: blob sha != the frozen loader blob_sha1 (STOP)")
    rec = Path(root) / tk["loader"]["check_record"]
    if hashlib.sha256(rec.read_bytes()).hexdigest() != tk["loader"]["check_record_sha256"]:
        raise SystemExit("loader check record sha256 != the frozen check_record_sha256 (STOP)")
    return tk


def licence_adaptable(licence: str, allowed: list[str]) -> bool:
    lic = str(licence)
    ok = any(lic == a or (a.endswith("*") and lic.startswith(a[:-1])) for a in allowed)
    return ok and "ND" not in lic.upper().split("-")


def face_row(log_rows: list[dict], cfg: dict, cont: dict) -> dict:
    """The frozen TALKFACE face: log row `talkface_face_rank` (1-based), a face pass with the frozen sha."""
    rank = int(cont["talkface_face_rank"])
    if rank < 1 or rank > len(log_rows):
        raise SystemExit(f"TALKFACE face rank {rank} outside the face log ({len(log_rows)} rows): STOP")
    after = int(cfg["controls"]["refclips_d085"]["talkface"]["face_continuation"]["after_rank"])
    if rank <= after:
        raise SystemExit(f"TALKFACE face rank {rank} <= after_rank {after} (a LOC face): STOP")
    row = log_rows[rank - 1]
    want = cfg["controls"]["refclips_artifacts"]["talkface_face_sha256"]
    if row.get("category") != "face" or row.get("decision") != "pass":
        raise SystemExit(f"face log row {rank} is not a face pass: STOP")
    if row.get("source_sha256") != want or cont.get("talkface_face_source_sha256") != want:
        raise SystemExit(f"face log row {rank} sha != the frozen talkface_face_sha256: STOP")
    return row


def static_frame(rgb: np.ndarray, crop_box) -> np.ndarray:
    from yct.tribe_run import locimg

    return R._u8(R._frame(locimg.patch(rgb, crop_box)))


def speech_windows(events: list[dict]) -> list[tuple[float, float]]:
    """[onset, onset + utterance_s) per event (utterance_s set by refclips58.clip_audio)."""
    return [(float(e["onset"]), float(e["onset"]) + float(e["utterance_s"])) for e in events]


def window_frames(windows: list[tuple[float, float]], fps: int = R.FPS, n: int = N_FRAMES) -> list[int]:
    """Frame indices whose time n / fps lies inside a window."""
    return [i for i in range(n) if any(a <= i / fps < b for a, b in windows)]


def compose(static: np.ndarray, w2l: dict[int, np.ndarray], windows: list[tuple[float, float]],
            fps: int = R.FPS, n: int = N_FRAMES) -> list[np.ndarray]:
    need = window_frames(windows, fps, n)
    miss = [i for i in need if i not in w2l]
    if miss:
        raise SystemExit(f"Wav2Lip output lacks {len(miss)} in-window frames (first {miss[0]}): STOP")
    inside = set(need)
    return [np.asarray(w2l[i], np.uint8) if i in inside else static for i in range(n)]


def to_grey(bgr: np.ndarray) -> np.ndarray:
    """Wav2Lip writes BGR uint8 frames; the clip is grey: BT.709 luma (locimg.grey709) on RGB order."""
    from yct.tribe_run import locimg

    return locimg.grey709(np.ascontiguousarray(bgr[..., ::-1]))


def qc(frames: list[np.ndarray], static: np.ndarray, windows: list[tuple[float, float]],
       speech_gate: dict, fps: int = R.FPS) -> dict[str, Any]:
    n = len(frames)
    inside = set(window_frames(windows, fps, n))
    outside_bad = [i for i in range(n) if i not in inside and not np.array_equal(frames[i], static)]
    motion, mad = [], []
    for a, b in windows:
        idx = [i for i in range(n) if a <= i / fps < b]
        d = [float(np.abs(frames[i].astype(np.int16) - static).mean()) for i in idx]
        motion.append(any(x > 0 for x in d))
        mad.append(float(np.mean(d)) if d else 0.0)
    ck = {"n_frames": {"n": n, "pass": n == N_FRAMES},
          "outside_static": {"n_bad": len(outside_bad), "first_bad": outside_bad[:5],
                             "pass": not outside_bad},
          "lip_motion": {"per_window": motion, "pass": bool(motion) and all(motion)},
          "speech_gate": speech_gate,
          "window_mean_abs_diff": {"values": mad, "gating": False}}
    ok = all(v.get("pass", True) for v in ck.values() if v.get("gating", True) is not False)
    return {"name": "talkface_00", "family": "TALKFACE", "checks": ck, "pass": ok}


def classify_failure(text: str) -> str:
    """face_rule.skip_on: s3fd_no_face when the pinned inference reports no face, else wav2lip_error."""
    return "s3fd_no_face" if "Face not detected" in str(text) else "wav2lip_error"


def skip_record(face: dict, rank: int, reason: str, run_id: str) -> dict:
    if reason not in ("s3fd_no_face", "wav2lip_error", "licence_not_adaptable"):
        raise SystemExit(f"{reason!r} is not a pre-stated TALKFACE skip: STOP")
    return {"rank": rank, "source_sha256": face["source_sha256"], "skip_on": reason, "run_id": run_id}


def public_numbers(obj: Any) -> str:
    """The JSON that may be committed: numbers and shas only (frames are never serialised)."""
    return json.dumps(obj, default=lambda x: None if isinstance(x, np.ndarray) else str(x), sort_keys=True)
