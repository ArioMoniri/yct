"""Activation localisation outputs (v2.md §1, v2.4 G-D032; D-032, D-034). DESCRIPTIVE, not inferential.

Firewall (G-D032 Referee D5-D7, Biostat D2, Neuro D1-D4):

* Input maps are T1 predictions, spatially standardised per TR (union medial wall, D-034) and
  averaged over the frozen W (:func:`video_map`); group means / the difference map are averaged
  from those. :func:`peak_table` refuses a map that is not spatially standardised. Difference maps
  exist only after unblinding.
* Every table and figure carries the fixed caption ``localize.caption`` (config.yaml): descriptive,
  not inferential, CIs not adjusted for parcel selection. :func:`write_peak_table` writes it as a
  header; :func:`render_four_views` draws it on the figure; ``DataFrame.attrs['caption']`` holds it.
* :func:`lint_claims` flags banned claim language (``localize.banned_patterns``).
* CIs come from a company-cluster bootstrap stratified by group (:func:`company_bootstrap`,
  generator :func:`bootstrap_maps`), BCa with a leave-one-company-out jackknife
  (:func:`bca_interval`). ``stability_topk`` = share of bootstrap replicates in which the parcel is in
  the top K of the same sign. The difference table carries ``p_perm`` (per-parcel label permutation
  within blocks, :func:`parcel_permutation_p`) and its BH-FDR ``q_bh`` over all 400 parcels
  (:func:`bh_fdr`) -- the exploratory parcel family of v2.md §1.
* Ranking: top K positive and top K negative Schaefer-400 parcels overall (not per hemisphere),
  each with its Yeo-7 network, the BEST-OVERLAP HCP-MMP1 area (the HCP label covering most of the
  parcel's vertices) with its overlap fraction (plus the second-best area when the fraction is
  < ``hcp_second_below``), and the modal Destrieux label. Parcels whose share of unreliable vertices
  exceeds ``unreliable_parcel_max_frac`` are excluded from the ranking (count in attrs).
* Surface maps: medial wall not coloured; unreliable vertices STIPPLED with two colours outside the
  colormap (never a grey that reads as zero), with a legend entry.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from yct.config import load_config
from yct.features.atlas import Atlas, AtlasSet, schaefer_hemi
from yct.features.networks import parcel_means, spatial_standardize, window_average

NV = 20484
NH = 10242
_N = NormalDist()

COLUMNS = ["sign", "rank", "parcel_id", "parcel", "hemi", "yeo7", "hcp_mmp", "hcp_overlap", "hcp_mmp_2nd",
           "hcp_overlap_2nd", "destrieux", "value", "ci_lo", "ci_hi", "stability_topk", "p_perm", "q_bh",
           "unreliable_frac"]


class ClaimLanguageError(ValueError):
    """Report text uses banned (reverse-inference / valuation) claim language."""


def _loc_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return (cfg if cfg is not None else load_config())["localize"]


def caption(cfg: dict[str, Any] | None = None) -> str:
    """The fixed caption every localisation output carries (config ``localize.caption``)."""
    return " ".join(str(_loc_cfg(cfg)["caption"]).split())


# ----------------------------------------------------------------------------- claim-language lint

def lint_claims(text: str, cfg: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """[(pattern, matched text)] for every banned claim-language match (case-insensitive)."""
    hits = []
    for pat in _loc_cfg(cfg)["banned_patterns"]:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            hits.append((pat, m.group(0)))
    return hits


def assert_no_claims(text: str, cfg: dict[str, Any] | None = None) -> None:
    hits = lint_claims(text, cfg)
    if hits:
        raise ClaimLanguageError(f"banned claim language: {sorted({h[1] for h in hits})}")


# ----------------------------------------------------------------------------- maps

def video_map(pred: np.ndarray, medial_wall: np.ndarray, start: int, length: int,
              cfg: dict[str, Any] | None = None) -> np.ndarray:
    """The localisation map of one video: spatially standardised per TR, averaged over W."""
    ddof = int((cfg if cfg is not None else load_config())["features"]["standardize_ddof"])
    return window_average(spatial_standardize(pred, medial_wall, ddof=ddof), start, length)


def check_standardized(vmap: np.ndarray, medial_wall: np.ndarray, rtol: float = 1e-6) -> None:
    """Raise unless ``vmap`` is NaN exactly on the medial wall and centred over cortex (H1 scale)."""
    vmap = np.asarray(vmap, dtype=np.float64)
    if vmap.shape != (NV,):
        raise ValueError(f"map must have shape ({NV},), got {vmap.shape}")
    if not np.isnan(vmap[medial_wall]).all() or not np.isfinite(vmap[~medial_wall]).all():
        raise ValueError("map must be NaN on the (union) medial wall and finite on cortex: use video_map")
    ctx = vmap[~medial_wall]
    if abs(ctx.mean()) > rtol * max(1.0, float(np.abs(ctx).max())):
        raise ValueError("map is not spatially standardised (cortical mean != 0): use video_map")


def parcel_values(maps: np.ndarray, schaefer: Atlas) -> np.ndarray:
    """(N, P) Schaefer parcel means of (N, 20484) maps (column i = parcel id i + 1)."""
    maps = np.atleast_2d(np.asarray(maps, dtype=np.float64))
    return np.stack([parcel_means(m, schaefer) for m in maps])


# ----------------------------------------------------------------------------- bootstrap

@dataclass
class ParcelBootstrap:
    estimate: np.ndarray      # (P,)
    boots: np.ndarray         # (B, P)
    jack: np.ndarray          # (J, P) leave-one-company-out estimates
    stat: str
    method: str = "BCa, company-cluster bootstrap stratified by group"


def _strata(group: np.ndarray | None, company: np.ndarray, stat: str, groups: tuple | None):
    n = len(company)
    group = np.asarray(group) if group is not None else np.zeros(n, dtype=int)
    if stat == "diff":
        levels = tuple(groups) if groups is not None else tuple(sorted(set(group.tolist())))
        if len(levels) != 2:
            raise ValueError(f"difference needs exactly 2 groups, got {levels}")
    elif stat == "mean":
        levels = tuple(sorted(set(group.tolist())))
    else:
        raise ValueError(f"stat must be 'mean' or 'diff', got {stat!r}")
    strata = []
    for g in levels:
        idx = np.flatnonzero(group == g)
        if idx.size == 0:
            raise ValueError(f"group {g!r} is empty")
        comps = sorted(set(np.asarray(company)[idx].tolist()))
        members = [idx[np.asarray(company)[idx] == c] for c in comps]
        strata.append((g, comps, members))
    return levels, strata


def _combine_stat(stat: str, means: list[np.ndarray]) -> np.ndarray:
    return means[1] - means[0] if stat == "diff" else means[0]


def bootstrap_maps(maps: np.ndarray, group: np.ndarray | None, company: np.ndarray, n_boot: int, seed: int,
                   stat: str = "mean", groups: tuple | None = None) -> Iterator[np.ndarray]:
    """Generator of n_boot bootstrap maps (group mean, or ``groups[1] - groups[0]`` for ``stat='diff'``).

    Resampling unit = company (one video per company in the confirmatory set), drawn with
    replacement WITHIN each group (stratified). With ``stat='mean'`` and several groups present,
    pass the videos of one group only.
    """
    maps = np.asarray(maps, dtype=np.float64)
    levels, strata = _strata(group, company, stat, groups)
    if stat == "mean" and len(strata) != 1:
        raise ValueError("stat='mean' expects the videos of a single group")
    rng = np.random.default_rng(seed)
    for _ in range(int(n_boot)):
        means = []
        for _g, comps, members in strata:
            pick = rng.integers(0, len(comps), len(comps))
            idx = np.concatenate([members[i] for i in pick])
            means.append(maps[idx].mean(axis=0))
        yield _combine_stat(stat, means)


def company_bootstrap(values: np.ndarray, group: np.ndarray | None, company: np.ndarray,
                      n_boot: int | None = None,
                      seed: int = 0, stat: str = "mean", groups: tuple | None = None,
                      cfg: dict[str, Any] | None = None) -> ParcelBootstrap:
    """Company-cluster bootstrap (stratified by group) of parcel-level group means / differences.

    ``values`` = (N, P) per-video parcel values (:func:`parcel_values`). Same resampling as
    :func:`bootstrap_maps` (parcel means are linear in the vertex map), computed with multinomial
    company weights; plus the leave-one-company-out jackknife for the BCa acceleration.
    """
    n_boot = int(n_boot if n_boot is not None else _loc_cfg(cfg)["bootstrap_B"])
    values = np.asarray(values, dtype=np.float64)
    levels, strata = _strata(group, company, stat, groups)
    if stat == "mean" and len(strata) != 1:
        raise ValueError("stat='mean' expects the videos of a single group")
    rng = np.random.default_rng(seed)
    sums, cnts = [], []
    for _g, _comps, members in strata:
        sums.append(np.stack([values[m].sum(axis=0) for m in members]))       # (C, P)
        cnts.append(np.array([len(m) for m in members], dtype=float))         # (C,)
    est = _combine_stat(stat, [s.sum(0) / c.sum() for s, c in zip(sums, cnts, strict=True)])
    boot_means = []
    for s, c in zip(sums, cnts, strict=True):
        w = rng.multinomial(len(c), np.full(len(c), 1 / len(c)), size=n_boot).astype(float)   # (B, C)
        boot_means.append((w @ s) / (w @ c)[:, None])
    boots = _combine_stat(stat, boot_means)
    jack = []
    for si, c in enumerate(cnts):
        if len(c) < 2:
            continue
        for ci in range(len(c)):
            means = []
            for sj, (s2, c2) in enumerate(zip(sums, cnts, strict=True)):
                if sj == si:
                    keep = np.arange(len(c2)) != ci
                    means.append(s2[keep].sum(0) / c2[keep].sum())
                else:
                    means.append(s2.sum(0) / c2.sum())
            jack.append(_combine_stat(stat, means))
    return ParcelBootstrap(estimate=est, boots=boots, jack=np.asarray(jack), stat=stat)


def bca_interval(estimate: np.ndarray, boots: np.ndarray, jack: np.ndarray,
                 level: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised BCa interval per column (Efron 1987); NaN where undefined."""
    est = np.atleast_1d(np.asarray(estimate, float))
    boots = np.asarray(boots, float)
    jack = np.asarray(jack, float)
    nb = boots.shape[0]
    less = (boots < est).mean(0) + 0.5 * (boots == est).mean(0)
    less = np.clip(less, 0.5 / nb, 1 - 0.5 / nb)
    z0 = np.array([_N.inv_cdf(p) for p in less])
    if jack.ndim != 2 or jack.shape[0] < 2:
        jack = np.zeros((2, boots.shape[1]))          # no jackknife: acceleration 0 (bias-corrected only)
    d = jack.mean(0) - jack
    num = (d**3).sum(0)
    den = 6 * ((d**2).sum(0)) ** 1.5
    with np.errstate(invalid="ignore", divide="ignore"):
        acc = np.where(den > 0, num / den, 0.0)
    out = []
    for za in (_N.inv_cdf((1 - level) / 2), _N.inv_cdf(1 - (1 - level) / 2)):
        zz = z0 + za
        adj = np.array([_N.cdf(v) for v in z0 + zz / (1 - acc * zz)])
        srt = np.sort(boots, axis=0)
        pos = np.clip(adj * (nb - 1), 0, nb - 1)
        lo_i, hi_i = np.floor(pos).astype(int), np.ceil(pos).astype(int)
        cols = np.arange(boots.shape[1])
        frac = pos - lo_i
        out.append(srt[lo_i, cols] * (1 - frac) + srt[hi_i, cols] * frac)
    lo, hi = out
    bad = ~np.isfinite(est) | ~np.isfinite(boots).all(0)
    lo[bad], hi[bad] = np.nan, np.nan
    return lo, hi


def topk_stability(boots: np.ndarray, k: int, sign: str, eligible: np.ndarray | None = None) -> np.ndarray:
    """(P,) share of bootstrap replicates in which each parcel is in the top k of the given sign."""
    b = np.asarray(boots, float).copy()
    if eligible is not None:
        b[:, ~eligible] = np.nan
    s = b if sign == "pos" else -b
    s = np.where(np.isfinite(s) & (s > 0), s, -np.inf)
    kk = min(k, s.shape[1])
    thr = -np.sort(-s, axis=1)[:, kk - 1:kk]
    return ((s >= thr) & np.isfinite(s) & (s > -np.inf)).mean(axis=0)


# ----------------------------------------------------------------------------- permutation p, BH-FDR

def parcel_permutation_p(values: np.ndarray, group: np.ndarray, n_perm: int, seed: int,
                         blocks: np.ndarray | None = None, groups: tuple | None = None) -> np.ndarray:
    """Two-sided per-parcel permutation p for mean(groups[1]) - mean(groups[0]); labels permuted
    within exchangeability ``blocks`` (era); p = (b + 1) / (n_perm + 1)."""
    values = np.asarray(values, float)
    group = np.asarray(group)
    levels = tuple(groups) if groups is not None else tuple(sorted(set(group.tolist())))
    if len(levels) != 2:
        raise ValueError("permutation p needs exactly 2 groups")
    blocks = np.zeros(len(group), int) if blocks is None else np.asarray(blocks)
    y = (group == levels[1]).astype(float)

    def diff(lab: np.ndarray) -> np.ndarray:
        return values[lab == 1].mean(0) - values[lab == 0].mean(0)

    obs = np.abs(diff(y))
    rng = np.random.default_rng(seed)
    ge = np.zeros(values.shape[1])
    for _ in range(int(n_perm)):
        perm = y.copy()
        for blk in np.unique(blocks):
            idx = np.flatnonzero(blocks == blk)
            perm[idx] = rng.permutation(y[idx])
        ge += np.abs(diff(perm)) >= obs - 1e-12
    return (ge + 1) / (n_perm + 1)


def bh_fdr(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg q-values (step-up, monotone, capped at 1); NaNs pass through."""
    p = np.asarray(p, float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    pv = p[ok]
    m = pv.size
    if m == 0:
        return q
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q


# ----------------------------------------------------------------------------- peak table

def _overlaps(other: Atlas, mask: np.ndarray) -> list[tuple[str, float]]:
    lab = other.labels[mask]
    lab = lab[lab != other.background]
    if lab.size == 0:
        return [(other.names[other.background], 0.0)]
    ids, cnt = np.unique(lab, return_counts=True)
    order = np.argsort(-cnt, kind="stable")
    return [(other.names[ids[i]], float(cnt[i] / mask.sum())) for i in order]


def peak_table(vmap: np.ndarray, atlases: AtlasSet, boot: ParcelBootstrap | None = None,
               p_perm: np.ndarray | None = None, unreliable: np.ndarray | None = None,
               kind: str = "group_mean", k: int | None = None, ci_level: float | None = None,
               cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Top-k positive (descending) then top-k negative (ascending) Schaefer parcels; descriptive.

    ``vmap`` must be spatially standardised and W-averaged (:func:`video_map` and its means).
    ``kind='difference'`` requires ``p_perm`` (per-parcel permutation p) and adds BH-FDR ``q_bh``.
    The returned frame's ``attrs['caption']`` is the fixed caption.
    """
    lc = _loc_cfg(cfg)
    k = int(k if k is not None else lc["top_k"])
    ci_level = float(ci_level if ci_level is not None else lc["ci_level"])
    if kind not in ("group_mean", "difference"):
        raise ValueError(f"kind must be 'group_mean' or 'difference', got {kind!r}")
    vmap = np.asarray(vmap, dtype=np.float64)
    if vmap.shape != (NV,):
        raise ValueError(f"map must have shape ({NV},), got {vmap.shape}")
    mw = atlases.medial_wall
    check_standardized(vmap, mw)
    sch = atlases.schaefer
    vals = parcel_means(vmap, sch)
    n_par = vals.size

    unrel_frac = np.zeros(n_par)
    if unreliable is not None:
        unreliable = np.asarray(unreliable, bool)
        if unreliable.shape != (NV,):
            raise ValueError(f"unreliable must have shape ({NV},)")
        cnt = np.bincount(sch.labels, minlength=n_par + 1)[1:]
        bad = np.bincount(sch.labels[unreliable], minlength=n_par + 1)[1:]
        unrel_frac = np.where(cnt > 0, bad / np.maximum(cnt, 1), 0.0)
    eligible = np.isfinite(vals) & (unrel_frac <= float(lc["unreliable_parcel_max_frac"]))

    lo = hi = stab_pos = stab_neg = np.full(n_par, np.nan)
    if boot is not None:
        if boot.boots.shape[1] != n_par or boot.estimate.shape != (n_par,):
            raise ValueError(f"bootstrap must be parcel-level with {n_par} parcels")
        if not np.allclose(boot.estimate[np.isfinite(vals)], vals[np.isfinite(vals)], atol=1e-8):
            raise ValueError("bootstrap estimate does not match the map's parcel means")
        lo, hi = bca_interval(boot.estimate, boot.boots, boot.jack, ci_level)
        stab_pos = topk_stability(boot.boots, k, "pos", eligible)
        stab_neg = topk_stability(boot.boots, k, "neg", eligible)
    q = np.full(n_par, np.nan)
    pp = np.full(n_par, np.nan)
    if kind == "difference":
        if p_perm is None:
            raise ValueError("the difference table must carry permutation p and BH-FDR q (v2.4 G-D032)")
        pp = np.asarray(p_perm, float)
        if pp.shape != (n_par,):
            raise ValueError(f"p_perm must have shape ({n_par},)")
        q = bh_fdr(pp)
    elif p_perm is not None:
        raise ValueError("p_perm applies to the difference map only")

    order = np.argsort(vals)
    pos = [i for i in order[::-1] if eligible[i] and vals[i] > 0][:k]
    neg = [i for i in order if eligible[i] and vals[i] < 0][:k]
    second_below = float(lc["hcp_second_below"])
    rows = []
    for sign, idx in (("pos", pos), ("neg", neg)):
        stab = stab_pos if sign == "pos" else stab_neg
        for r, i in enumerate(idx, start=1):
            pid = i + 1
            name = sch.names[pid]
            mask = sch.labels == pid
            hcp = _overlaps(atlases.hcp, mask)
            des = _overlaps(atlases.destrieux, mask)
            second = hcp[1] if hcp[0][1] < second_below and len(hcp) > 1 else ("", np.nan)
            rows.append({
                "sign": sign, "rank": r, "parcel_id": pid, "parcel": name,
                "hemi": schaefer_hemi(name), "yeo7": _overlaps(atlases.yeo7, mask)[0][0],
                "hcp_mmp": hcp[0][0], "hcp_overlap": hcp[0][1],
                "hcp_mmp_2nd": second[0], "hcp_overlap_2nd": second[1], "destrieux": des[0][0],
                "value": float(vals[i]), "ci_lo": float(lo[i]), "ci_hi": float(hi[i]),
                "stability_topk": float(stab[i]), "p_perm": float(pp[i]), "q_bh": float(q[i]),
                "unreliable_frac": float(unrel_frac[i]),
            })
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.attrs.update({
        "caption": caption(cfg),
        "kind": kind,
        "ci_method": boot.method if boot is not None else "none",
        "ci_level": ci_level,
        "n_excluded_unreliable": int((np.isfinite(vals) & ~eligible).sum()),
        "map": "T1, spatially standardised per TR (union medial wall), averaged over W",
        "hcp_label": "best-overlap HCP-MMP1 area (overlap fraction); 2nd-best when fraction < "
                     f"{second_below}",
        "q_bh": "BH-FDR over all parcels of the per-parcel permutation p (exploratory family)"
                if kind == "difference" else "n/a (group mean)",
    })
    return df


def write_peak_table(df: pd.DataFrame, path: str | Path, cfg: dict[str, Any] | None = None) -> Path:
    """CSV with the fixed caption and the table's provenance as '# ' header lines (always)."""
    cap = caption(cfg)
    assert_no_claims(cap, cfg)
    meta = {k: v for k, v in df.attrs.items() if k != "caption"}
    lines = [f"# {cap}"] + [f"# {k}: {v}" for k, v in meta.items()]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
        df.to_csv(fh, index=False)
    return out


def read_peak_table(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """(table, header lines) of a file written by :func:`write_peak_table`."""
    with open(path) as fh:
        header = []
        for line in fh:
            if not line.startswith("# "):
                break
            header.append(line[2:].rstrip("\n"))
    return pd.read_csv(path, comment=None, skiprows=len(header)), header


# ----------------------------------------------------------------------------- four-view maps

def _unreliable_faces(faces: np.ndarray, unreliable_h: np.ndarray) -> np.ndarray:
    return unreliable_h[faces].sum(axis=1) >= 2


def stipple_colors(base: np.ndarray, faces: np.ndarray, unreliable_h: np.ndarray,
                   pattern: list[str] | tuple[str, ...]) -> np.ndarray:
    """Face colours with unreliable faces replaced by an alternating two-colour stipple."""
    from matplotlib.colors import to_rgba

    out = np.asarray(base, float).copy()
    sel = np.flatnonzero(_unreliable_faces(faces, unreliable_h))
    cols = np.array([to_rgba(c) for c in pattern])
    out[sel] = cols[sel % len(cols)]
    return out


def render_four_views(vmap: np.ndarray, medial_wall: np.ndarray | None = None,
                      unreliable: np.ndarray | None = None, title: str | None = None,
                      vmax: float | None = None, cmap: str = "RdBu_r", views: list[str] | None = None,
                      cfg: dict[str, Any] | None = None):
    """2 x 4 figure (LH, RH) x (lateral, medial, ventral, dorsal) on fsaverage5 inflated."""
    import matplotlib

    if matplotlib.get_backend().lower() not in ("agg", "pdf", "svg", "cairo"):
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from nilearn import datasets, plotting

    lc = _loc_cfg(cfg)
    if title:
        assert_no_claims(title, cfg)
    vmap = np.asarray(vmap, dtype=np.float64).copy()
    if vmap.shape != (NV,):
        raise ValueError(f"map must have shape ({NV},), got {vmap.shape}")
    views = list(views or lc["views"])
    pattern = list(lc["unreliable_pattern"])
    hidden = ~np.isfinite(vmap)
    if medial_wall is not None:
        hidden |= medial_wall
    unrel = np.zeros(NV, bool) if unreliable is None else np.asarray(unreliable, bool) & ~hidden
    shown = ~hidden & ~unrel
    if vmax is None:
        vmax = float(np.nanmax(np.abs(vmap[shown]))) if shown.any() else 1.0
        vmax = vmax or 1.0
    thr = 1e-6 * vmax                                      # hidden vertices (0) stay uncoloured
    stat = np.where(shown, vmap, 0.0)

    fs = datasets.load_fsaverage("fsaverage5")
    sulc = datasets.load_fsaverage_data(mesh="fsaverage5", data_type="sulcal")
    bg_parts = {h: np.asarray(sulc.data.parts[h], dtype=float) for h in ("left", "right")}
    fig = plt.figure(figsize=(4 * len(views), 8.3))
    for row, (hemi, sl) in enumerate((("left", slice(0, NH)), ("right", slice(NH, NV)))):
        bg = bg_parts[hemi]
        bg = 0.5 * bg / (np.abs(bg).max() or 1.0)
        mesh = fs["inflated"].parts[hemi]
        for col, view in enumerate(views):
            ax = fig.add_subplot(2, len(views), row * len(views) + col + 1, projection="3d")
            plotting.plot_surf_stat_map(
                mesh, stat[sl], bg_map=bg, hemi=hemi, view=view,
                cmap=cmap, colorbar=(row == 1 and col == len(views) - 1), threshold=thr,
                vmin=-vmax, vmax=vmax, symmetric_cbar=True, axes=ax, figure=fig,
                title=f"{'LH' if hemi == 'left' else 'RH'} {view}",
            )
            if unrel[sl].any():                            # stipple (not grey) the unreliable faces
                coll = ax.collections[0]
                base = np.asarray(getattr(coll, "_facecolor3d", coll.get_facecolor()))
                coll.set_facecolor(stipple_colors(base, np.asarray(mesh.faces), unrel[sl], pattern))
    if unrel.any():
        fig.legend(handles=[Patch(facecolor=pattern[1], edgecolor=pattern[0], hatch="..",
                                  label="stippled: unreliable vertices (masked, not zero)")],
                   loc="upper right")
    if title:
        fig.suptitle(title)
    fig.text(0.01, 0.005, caption(cfg), fontsize=7, wrap=True, ha="left", va="bottom")
    return fig


def plot_four_views(vmap: np.ndarray, out_png: str | Path, medial_wall: np.ndarray | None = None,
                    unreliable: np.ndarray | None = None, title: str | None = None,
                    vmax: float | None = None, cmap: str = "RdBu_r", views: list[str] | None = None,
                    dpi: int = 110, cfg: dict[str, Any] | None = None) -> Path:
    """Render :func:`render_four_views` (caption always on the figure) and save it."""
    import matplotlib.pyplot as plt

    fig = render_four_views(vmap, medial_wall, unreliable, title, vmax, cmap, views, cfg)
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out
