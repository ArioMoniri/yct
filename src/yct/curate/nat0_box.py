"""T-NAT0 session-0 box side (D-075 §3 N1/N2). Runs in the pinned WhisperX env (faster-whisper 1.2.1,
pyannote.audio 4.1.0; outputs/runs/wave1p2b_20261117T234829Z/wx_pip_freeze.txt) on the buffer's 16 kHz
mono T1 wavs (the normalised clip's own audio, so the samples are those that enter the clip):

  N1  faster_whisper.WhisperModel(large-v3).detect_language on samples [0, 30 s) -> all language probs
  N2  pyannote/speaker-diarization-3.1 (pinned revisions, loaded OFFLINE from the S3 mirror) -> segments

    python -m yct.curate.nat0_box --wavs DIR --mirror DIR --out OUT.json [--device cuda]

Only numbers leave the box (language probabilities, speaker turns); no text. The decision rules
(thresholds) live in yct.curate.refstim_auto.nat_decide, applied on the pod."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

REPOS = {"diarization": "speaker-diarization-3.1", "segmentation": "segmentation-3.0",
         "embedding": "wespeaker-voxceleb-resnet34-LM",
         "plda": "speaker-diarization-community-1"}     # D-082 draft: only its plda/ subfolder is mirrored
PLDA_FILES = ("plda.npz", "xvec_transform.npz")
SR = 16000


def dir_sha(d: Path) -> str:
    """sha256 of the sorted '<relpath>\\t<sha256>' lines of every file under d (HF .cache metadata
    excluded): the artifact sha of one mirrored model repo."""
    lines = []
    for p in sorted(x for x in Path(d).rglob("*") if x.is_file() and ".cache" not in x.parts):
        lines.append(f"{p.relative_to(d).as_posix()}\t{hashlib.sha256(p.read_bytes()).hexdigest()}")
    if not lines:
        raise RuntimeError(f"empty model dir {d}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def check_mirror(mirror: Path, want: dict[str, str]) -> None:
    for k, name in REPOS.items():
        got = dir_sha(mirror / name)
        if got != want[k]:
            raise SystemExit(f"pyannote {k} mirror sha {got[:12]} != frozen {want[k][:12]}")


def patched_config(mirror: Path, out_dir: Path) -> Path:
    """The pinned 3.1 pipeline config with its two model references pointed at the local mirror (the
    original config file is unchanged and covered by the diarization sha), plus the pinned
    community-1 PLDA passed explicitly (D-082 draft; loaded by 4.1.0, unused by AgglomerativeClustering)."""
    import yaml

    c = yaml.safe_load((mirror / REPOS["diarization"] / "config.yaml").read_text())
    p = c["pipeline"]["params"]
    if p.get("segmentation") != "pyannote/segmentation-3.0" or \
            p.get("embedding") != "pyannote/wespeaker-voxceleb-resnet34-LM":
        raise SystemExit(f"unexpected 3.1 pipeline params {p}")
    if p.get("clustering") != "AgglomerativeClustering":
        # pyannote.audio 4.1.0 applies the PLDA only under VBxClustering (D-082 draft): refuse it
        raise SystemExit(f"unexpected 3.1 clustering {p.get('clustering')!r}, need AgglomerativeClustering")
    plda = mirror / REPOS["plda"] / "plda"
    missing = [f for f in PLDA_FILES if not (plda / f).is_file()]
    if missing:
        raise SystemExit(f"incomplete plda mirror {plda}: missing {missing}")
    p["segmentation"] = str(mirror / REPOS["segmentation"] / "pytorch_model.bin")
    p["embedding"] = str(mirror / REPOS["embedding"] / "pytorch_model.bin")
    p["plda"] = str(plda)     # explicit, so 4.1.0 never reaches for the unpinned hub default
    out_dir.mkdir(parents=True, exist_ok=True)
    f = out_dir / "config.yaml"
    f.write_text(yaml.safe_dump(c, sort_keys=False))
    return f


def load_pipeline(mirror: Path, work: Path, device: str = "cpu"):
    os.environ["HF_HUB_OFFLINE"] = "1"
    import torch
    from pyannote.audio import Pipeline

    pipe = Pipeline.from_pretrained(str(patched_config(mirror, work)))
    if pipe is None:
        raise SystemExit("pyannote Pipeline.from_pretrained returned None")
    return pipe.to(torch.device(device))


def read_wav(path: Path):
    import numpy as np
    import soundfile as sf

    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SR or x.shape[1] != 1:
        raise SystemExit(f"{path.name}: {sr} Hz x {x.shape[1]} ch, need {SR} mono")
    x = x[:, 0]
    if not np.isfinite(x).all():
        raise SystemExit(f"{path.name}: non-finite samples")
    return x


def _torch_waveform(x):
    import torch

    return torch.from_numpy(x).unsqueeze(0)


def diarize(pipe, x, waveform=_torch_waveform) -> list[list]:
    out = pipe({"waveform": waveform(x), "sample_rate": SR})
    ann = getattr(out, "speaker_diarization", out)    # pyannote.audio 4.x DiarizeOutput or Annotation
    return [[float(t.start), float(t.end), str(s)] for t, _, s in ann.itertracks(yield_label=True)]


def lang_probs(model, x, samples_s: list[float]) -> dict[str, float]:
    a, b = int(samples_s[0] * SR), int(samples_s[1] * SR)
    _lang, _p, allp = model.detect_language(x[a:b])
    return {str(k): float(v) for k, v in allp}


def main(argv: list[str] | None = None) -> int:
    import importlib.metadata as md

    ap = argparse.ArgumentParser()
    ap.add_argument("--wavs", required=True)
    ap.add_argument("--mirror", required=True)
    ap.add_argument("--shas", required=True, help="JSON {diarization, segmentation, embedding, plda} frozen shas")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--samples-s", default="0,30")
    a = ap.parse_args(argv)
    vers = {p: md.version(p) for p in ("faster-whisper", "pyannote.audio")}
    if vers != {"faster-whisper": "1.2.1", "pyannote.audio": "4.1.0"}:
        raise SystemExit(f"unpinned env {vers}")
    mirror = Path(a.mirror)
    check_mirror(mirror, json.loads(a.shas))
    from faster_whisper import WhisperModel

    ct = "float16" if a.device == "cuda" else "int8"
    model = WhisperModel("large-v3", device=a.device, compute_type=ct)
    pipe = load_pipeline(mirror, Path(a.out).parent / "pyannote_cfg", a.device)
    samples = [float(s) for s in a.samples_s.split(",")]
    res = {"versions": vers, "results": {}}
    for w in sorted(Path(a.wavs).glob("*.wav")):
        x = read_wav(w)
        res["results"][w.stem] = {"lang_probs": lang_probs(model, x, samples),
                                  "segments": diarize(pipe, x), "n_samples": int(len(x))}
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({"n": len(res["results"]), **vers}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
