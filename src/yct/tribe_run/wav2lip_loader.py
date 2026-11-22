"""D-085 part 2 (council B2/B3): load the official Wav2Lip-SD-NOGAN.pt into the pinned bac9a81 class.

Council ruling: option (b) (an upstream commit whose own loader reads the SD archive), fixed fallback (a).
Upstream master HEAD is the pinned revision bac9a81 and no commit in its history loads the SD archives, so
(b) does not exist and (a) applies; this was established before any real-face run. Path (a), decided on a
synthetic fixture only (outputs/runs/d085p2_loader_check/loader_check.json): the archive's state_dict loads
into the pinned `models.Wav2Lip` with strict=True (352/352 keys, equal shapes) and reproduces the TorchScript
forward exactly, so the pinned forward pass and preprocessing stay unchanged. There is no silent jit
fallback: a strict failure is a STOP. GAN is never used.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any


def load_nogan(weights: Path, expect_sha256: str, model_cls: Callable[[], Any],
               torch: Any) -> tuple[Any, dict]:
    w = Path(weights)
    if "GAN" in w.name and "NOGAN" not in w.name:
        raise SystemExit(f"{w.name}: the GAN model is never used (council D-085 part 2)")
    got = hashlib.sha256(w.read_bytes()).hexdigest()
    if got != expect_sha256:
        raise SystemExit(f"{w.name}: sha256 {got[:12]}… != the frozen weights_sha256: STOP to the owner")
    arch = torch.jit.load(str(w), map_location="cpu")
    sd = arch.state_dict()
    m = model_cls()
    try:
        m.load_state_dict(sd, strict=True)
    except RuntimeError as e:
        raise SystemExit(f"NOGAN state_dict does not load strict into the pinned class ({e}): STOP "
                         "(the path was decided on the fixture; no jit fallback)") from e
    m.eval()
    return m, {"path": "strict_state_dict", "n_keys": len(sd)}
