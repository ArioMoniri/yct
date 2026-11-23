"""D-071 (P4b pre-run freeze): config keys, the MT_plus demotion key, curation keys, stimulus-balance rules.
Label-free: reads config.yaml and DECISIONS.md only."""
import re
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from yct.config import load_config, with_overrides
from yct.config_schema import validate_config

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
C = CFG["controls"]
R = C["refclips"]
A = C["kernel"]["acceptance"]


def test_demotion_key_mt_plus_only():
    assert A["on_fail"] == {"FFC": "stop", "AUD": "stop", "AUD_audioonly": "stop", "MT_plus": "descriptive"}
    assert A["on_stop_invalid"] == "stop" and A["demotion_final"] is True
    assert A["K6"]["roi"] == "MT_plus"
    assert C["regressors"]["motion"]["gating"] is True     # frozen at c616a9d; read together with on_fail


@pytest.mark.parametrize("bad", [{"on_stop_invalid": "descriptive"}, {"on_fail": {"FFC": "maybe"}}])
def test_demotion_key_rejects_other_values(bad):
    validate_config(CFG)
    with pytest.raises(ValidationError):
        validate_config(with_overrides(CFG, {"controls": {"kernel": {"acceptance": bad}}}))


def test_acceptance_thresholds():
    assert A["K1"] == {"alpha": 0.01, "sign_all_positive": True, "ffc_min_positive_frac": 0.8}
    assert A["K2"]["plateau_frac"] == 0.9 and A["K2"]["window"] == [-1, 4]
    assert A["K3"]["min"] == 3
    assert A["K3p"]["alpha_two_sided"] == 0.01 and A["K3p"]["max_frac_peak"] == 0.10
    assert A["K4a"]["min_median_r"] == 0.5 and A["K4b"]["min_r"] == 0.7
    assert C["kernel"]["window_tr"] == [-4, 8]  # single source of the kernel lags
    assert "lags" not in A


def test_pass_block_replaced_and_single_sources():
    p = C["pass"]
    assert set(p) == {"a", "b", "c", "d"}
    assert p["a"] == {"mean_z_min": 0.2, "alpha": 0.001, "z_clip": 0.999999, "low_sd_pctile": 10,
                      "min_videos": 15}
    assert p["b"] == {"alpha": 0.01} and p["c"]["route_blocks"] is False and p["c"]["n_perm"] == 10000
    assert "readout_lags" not in p["d"] and C["readout_lag_tr"] == [0, 3]
    assert "era_merge_min" not in p["c"] and CFG["era_merge_min_videos"] == 6
    assert C["kernel"]["min_reference_clips"] == min(R["families"][f] for f in ("LOC", "MOT", "SPK")) == 16


def test_rois_per_hemi_sum_to_totals_and_mw_removed():
    for roi, (left, right) in C["rois_per_hemi"].items():
        assert left + right == C["rois"][roi]["n_vertices"], roi
    assert C["mw_removed_frac"] == {r: 0.0 for r in C["rois_per_hemi"]}


def test_curation_snapshot_keys():
    assert R["loc_categories"] == ["face", "body", "place"]
    assert R["loc_per_category"] == 20 and R["nat_n"] == 15
    assert all(isinstance(v, list) and v for v in R["image_queries"].values())
    assert set(R["image_queries"]) == set(R["loc_categories"])
    assert R["snapshot_limits"] == {"image": 2000, "nat": 1000}
    lic = R["image_licences"]
    assert "PD-*" in lic and not any("SA" in x or "NC" in x or "ND" in x for x in lic)
    assert {"licence", "personality_rights", "duplicate"} <= set(R["reject_reasons"])
    art = C["refclips_artifacts"]
    assert set(art) == {"image_snapshot_sha256", "nat_snapshot_sha256", "image_manifest_sha256",
                        "nat_manifest_sha256", "manifest_sha256",
                        "speech_corpus_sha256",         # D-085 draft (speech corpus, set before its freeze)
                        "speech_selection_sha256",      # D-085 part 2 step 2 (D-089 rates)
                        "talkface_face_sha256"}         # D-085 part 2 step 3
    assert "manifest_sha256" not in R                   # later-filled values never sit in the frozen subtree


def test_artifact_sha_must_be_hex():
    with pytest.raises(ValidationError):
        validate_config(with_overrides(CFG, {"controls": {"refclips_artifacts": {"manifest_sha256": "x"}}}))
    ok = with_overrides(CFG, {"controls": {"refclips_artifacts": {"manifest_sha256": "a" * 64}}})
    validate_config(ok)
    assert ok["controls"]["refclips_artifacts"]["manifest_sha256"] == "a" * 64


def test_cap_keys_and_launcher_limit():
    assert R["campaign_cap_usd"] == 75 and R["campaign_warn_usd"] == 60
    assert R["ledger_name_prefix"] == "yct-p4b-ref"
    assert R["s3_root"].endswith("/wave1/derived/p4b_ref/v1/") and "/p4/" not in R["s3_root"]
    assert CFG["p4"]["launcher_max_hours"] == 1.75
    with pytest.raises(ValidationError):
        validate_config(with_overrides(CFG, {"controls": {"refclips": {"campaign_warn_usd": 80}}}))


def _shift(i):
    return 0 if (i // 2) % 2 == 0 else -1


def test_shift_rule_balanced_per_half():
    assert R["shift_rule"] == "s = 0 if (i // 2) % 2 == 0 else -1"
    for n in (R["families"]["SPK"], R["families"]["MOT"], R["families"]["LOC"]):
        for half in (0, 1):
            c = Counter(_shift(i) for i in range(n) if i % 2 == half)
            assert c[0] == c[-1], (n, half, c)


def test_mot_direction_and_pattern_balanced_per_half():
    assert R["mot_direction_rule"] == "((3 * (i // 2) + k) % 8)"
    assert R["mot_pattern_rule"] == "dot if (i // 4) % 2 == 0 else grating"
    n = R["families"]["MOT"]
    pairs = set()
    for half in (0, 1):
        idx = [i for i in range(n) if i % 2 == half]
        dirs = Counter((3 * (i // 2) + k) % 8 for i in idx for k in range(3))
        assert set(dirs.values()) == {3} and len(dirs) == 8, (half, dirs)
        cross = Counter(("dot" if (i // 4) % 2 == 0 else "grating", _shift(i)) for i in idx)
        assert set(cross.values()) == {2} and len(cross) == 4, (half, cross)
    for i in range(n):
        for k in range(3):
            pairs.add((i, (3 * (i // 2) + k) % 8))
    assert len(pairs) == 3 * n == 48


def test_loc_latin_rows_split_per_half():
    assert R["loc_latin_rule"] == "(i // 2) % 3"
    for half in (0, 1):
        c = Counter((i // 2) % 3 for i in range(R["families"]["LOC"]) if i % 2 == half)
        assert sorted(c.values()) == [3, 3, 4], (half, c)


def test_seeds_present():
    s = CFG["seeds"]
    assert (s["controls_perm"], s["controls_boot"], s["refclips"]) == (20261119, 20261120, 20261121)


def test_d073_reserved_for_the_audio_only_ablation():
    text = (ROOT / "DECISIONS.md").read_text()
    for line in re.findall(r"^\s*- D-073\b.*$", text, flags=re.M):
        assert "audio-only" in line.lower(), line
