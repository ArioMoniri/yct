"""ROADMAP P0 test_config_schema (QA P0 #1): config.yaml is validated by yct.config_schema (pydantic,
extra="forbid", strict types). The repo config must load; a missing key, a wrong type and an unknown key
must each be rejected, in every section."""
import copy

import pytest
import yaml
from pydantic import ValidationError

from yct.config import CONFIG_PATH, load_config
from yct.config_schema import Config, validate_config

RAW = yaml.safe_load(CONFIG_PATH.read_text())
FREE_FORM = {"era_strata"}  # mapping of stratum name -> typed Era entries


def _cfg():
    return copy.deepcopy(RAW)


def test_repo_config_is_valid():
    validate_config(_cfg())
    assert load_config() == RAW


def test_schema_covers_every_top_level_section():
    assert set(RAW) == {f.alias or n for n, f in Config.model_fields.items()}


@pytest.mark.parametrize("section", sorted(k for k, v in RAW.items() if isinstance(v, dict)))
def test_unknown_key_rejected_in_every_section(section):
    c = _cfg()
    c[section]["mistyped_key"] = 1
    with pytest.raises(ValidationError, match="mistyped_key"):
        validate_config(c)


def test_unknown_top_level_key_rejected():
    c = _cfg()
    c["windw"] = {"default_start_tr": 5}
    with pytest.raises(ValidationError, match="windw"):
        validate_config(c)


@pytest.mark.parametrize("section", sorted(k for k, v in RAW.items() if isinstance(v, dict) and v
                                           and k not in FREE_FORM))
def test_missing_key_rejected_in_every_section(section):
    for key in RAW[section]:
        c = _cfg()
        del c[section][key]
        with pytest.raises(ValidationError, match=key):
            validate_config(c)


@pytest.mark.parametrize("path,bad", [
    ("tribe.tr_s", "1.0"),                                   # str where a number is expected
    ("window.default_start_tr", 5.5),                        # float where an int is expected
    ("window.min_tail_s", -1),                               # negative tail
    ("normalize.photometric.enabled", "yes"),                # str where a bool is expected
    ("normalize.photometric.color_matrix", "bt601"),         # BT.709 everywhere (QA D6)
    ("normalize.video.crf", 99),
    ("budget.max_hours_per_instance", 5),                    # hard cap 4 h
    ("atlases.schaefer400_7.lh.sha256", "abc"),
    ("localize.unreliable_pattern", ["#000000"]),
    ("m0.forced_speech", ["speech_rate_wps"]),
    ("controls.regressors.face.roi", "NOPE"),
    ("owner.arn_pin", "someone"),
    ("guards.test_weakening_allowlist",
     [{"commit": "abc", "path": "t", "kind": "skip", "ticket": "BUG-001"}]),
    ("frozen", [{"key": "window", "frozen_at": "HEAD"}]),
])
def test_wrong_type_or_value_rejected(path, bad):
    c = _cfg()
    *parents, leaf = path.split(".")
    d = c
    for p in parents:
        d = d[p]
    d[leaf] = bad
    with pytest.raises(ValidationError):
        validate_config(c)


@pytest.mark.parametrize("url", [
    "https://raw.githubusercontent.com/ThomasYeoLab/CBIG/master/x.annot",
    "https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.1/x.annot",
])
def test_atlas_urls_must_be_commit_pinned(url):
    """Watchdog G-D032 c2 #3: CBIG must be pinned to a commit, not master."""
    c = _cfg()
    c["atlases"]["schaefer400_7"]["lh"]["url"] = url
    with pytest.raises(ValidationError, match="pinned|commit"):
        validate_config(c)


def test_cbig_pinned_commit_and_hashes_unchanged():
    s = RAW["atlases"]["schaefer400_7"]
    for h in ("lh", "rh"):
        assert "/ThomasYeoLab/CBIG/634f676630929a71297852d01dd92a287103e861/" in s[h]["url"]
    assert s["lh"]["sha256"] == "48dcdc0c63df9feddb34eb631ef3571dfbd73360709a3aa799e05e1bc7d9e2b5"
    assert s["rh"]["sha256"] == "1c24e9c5e2e35df05ddb8b82c60ea4ebbbbe48986bc11aa24a58ede47742f5aa"


def test_load_config_validates(tmp_path):
    c = _cfg()
    c["tribe"]["tr_s"] = "fast"
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(c))
    with pytest.raises(ValidationError):
        load_config(p)
    assert load_config(p, validate=False)["tribe"]["tr_s"] == "fast"


def test_era_blocks_merge_e1_e2():
    """D-047: E1 + E2 -> E12; raw era_strata unchanged."""
    assert RAW["era_blocks"]["merge"] == {"E12": ["E1", "E2"], "E3": ["E3"]}
    assert set(RAW["era_strata"]) == {"E1", "E2", "E3"}


@pytest.mark.parametrize("merge", [
    {"E12": ["E1", "E2"]},                          # E3 missing
    {"E12": ["E1", "E2"], "E3": ["E3", "E2"]},      # E2 twice
    {"E12": ["E1", "E2"], "E3": ["E3", "E4"]},      # unknown stratum
])
def test_era_blocks_must_partition_era_strata(merge):
    c = _cfg()
    c["era_blocks"]["merge"] = merge
    with pytest.raises(ValidationError, match="era_strata"):
        validate_config(c)


@pytest.mark.parametrize("path,bad", [
    ("manifest.decision_date.W.month", 13),
    ("manifest.decision_date.S.year_offset", 1),
    ("era_blocks.route_merge_min_videos", 0),
])
def test_manifest_and_era_block_values_checked(path, bad):
    c = _cfg()
    *parents, leaf = path.split(".")
    d = c
    for p in parents:
        d = d[p]
    d[leaf] = bad
    with pytest.raises(ValidationError):
        validate_config(c)


def test_manifest_decision_date_needs_all_seasons():
    c = _cfg()
    del c["manifest"]["decision_date"]["X"]
    with pytest.raises(ValidationError, match="seasons"):
        validate_config(c)
