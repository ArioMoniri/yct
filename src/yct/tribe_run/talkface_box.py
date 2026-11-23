"""D-085 part 2 step 4 / D-090 draft, box side: run the PINNED Wav2Lip (bac9a81) inference with the frozen
NOGAN loader.

  python -m yct.tribe_run.talkface_box --repo W2L --weights W --weights-sha S --s3fd P --s3fd-sha S \
      --face static.png --face-sha S --audio clip16k.wav --audio-sha S --fps 30 --windows '[[a, b], ...]' \
      --out frames.npz --record rec.json
  (--fixture-box y1 y2 x1 x2: CPU rehearsal on a synthetic image, s3fd bypassed through the pinned --box arg)

The pinned inference module is imported with its own argparse (sys.argv set first) and used unchanged:
audio.load_wav / melspectrogram, the mel chunking of inference.main (copied line for line: 80/fps,
mel_step_size 16), datagen (s3fd face_detect on the static frame), the pinned models.Wav2Lip forward. Only
two things differ from inference.main: the model comes from wav2lip_loader.load_nogan (strict state_dict,
sha-checked, no GAN), and frames are kept losslessly (grey uint8 via locimg.grey709, only the in-window
indices) instead of the DIVX .avi + ffmpeg mux. s3fd weights are placed where the pinned SFDDetector reads
them (no download). The record holds numbers only; the frames file stays private (internal TALKFACE clip).

Exit codes (D-090 skips.box_exit; owner 2026-11-23 "As reviewers propose"): 0 ok; 10 = the pinned "Face not
detected" (s3fd_no_face, the only face skip); 30 = STOP (input / weights / s3fd sha, loader, mel NaN, import,
OOM, any traceback). The driver maps timeouts, ssh and transfer faults to exit 75 itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import traceback
from pathlib import Path

EXIT_OK, EXIT_NO_FACE, EXIT_STOP = 0, 10, 30


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def box_grey(bgr):
    """BT.709 luma of a BGR uint8 frame = locimg.grey709 on the RGB order (bit for bit, D-090 frames.luma)."""
    import numpy as np

    from yct.tribe_run import locimg

    return locimg.grey709(np.ascontiguousarray(bgr[..., ::-1]))


def _args(argv: list[str] | None):
    ap = argparse.ArgumentParser()
    for k in ("--repo", "--weights", "--weights-sha", "--face", "--face-sha", "--audio", "--audio-sha",
              "--out", "--record", "--windows"):
        ap.add_argument(k, required=True)
    ap.add_argument("--s3fd")
    ap.add_argument("--s3fd-sha")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--fixture-box", type=int, nargs=4)
    a = ap.parse_args(argv)
    for k in ("repo", "weights", "face", "audio", "out", "record", "s3fd"):   # BUG-049: before the chdir
        if getattr(a, k):
            setattr(a, k, str(Path(getattr(a, k)).resolve()))
    return a


def _run(a) -> int:
    import os

    import numpy as np
    import torch

    for p, want, what in ((a.face, a.face_sha, "static.png"), (a.audio, a.audio_sha, "clip16k.wav")):
        if _sha(Path(p)) != want:
            raise SystemExit(f"{what} sha256 != the inputs record: STOP")
    repo = Path(a.repo).resolve()
    rec: dict = {"torch": torch.__version__, "cuda": torch.cuda.is_available()}
    sfd = repo / "face_detection" / "detection" / "sfd" / "s3fd.pth"
    if a.fixture_box is None:
        if not a.s3fd or _sha(Path(a.s3fd)) != a.s3fd_sha:
            raise SystemExit("s3fd weights sha256 != the frozen face_detector_sha256: STOP")
        shutil.copyfile(a.s3fd, sfd)
        rec["s3fd_sha256"] = _sha(sfd)
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    Path("temp").mkdir(exist_ok=True)
    pinned = ["inference.py", "--checkpoint_path", str(a.weights), "--face", str(a.face), "--audio",
              str(a.audio), "--static", "True", "--fps", str(a.fps)]
    if a.fixture_box is not None:
        pinned += ["--box", *map(str, a.fixture_box)]
    sys.argv = pinned
    import inference  # noqa: E402  (pinned upstream module; parses sys.argv at import)
    from models import Wav2Lip  # noqa: E402

    from yct.tribe_run.wav2lip_loader import load_nogan

    model, info = load_nogan(Path(a.weights), a.weights_sha, Wav2Lip, torch)
    model = model.to(inference.device).eval()
    rec.update(loader=info, device=inference.device)
    import cv2

    full_frames = [cv2.imread(str(a.face))]
    wav = inference.audio.load_wav(str(a.audio), 16000)
    mel = inference.audio.melspectrogram(wav)
    rec["n_mel_frames"] = int(mel.shape[1])
    if np.isnan(mel.reshape(-1)).sum() > 0:
        raise SystemExit("Mel contains nan (pinned check): STOP (an audio fault, never a face skip)")
    mel_chunks, mult, i = [], 80. / a.fps, 0          # inference.main, line for line
    while 1:
        start_idx = int(i * mult)
        if start_idx + inference.mel_step_size > len(mel[0]):
            mel_chunks.append(mel[:, len(mel[0]) - inference.mel_step_size:])
            break
        mel_chunks.append(mel[:, start_idx: start_idx + inference.mel_step_size])
        i += 1
    rec["n_mel_chunks"] = len(mel_chunks)
    windows = [tuple(w) for w in json.loads(a.windows)]
    keep = {j for j in range(len(mel_chunks)) if any(x <= j / a.fps < y for x, y in windows)}
    out, j = {}, 0
    for img_batch, mel_batch, frames, coords in inference.datagen(full_frames.copy(), mel_chunks):
        img_batch = torch.FloatTensor(np.transpose(img_batch, (0, 3, 1, 2))).to(inference.device)
        mel_batch = torch.FloatTensor(np.transpose(mel_batch, (0, 3, 1, 2))).to(inference.device)
        with torch.no_grad():
            pred = model(mel_batch, img_batch)
        pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.
        for p, f, c in zip(pred, frames, coords, strict=True):
            y1, y2, x1, x2 = c
            p = cv2.resize(p.astype(np.uint8), (x2 - x1, y2 - y1))
            f[y1:y2, x1:x2] = p
            if j in keep:
                out[f"f{j:05d}"] = box_grey(f)
            j += 1
        rec["face_box"] = [int(v) for v in coords[0]]
    np.savez_compressed(a.out, **out)
    rec.update(n_frames_total=j, n_frames_kept=len(out), frames_sha256=_sha(Path(a.out)))
    Path(a.record).write_text(json.dumps(rec, sort_keys=True))
    print(json.dumps({k: rec[k] for k in ("n_mel_chunks", "n_frames_total", "n_frames_kept")}))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    a = _args(argv)
    try:
        return _run(a)
    except BaseException as exc:  # noqa: BLE001 - every failure is classified, never swallowed silently
        msg = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        if "Face not detected" in msg:
            print(f"TALKFACE_BOX_EXIT {EXIT_NO_FACE} s3fd_no_face", flush=True)
            return EXIT_NO_FACE
        print(f"TALKFACE_BOX_EXIT {EXIT_STOP} stop: {msg[:300]}", flush=True)
        return EXIT_STOP


if __name__ == "__main__":
    raise SystemExit(main())
