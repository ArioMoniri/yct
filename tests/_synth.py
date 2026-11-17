"""Synthetic media generators for P2/P3 tests (ffmpeg lavfi only; no real videos, no network)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from yct.config import load_config, with_overrides

FAST = {"normalize": {"video": {"preset": "ultrafast"}}}


def fast_cfg(**extra) -> dict:
    cfg = with_overrides(load_config(), FAST)
    return with_overrides(cfg, extra) if extra else cfg


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-nostdin", *args], check=True)


def enc(out: Path) -> list[str]:
    return ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)]


def clip(out: Path, *, size="640x360", dur=4.0, fps=30, freq=220, vf: str | None = None,
         audio: str | None = None) -> Path:
    """testsrc2 video + sine audio (stereo, identical channels)."""
    a = audio or f"sine=f={freq}:r=48000:d={dur},aformat=channel_layouts=stereo"
    v = f"testsrc2=s={size}:r={fps}:d={dur}" + (f",{vf}" if vf else "")
    ff("-f", "lavfi", "-i", v, "-f", "lavfi", "-i", a, "-shortest", *enc(out))
    return out


def padded_clip(out: Path, lead=2.0, body=4.0, tail=1.5, size="640x360") -> Path:
    """black+silent lead, testsrc2+sine body, black+silent tail."""
    ff(
        "-f", "lavfi", "-i", f"color=black:s={size}:r=30:d={lead}",
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={lead}",
        "-f", "lavfi", "-i", f"testsrc2=s={size}:r=30:d={body}",
        "-f", "lavfi", "-i", f"sine=f=220:r=48000:d={body},aformat=channel_layouts=stereo",
        "-f", "lavfi", "-i", f"color=black:s={size}:r=30:d={tail}",
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={tail}",
        "-filter_complex", "[0][1][2][3][4][5]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", *enc(out),
    )
    return out


def inverted_stereo_clip(out: Path, dur=3.0) -> Path:
    """Right channel = -left channel (mono sum cancels)."""
    return clip(out, dur=dur, audio=f"sine=f=330:r=48000:d={dur},pan=stereo|c0=c0|c1=-1*c0")


def vfr_clip(out: Path, dur=4.0) -> Path:
    """Variable frame rate: drop 2 of every 3 frames during the first second, keep all afterwards."""
    ff("-f", "lavfi", "-i", f"testsrc2=s=640x360:r=30:d={dur}",
       "-f", "lavfi", "-i", f"sine=f=220:r=48000:d={dur}",
       "-vf", "select='gte(t\\,1)+not(mod(n\\,3))'", "-fps_mode", "vfr", "-shortest", *enc(out))
    return out


def av_offset_clip(out: Path, offset_s=0.1, dur=3.0) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=s=640x360:r=30:d={dur}",
       "-itsoffset", str(offset_s), "-f", "lavfi", "-i", f"sine=f=220:r=48000:d={dur}",
       "-map", "0:v", "-map", "1:a", *enc(out))
    return out
