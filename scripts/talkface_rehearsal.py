#!/usr/bin/env python3
# ruff: noqa: E501
"""D-090 draft: the $0 pod-CPU rehearsal of the TALKFACE path (council talkface). Synthetic inputs only:
no real face, no corpus text, numbers only. Run on the pod with the yct venv; the box runs in the
hashed-lock w2l venv.

  python scripts/talkface_rehearsal.py --dir D --w2l-python VENV/bin/python --repo WAV2LIP --lock LOCK \
      --freeze FREEZE --probe PROBE.json --mirror S3_PREFIX --out REHEARSAL.json

Steps: (0) env: the w2l venv freeze == the hashed lock pins and the probe is torch 2.8.0+cu128 / python 3.11;
the Wav2Lip checkout is the pinned revision with the loader-check file shas. (1) fixture: a synthetic grey
640x360 image (3-channel png, no face) and a 58 s noise-bed clip (no speech) -> 16 kHz driving audio;
windows at the TALKFACE onsets. (2) talkface_box --fixture-box on CPU (strict NOGAN load): exit 0,
n_mel_chunks == n_frames_total == 1736, kept == window frames, outside the face box == the static grey
(box_grey identity). (3) talkface_box with the real mirrored s3fd on the same synthetic image: s3fd must load
under torch 2.8 (weights_only) and the run must end in the pinned 'Face not detected' -> exit 10 ->
s3fd_no_face. (4) talkface.finish_local end to end on the fixture frames (compose, frozen encode twice, QC).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from yct.config import load_config  # noqa: E402
from yct.tribe_run import refclips58 as R  # noqa: E402,N812
from yct.tribe_run import talkface as T  # noqa: E402,N812
from yct.tribe_run import talkface_box as TB  # noqa: E402,N812

FIXTURE_BOX = [120, 240, 260, 380]        # y1, y2, x1, x2 on the 640x360 synthetic frame
WINDOWS = [[9.0, 10.4], [29.0, 31.2], [49.0, 52.5]]


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fixture(d: Path, cfg: dict) -> dict:
    import cv2

    d.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:R.H, 0:R.W]
    g = (96 + 64 * np.sin(xx / 37.0) * np.cos(yy / 23.0)).round().clip(0, 255).astype(np.uint8)
    cv2.imwrite(str(d / "static.png"), np.repeat(g[..., None], 3, 2))
    audio = R.bed()
    R._write_wav(audio, d / "rendered48k.wav", R.SR)
    a16 = R.resample_bandlimited(audio, R.SR, 16000)
    R._write_wav(a16, d / "clip16k.wav", 16000)
    np.savez(d / "utterances.npz")
    (d / "rows.json").write_text("[]")
    rec = {"windows": WINDOWS, "onsets": [], "utterance_s": [], "fixture": "synthetic_no_face_no_speech",
           "n_mel_chunks_expected": T.expected_n_chunks(len(a16), R.FPS),
           "static_png_sha256": _sha(d / "static.png"), "clip16k_wav_sha256": _sha(d / "clip16k.wav"),
           "rendered48k_sha256": _sha(d / "rendered48k.wav"), "n16": int(len(a16))}
    (d / "inputs_record.json").write_text(json.dumps(rec, sort_keys=True))
    T.check_windows([tuple(w) for w in WINDOWS], rec["n_mel_chunks_expected"], R.FPS)
    return rec


def box(a, d: Path, rec: dict, cfg: dict, tag: str, fixture_box: bool) -> dict:
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    out = d / tag
    out.mkdir(exist_ok=True)
    cmd = [a.w2l_python, "-m", "yct.tribe_run.talkface_box", "--repo", a.repo,
           "--weights", str(d / "w" / "Wav2Lip-SD-NOGAN.pt"), "--weights-sha", tk["weights_sha256"],
           "--face", str(d / "static.png"), "--face-sha", rec["static_png_sha256"],
           "--audio", str(d / "clip16k.wav"), "--audio-sha", rec["clip16k_wav_sha256"], "--fps", str(tk["fps"]),
           "--windows", json.dumps(rec["windows"]), "--out", str(out / "frames.npz"),
           "--record", str(out / "w2l_record.json")]
    if fixture_box:
        cmd += ["--fixture-box", *map(str, FIXTURE_BOX)]
    else:
        cmd += ["--s3fd", str(d / "w" / "s3fd-619a316812.pth"), "--s3fd-sha", tk["face_detector_sha256"]]
    env = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin", "CUDA_VISIBLE_DEVICES": "",
           "HOME": str(d / "home")}
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (out / "box.log").write_text(p.stdout[-20000:] + "\n--- stderr ---\n" + p.stderr[-20000:])
    res = {"rc": p.returncode, "class": T.classify_box_exit(p.returncode)}
    tail = [x for x in (p.stdout + p.stderr).splitlines() if "TALKFACE_BOX_EXIT" in x or "Error" in x]
    res["exit_lines"] = [x[:200] for x in tail[-3:]]
    if (out / "w2l_record.json").exists():
        r = json.loads((out / "w2l_record.json").read_text())
        res["record"] = {k: r.get(k) for k in ("n_mel_frames", "n_mel_chunks", "n_frames_total",
                                                "n_frames_kept", "face_box", "torch", "device", "frames_sha256")}
        res["record"]["loader_strict"] = (r.get("loader") or {}).get("path")
    return res


def luma_identity(d: Path, tag: str, face_box: list[int]) -> dict:
    import cv2

    bgr = cv2.imread(str(d / "static.png"))
    static = TB.box_grey(bgr)
    m = np.ones(static.shape, bool)
    y1, y2, x1, x2 = face_box
    m[y1:y2, x1:x2] = False
    bad, n = 0, 0
    with np.load(d / tag / "frames.npz") as z:
        for k in z.files:
            n += 1
            bad += int(not np.array_equal(z[k][m], static[m]))
    return {"static_eq_png_channel": bool(np.array_equal(static, bgr[..., 0])), "n_frames": n,
            "n_outside_box_mismatch": bad, "pass": bad == 0 and bool(np.array_equal(static, bgr[..., 0]))}


def main() -> int:
    ap = argparse.ArgumentParser()
    for k in ("--dir", "--w2l-python", "--repo", "--lock", "--freeze", "--probe", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args()
    cfg = load_config()
    d = Path(a.dir)
    res: dict = {"purpose": "D-090 TALKFACE $0 pod-CPU rehearsal (synthetic only; no real face, no corpus text)"}
    lock, freeze = Path(a.lock).read_text(), Path(a.freeze).read_text()
    ok, diff = T.freeze_matches(lock, freeze)
    probe = json.loads(Path(a.probe).read_text())
    env = cfg["controls"]["refclips_d090"]["env"]
    res["env"] = {"lock_sha256": hashlib.sha256(lock.encode()).hexdigest(),
                  "lock_sha_matches_config": hashlib.sha256(lock.encode()).hexdigest() == env["lock_sha256"],
                  "freeze_sha256": hashlib.sha256(freeze.encode()).hexdigest(), "freeze_matches_lock": ok,
                  "diff": diff, "probe": probe}
    check = json.loads((ROOT / cfg["controls"]["refclips_d085"]["talkface"]["loader"]["check_record"]).read_text())
    repo = Path(a.repo)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    res["repo"] = {"head": head.strip(),
                   "files_match": {f: _sha(repo / f) == check[k] for f, k in
                                   (("README.md", "readme_sha256"), ("models/wav2lip.py", "models_wav2lip_py_sha256"),
                                    ("inference.py", "inference_py_sha256"))}}
    rec = fixture(d, cfg)
    res["fixture"] = {k: rec[k] for k in ("n16", "n_mel_chunks_expected", "windows")}
    res["box_fixture"] = box(a, d, rec, cfg, "fixture", True)
    want_kept = len([i for i in T.window_frames([tuple(w) for w in WINDOWS]) if i < 1736])
    r = res["box_fixture"].get("record") or {}
    res["box_fixture"]["checks"] = {
        "exit_ok": res["box_fixture"]["rc"] == 0,
        "n_mel_chunks_eq_expected": r.get("n_mel_chunks") == rec["n_mel_chunks_expected"] == 1736,
        "n_frames_total_eq_n_mel_chunks": r.get("n_frames_total") == r.get("n_mel_chunks"),
        "kept_eq_window_frames": r.get("n_frames_kept") == want_kept, "want_kept": want_kept}
    if res["box_fixture"]["rc"] == 0:
        res["luma_identity"] = luma_identity(d, "fixture", r["face_box"])
        fin = T.finish_local(cfg, d, d / "fixture", d / "finish")
        q = fin["qc"]
        res["finish"] = {"qc_pass": q["pass"],
                         "gates": {k: bool(v.get("pass")) for k, v in q["checks"].items()
                                   if v.get("gating", True) is not False},
                         "descriptive": {k: v for k, v in q["checks"].items() if v.get("gating") is False},
                         "decoded_sha256": fin["decoded_sha256"], "n_frames": fin["n_frames"]}
    res["box_s3fd"] = box(a, d, rec, cfg, "s3fd", False)
    res["box_s3fd"]["checks"] = {"classified_s3fd_no_face": res["box_s3fd"]["class"] == "s3fd_no_face"}
    Path(a.out).write_text(T.public_numbers(res) + "\n")
    print(T.public_numbers({"env_ok": ok, "fixture": res["box_fixture"]["checks"],
                            "s3fd": res["box_s3fd"]["checks"], "finish_pass": res.get("finish", {}).get("qc_pass")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
