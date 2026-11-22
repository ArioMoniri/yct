"""D-085 part 2: the pinned espeak-ng engine (council B1).

Synthesis first re-hashes the pod's binary, library and data tree against `speech.engine_pin` and stops on
any mismatch (never reinstall-and-continue). The data-tree hash is the method recorded on the pod:
`cd DATA && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`.

The synthesiser returns the waveform on the build's path (R-11 S-23/S-24): the native 22050 Hz output is
band-limited resampled (refclips58.resample_bandlimited, polyphase Kaiser FIR) to `speech.selection_sr`
(48 kHz), so the corpus-selection span and the build's span are measured on the same signal.
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import wave
from pathlib import Path

import numpy as np


def _file_sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def data_tree_sha256(data_dir: Path) -> str:
    d = Path(data_dir)
    rels = sorted(("./" + p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()),
                  key=lambda s: s.encode())
    lines = "".join(f"{_file_sha(d / r[2:])}  {r}\n" for r in rels)
    return hashlib.sha256(lines.encode()).hexdigest()


def n_data_files(data_dir: Path) -> int:
    return sum(1 for p in Path(data_dir).rglob("*") if p.is_file())


def verify_engine(pin: dict, paths: dict) -> dict[str, str]:
    """Fail closed: every recorded sha must match the installed engine (STOP to the owner otherwise)."""
    got = {"binary": _file_sha(paths["binary"]), "lib": _file_sha(paths["lib"]),
           "data_tree": data_tree_sha256(paths["data_dir"])}
    want = {"binary": pin["binary_sha256"], "lib": pin["lib_sha256"], "data_tree": pin["data_tree_sha256"]}
    bad = [k for k in want if got[k] != want[k]]
    if bad:
        raise SystemExit(f"espeak-ng engine differs from the frozen engine_pin ({bad}): STOP to the owner "
                         "(no reinstall, no synthesis)")
    return got


def _wav_to_float(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise SystemExit("espeak-ng output is not 16-bit mono: STOP")
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768.0
    return x, sr


class EspeakSynth:
    """Callable text -> (waveform in full-scale units at selection_sr, selection_sr)."""

    def __init__(self, spec: dict, paths: dict | None = None):
        self.spec = spec
        self.paths = {k: Path(v) for k, v in (paths or spec["engine_paths"]).items()}
        self.verified = verify_engine(spec["engine_pin"], self.paths)

    def args(self, text: str) -> list[str]:
        s = self.spec
        return [str(self.paths["binary"]), "-v", s["voice"], "-s", str(s["rate_wpm"]), "-p", str(s["pitch"]),
                "-a", str(s["amplitude"]), "--stdout", text]

    def __call__(self, text: str) -> tuple[np.ndarray, int]:
        from yct.tribe_run.refclips58 import resample_bandlimited

        r = subprocess.run(self.args(text), check=True, capture_output=True)
        x, sr = _wav_to_float(r.stdout)
        if sr != self.spec["engine_pin"]["native_sr"]:
            raise SystemExit(f"espeak-ng rate {sr} != the pinned native_sr: STOP")
        out_sr = int(self.spec["selection_sr"])
        return resample_bandlimited(x, sr, out_sr), out_sr
