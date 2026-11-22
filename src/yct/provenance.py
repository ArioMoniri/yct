"""R-11 X-02: toolchain record (ffmpeg build, linked libs, binary sha256) for every new P2/P3/NAT run dir."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def toolchain_record(run: Callable[[list[str]], str] = _run,
                     which: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    lines = run(["ffmpeg", "-nostdin", "-version"]).splitlines()
    libs = " | ".join(x.strip() for x in lines if x.strip().startswith("lib"))
    path = which("ffmpeg")
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None
    return {"ffmpeg_version": lines[0] if lines else "", "libs": libs, "ffmpeg_path": path,
            "ffmpeg_sha256": sha}
