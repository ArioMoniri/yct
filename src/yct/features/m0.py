"""M0 assembly for H4 (v2.md §1 H4; v2.4 G-D032 Biostat D1; DECISIONS D-034, Q(M0) rule D-037).

All steps are LABEL-FREE: no outcome, group or era-by-label information is read here.

1. :func:`m0_window_features` -- per video, average the per-TR confounds (yct.confounds) over the
   frozen window W = [start, start + length) TRs. ``n_words_w`` = words whose midpoint falls in W.
2. :func:`label_free_exclusions` -- drop videos with no audio track or fewer than
   ``m0.min_words_in_w`` (20) words in W (TRIBE known issue #7: silent tracks get noise z-scored
   to unit variance). Every exclusion is logged with its reason.
3. :func:`impute_m0` -- pre-specified, label-free imputation (documented rules, ``IMPUTATION_RULES``):
     * face features (``face_*``) with no sampled detection in W -> 0 (no face = zero face fraction);
     * pitch (``pitch_*``) with no voiced frame in W -> median over the videos that have voiced
       speech in W (the analysis set, label-free), plus the binary indicator ``voiced_any``
       (1 = voiced speech present; binary, never squared);
     * ``speech_rate_wps`` missing (no transcript tsv) -> hard failure, never imputed;
     * ``text_frac`` is never in M0 (on-screen text detection is not implemented); listing it is
       an error, not an imputation;
     * any other non-finite value -> hard failure.
   The result is asserted finite.
4. :func:`q_m0` -- Q(M0) under DECISIONS D-037 (v2.5 C3; replaces the D-034 1/VIF K_Q set and the
   withdrawn D-036 PCA rule). NO PCA. Q always contains ALL linear M0 terms (z-scored continuous
   features, the binary ``voiced_any``, era dummies) and the forced speech_rate^2, speech_frac^2,
   speech_rate*speech_frac (TRIBE known issue #8); further quadratic terms follow in a fixed, label-free
   prereg order (:func:`optional_term_order`) until the NUMERICAL rank (SVD, rcond ``m0.rank_rcond`` =
   1e-8) reaches floor(N/3). If the linear + forced block alone exceeds floor(N/3), the pre-registered
   label-free ``m0.merge_list`` is applied step by step. cond(Q) <= ``m0.max_cond`` is asserted;
   aliased columns are dropped and logged. :func:`q_dimension_table` is the planned dimension table.
5. :func:`residualize` -- R = M1 residualised by unpenalised OLS on Q(M0).
The P5b "dropped term drives M1 and y" FPR simulation is :mod:`yct.features.h4_null_sim`.
"""
from __future__ import annotations

import itertools
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from yct.config import load_config

log = logging.getLogger(__name__)

IMPUTATION_RULES = {
    "face_*": "no face detected in W -> 0",
    "pitch_*": "no voiced frame in W -> dataset median over videos with voiced speech; voiced_any = 0",
    "speech_rate_wps": "missing transcript -> hard failure (never imputed)",
    "text_frac": "never in M0 (not implemented)",
    "other": "non-finite -> hard failure",
}
VOICED = "voiced_any"


def _m0_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return (cfg if cfg is not None else load_config())["m0"]


def m0_feature_list(cfg: dict[str, Any] | None = None) -> list[str]:
    """The frozen M0 per-TR feature list (config ``m0.features``); never contains ``text_frac``."""
    mc = _m0_cfg(cfg)
    feats = list(mc["features"])
    banned = set(mc.get("never", [])) | {"text_frac"}
    bad = banned & set(feats)
    if bad:
        raise ValueError(f"M0 must not contain {sorted(bad)} (v2.4 G-D032 Biostat D1a)")
    if len(set(feats)) != len(feats):
        raise ValueError("duplicate M0 features")
    return feats


# ----------------------------------------------------------------------------- 1. window averaging

def m0_window_features(per_tr: pd.DataFrame, start: int, length: int, features: list[str] | None = None,
                       tr_s: float | None = None, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """W-average per-TR confounds per video -> DataFrame indexed by video_id.

    Columns: the M0 features (NaN when the feature is undefined in every W TR, e.g. pitch with no
    voiced speech), ``n_words_w``, and ``n_tr_w``. Raises if a video does not cover all of W.
    """
    cfg = cfg if cfg is not None else load_config()
    features = list(features if features is not None else m0_feature_list(cfg))
    tr_s = float(tr_s if tr_s is not None else cfg["tribe"]["tr_s"])
    if start < 0 or length <= 0:
        raise ValueError(f"bad window [{start}, {start + length})")
    missing = [c for c in [*features, "video_id", "tr", "tr_coverage"] if c not in per_tr.columns]
    if missing:
        raise KeyError(f"per-TR confounds lack {missing}")
    rows = {}
    for vid, d in per_tr.groupby("video_id", sort=True):
        w = d[(d["tr"] >= start) & (d["tr"] < start + length)].sort_values("tr")
        if len(w) != length or not np.array_equal(w["tr"].to_numpy(), np.arange(start, start + length)):
            raise ValueError(f"{vid}: confounds do not cover W = [{start}, {start + length}) TRs")
        out = {}
        for c in features:
            v = w[c].to_numpy(dtype=float)
            out[c] = float(np.mean(v[np.isfinite(v)])) if np.isfinite(v).any() else np.nan
        rate = (w["speech_rate_wps"].to_numpy(dtype=float) if "speech_rate_wps" in w
                else np.full(length, np.nan))
        cov = w["tr_coverage"].to_numpy(dtype=float)
        out["n_words_w"] = float(np.round(np.sum(rate * cov * tr_s))) if np.isfinite(rate).all() else np.nan
        out["n_tr_w"] = len(w)
        rows[vid] = out
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "video_id"
    return df


# ----------------------------------------------------------------------------- 2. exclusions

def label_free_exclusions(wdf: pd.DataFrame, has_audio: Mapping[str, bool], min_words: int | None = None,
                          cfg: dict[str, Any] | None = None) -> tuple[list[str], pd.DataFrame]:
    """(kept video ids, exclusion log [video_id, reason]). Label-free; every exclusion is logged."""
    min_words = int(min_words if min_words is not None else _m0_cfg(cfg)["min_words_in_w"])
    kept, excl = [], []
    for vid in wdf.index:
        if vid not in has_audio:
            raise KeyError(f"{vid}: has_audio_track unknown (confounds summary missing)")
        nw = wdf.at[vid, "n_words_w"]
        if not has_audio[vid]:
            reason = "no_audio_track"
        elif not np.isfinite(nw):
            raise ValueError(f"{vid}: word count in W unknown (no transcript tsv); never imputed")
        elif nw < min_words:
            reason = f"fewer_than_{min_words}_words_in_W ({int(nw)})"
        else:
            kept.append(vid)
            continue
        excl.append({"video_id": vid, "reason": reason})
        log.info("M0 label-free exclusion: %s (%s)", vid, reason)
    return kept, pd.DataFrame(excl, columns=["video_id", "reason"])


# ----------------------------------------------------------------------------- 3. imputation

def impute_m0(wdf: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply IMPUTATION_RULES; returns (finite M0 incl. ``voiced_any``, imputation report)."""
    if "text_frac" in features:
        raise ValueError("text_frac is never in M0 (not implemented); it is not imputed")
    x = wdf[features].astype(float).copy()
    report: dict[str, Any] = {"rules": IMPUTATION_RULES, "n_imputed": {}}
    if "speech_rate_wps" in x and not np.isfinite(x["speech_rate_wps"]).all():
        bad = list(x.index[~np.isfinite(x["speech_rate_wps"])])
        raise ValueError(f"speech_rate_wps missing for {bad} (no transcript tsv): fail hard, never imputed")
    for c in [c for c in features if c.startswith("face_")]:
        n = int((~np.isfinite(x[c])).sum())
        x[c] = x[c].where(np.isfinite(x[c]), 0.0)
        report["n_imputed"][c] = n
    pitch = [c for c in features if c.startswith("pitch_")]
    if pitch:
        voiced = np.isfinite(x[pitch]).all(axis=1)
        if not voiced.any():
            raise ValueError("no video has voiced speech in W: pitch features cannot be imputed")
        for c in pitch:
            med = float(np.median(x.loc[voiced, c]))
            report["n_imputed"][c] = int((~voiced).sum())
            report.setdefault("pitch_median", {})[c] = med
            x[c] = x[c].where(voiced, med)
        x[VOICED] = voiced.astype(float)
    if not np.isfinite(x.to_numpy()).all():
        bad = {c: list(x.index[~np.isfinite(x[c])]) for c in x.columns if not np.isfinite(x[c]).all()}
        raise ValueError(f"non-finite M0 values with no imputation rule: {bad}")
    return x, report


@dataclass
class M0Result:
    m0: pd.DataFrame                       # finite, indexed by video_id
    excluded: pd.DataFrame                 # [video_id, reason]
    imputation: dict[str, Any]
    binary: list[str] = field(default_factory=list)


def assemble_m0(per_tr: pd.DataFrame, start: int, length: int, has_audio: Mapping[str, bool],
                cfg: dict[str, Any] | None = None) -> M0Result:
    """Window-average -> label-free exclusions -> imputation -> finite assert."""
    cfg = cfg if cfg is not None else load_config()
    feats = m0_feature_list(cfg)
    wdf = m0_window_features(per_tr, start, length, feats, cfg=cfg)
    kept, excluded = label_free_exclusions(wdf, has_audio, cfg=cfg)
    m0, rep = impute_m0(wdf.loc[kept], feats)
    assert np.isfinite(m0.to_numpy()).all()
    binary = [c for c in _m0_cfg(cfg).get("binary", []) if c in m0.columns]
    return M0Result(m0=m0, excluded=excluded, imputation=rep, binary=binary)


# ----------------------------------------------------------------------------- 4-5. Q(M0), rule D-037

def zscore(x: np.ndarray, ddof: int = 0) -> np.ndarray:
    """Column z-score over the analysis set (label-free); constant columns -> 0."""
    x = np.asarray(x, dtype=float)
    sd = x.std(axis=0, ddof=ddof)
    return (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1.0)


def numerical_rank(q: np.ndarray, rcond: float = 1e-8) -> int:
    """Numerical rank: number of singular values > rcond * s_max (not the column count)."""
    q = np.asarray(q, dtype=float)
    if q.size == 0:
        return 0
    s = np.linalg.svd(q, compute_uv=False)
    return int((s > rcond * s[0]).sum()) if s[0] > 0 else 0


def condition_number(q: np.ndarray) -> float:
    s = np.linalg.svd(np.asarray(q, dtype=float), compute_uv=False)
    return float(s[0] / s[-1]) if s[-1] > 0 else float("inf")


def merge_list(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The pre-registered, label-free merge list (config ``m0.merge_list``), validated."""
    mc = _m0_cfg(cfg)
    feats = m0_feature_list(cfg)
    forced = set(mc["forced_speech"])
    binary = set(mc.get("binary", []))
    seen: set[str] = set()
    out = []
    for step in mc.get("merge_list", []):
        mem = list(step["members"])
        if len(mem) < 2:
            raise ValueError(f"merge step {step['name']!r} needs >= 2 members")
        bad = [m for m in mem if m not in feats]
        if bad:
            raise ValueError(f"merge step {step['name']!r}: {bad} not in m0.features")
        if forced & set(mem) or binary & set(mem):
            raise ValueError(f"merge step {step['name']!r} may not merge forced speech or binary features")
        if seen & set(mem):
            raise ValueError(f"merge step {step['name']!r} reuses {sorted(seen & set(mem))}")
        if step["name"] in feats:
            raise ValueError(f"merge composite name {step['name']!r} collides with an M0 feature")
        seen |= set(mem)
        out.append({"name": str(step["name"]), "members": mem, "why": str(step.get("why", ""))})
    return out


def apply_merges(m0: pd.DataFrame, steps: list[dict[str, Any]], ddof: int = 0) -> pd.DataFrame:
    """Replace each step's members by their composite (mean of z-scores), at the first member's position."""
    x = m0.astype(float).copy()
    for st in steps:
        mem = st["members"]
        missing = [m for m in mem if m not in x.columns]
        if missing:
            raise KeyError(f"merge {st['name']!r}: {missing} not in M0")
        comp = zscore(x[mem].to_numpy(), ddof).mean(axis=1)
        pos = list(x.columns).index(mem[0])
        x = x.drop(columns=mem)
        x.insert(min(pos, x.shape[1]), st["name"], comp)
    return x


def _era_dummies(era: pd.Series | None, index: pd.Index) -> dict[str, np.ndarray]:
    if era is None:
        return {}
    e = pd.Series(era).reindex(index)
    if e.isna().any():
        raise ValueError("era missing for some videos")
    return {f"era={lev}": (e == lev).to_numpy(dtype=float) for lev in sorted(e.unique())[1:]}


def _greedy(cols: dict[str, np.ndarray], names: list[str], rcond: float,
            kept: list[str] | None = None,
            limit: int | None = None) -> tuple[list[str], list[str], list[str]]:
    """Add columns in order; drop aliased ones; stop once rank == limit. -> (kept, aliased, not_reached)."""
    kept = list(kept or [])
    rank = numerical_rank(np.column_stack([cols[k] for k in kept]), rcond) if kept else 0
    aliased: list[str] = []
    for i, nm in enumerate(names):
        if limit is not None and rank >= limit:
            return kept, aliased, names[i:]
        r = numerical_rank(np.column_stack([*(cols[k] for k in kept), cols[nm]]), rcond)
        if r > rank:
            kept.append(nm)
            rank = r
        else:
            aliased.append(nm)
    return kept, aliased, []


def optional_term_order(z: pd.DataFrame, forced: list[str], ddof: int = 0) -> list[str]:
    """Fixed prereg order of the optional quadratic terms (label-free; no PCA).

    Squares of the non-forced continuous features by descending variance of z^2, then every pairwise
    product except the forced speech product by descending variance of z_a * z_b; ties by name.
    """
    cont = list(z.columns)
    rest = [c for c in cont if c not in forced]
    sq = sorted(rest, key=lambda c: (-round(float(np.var(z[c] ** 2, ddof=ddof)), 12), c))
    fpair = tuple(sorted(forced))
    pairs = [(a, b) for a, b in itertools.combinations(cont, 2) if tuple(sorted((a, b))) != fpair]
    pr = sorted(pairs, key=lambda ab: (-round(float(np.var(z[ab[0]] * z[ab[1]], ddof=ddof)), 12), ab))
    return [f"{c}^2" for c in sq] + [f"{a}*{b}" for a, b in pr]


@dataclass
class QPlan:
    q: np.ndarray                 # (N, rank) kept columns, full numerical column rank
    columns: list[str]
    rank: int
    limit: int
    cond: float
    aliased: list[str]            # dropped: in the span of earlier columns (logged)
    merges: list[str]             # merge-list steps applied (in order)
    linear: list[str]             # linear M0 terms after merges (continuous z + binary)
    forced_quadratic: list[str]
    optional: list[str]           # optional quadratic terms included
    candidates: list[str]         # the full fixed-order optional list
    excluded_terms: list[str]     # optional terms NOT in Q: "beyond M0" is beyond the span WITHOUT these
    m0_used: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)


def q_m0(m0: pd.DataFrame, binary: list[str] | tuple[str, ...] | None = None, era: pd.Series | None = None,
         cfg: dict[str, Any] | None = None) -> QPlan:
    """Q(M0) for the H4 residualisation under DECISIONS D-037 (label-free, deterministic; NO PCA).

    1. Linear block: 1, z(forced speech), z(other continuous M0), binary (raw), era dummies -- always.
    2. Forced quadratics: speech_rate^2, speech_frac^2, speech_rate*speech_frac -- always.
    3. If rank(1 + 2) > floor(N/3): apply ``m0.merge_list`` steps in order, one at a time, until it fits
       (exhausted -> ValueError). Never PCA.
    4. Optional quadratic terms in :func:`optional_term_order`, each kept only while it raises the
       numerical rank (rcond ``m0.rank_rcond``) and rank <= floor(N/3).
    Asserts finiteness, rank <= floor(N/3) and cond(Q) <= ``m0.max_cond``. Aliased columns are logged.
    """
    mc = _m0_cfg(cfg)
    forced = list(mc["forced_speech"])
    binary = list(binary if binary is not None else [b for b in mc.get("binary", []) if b in m0.columns])
    rcond = float(mc["rank_rcond"])
    max_cond = float(mc["max_cond"])
    ddof = int(mc.get("z_ddof", 0))
    x0 = m0.astype(float)
    if not np.isfinite(x0.to_numpy()).all():
        raise ValueError("M0 has non-finite entries: run impute_m0 first")
    for f in forced:
        if f not in x0.columns:
            raise KeyError(f"forced speech feature {f!r} is not in M0 (D-034/D-037)")
    n = len(x0)
    limit = n // 3
    era_cols = _era_dummies(era, x0.index)
    steps = merge_list(cfg)

    applied: list[str] = []
    while True:
        x = apply_merges(x0, [s for s in steps if s["name"] in applied], ddof)
        cont = [c for c in x.columns if c not in binary]
        z = pd.DataFrame(zscore(x[cont].to_numpy(), ddof), index=x.index, columns=cont)
        cols: dict[str, np.ndarray] = {"1": np.ones(n)}
        for c in forced:
            cols[c] = z[c].to_numpy()
        for c in cont:
            if c not in forced:
                cols[c] = z[c].to_numpy()
        for b in binary:
            cols[b] = x[b].to_numpy()
        cols.update(era_cols)
        sr, sf = forced
        fq = {f"{sr}^2": z[sr].to_numpy() ** 2, f"{sf}^2": z[sf].to_numpy() ** 2,
              f"{sr}*{sf}": z[sr].to_numpy() * z[sf].to_numpy()}
        cols.update(fq)
        req = list(cols)
        kept, aliased, _ = _greedy(cols, req, rcond)
        if len(kept) <= limit:
            break
        nxt = [s for s in steps if s["name"] not in applied]
        if not nxt:
            raise ValueError(
                f"rank of the linear + forced block = {len(kept)} > floor(N/3) = {limit} (N = {n}) "
                f"even after the full merge list {applied}; a DECISIONS entry is required before P6 (D-037)")
        applied.append(nxt[0]["name"])
        log.warning("Q(M0): rank %d > floor(N/3) = %d -> merge step %r (%s)", len(kept), limit,
                    nxt[0]["name"], "+".join(nxt[0]["members"]))

    cand = optional_term_order(z, forced, ddof)
    for t in cand:
        if "*" in t:
            a, b = t.split("*")
            cols[t] = z[a].to_numpy() * z[b].to_numpy()
        else:
            cols[t] = z[t.removesuffix("^2")].to_numpy() ** 2
    kept, al2, not_reached = _greedy(cols, cand, rcond, kept=kept, limit=limit)
    aliased += al2
    optional = [t for t in cand if t in kept]
    q = np.column_stack([cols[k] for k in kept])
    if not np.isfinite(q).all():
        raise ValueError("Q(M0) has non-finite entries")
    rank = numerical_rank(q, rcond)
    if rank != q.shape[1] or rank > limit:
        raise ValueError(f"Q(M0) rank {rank} with {q.shape[1]} kept columns, limit {limit}")
    cond = condition_number(q)
    if cond > max_cond:
        raise ValueError(f"cond(Q) = {cond:.3g} > m0.max_cond = {max_cond:.3g}: near-collinear M0 (D-037)")
    if aliased:
        log.warning("Q(M0): %d aliased column(s) dropped (in the span of earlier columns): %s",
                    len(aliased), aliased)
    excluded = [t for t in cand if t not in optional]
    log.info("Q(M0) D-037: N=%d limit=%d rank=%d merges=%s optional=%s excluded=%d", n, limit, rank, applied,
             optional, len(excluded))
    return QPlan(q=q, columns=kept, rank=rank, limit=limit, cond=cond, aliased=aliased, merges=applied,
                 linear=[c for c in req if c in x.columns], forced_quadratic=list(fq), optional=optional,
                 candidates=cand, excluded_terms=excluded, m0_used=x)


def residualize(m1: np.ndarray, q: np.ndarray) -> np.ndarray:
    """R = M1 - Q (Q^+ M1): unpenalised OLS residuals on Q(M0) (label-free, full analysis set)."""
    m1 = np.asarray(m1, dtype=float)
    beta, *_ = np.linalg.lstsq(q, m1, rcond=None)
    return m1 - q @ beta


def q_dimension_table(n_values: tuple[int, ...] = (40, 60, 80), n_era_levels: int = 3,
                      voiced_varies: bool = True, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Planned Q(M0) dimensions under D-037 for generic (non-aliased) data -- the prereg table.

    Columns: N, limit = floor(N/3), required (1 + linear + era + 3 forced), merges, optional, rank.
    """
    mc = _m0_cfg(cfg)
    p = len(m0_feature_list(cfg))
    n_bin = len(mc.get("binary", [])) if voiced_varies else 0
    n_merge_avail = sum(len(s["members"]) - 1 for s in merge_list(cfg))
    req = 1 + p + n_bin + (n_era_levels - 1) + 3
    rows = []
    for n in n_values:
        lim = n // 3
        merges, red = 0, 0
        for s in merge_list(cfg):
            if req - red <= lim:
                break
            merges += 1
            red += len(s["members"]) - 1
        if req - red > lim:
            raise ValueError(f"N = {n}: merge list (max -{n_merge_avail}) cannot fit floor(N/3) = {lim}")
        cont = p - red
        n_opt_avail = (cont - 2) + (math.comb(cont, 2) - 1)
        opt = min(lim - (req - red), n_opt_avail)
        rows.append({"N": n, "limit": lim, "required": req, "merges": merges, "optional": opt,
                     "rank": req - red + opt})
    return pd.DataFrame(rows)
