"""Analyst manifest (data/manifest.csv) schema and label-free derived columns (D-046, D-047).

Columns (analyst view; never an outcome, confidence tier, evidence or discovery route):

    video_id, url, platform, upload_date, claimed_batch, era_stratum, company_id, duration_s, language,
    is_original_application_video, in_primary,              # wave-1 Curator columns (BUG-012)
    era_block, wave, collected_after_lock, platform_nonYT, upload_lag_days   # FIX-P1 (D-046/D-047/D-048)
    qc_pass, company_key                                                    # D-050; D-053

* ``era_block``: raw ``era_stratum`` mapped through config ``era_blocks.merge`` (E1 + E2 -> E12, D-047).
* ``wave``: 1 for every row collected before the prereg lock; ``collected_after_lock`` is True only for
  rows collected after the ``prereg-lock`` tag (D-044, D-046).
* ``platform_nonYT``: ``platform != "youtube"`` (D-047 forced M0 covariate).
* ``upload_lag_days``: upload_date minus the nominal decision date of ``claimed_batch``
  (:func:`decision_date`, config ``manifest.decision_date``); empty when either is UNKNOWN. Positive =
  uploaded after the decision. Label-free: it uses the YC calendar, never the outcome. Always equal to
  :func:`fill_upload_lag` (``validate`` checks it; D-053). Since D-053 it is a SENSITIVITY-only M0
  covariate (possibly outcome-caused: post-decision uploads), never forced into the primary Q(M0).
* ``company_key``: ``sha256(salt + company_id)[:12]``, salt = config ``manifest.company_key.salt`` (a
  non-secret project constant; pseudonymisation against casual joins, not secrecy). Analysis code uses
  ``company_key`` (:func:`analysis_view`); ``company_id`` is a curation column only (D-053, Referee P1 B4).

Decision-date rule (D-048): YC notifies applicants shortly after the interview weeks, which follow a fixed
seasonal calendar. The nominal decision date per batch season is config ``manifest.decision_date``:
W<yy> -> 15 Nov of the previous year; X<yy> (Spring) -> 1 Mar; S<yy> -> 15 May; F<yy> (Fall) -> 15 Aug of
the batch year. Real dates vary by a few weeks per cycle, so the covariate has ~1-month precision; it is
used only as a coarse M0 covariate (upload timing relative to the decision), never as an outcome proxy.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

WAVE1_COLUMNS = [
    "video_id", "url", "platform", "upload_date", "claimed_batch", "era_stratum", "company_id", "duration_s",
    "language", "is_original_application_video", "in_primary",
]
DERIVED_COLUMNS = [
    "era_block", "wave", "collected_after_lock", "platform_nonYT", "upload_lag_days", "qc_pass",
    "company_key",
]
ANALYSIS_DROP = ["company_id", "url"]   # curation-only identifiers, never passed to analysis code (D-053)
COLUMNS = WAVE1_COLUMNS + DERIVED_COLUMNS
UNKNOWN = "UNKNOWN"
SEALED_URL_PREFIX = "sealed:"
_BATCH = re.compile(r"^([WSFX])(\d{2}|\d{4})$")
_BOOL = {"True": True, "False": False}


def era_block(era_stratum: str, cfg: Mapping[str, Any]) -> str:
    """Map a raw era stratum to its analysis block (config ``era_blocks``)."""
    eb = cfg["era_blocks"]
    for block, members in eb["merge"].items():
        if era_stratum in members:
            return block
    if era_stratum == UNKNOWN:
        return eb["unknown"]
    raise ValueError(f"era_stratum {era_stratum!r} is in no era_blocks.merge entry")


def decision_date(claimed_batch: str, cfg: Mapping[str, Any]) -> dt.date | None:
    """Nominal YC decision date for a batch code (W22, S2016, F24, X25); None if UNKNOWN/unparseable."""
    m = _BATCH.match(str(claimed_batch).strip().upper())
    if not m:
        return None
    season, yy = m.groups()
    year = int(yy) + (2000 if len(yy) == 2 else 0)
    rule = cfg["manifest"]["decision_date"][season]
    return dt.date(year + rule["year_offset"], rule["month"], rule["day"])


def parse_upload_date(s: str) -> dt.date | None:
    s = str(s).strip()
    if re.fullmatch(r"\d{8}", s):
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return dt.date.fromisoformat(s)
    return None


def upload_lag_days(upload_date: str, claimed_batch: str, cfg: Mapping[str, Any]) -> int | None:
    """upload_date - decision_date(claimed_batch) in days; None when either is unknown."""
    up, dec = parse_upload_date(upload_date), decision_date(claimed_batch, cfg)
    if up is None or dec is None:
        return None
    return (up - dec).days


def fill_upload_lag(df: pd.DataFrame, cfg: Mapping[str, Any]) -> pd.DataFrame:
    """Return a copy with ``upload_lag_days`` computed where upload_date and claimed_batch are known."""
    out = df.copy()
    lags = [upload_lag_days(u, b, cfg) for u, b in zip(out["upload_date"], out["claimed_batch"], strict=True)]
    out["upload_lag_days"] = ["" if v is None else str(v) for v in lags]
    return out


def company_key(company_id: str, cfg: Mapping[str, Any]) -> str:
    """Salted company pseudonym: sha256(salt + company_id)[:length] (config ``manifest.company_key``)."""
    ck = cfg["manifest"]["company_key"]
    return hashlib.sha256((str(ck["salt"]) + str(company_id)).encode()).hexdigest()[: int(ck["length"])]


def add_company_key(df: pd.DataFrame, cfg: Mapping[str, Any]) -> pd.DataFrame:
    out = df.copy()
    out["company_key"] = [company_key(c, cfg) for c in out["company_id"]]
    return out


def add_derived_columns(df: pd.DataFrame, cfg: Mapping[str, Any], wave: int = 1,
                        collected_after_lock: bool = False) -> pd.DataFrame:
    """Wave-1 manifest -> current schema; ``upload_lag_days`` by :func:`fill_upload_lag` (D-053)."""
    out = df[WAVE1_COLUMNS].copy()
    out["era_block"] = [era_block(e, cfg) for e in out["era_stratum"]]
    out["wave"] = str(int(wave))
    out["collected_after_lock"] = str(bool(collected_after_lock))
    out["platform_nonYT"] = [str(p.strip().lower() != "youtube") for p in out["platform"]]
    out["upload_lag_days"] = ""
    out = fill_upload_lag(out, cfg)
    # D-050: owner label QC not yet run for new rows -> not in the analysis set until it passes.
    out["qc_pass"] = df["qc_pass"].astype(str) if "qc_pass" in df.columns else "False"
    out = add_company_key(out, cfg)
    return out[COLUMNS]


def read_manifest(path) -> pd.DataFrame:
    """Read as strings exactly as written (no NA conversion)."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_manifest(df: pd.DataFrame, path) -> None:
    """LF line endings, no index (FIX-P1: manifest normalised to LF)."""
    df.to_csv(path, index=False, lineterminator="\n")


def analysis_set(df: pd.DataFrame) -> pd.DataFrame:
    """Wave-1 primary analysis set (D-050): conf-A per Curator AND owner label-QC pass."""
    return df[(df["in_primary"] == "True") & (df["qc_pass"] == "True")]


def analysis_view(df: pd.DataFrame) -> pd.DataFrame:
    """The analysis set as analysis code sees it: ``company_key`` instead of ``company_id``, no URL."""
    return analysis_set(df).drop(columns=ANALYSIS_DROP)


def validate(df: pd.DataFrame, cfg: Mapping[str, Any]) -> list[str]:
    """Schema problems (empty list = valid)."""
    errs: list[str] = []
    if list(df.columns) != COLUMNS:
        return [f"columns {list(df.columns)} != {COLUMNS}"]
    for col in ("video_id", "url"):
        dup = df[col][df[col].duplicated()].tolist()
        if dup:
            errs.append(f"duplicate {col}: {dup[:5]}")
    if not df["video_id"].str.fullmatch(r"yct_\d{4}").all():
        errs.append("video_id must match yct_NNNN")
    for col in ("in_primary", "collected_after_lock", "platform_nonYT", "qc_pass"):
        bad = df.loc[~df[col].isin(_BOOL), "video_id"].tolist()
        if bad:
            errs.append(f"{col} not True/False: {bad[:5]}")
    if not df["is_original_application_video"].isin({"true", "false"}).all():
        errs.append("is_original_application_video not true/false")
    eras = set(cfg["era_strata"]) | {UNKNOWN}
    bad = df.loc[~df["era_stratum"].isin(eras), "video_id"].tolist()
    if bad:
        errs.append(f"era_stratum not in {sorted(eras)}: {bad[:5]}")
    else:
        exp = [era_block(e, cfg) for e in df["era_stratum"]]
        bad = df.loc[df["era_block"] != exp, "video_id"].tolist()
        if bad:
            errs.append(f"era_block inconsistent with era_stratum: {bad[:5]}")
    if not df["wave"].str.fullmatch(r"[1-9]\d*").all():
        errs.append("wave must be a positive integer")
    exp_nonyt = (df["platform"].str.lower() != "youtube").map(str)
    if (df["platform_nonYT"] != exp_nonyt).any():
        errs.append("platform_nonYT inconsistent with platform")
    lag = df["upload_lag_days"]
    if not (lag.eq("") | lag.str.fullmatch(r"-?\d+")).all():
        errs.append("upload_lag_days must be empty or an integer")
    else:
        exp_lag = fill_upload_lag(df, cfg)["upload_lag_days"]
        bad = df.loc[lag != exp_lag, "video_id"].tolist()
        if bad:
            errs.append(f"upload_lag_days != fill_upload_lag (config manifest.decision_date): {bad[:5]}")
    exp_key = [company_key(c, cfg) for c in df["company_id"]]
    bad = df.loc[df["company_key"] != exp_key, "video_id"].tolist()
    if bad:
        errs.append(f"company_key != sha256(salt + company_id)[:12]: {bad[:5]}")
    if (df.loc[df["wave"] == "1", "collected_after_lock"] == "True").any():
        errs.append("wave-1 rows cannot be collected_after_lock")
    urls = df["url"]
    if not (urls.str.match(r"https?://") | urls.eq(SEALED_URL_PREFIX + df["video_id"])).all():
        errs.append("url must be http(s) or sealed:<video_id>")
    return errs
