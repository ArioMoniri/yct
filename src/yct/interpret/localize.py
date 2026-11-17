"""Activation localisation outputs (v2.md §1 v2.3, D-032). Descriptive, not inferential.

For a (20484,) map on fsaverage5 (a group mean or a difference map, LH then RH):

* :func:`peak_table` -- top-K positive and top-K negative Schaefer-400 parcels by parcel mean,
  each with hemisphere, Yeo-7 network, best-overlap HCP-MMP1 area (the HCP label covering most
  of the parcel's vertices, with that fraction), modal Destrieux label, value and a percentile
  bootstrap CI from optional bootstrap maps (B, 20484).
* :func:`plot_four_views` -- lateral / medial / ventral / dorsal views of each hemisphere on the
  fsaverage5 inflated surface; medial wall masked (not coloured), reliability-masked vertices
  greyed (not coloured, flat light background) and outlined in black.

Only parcels from the confirmatory family carry inferential claims.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yct.config import load_config
from yct.features.atlas import Atlas, AtlasSet, schaefer_hemi
from yct.features.networks import parcel_means

NV = 20484
NH = 10242


def _loc_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return (cfg if cfg is not None else load_config())["localize"]


def _modal_label(other: Atlas, mask: np.ndarray) -> tuple[str, float]:
    lab = other.labels[mask]
    lab = lab[lab != other.background]
    if lab.size == 0:
        return other.names[other.background], 0.0
    ids, cnt = np.unique(lab, return_counts=True)
    i = int(cnt.argmax())
    return other.names[ids[i]], float(cnt[i] / mask.sum())


def peak_table(vmap: np.ndarray, atlases: AtlasSet, bootstrap: np.ndarray | None = None,
               k: int | None = None, ci_level: float | None = None,
               cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Top-k positive (descending) then top-k negative (ascending) Schaefer parcels."""
    lc = _loc_cfg(cfg) if (k is None or ci_level is None) else {}
    k = int(k if k is not None else lc["top_k"])
    ci_level = float(ci_level if ci_level is not None else lc["ci_level"])
    vmap = np.asarray(vmap, dtype=np.float64)
    if vmap.shape != (NV,):
        raise ValueError(f"map must have shape ({NV},), got {vmap.shape}")
    sch = atlases.schaefer
    vals = parcel_means(vmap, sch)
    lo, hi = np.full(vals.shape, np.nan), np.full(vals.shape, np.nan)
    if bootstrap is not None:
        boots = np.asarray(bootstrap, dtype=np.float64)
        if boots.ndim != 2 or boots.shape[1] != NV:
            raise ValueError(f"bootstrap must have shape (B, {NV}), got {boots.shape}")
        bp = np.stack([parcel_means(b, sch) for b in boots])
        a = (1 - ci_level) / 2
        lo, hi = np.nanquantile(bp, a, axis=0), np.nanquantile(bp, 1 - a, axis=0)

    ok = np.isfinite(vals)
    order = np.argsort(vals)
    pos = [i for i in order[::-1] if ok[i] and vals[i] > 0][:k]
    neg = [i for i in order if ok[i] and vals[i] < 0][:k]
    rows = []
    for sign, idx in (("pos", pos), ("neg", neg)):
        for r, i in enumerate(idx, start=1):
            pid = i + 1
            name = sch.names[pid]
            mask = sch.labels == pid
            hcp, frac = _modal_label(atlases.hcp, mask)
            des, _ = _modal_label(atlases.destrieux, mask)
            rows.append({
                "sign": sign, "rank": r, "parcel_id": pid, "parcel": name,
                "hemi": schaefer_hemi(name), "yeo7": atlases.yeo7.names[int(np.bincount(
                    atlases.yeo7.labels[mask]).argmax())],
                "hcp_mmp": hcp, "hcp_overlap": frac, "destrieux": des,
                "value": float(vals[i]), "ci_lo": float(lo[i]), "ci_hi": float(hi[i]),
            })
    return pd.DataFrame(rows, columns=["sign", "rank", "parcel_id", "parcel", "hemi", "yeo7", "hcp_mmp",
                                       "hcp_overlap", "destrieux", "value", "ci_lo", "ci_hi"])


def plot_four_views(vmap: np.ndarray, out_png: str | Path, medial_wall: np.ndarray | None = None,
                    unreliable: np.ndarray | None = None, title: str | None = None,
                    vmax: float | None = None, cmap: str = "RdBu_r", views: list[str] | None = None,
                    dpi: int = 110) -> Path:
    """2 x 4 grid (LH, RH) x (lateral, medial, ventral, dorsal) on fsaverage5 inflated."""
    import matplotlib

    if matplotlib.get_backend().lower() not in ("agg", "pdf", "svg", "cairo"):
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nilearn import datasets, plotting

    vmap = np.asarray(vmap, dtype=np.float64).copy()
    if vmap.shape != (NV,):
        raise ValueError(f"map must have shape ({NV},), got {vmap.shape}")
    views = list(views or load_config()["localize"]["views"])
    hidden = ~np.isfinite(vmap)
    if medial_wall is not None:
        hidden |= medial_wall
    shown = ~hidden if unreliable is None else ~hidden & ~unreliable
    if vmax is None:
        vmax = float(np.nanmax(np.abs(vmap[shown]))) if shown.any() else 1.0
        vmax = vmax or 1.0
    thr = 1e-6 * vmax                                      # hidden vertices (0) stay uncoloured
    stat = np.where(shown, vmap, 0.0)

    fs = datasets.load_fsaverage("fsaverage5")
    sulc = datasets.load_fsaverage_data(mesh="fsaverage5", data_type="sulcal")
    bg_parts = {h: np.asarray(sulc.data.parts[h], dtype=float) for h in ("left", "right")}
    fig = plt.figure(figsize=(4 * len(views), 7.5))
    for row, (hemi, sl) in enumerate((("left", slice(0, NH)), ("right", slice(NH, NV)))):
        bg = bg_parts[hemi]
        bg = 0.5 * bg / (np.abs(bg).max() or 1.0)
        if unreliable is not None:
            bg = np.where(unreliable[sl], -1.0, bg)        # greyed: lightest background
        for col, view in enumerate(views):
            ax = fig.add_subplot(2, len(views), row * len(views) + col + 1, projection="3d")
            plotting.plot_surf_stat_map(
                fs["inflated"].parts[hemi], stat[sl], bg_map=bg, hemi=hemi, view=view,
                cmap=cmap, colorbar=(row == 1 and col == len(views) - 1), threshold=thr,
                vmin=-vmax, vmax=vmax, symmetric_cbar=True, axes=ax, figure=fig,
                title=f"{'LH' if hemi == 'left' else 'RH'} {view}",
            )
            if unreliable is not None and unreliable[sl].any():   # outline the greyed region
                plotting.plot_surf_contours(
                    fs["inflated"].parts[hemi], unreliable[sl].astype(int), levels=[1],
                    colors=["k"], axes=ax, figure=fig,
                )
    if title:
        fig.suptitle(title)
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out
