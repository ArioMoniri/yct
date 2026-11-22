"""T-NAT0 pyannote setup step (D-075 §1/§3; yct pod; run with the pinned WhisperX env /work/yct/venv_wx).

  download MIRROR      snapshot_download the pinned repos (3 from D-075 + the community-1 plda/
                       subfolder, D-082 draft) (owner-accepted HF gates; the token
                       is read by huggingface_hub from $HF_TOKEN_PATH, a umask-077 file the wrapper
                       pipes from SSM /yct/hf_token and shreds afterwards; never printed) into
                       MIRROR/<repo>; print the shas
  upload MIRROR        mirror -> controls.refclips.s3_root/<refclips_auto.nat.weights_mirror>pyannote/
  verify MIRROR WORK   load 3.1 OFFLINE (HF_HUB_OFFLINE=1) under pyannote.audio 4.1.0 from the mirror on
                       CPU and diarize a synthetic two-voice espeak-ng fixture; exit 0 iff it loads
                       and returns exactly two speakers
                       (a load failure is a STOP to the council: no switch to another pipeline)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.curate import nat0_box as nb  # noqa: E402


def pins(cfg: dict) -> dict[str, tuple[str, str]]:
    d = cfg["controls"]["refclips_auto"]["nat"]["diarization"]
    seg_repo, seg_rev = d["segmentation"].split("@")
    emb_repo, emb_rev = d["embedding"].split("@")
    plda = cfg["controls"]["refclips_d082"]["plda"]           # D-082 draft (BUG-040)
    return {"diarization": (d["pipeline"], d["revision"]), "segmentation": (seg_repo, seg_rev),
            "embedding": (emb_repo, emb_rev), "plda": (plda["repo"], plda["revision"])}


def allow_patterns(k: str) -> list[str] | None:
    """Only the plda/ subfolder of community-1 is mirrored (its own models are never loaded)."""
    return ["plda/*"] if k == "plda" else None


def fixture_ok(segs: list) -> bool:
    """The A-B-A two-voice fixture must come back as exactly two speakers (diarisation is correct)."""
    return bool(segs) and len({s[2] for s in segs}) == 2


def download(mirror: Path) -> dict:
    from huggingface_hub import snapshot_download

    out = {}
    for k, (repo, rev) in pins(load_config()).items():
        d = mirror / nb.REPOS[k]
        snapshot_download(repo_id=repo, revision=rev, local_dir=str(d), allow_patterns=allow_patterns(k))
        out[f"pyannote_{k}_sha256"] = nb.dir_sha(d)
    return out


def upload(mirror: Path) -> None:
    cfg = load_config()
    root = cfg["controls"]["refclips"]["s3_root"].rstrip("/")
    dest = f"{root}/{cfg['controls']['refclips_auto']['nat']['weights_mirror'].strip('/')}/pyannote/"
    subprocess.run(["aws", "s3", "sync", "--only-show-errors", "--region", "eu-central-1", "--exclude",
                    "*/.cache/*", str(mirror), dest], check=True)
    print(dest)


def two_voice_fixture(work: Path) -> Path:
    """Two espeak-ng voices, A-B-A (synthetic; no real recording)."""
    import numpy as np
    import soundfile as sf

    work.mkdir(parents=True, exist_ok=True)
    parts = []
    texts = [("en-us+m3", "The quick brown fox jumps over the lazy dog. " * 2),
             ("en-us+f4", "Pack my box with five dozen liquor jugs, she said. " * 2),
             ("en-us+m3", "Then the fox ran into the forest and was gone. " * 2)]
    for i, (voice, text) in enumerate(texts):
        f = work / f"part{i}.wav"
        subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(f), text], check=True)
        subprocess.run(["ffmpeg", "-y", "-nostdin", "-v", "error", "-i", str(f), "-ac", "1", "-ar",
                        str(nb.SR), str(f.with_suffix(".16k.wav"))], check=True)
        x, _ = sf.read(str(f.with_suffix(".16k.wav")), dtype="float32")
        parts += [x, np.zeros(nb.SR // 2, np.float32)]
    out = work / "two_voice.wav"
    sf.write(str(out), np.concatenate(parts), nb.SR, subtype="PCM_16")
    return out


def verify(mirror: Path, work: Path) -> dict:
    import importlib.metadata as md

    want = {k: v for k, v in {k.removeprefix("pyannote_").removesuffix("_sha256"): v
                              for k, v in load_config()["controls"]["refclips_auto_artifacts"].items()
                              if k.startswith("pyannote_")}.items()}
    shas = {k: nb.dir_sha(mirror / n) for k, n in nb.REPOS.items()}
    if all(want.values()) and shas != want:
        raise SystemExit(f"mirror shas {shas} != config {want}")
    pipe = nb.load_pipeline(mirror, work / "cfg", "cpu")
    segs = nb.diarize(pipe, nb.read_wav(two_voice_fixture(work)))
    res = {"pyannote.audio": md.version("pyannote.audio"), "n_turns": len(segs),
           "n_speakers": len({s[2] for s in segs}), "speech_s": round(sum(e - s for s, e, _ in segs), 3),
           "mirror_shas": shas}
    res["plda_loaded"] = getattr(pipe, "_plda", None) is not None
    res["clustering"] = getattr(pipe, "klustering", None)
    print(json.dumps(res))
    if md.version("pyannote.audio") != "4.1.0" or not fixture_ok(segs):
        raise SystemExit(f"STOP: 3.1 under pyannote.audio 4.1.0 did not run cleanly: {res}")
    return res


if __name__ == "__main__":
    cmd, rest = sys.argv[1], [Path(p) for p in sys.argv[2:]]
    if cmd == "download":
        print(json.dumps(download(rest[0]), indent=1))
    elif cmd == "upload":
        upload(rest[0])
    elif cmd == "verify":
        verify(rest[0], rest[1])
    else:
        raise SystemExit(__doc__)
