"""D-074: Commons category candidate source for the localiser images (config + schema + freeze)."""

import copy
import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from yct.config import load_config
from yct.config_schema import validate_config

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
D = CFG["controls"]["refclips_d074"]
R = CFG["controls"]["refclips"]


def _bad(mut):
    c = copy.deepcopy(CFG)
    mut(c["controls"]["refclips_d074"])
    with pytest.raises(ValidationError):
        validate_config(c)


def test_d074_key_values():
    assert D["decision"] == "D-074"
    assert D["image_sources"] == {
        "face": [{"category": "Portrait photographs", "depth": 0}],
        "body": [{"category": "Rear views of people", "depth": 0}],
        "place": [{"category": "Empty rooms", "depth": 0}, {"category": "Empty streets", "depth": 0}],
    }
    assert D["namespace"] == 6 and D["bitmap_mediatype"] == "BITMAP"
    assert "iiprop=mime|mediatype|sha1|size" in D["api"] and "prop=info|imageinfo" in D["api"]
    assert D["image_snapshot_limit"] == 6000 and D["require_complete"] is True
    assert D["snapshot_file_suffix"] == "_d074"
    validate_config(CFG)


@pytest.mark.parametrize("mut", [
    lambda d: d.update(extra=1),
    lambda d: d["image_sources"]["face"][0].update(depth=1),
    lambda d: d.update(require_complete=False),
    lambda d: d.update(snapshot_file_suffix="_v2"),
    lambda d: d.update(decision="D-075"),
    lambda d: d.update(namespace=0),
    lambda d: d.update(bitmap_mediatype="DRAWING"),
    lambda d: d["image_sources"].update(face=[]),
    lambda d: d["image_sources"].pop("body"),
    lambda d: d["image_sources"].update(object=[{"category": "x", "depth": 0}]),
    lambda d: d.update(image_snapshot_limit=0),
])
def test_d074_schema_rejects(mut):
    _bad(mut)


def test_d071_record_unchanged():
    assert R["version"] == "v1"
    assert R["s3_root"] == "s3://yct-research-235229001983/wave1/derived/p4b_ref/v1/"
    assert R["image_queries"]["face"] == ['"frontal portrait photograph"']
    assert R["snapshot_limits"] == {"image": 2000, "nat": 1000}
    assert set(D["image_sources"]) == set(R["loc_categories"])


def test_d074_entry_in_decisions_and_d073_still_reserved():
    text = (ROOT / "DECISIONS.md").read_text()
    entries = re.findall(r"^- D-074\b.*$", text, flags=re.M)
    assert len(entries) == 1 and "owner approved" in entries[0]
    assert not re.findall(r"^- D-073\b", text, flags=re.M)      # D-073 still reserved (ablation)


def test_d074_frozen_rows_once_present_point_at_the_key_commit():
    rows = {r["key"]: r["frozen_at"] for r in yaml.safe_load((ROOT / "config.yaml").read_text())["frozen"]}
    if "controls.refclips_d074" in rows:
        sha = rows["controls.refclips_d074"]
        assert re.fullmatch(r"[0-9a-f]{40}", sha)
    if "controls.refclips_artifacts.image_snapshot_sha256" in rows:
        assert CFG["controls"]["refclips_artifacts"]["image_snapshot_sha256"] is not None
