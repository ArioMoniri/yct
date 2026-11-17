"""M1 network features from TRIBE predictions (v2.md §1 "Primary features, M1 (k = 7)").

Pipeline per video, for a prediction ``pred`` of shape (T, 20484):

1. :func:`spatial_standardize`: at each TR, centre and scale across non-medial-wall vertices
   (medial wall -> NaN; the medial wall is the union mask of ``atlas.load_all``, D-034; ddof
   from ``features.standardize_ddof``, independent of ``features.spatial_sd_ddof``). Never
   z-score per vertex over time (that zeroes every mean [B1]).
2. :func:`window_average` over W = [start, start + length) TRs.
3. :func:`yeo7_means`: network means. The size-weighted sum of the 7 means is 0 (rank 6), so
   M1 keeps the 6 non-limbic networks; Limbic is the omitted reference.
4. 7th feature: the time-averaged spatial SD of the *raw* prediction over cortex
   (:func:`spatial_sd`), which keeps the contrast signal that standardisation removes.

Secondary: :func:`global_amplitude` G = window-mean of the per-TR cortical mean of the raw
prediction (relative z-units; TRIBE targets were z-scored, tribe_requirements §3).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from yct.config import load_config
from yct.features.atlas import Atlas


def _feat_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return (cfg if cfg is not None else load_config())["features"]


def _check(pred: np.ndarray, mask: np.ndarray) -> np.ndarray:
    pred = np.asarray(pred, dtype=np.float64)
    if pred.ndim == 1:
        pred = pred[None, :]
    if pred.shape[-1] != mask.shape[0]:
        raise ValueError(f"prediction has {pred.shape[-1]} vertices, mask {mask.shape[0]}")
    return pred


def spatial_standardize(pred: np.ndarray, medial_wall: np.ndarray, ddof: int = 0) -> np.ndarray:
    """Per-TR z-score across cortex (non-medial vertices); medial wall set to NaN.

    Raises on any non-finite cortical value: one NaN vertex would otherwise silently turn the
    whole TR into NaN (G-D032 Biostat D4).
    """
    x = _check(pred, medial_wall)
    ctx = x[:, ~medial_wall]
    if not np.isfinite(ctx).all():
        bad = np.argwhere(~np.isfinite(ctx))
        raise ValueError(f"non-finite prediction on {len(bad)} cortical (TR, vertex) entries, "
                         f"first at TR {int(bad[0, 0])}")
    mu = ctx.mean(axis=1, keepdims=True)
    sd = ctx.std(axis=1, ddof=ddof, keepdims=True)
    if (sd <= 0).any():
        raise ValueError("spatially constant TR: cannot standardise")
    out = np.full_like(x, np.nan)
    out[:, ~medial_wall] = (ctx - mu) / sd
    return out


def window_average(x: np.ndarray, start: int, length: int) -> np.ndarray:
    """Mean over TRs [start, start + length); raises if the series is too short."""
    x = np.asarray(x)
    if start < 0 or length <= 0 or start + length > x.shape[0]:
        raise ValueError(f"window [{start}, {start + length}) outside series of {x.shape[0]} TRs")
    return x[start:start + length].mean(axis=0)


def label_means(vmap: np.ndarray, atlas: Atlas) -> np.ndarray:
    """Mean of a (20484,) map within each non-background label (index = label id - 1)."""
    vmap = np.asarray(vmap, dtype=np.float64)
    if vmap.shape != atlas.labels.shape:
        raise ValueError(f"map shape {vmap.shape} != atlas {atlas.labels.shape}")
    lab = atlas.labels
    keep = (lab != atlas.background) & np.isfinite(vmap)
    n = len(atlas.names)
    sums = np.bincount(lab[keep], weights=vmap[keep], minlength=n)
    cnt = np.bincount(lab[keep], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums / cnt
    return np.delete(means, atlas.background)


def parcel_means(vmap: np.ndarray, schaefer: Atlas) -> np.ndarray:
    """Schaefer-400 parcel means; element i is parcel id i + 1."""
    return label_means(vmap, schaefer)


def yeo7_means(vmap: np.ndarray, yeo7: Atlas) -> pd.Series:
    """All 7 Yeo network means (H1 tests all 7)."""
    return pd.Series(label_means(vmap, yeo7), index=list(yeo7.names[1:]), dtype=float)


def spatial_sd(pred: np.ndarray, medial_wall: np.ndarray, start: int, length: int, ddof: int = 0) -> float:
    """Time-averaged (over W) spatial SD of the raw prediction across cortex."""
    x = _check(pred, medial_wall)
    return float(window_average(x[:, ~medial_wall].std(axis=1, ddof=ddof), start, length))


def global_amplitude(pred: np.ndarray, medial_wall: np.ndarray, start: int, length: int) -> float:
    """G: window-mean of the per-TR cortical mean of the raw prediction (secondary feature)."""
    x = _check(pred, medial_wall)
    return float(window_average(x[:, ~medial_wall].mean(axis=1), start, length))


def m1_features(pred: np.ndarray, yeo7: Atlas, medial_wall: np.ndarray, start: int, length: int,
                cfg: dict[str, Any] | None = None) -> pd.Series:
    """M1 (k = 7): the 6 non-limbic Yeo means of the standardised, W-averaged map + spatial SD."""
    fc = _feat_cfg(cfg)
    avg = window_average(spatial_standardize(pred, medial_wall, ddof=int(fc["standardize_ddof"])),
                         start, length)
    means = yeo7_means(avg, yeo7)
    nets = list(fc["m1_networks"])
    if fc["m1_reference"] in nets or set(nets) | {fc["m1_reference"]} != set(means.index):
        raise ValueError("features.m1_networks + m1_reference must partition the Yeo-7 networks")
    out = means[nets].copy()
    out["spatial_sd"] = spatial_sd(pred, medial_wall, start, length, ddof=int(fc["spatial_sd_ddof"]))
    return out
