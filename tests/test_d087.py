"""D-087 draft (p4b_ref/v2, the single D-071 (h) redesign): pre-build post-SHINE YuNet screen + replacement
loop, the v4 filter continuation mode, and the TALKFACE start rank. Tests written before the code."""
import copy
import importlib.util
import inspect
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import locscreen as L
from yct.tribe_run import refclips_qc85 as Q

ROOT = Path(__file__).resolve().parents[1]
CATS = ["face", "body", "place"]


def _runner():
    spec = importlib.util.spec_from_file_location("refstim_auto_run", ROOT / "scripts" / "refstim_auto_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cands(n_per=25):
    """Pass rows in v4 log order: rank strictly increasing within each category."""
    return {c: [{"title": f"{c}_{j}", "rank": 10 * j + 1, "category": c} for j in range(n_per)] for c in CATS}


def _code(title):
    c, j = title.split("_")
    return CATS.index(c), int(j)


def patch_of(row):   # a deterministic per-image patch whose identity survives the fake SHINE
    a = np.zeros((4, 4), np.uint8)
    a[0, 0], a[0, 1] = _code(row["title"])
    return a


def ident_shine(ims):
    return [np.asarray(x) for x in ims]


def fake_yunet(bad, calls=None):
    """Flags any image whose patch equals the patch of a title in `bad` (a set, mutable per test)."""
    bad_vals = {_code(t) for t in bad}

    def y(bgr, thr):
        if calls is not None:
            calls.append(1)
        v = (int(bgr[0, 0, 0]), int(bgr[0, 1, 0]))
        return [{"score": 0.68}] if v in bad_vals and 0.68 >= thr else []
    return y


def to_bgr(p, long_side):   # identity stand-in for refclips_qc85.to_bgr640 (keeps the pixel value)
    return np.repeat(np.asarray(p)[:, :, None], 3, axis=2)


def run_select(c, bad, max_rounds=5, n=20, calls=None, cfg=None):
    return L.select(c, n, patch_of, ident_shine, fake_yunet(bad, calls), thr=0.5, long_side=640,
                    max_rounds=max_rounds, cats=CATS, to_bgr=to_bgr)


def test_no_flags_keeps_the_v1_selection_in_one_round():
    out = run_select(cands(), set())
    assert out["rounds"] == 1
    for c in CATS:
        assert [r["title"] for r in out["slots"][c]] == [f"{c}_{j}" for j in range(20)]
    assert out["replacements"] == []


def test_flagged_image_is_replaced_in_its_slot_by_the_next_pass_in_rank_order():
    out = run_select(cands(), {"place_14"})
    s = [r["title"] for r in out["slots"]["place"]]
    assert s[14] == "place_20" and "place_14" not in s
    assert s[:14] == [f"place_{j}" for j in range(14)] and s[15:] == [f"place_{j}" for j in range(15, 20)]
    assert out["rounds"] == 2
    assert out["replacements"] == [{"round": 1, "category": "place", "slot": 14, "out": "place_14",
                                    "in": "place_20", "scores": [0.68]}]


def test_replacements_follow_rank_and_flagged_images_never_return():
    out = run_select(cands(), {"place_14", "place_20", "face_3"})
    p = [r["title"] for r in out["slots"]["place"]]
    assert p[14] == "place_21"           # place_20 replaced place_14, then was itself flagged
    assert [r["title"] for r in out["slots"]["face"]][3] == "face_20"
    assert {"place_14", "place_20", "face_3"} == set(out["excluded"])
    assert out["rounds"] == 3


def test_order_is_invariant_to_which_images_are_flagged():
    base = cands()
    before = copy.deepcopy(base)
    a = run_select(base, {"body_2"})
    b = run_select(base, {"body_7"})
    assert base == before                # the candidate order is never mutated
    # whichever slot is flagged, the replacement is the lowest-rank unused pass
    assert [r["title"] for r in a["slots"]["body"]][2] == "body_20"
    assert [r["title"] for r in b["slots"]["body"]][7] == "body_20"


def test_round_cap_is_a_stop():
    c = cands(40)
    bad = {f"place_{j}" for j in range(14, 40)}   # every replacement is flagged again
    with pytest.raises(L.ScreenStop, match="5 rounds"):
        run_select(c, bad, max_rounds=5)


def test_running_out_of_logged_passes_asks_for_a_continuation():
    c = cands(21)
    with pytest.raises(L.NeedMorePasses) as e:
        run_select(c, {"place_14", "place_20"})
    assert e.value.category == "place" and e.value.n_passes == 22


def test_rerun_with_more_passes_is_deterministic():
    bad = {"place_14", "place_20"}
    with pytest.raises(L.NeedMorePasses):
        run_select(cands(21), bad)
    out = run_select(cands(22), bad)
    assert [r["title"] for r in out["slots"]["place"]][14] == "place_21"
    assert out == run_select(cands(22), bad)


def test_shine_is_joint_over_all_60_in_category_order():
    seen = []

    def shine(ims):
        seen.append(len(ims))
        return ims
    L.select(cands(), 20, patch_of, shine, fake_yunet(set()), thr=0.5, long_side=640, max_rounds=5,
             cats=CATS, to_bgr=to_bgr)
    assert seen == [60]


def test_consumed_rank_and_talkface_start():
    out = run_select(cands(), {"face_3"})
    assert out["max_consumed_rank"]["face"] == 10 * 20 + 1      # face_20 (rank 201) went into LOC
    passes = [{"title": "f_a", "rank": 150}, {"title": "f_b", "rank": 205}, {"title": "f_c", "rank": 300}]
    rule = {"skip_on": ["no_face_detected"], "max_skips": 5}
    got = Q.talkface_face([p for p in passes if p["rank"] > out["max_consumed_rank"]["face"]], {}, rule,
                          after_rank=out["max_consumed_rank"]["face"])
    assert got["face"]["title"] == "f_b"
    with pytest.raises(ValueError):
        Q.talkface_face(passes, {}, rule, after_rank=out["max_consumed_rank"]["face"])


def test_talkface_default_after_rank_is_unchanged():
    rule = {"skip_on": [], "max_skips": 5}
    assert Q.talkface_face([{"title": "x", "rank": 500}], {}, rule)["face"]["title"] == "x"
    with pytest.raises(ValueError):
        Q.talkface_face([{"title": "x", "rank": 492}], {}, rule)


def test_screen_uses_the_frozen_t_lic_resize_by_default():
    sig = inspect.signature(L.select)
    assert sig.parameters["to_bgr"].default is Q.to_bgr640


def test_screen_refuses_until_d087_is_frozen():
    cfg = load_config()
    cfg["frozen"] = [f for f in cfg["frozen"] if not f["key"].startswith("controls.refclips_d087")]
    calls = []
    with pytest.raises(SystemExit, match="not frozen"):
        L.require_frozen(cfg)
    assert calls == []


def test_screen_runs_on_rendered_patches_not_built_frames():
    src = inspect.getsource(L)
    assert "decode" not in src and ".mp4" not in src


def test_pass_candidates_from_a_v4_log():
    rows = [{"title": "a", "decision": "pass"}, {"title": "b", "decision": "reject"},
            {"title": "c", "decision": "pass"}]
    assert L.pass_candidates(rows, "face") == [{"title": "a", "rank": 1, "category": "face", "row": rows[0]},
                                              {"title": "c", "rank": 3, "category": "face", "row": rows[2]}]


def test_d087_config_block():
    d = load_config()["controls"]["refclips_d087"]
    assert d["decision"] == "D-087" and d["redesign"] == "p4b_ref/v2" and d["consumes_redesign"] is True
    assert d["cost_cap_usd"] == 75
    s = d["screen"]
    q = load_config()["controls"]["refclips_d085"]["qc"]
    assert s["score_threshold"] == q["yunet_score_threshold"] and s["input_long_side"] == q["yunet_input_long_side"]
    assert s["max_rounds"] == 5 and s["order"] == "v4_log_rank" and s["slot_rule"] == "replace_in_slot"
    assert d["on_fail"] == "stop_owner_final"
    assert set(d["manifests"]) == set(CATS)
    for c, p in d["manifests"].items():
        assert p.endswith(f"image_{c}_manifest_v2.json")


# ---- the v4 filter continuation mode (scripts/refstim_auto_run.py) ----

def test_parse_targets():
    r = _runner()
    assert r.parse_targets(["--target", "place=22", "--target", "face=21"], CATS) == {"place": 22, "face": 21}
    assert r.parse_targets([], CATS) == {}
    with pytest.raises(SystemExit):
        r.parse_targets(["--target", "objects=22"], CATS)
    with pytest.raises(SystemExit):
        r.parse_targets(["--target", "place=x"], CATS)


def test_target_above_20_needs_d087_frozen_and_the_cap():
    r = _runner()
    cfg = load_config()
    assert r.effective_need("place", {}, 20, cfg) == 20
    unfrozen = copy.deepcopy(cfg)
    unfrozen["frozen"] = [f for f in cfg["frozen"] if not f["key"].startswith("controls.refclips_d087")]
    with pytest.raises(SystemExit, match="not frozen"):
        r.effective_need("place", {"place": 22}, 20, unfrozen)
    frozen = copy.deepcopy(cfg)
    frozen["frozen"] = cfg["frozen"] + [{"key": "controls.refclips_d087", "frozen_at": "0" * 40}]
    assert r.effective_need("place", {"place": 22}, 20, frozen) == 22
    cap = cfg["controls"]["refclips_d087"]["continuation"]["max_extra_per_category"]
    with pytest.raises(SystemExit, match="cap"):
        r.effective_need("place", {"place": 20 + cap + 1}, 20, frozen)
    with pytest.raises(SystemExit):
        r.effective_need("place", {"place": 19}, 20, frozen)


def test_run_uses_effective_need():
    src = inspect.getsource(_runner().run)
    assert "effective_need(" in src and "targets" in src
