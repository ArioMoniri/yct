"""D-085 part 2 step 4, box side: run the PINNED Wav2Lip (bac9a81) inference with the frozen NOGAN loader.

  python -m yct.tribe_run.talkface_box --repo W2L --weights W --weights-sha S --s3fd P --s3fd-sha S \
      --face static.png --audio clip16k.wav --fps 30 --windows '[[a, b], ...]' --out frames.npz \
      --record rec.json
  (--fixture-box y1 y2 x1 x2: CPU rehearsal on a synthetic image, s3fd bypassed through the pinned --box arg)

The pinned inference module is imported with its own argparse (sys.argv set first) and used unchanged:
audio.load_wav / melspectrogram, the mel chunking of inference.main (copied line for line: 80/fps,
mel_step_size 16), datagen (s3fd face_detect on the static frame), the pinned models.Wav2Lip forward. Only
two things differ from inference.main: the model comes from wav2lip_loader.load_nogan (strict state_dict,
sha-checked, no GAN), and frames are kept losslessly (grey uint8, only the in-window indices) instead of the
DIVX .avi + ffmpeg mux. s3fd weights are placed at the path the pinned SFDDetector reads (no download).
The record holds numbers only; the frames file stays private (internal TALKFACE clip).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    for k in ("--repo", "--weights", "--weights-sha", "--face", "--audio", "--out", "--record", "--windows"):
        ap.add_argument(k, required=True)
    ap.add_argument("--s3fd")
    ap.add_argument("--s3fd-sha")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--fixture-box", type=int, nargs=4)
    a = ap.parse_args(argv)
    import numpy as np
    import torch

    repo = Path(a.repo).resolve()
    rec: dict = {"torch": torch.__version__, "cuda": torch.cuda.is_available()}
    sfd = repo / "face_detection" / "detection" / "sfd" / "s3fd.pth"
    if a.fixture_box is None:
        if not a.s3fd or _sha(Path(a.s3fd)) != a.s3fd_sha:
            raise SystemExit("s3fd weights sha256 != the frozen face_detector_sha256: STOP")
        shutil.copyfile(a.s3fd, sfd)
        rec["s3fd_sha256"] = _sha(sfd)
    sys.path.insert(0, str(repo))
    import os

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
    if np.isnan(mel.reshape(-1)).sum() > 0:
        raise SystemExit("Mel contains nan (pinned check): wav2lip_error")
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
                g = (0.2126 * f[..., 2] + 0.7152 * f[..., 1] + 0.0722 * f[..., 0])
                out[f"f{j:05d}"] = g.round().clip(0, 255).astype(np.uint8)
            j += 1
        rec["face_box"] = [int(v) for v in coords[0]]
    np.savez_compressed(a.out, **out)
    rec.update(n_frames_total=j, n_frames_kept=len(out), frames_sha256=_sha(Path(a.out)))
    Path(a.record).write_text(json.dumps(rec, sort_keys=True))
    print(json.dumps({k: rec[k] for k in ("n_mel_chunks", "n_frames_total", "n_frames_kept")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
