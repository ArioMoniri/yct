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


MEL_HOP, MEL_STEP, W2L_SR = 200, 16, 16000     # pinned hparams.hop_size, inference.mel_step_size, sample rate


def expected_n_chunks(n_samples: int, fps: float, hop: int = MEL_HOP, step: int = MEL_STEP) -> int:
    """The number of mel chunks (= Wav2Lip frames) the pinned inference.main loop yields for an n_samples
    16 kHz wav: librosa stft center=True gives 1 + n // hop mel frames; then 80 / fps per frame, step 16."""
    n_mel = 1 + int(n_samples) // hop
    chunks, mult, i = 0, 80. / fps, 0
    while True:
        chunks += 1
        if int(i * mult) + step > n_mel:
            return chunks
        i += 1


def check_windows(windows, n_chunks: int, fps: float) -> None:
    """D-090: Wav2Lip renders frames 0 .. n_chunks - 1 only; every window must end by (n_chunks - 1)/fps."""
    last = (int(n_chunks) - 1) / fps
    bad = [(float(a), float(b)) for a, b in windows if float(b) > last + 1e-9]
    if bad:
        raise SystemExit(f"TALKFACE window(s) {bad} end after the last Wav2Lip frame ({last:.4f} s): STOP")


def _box(face_box, shape) -> np.ndarray:
    y1, y2, x1, x2 = (int(v) for v in face_box)
    m = np.zeros(shape, bool)
    m[max(0, y1):y2, max(0, x1):x2] = True
    return m


def _mad(a: np.ndarray, b: np.ndarray, m: np.ndarray | None = None) -> float:
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return float(d[m].mean()) if m is not None else float(d.mean())


def qc(frames: list[np.ndarray], static: np.ndarray, windows: list[tuple[float, float]], *, face_box,
       record: dict, expected: dict, speech_gate: dict, decode_identity: dict, fps: int = R.FPS
       ) -> dict[str, Any]:
    """D-090 TALKFACE QC (council talkface). Gating: frame / mel-chunk / kept counts; outside the windows
    every frame is the static frame; outside the face box every frame is the static frame; w2l_rendered
    (each window has a frame differing from static inside the box: a sanity gate, renamed from lip_motion);
    inbox_articulation (each window has a consecutive-frame difference inside the box); decode_identity;
    the constructive speech gate. Descriptive: per-window mean |frame - static|, the edge steps at each window
    onset / offset inside the box, mouth (lower half) vs upper-face MAD. A QC fail is a final STOP."""
    n = len(frames)
    inside = window_frames(windows, fps, n)
    inset = set(inside)
    box = _box(face_box, static.shape)
    y1, y2, x1, x2 = (int(v) for v in face_box)
    mid = (y1 + y2) // 2
    lower, upper = box.copy(), box.copy()
    lower[:mid], upper[mid:] = False, False
    out_win = [i for i in range(n) if i not in inset and not np.array_equal(frames[i], static)]
    out_box = [i for i in range(n) if not np.array_equal(frames[i][~box], static[~box])]
    rendered, artic, mad, edge, mvu = [], [], [], [], []
    for a, b in windows:
        idx = [i for i in inside if a <= i / fps < b]
        d = [_mad(frames[i], static, box) for i in idx]
        rendered.append(any(x > 0 for x in d))
        artic.append(any(not np.array_equal(frames[i][box], frames[j][box])
                         for i, j in zip(idx, idx[1:], strict=False)))
        mad.append(float(np.mean(d)) if d else 0.0)
        edge.append({"onset": d[0] if d else 0.0, "offset": d[-1] if d else 0.0})
        lo = [_mad(frames[i], static, lower) for i in idx]
        up = [_mad(frames[i], static, upper) for i in idx]
        mvu.append({"mouth": float(np.mean(lo)) if lo else 0.0, "upper": float(np.mean(up)) if up else 0.0})
    want_kept = len([i for i in inside if i < int(expected["n_mel_chunks"])])
    nm, nt = record.get("n_mel_chunks"), record.get("n_frames_total")
    ck = {"n_frames": {"n": n, "pass": n == int(expected["n_frames"])},
          "n_mel_chunks": {"n_mel_chunks": nm, "n_frames_total": nt, "expected": expected["n_mel_chunks"],
                           "pass": nm == nt == int(expected["n_mel_chunks"])},
          "kept_frames": {"n": record.get("n_frames_kept"), "expected": want_kept,
                          "pass": record.get("n_frames_kept") == want_kept},
          "outside_window_static": {"n_bad": len(out_win), "first_bad": out_win[:5], "pass": not out_win},
          "outside_face_box_static": {"n_bad": len(out_box), "first_bad": out_box[:5], "pass": not out_box},
          "w2l_rendered": {"per_window": rendered, "pass": bool(rendered) and all(rendered)},
          "inbox_articulation": {"per_window": artic, "pass": bool(artic) and all(artic)},
          "decode_identity": decode_identity,
          "speech_gate": speech_gate,
          "window_mean_abs_diff": {"values": mad, "gating": False},
          "edge_step": {"values": edge, "gating": False},
          "mouth_vs_upper_mad": {"values": mvu, "gating": False}}
    ok = all(bool(v.get("pass", False)) for v in ck.values() if v.get("gating", True) is not False)
    return {"name": "talkface_00", "family": "TALKFACE", "checks": ck, "pass": ok}


BOX_EXIT = {0: "ok", 10: "s3fd_no_face"}           # = controls.refclips_d090.skips.box_exit (stop = 30)


def classify_box_exit(rc: int) -> str:
    """D-090 (owner 'As reviewers propose'): talkface_box exit 0 = ok, 10 = the pinned 'Face not detected'
    (s3fd_no_face, the only face skip); any other non-zero exit is a STOP (loader / sha / mel nan / import /
    OOM / traceback). Timeouts, ssh and transfer faults never reach here: the driver maps them to exit 75."""
    return BOX_EXIT.get(int(rc), "stop")


SKIPS = ("s3fd_no_face", "licence_not_adaptable")   # = controls.refclips_d090.skips.skip_on


def skip_record(face: dict, rank: int, reason: str, run_id: str) -> dict:
    if reason not in SKIPS:
        raise SystemExit(f"{reason!r} is not a pre-stated TALKFACE skip: STOP")
    return {"rank": rank, "source_sha256": face["source_sha256"], "skip_on": reason, "run_id": run_id}


def freeze_pins(text: str) -> dict[str, str]:
    """name -> version from a uv/pip lock or `pip freeze` (lines 'name==version', hashes and comments
    ignored; names lower-cased with '_' -> '-')."""
    out = {}
    for line in str(text).splitlines():
        s = line.strip().rstrip("\\").strip()
        if not s or s.startswith(("#", "--")) or "==" not in s:
            continue
        name, ver = s.split(";")[0].split("==", 1)
        out[name.strip().lower().replace("_", "-")] = ver.strip().split()[0]
    return out


def freeze_matches(lock_text: str, freeze_text: str) -> tuple[bool, list[str]]:
    """D-090 env gate: the box `pip freeze` must equal the hashed lock pins exactly (no extra, no missing,
    no version drift); a mismatch is a STOP."""
    a, b = freeze_pins(lock_text), freeze_pins(freeze_text)
    diff = [f"{k}: lock {a.get(k)} != box {b.get(k)}" for k in sorted(set(a) | set(b))
            if a.get(k) != b.get(k)]
    return not diff, diff


def static_luma(patch: np.ndarray, cfg: dict) -> dict[str, float]:
    """Descriptive (owner 'Accept both'): the unSHINEd face patch luma vs the LOC SHINE targets."""
    sh = cfg["controls"]["refclips"]["shine"]
    p = np.asarray(patch, np.float64)
    return {"mean": float(p.mean()), "rms": float(p.std()), "loc_mean": float(sh["mean_luma"]),
            "loc_rms": float(sh["rms_contrast"]), "gating": False}


def _sha_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _write_pcm(x: np.ndarray, path: Path, sr: int) -> None:
    R._write_wav(np.asarray(x, np.float64), Path(path), sr)


def _read_pcm(path: Path) -> np.ndarray:
    import wave

    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.int16)


def prepare_inputs(cfg: dict, clip, prov, face_rgb: np.ndarray, crop_box, out_dir: Path) -> dict:
    """D-090 --prepare (pod CPU). Private files in out_dir (never committed: they carry the face and the
    speech): static.png (3-channel grey 640 x 360), rendered48k.wav (the clip audio, as SPK / BURST),
    clip16k.wav (the Wav2Lip driving audio: resample_bandlimited 48 -> 16 kHz, pcm16, exactly 928000
    samples), utterances.npz (the placed utterances, for the speech gate) and rows.json (the tsv word rows).
    Returns the public, numbers-only record (shas, windows, expected chunk count, crop_box, luma stats)."""
    import copy

    import cv2

    from yct.tribe_run import locimg

    d90 = cfg["controls"]["refclips_d090"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clip = copy.deepcopy(clip)
    audio, rows = R.clip_audio(clip, prov)
    wins = speech_windows(clip.events)
    n16 = int(d90["driving_audio"]["n_samples"])
    n_chunks = expected_n_chunks(n16, R.FPS)
    if n_chunks != int(d90["expected"]["n_mel_chunks"]):
        raise SystemExit(f"expected mel chunks {n_chunks} != frozen {d90['expected']['n_mel_chunks']}: STOP")
    check_windows(wins, n_chunks, R.FPS)
    pcm48 = R._write_wav
    pcm48(audio, out_dir / "rendered48k.wav", R.SR)
    a16 = R.resample_bandlimited(audio, R.SR, int(d90["driving_audio"]["sr"]))
    if len(a16) != n16:
        raise SystemExit(f"16 kHz driving audio has {len(a16)} samples != {n16}: STOP")
    _write_pcm(a16, out_dir / "clip16k.wav", int(d90["driving_audio"]["sr"]))
    utters = {f"u{e['k']}": R.trim_to_span(prov(clip.family, int(e["utterance"]))[0], R.SR)
              for e in clip.events}
    np.savez(out_dir / "utterances.npz", **utters)
    (out_dir / "rows.json").write_text(json.dumps(rows))
    patch = locimg.patch(face_rgb, crop_box)
    static = R._u8(R._frame(patch))
    cv2.imwrite(str(out_dir / "static.png"), np.repeat(static[..., None], 3, 2))
    rec = {"windows": [[float(a), float(b)] for a, b in wins],
            "onsets": [float(e["onset"]) for e in clip.events],
            "utterance_s": [float(e["utterance_s"]) for e in clip.events],
            "n_mel_chunks_expected": n_chunks, "crop_box": [int(v) for v in crop_box],
            "static_png_sha256": _sha_file(out_dir / "static.png"),
            "clip16k_wav_sha256": _sha_file(out_dir / "clip16k.wav"),
            "rendered48k_sha256": _sha_file(out_dir / "rendered48k.wav"),
            "static_luma_vs_loc": static_luma(patch, cfg)}
    (out_dir / "inputs_record.json").write_text(json.dumps(rec, sort_keys=True))
    return rec


def _decoded_frame(mp4: Path, i: int, fps: int = R.FPS) -> np.ndarray:
    import subprocess

    raw = subprocess.run([*R.FF, "-i", str(mp4), "-vf", f"select=eq(n\\,{int(i)})", "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(R.H, R.W)


def finish_local(cfg: dict, inputs_dir: Path, talk_dir: Path, out_dir: Path) -> dict:
    """D-090 post-session finish (pod CPU): frames.npz sha vs the box record -> compose with the static frame
    -> the frozen SPK / BURST encode (refclips58.encode) twice (decode_identity: same decoded sha, tol 0)
    -> QC (with the constructive speech gate on the rendered 48 kHz audio). Returns numbers only; the clip
    and frames stay in out_dir / the private mirror (publish false)."""
    import cv2

    from yct.tribe_run import refclips_qc85 as Q  # noqa: N812

    d90 = cfg["controls"]["refclips_d090"]
    inputs_dir, talk_dir, out_dir = Path(inputs_dir), Path(talk_dir), Path(out_dir)
    rec = json.loads((talk_dir / "w2l_record.json").read_text())
    if _sha_file(talk_dir / "frames.npz") != rec.get("frames_sha256"):
        raise SystemExit("frames.npz sha256 != the box record frames_sha256: STOP")
    static = cv2.imread(str(inputs_dir / "static.png"))
    if static is None or not (np.array_equal(static[..., 0], static[..., 1])
                              and np.array_equal(static[..., 1], static[..., 2])):
        raise SystemExit("static.png is not the 3-channel grey static frame: STOP")
    static = np.ascontiguousarray(static[..., 0])
    with np.load(talk_dir / "frames.npz") as z:
        w2l = {int(k[1:]): z[k] for k in z.files}
    meta = json.loads((inputs_dir / "inputs_record.json").read_text())
    wins = [tuple(w) for w in meta["windows"]]
    frames = compose(static, w2l, wins)
    pcm = _read_pcm(inputs_dir / "rendered48k.wav")
    audio = pcm.astype(np.float64) / 32767
    rows = [tuple(r) for r in json.loads((inputs_dir / "rows.json").read_text())]
    shas, dec = [], []
    for k in ("a", "b"):
        shas.append(R.encode(frames, audio, rows, out_dir / k, "talkface_00", cfg))
        dec.append(R.decoded_sha(out_dir / k / "talkface_00.mp4"))
    for f in ("mp4", "wav", "tsv"):
        src = out_dir / "a" / f"talkface_00.{f}"
        src.replace(out_dir / f"talkface_00.{f}")
    dident = {"decoded_sha256": dec, "mp4_sha256": [s["mp4"] for s in shas],
              "pass": dec[0] == dec[1] and shas[0] == shas[1]}
    with np.load(inputs_dir / "utterances.npz") as z:
        place = [(float(o), z[f"u{k}"]) for k, o in enumerate(meta["onsets"])]
    gate = Q.speech_gate(pcm, Q.pcm16(R.bed()), R.bed(), place)
    q = qc(frames, static, wins, face_box=rec["face_box"], record=rec, expected=d90["expected"],
           speech_gate=gate, decode_identity=dident)
    dv = []
    for t in [o + 0.5 for o in meta["onsets"]]:
        i = int(round(t * R.FPS))
        dec_i = _decoded_frame(out_dir / "talkface_00.mp4", i).astype(np.int16)
        d = np.abs(dec_i - frames[i].astype(np.int16))
        dv.append({"frame": i, "max_abs_diff": int(d.max()), "mean_abs_diff": float(d.mean())})
    q["checks"]["decoded_vs_composed"] = {"frames": dv, "gating": False}
    return {"qc": q, "sha256": shas[0], "decoded_sha256": dec[0], "n_frames": len(frames),
            "frames_sha256": rec["frames_sha256"], "static_luma_vs_loc": meta.get("static_luma_vs_loc")}


def public_numbers(obj: Any) -> str:
    """The JSON that may be committed: numbers and shas only (frames are never serialised)."""
    return json.dumps(obj, default=lambda x: None if isinstance(x, np.ndarray) else str(x), sort_keys=True)
