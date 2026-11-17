"""ROADMAP P1 'Manifest schema' test + FIX-P1 derived columns (D-046, D-047, D-048).

Reads only the analyst manifest (no outcome information exists there)."""
import datetime as dt
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from yct.config import load_config
from yct.curate import manifest as mf

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.csv"
CFG = load_config()


def _guard():
    spec = importlib.util.spec_from_file_location("check_blinding", ROOT / "scripts" / "check_blinding.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def df():
    return mf.read_manifest(MANIFEST)


def test_columns(df):
    assert list(df.columns) == mf.COLUMNS
    assert "outcome" not in {c.lower() for c in df.columns}
    assert not {"label_confidence", "evidence_url", "discovery_method", "route"} & set(df.columns)


def test_schema_valid(df):
    assert mf.validate(df, CFG) == []


def test_unique_ids_and_urls(df):
    assert df["video_id"].is_unique
    assert df["url"].is_unique


def test_bool_columns(df):
    for col in ("in_primary", "collected_after_lock", "platform_nonYT"):
        assert set(df[col]) <= {"True", "False"}, col


def test_era_values(df):
    assert set(df["era_stratum"]) <= {"E1", "E2", "E3", "UNKNOWN"}
    assert set(df["era_block"]) <= {"E12", "E3", "UNKNOWN"}
    assert (df.loc[df["era_stratum"].isin(["E1", "E2"]), "era_block"] == "E12").all()
    assert (df.loc[df["era_stratum"] == "E3", "era_block"] == "E3").all()


def test_wave1_columns(df):
    assert set(df["wave"]) == {"1"}
    assert set(df["collected_after_lock"]) == {"False"}
    assert (df["platform_nonYT"] == (df["platform"] != "youtube").map(str)).all()
    assert (df["upload_lag_days"].eq("") | df["upload_lag_days"].str.fullmatch(r"-?\d+")).all()


def test_lf_line_endings():
    assert b"\r" not in MANIFEST.read_bytes()


def test_no_outcome_words_in_urls(df):
    g = _guard()
    assert [v for v, u in zip(df["video_id"], df["url"], strict=True) if g.outcome_words(u)] == []
    assert df.loc[df["video_id"] == "yct_0644", "url"].tolist() == ["sealed:yct_0644"]


def test_primary_counts_unchanged(df):
    """FIX-P1 adds columns only: wave-1 rows and in_primary flags are untouched (58 primary, 56 companies)."""
    assert len(df) == 661
    prim = df[df["in_primary"] == "True"]
    assert len(prim) == 58
    assert prim["company_id"].nunique() == 56


# ---------------------------------------------------------------- helpers (synthetic)
@pytest.mark.parametrize("batch,expected", [
    ("W22", dt.date(2021, 11, 15)), ("S20", dt.date(2020, 5, 15)), ("F24", dt.date(2024, 8, 15)),
    ("X25", dt.date(2025, 3, 1)), ("W2016", dt.date(2015, 11, 15)), ("s21", dt.date(2021, 5, 15)),
    ("UNKNOWN", None), ("P26", None), ("", None),
])
def test_decision_date(batch, expected):
    assert mf.decision_date(batch, CFG) == expected


@pytest.mark.parametrize("up,batch,expected", [
    ("20220101", "W22", 47), ("2020-05-14", "S20", -1), ("UNKNOWN", "S20", None),
    ("20200101", "UNKNOWN", None),
])
def test_upload_lag_days(up, batch, expected):
    assert mf.upload_lag_days(up, batch, CFG) == expected


def test_fill_upload_lag_and_derived_columns():
    raw = pd.DataFrame({
        "video_id": ["yct_0001", "yct_0002", "yct_0003"],
        "url": ["https://a/1", "https://a/2", "https://a/3"],
        "platform": ["youtube", "linkedin", "web"],
        "upload_date": ["20220101", "UNKNOWN", "20200601"],
        "claimed_batch": ["W22", "S21", "UNKNOWN"],
        "era_stratum": ["E3", "E1", "UNKNOWN"],
        "company_id": ["a", "b", "c"], "duration_s": ["60", "61", "62"], "language": ["en"] * 3,
        "is_original_application_video": ["true"] * 3, "in_primary": ["True", "False", "False"],
    })
    out = mf.add_derived_columns(raw, CFG)
    assert list(out.columns) == mf.COLUMNS
    assert out["era_block"].tolist() == ["E3", "E12", "UNKNOWN"]
    assert out["platform_nonYT"].tolist() == ["False", "True", "True"]
    assert out["upload_lag_days"].tolist() == ["", "", ""]
    assert mf.validate(out, CFG) == []
    filled = mf.fill_upload_lag(out, CFG)
    assert filled["upload_lag_days"].tolist() == ["47", "", ""]
    assert mf.validate(filled, CFG) == []


def test_validate_catches_problems():
    good = mf.read_manifest(MANIFEST).head(5).copy()
    bad = good.copy()
    bad.loc[1, "video_id"] = bad.loc[0, "video_id"]
    assert any("duplicate video_id" in e for e in mf.validate(bad, CFG))
    bad = good.copy()
    bad.loc[0, "in_primary"] = "yes"
    assert any("in_primary" in e for e in mf.validate(bad, CFG))
    bad = good.copy()
    bad.loc[0, "era_block"] = "E1"
    assert any("era_block" in e for e in mf.validate(bad, CFG))
    bad = good.copy()
    bad.loc[0, "era_stratum"] = "E9"
    assert any("era_stratum" in e for e in mf.validate(bad, CFG))
    bad = good.copy()
    bad.loc[0, "upload_lag_days"] = "soon"
    assert any("upload_lag_days" in e for e in mf.validate(bad, CFG))
    assert any("columns" in e for e in mf.validate(good.drop(columns=["wave"]), CFG))


def test_era_block_rejects_unmapped_stratum():
    with pytest.raises(ValueError):
        mf.era_block("E9", CFG)


def test_qc_pass_analysis_set(df):
    """D-050: owner label QC removes exactly the 5 disagreeing / non-A re-derived ids."""
    qc_fail = {"yct_0401", "yct_0640", "yct_0641", "yct_0642", "yct_0643"}
    assert set(df.loc[(df["in_primary"] == "True") & (df["qc_pass"] == "False"), "video_id"]) == qc_fail
    assert (df.loc[df["qc_pass"] == "True", "in_primary"] == "True").all()
    assert len(mf.analysis_set(df)) == 53
