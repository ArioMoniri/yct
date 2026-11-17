"""M0 assembly for H4 (v2.md §1 H4; v2.4 G-D032 Biostat D1, Referee #7/#8; DECISIONS D-034).

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
4. :func:`select_kq` -- K_Q set: ``m0.forced_kq`` (speech rate and speech fraction, known issue
   #8) are ALWAYS included; the remaining slots go to the non-binary features with the largest
   variance-inflation-adjusted variance of the z-scored feature, i.e. 1 / VIF_j = 1 - R^2_j.
5. :func:`build_q` -- Q(M0) = [1, z(M0), z(M0_nonbinary)^2, pairwise products among K_Q,
   era dummies (linear only)]. Asserts every entry is finite and that the NUMERICAL rank (SVD,
   numpy default tolerance) is <= floor(N / 3); aliased columns are logged.
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
        rate = w["speech_rate_wps"].to_numpy(dtype=float) if "speech_rate_wps" in w else np.full(length, np.nan)
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


# ----------------------------------------------------------------------------- 4-5. K_Q and Q(M0)

def _z(x: np.ndarray) -> np.ndarray:
    sd = x.std(axis=0)
    return (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1.0)


def vif_adjusted_variance(m0: pd.DataFrame, binary: list[str] | tuple[str, ...] = ()) -> pd.Series:
    """1 / VIF_j = 1 - R^2_j of each z-scored non-binary feature on the others (label-free)."""
    cols = [c for c in m0.columns if c not in binary]
    z = _z(m0[cols].to_numpy(dtype=float))
    out = {}
    for j, c in enumerate(cols):
        y = z[:, j]
        if not np.any(y):
            out[c] = 0.0
            continue
        others = np.column_stack([np.ones(len(y)), np.delete(z, j, axis=1)])
        beta, *_ = np.linalg.lstsq(others, y, rcond=None)
        res = y - others @ beta
        out[c] = float(res @ res / (y @ y))
    return pd.Series(out)


def select_kq(m0: pd.DataFrame, k_q: int | None = None, forced: list[str] | None = None,
              binary: list[str] | tuple[str, ...] = (), cfg: dict[str, Any] | None = None) -> list[str]:
    """K_Q set: forced features first (always included), then the largest 1/VIF non-binary features."""
    mc = _m0_cfg(cfg) if (k_q is None or forced is None) else {}
    k_q = int(k_q if k_q is not None else mc["k_q"])
    forced = list(forced if forced is not None else mc["forced_kq"])
    for f in forced:
        if f not in m0.columns:
            raise KeyError(f"forced K_Q feature {f!r} is not in M0")
        if f in binary:
            raise ValueError(f"forced K_Q feature {f!r} is binary")
    if k_q < len(forced):
        raise ValueError(f"k_q = {k_q} < {len(forced)} forced features {forced}")
    score = vif_adjusted_variance(m0, binary).drop(forced, errors="ignore")
    rest = sorted(score.index, key=lambda c: (-score[c], c))
    return forced + rest[: k_q - len(forced)]


@dataclass
class QResult:
    q: np.ndarray
    columns: list[str]
    rank: int
    limit: int
    aliased: list[str]
    kq: list[str]


def _aliased(q: np.ndarray, names: list[str]) -> list[str]:
    kept: list[int] = []
    aliased = []
    r = 0
    for j in range(q.shape[1]):
        r_new = np.linalg.matrix_rank(q[:, [*kept, j]])
        if r_new > r:
            kept.append(j)
            r = r_new
        else:
            aliased.append(names[j])
    return aliased


def build_q(m0: pd.DataFrame, kq: list[str], binary: list[str] | tuple[str, ...] = (),
            era: pd.Series | None = None, forced: list[str] | None = None,
            cfg: dict[str, Any] | None = None) -> QResult:
    """Q(M0) for the H4 residualisation. Raises unless finite and numerical rank <= floor(N/3)."""
    forced = list(forced if forced is not None else _m0_cfg(cfg)["forced_kq"])
    missing = [f for f in forced if f not in kq]
    if missing:
        raise ValueError(f"K_Q must include {missing} (speech rate / speech fraction, D-034)")
    x = m0.astype(float)
    if not np.isfinite(x.to_numpy()).all():
        raise ValueError("M0 has non-finite entries: run impute_m0 first")
    n = len(x)
    nonbin = [c for c in x.columns if c not in binary]
    z = pd.DataFrame(_z(x[nonbin].to_numpy()), index=x.index, columns=nonbin)
    cols: dict[str, np.ndarray] = {"1": np.ones(n)}
    for c in x.columns:
        cols[c] = z[c].to_numpy() if c in nonbin else x[c].to_numpy()
    for c in nonbin:
        cols[f"{c}^2"] = z[c].to_numpy() ** 2
    for a, b in itertools.combinations(kq, 2):
        if a in binary or b in binary:
            raise ValueError(f"K_Q feature {a if a in binary else b!r} is binary")
        cols[f"{a}*{b}"] = z[a].to_numpy() * z[b].to_numpy()
    if era is not None:
        e = pd.Series(era).reindex(x.index)
        if e.isna().any():
            raise ValueError("era missing for some videos")
        for lev in sorted(e.unique())[1:]:
            cols[f"era={lev}"] = (e == lev).to_numpy(dtype=float)
    names = list(cols)
    q = np.column_stack([cols[k] for k in names])
    if not np.isfinite(q).all():
        raise ValueError("Q(M0) has non-finite entries")
    rank = int(np.linalg.matrix_rank(q))
    limit = n // 3
    aliased = _aliased(q, names)
    if aliased:
        log.warning("Q(M0): %d aliased column(s): %s", len(aliased), aliased)
    if rank > limit:
        raise ValueError(f"numerical rank(Q) = {rank} > floor(N/3) = {limit} (N = {n}); reduce the "
                         f"M0 list or K_Q before P6 (v2.md §1 H4)")
    return QResult(q=q, columns=names, rank=rank, limit=limit, aliased=aliased, kq=list(kq))


def q_column_count(p: int, n_binary: int, k_q: int, n_era: int = 0) -> int:
    """Number of Q columns for p M0 features (incl. binary), before any aliasing."""
    return 1 + p + (p - n_binary) + math.comb(k_q, 2) + max(0, n_era - 1)
