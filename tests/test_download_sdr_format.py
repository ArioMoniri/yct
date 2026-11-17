"""ENH-006: scripts/owner_download_youtube.sh prefers SDR formats; the old selector stays as its tail
(backward compatible). The default selector is read from the script (static checks; yt-dlp is not in
requirements.lock, so its selector semantics were checked by hand with yt-dlp 2026.10.26:
SDR 360p preferred over HDR10/HLG 720p; unknown dynamic_range kept; HDR-only falls back)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "owner_download_youtube.sh"
OLD = "b[ext=mp4][height>=360]/b[ext=mp4]/b"


def default_format() -> str:
    text = SCRIPT.read_text()
    sdr = re.search(r"^SDR_FORMAT='([^']+)'$", text, re.M).group(1)
    fmt = re.search(r'^FORMAT="\$\{FORMAT:-\$SDR_FORMAT/([^}]+)\}"$', text, re.M).group(1)
    return f"{sdr}/{fmt}"


def test_script_uses_format_variable_and_keeps_old_selector_as_tail():
    text = SCRIPT.read_text()
    assert '-f "$FORMAT"' in text and '-f "b[ext=mp4]' not in text
    f = default_format()
    assert f.endswith("/" + OLD)
    head = f[: -len(OLD)]
    assert "[dynamic_range=?SDR]" in head and "[vcodec!*=vp09.02]" in head
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
