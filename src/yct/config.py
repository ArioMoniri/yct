"""Load config.yaml (every tunable lives there; v2.md §3)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load_config(path: str | Path | None = None, validate: bool = True) -> dict[str, Any]:
    """Parsed config.yaml. validate=True (default) checks it against yct.config_schema (unknown keys,
    missing keys and wrong types raise pydantic.ValidationError)."""
    with open(path or CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh) or {}
    if validate:
        from yct.config_schema import validate_config

        validate_config(cfg)
    return cfg


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
