"""Load config.yaml (every tunable lives there; v2.md §3)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or CONFIG_PATH) as fh:
        return yaml.safe_load(fh) or {}


def with_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge `overrides` into a copy of `cfg` (tests use this, e.g. a faster x264 preset)."""
    out = copy.deepcopy(cfg)

    def merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(out, overrides)
    return out
