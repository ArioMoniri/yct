"""D-087 v2 (council cycle 1 + owner rulings 2026-11-23): round-0 pre-exclusion of place_14, the pre-build
scramble/swap screen of every slot, face intact detections descriptive only, per-patch sha256 in the screen
record, the pod driver (continuation committed before re-screening), the v2 builder path with the split
rebuild identity, and T-DRV-V2 (the v2 cap in guard_launch). Tests written before the code."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import locscreen as L  # noqa: N812
from yct.tribe_run import ref_campaign as rcmp
from yct.tribe_run import refclips58 as R  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
CATS = ["face", "body", "place"]
PLACE14 = "File:Naantali, Kultaranta 1 kerros, presidentin työhuone 1974 (HK10000-5797).tif"


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cands(n_per=25):
    return {c: [{"title": f"{c}_{j}", "rank": 10 * j + 1, "category": c} for j in range(n_per)] for c in CATS}


def _code(title):
    c, j = title.split("_")
    return CATS.index(c), int(j)


def patch_of(row):
    a = np.zeros((4, 4), np.uint8)
    a[0, 0], a[0, 1] = _code(row["title"])
    return a


def ident(ims):
    return [np.asarray(x) for x in ims]


def to_bgr(p, long_side):
    return np.repeat(np.asarray(p)[:, :, None], 3, axis=2)


def yunet_on(bad):
    bad_vals = {_code(t) for t in bad}

    def y(bgr, thr):
        v = (int(bgr[0, 0, 0]), int(bgr[0, 1, 0]))
        return [{"score": 0.7}] if v in bad_vals else []
    return y


def render_with_scrambles(scr_bad):
    """Fake render: intact entries are the processed patches; each slot also gets one 'scramble' entry whose
    pixel code is the slot image's code + 100 in [0,1] when the slot title is in scr_bad (else a blank)."""
    def render(by_cat, slots):
        out = []
        for c in CATS:
            for k, p in enumerate(by_cat[c]):
                out.append({"category": c, "slot": k, "kind": "intact", "clip": f"loc_{k:02d}", "k": 0,
                            "patch": p})
                s = np.full((4, 4), 250, np.uint8)      # a blank that matches no image code
                if slots[c][k]["title"] in scr_bad:
                    s[0, 0], s[0, 1] = 200, 200
                out.append({"category": c, "slot": k, "kind": "scramble", "clip": f"loc_{k:02d}", "k": 0,
                            "patch": s})
        return out
    return render


def yunet_scr(bad_intact):
    bad_vals = {_code(t) for t in bad_intact}

    def y(bgr, thr):
        v = (int(bgr[0, 0, 0]), int(bgr[0, 1, 0]))
        return [{"score": 0.7}] if v in bad_vals or v == (200, 200) else []
    return y


GATE = L.make_gate(["body", "place"], ["scramble", "swap"], CATS)


def sel(c, y, render=None, pre=(), n=20, max_rounds=5):
    return L.select(c, n, patch_of, ident, y, thr=0.5, long_side=640, max_rounds=max_rounds, cats=CATS,
                    to_bgr=to_bgr, render=render, gate=GATE, pre_excluded=pre)


# ---- round-0 pre-exclusion (owner: "Pre-exclude place_14") ----
def test_pre_excluded_image_is_replaced_in_its_slot_in_round_0():
    out = sel(cands(), yunet_on(set()), pre=["place_14"])
    s = [r["title"] for r in out["slots"]["place"]]
    assert s[14] == "place_20" and "place_14" not in s
    assert s[:14] == [f"place_{j}" for j in range(14)] and s[15:] == [f"place_{j}" for j in range(15, 20)]
    r0 = [r for r in out["replacements"] if r["round"] == 0]
    assert r0 == [{"round": 0, "category": "place", "slot": 14, "out": "place_14", "in": "place_20",
                   "scores": [], "reason": "pre_excluded"}]
    assert "place_14" in out["excluded"]


def test_pre_excluded_needs_a_continuation_when_only_20_are_logged():
    with pytest.raises(L.NeedMorePasses) as e:
        sel(cands(20), yunet_on(set()), pre=["place_14"])
    assert (e.value.category, e.value.n_passes) == ("place", 21)


def test_unknown_pre_excluded_title_is_refused():
    with pytest.raises(ValueError, match="not among the slot images"):
        sel(cands(), yunet_on(set()), pre=["place_99"])


# ---- scramble/swap screen (owner: "Screen scrambles too"), face intact descriptive (owner Q1) ----
def test_face_intact_hit_is_descriptive_and_never_replaced():
    out = sel(cands(), yunet_on({"face_3"}), render=render_with_scrambles(set()))
    assert [r["title"] for r in out["slots"]["face"]] == [f"face_{j}" for j in range(20)]
    d = out["round_log"][-1]["descriptive"]
    assert any(x["title"] == "face_3" and x["kind"] == "intact" for x in d)


def test_face_absent_is_recorded():
    out = sel(cands(), yunet_on({"face_0"}), render=render_with_scrambles(set()))
    assert out["face_absent"] == [f"face_{j}" for j in range(1, 20)]


def test_scramble_hit_replaces_that_slot_including_a_face_slot():
    out = sel(cands(), yunet_scr(set()), render=render_with_scrambles({"face_5", "body_2"}))
    assert out["slots"]["face"][5]["title"] == "face_20"
    assert out["slots"]["body"][2]["title"] == "body_20"
    kinds = {(r["category"], r["slot"]): r["kinds"] for r in out["replacements"]}
    assert kinds[("face", 5)] == ["scramble"] and kinds[("body", 2)] == ["scramble"]
    assert out["max_consumed_rank"]["face"] == cands()["face"][20]["rank"]


def test_make_gate_reads_the_rule():
    g = L.make_gate(["body", "place"], ["scramble", "swap"], CATS)
    assert g({"category": "face", "kind": "scramble"}) and g({"category": "face", "kind": "swap"})
    assert not g({"category": "face", "kind": "intact"})
    assert g({"category": "body", "kind": "intact"}) and g({"category": "place", "kind": "intact"})


# ---- per-patch sha256 (council B2 / rebuild identity) ----
def test_result_has_one_patch_sha_per_slot_of_the_final_round():
    out = sel(cands(), yunet_on({"place_3"}))
    for c in CATS:
        assert len(out["patch_sha256"][c]) == 20
    want = L.patch_sha(patch_of({"title": "place_20"}))
    assert out["patch_sha256"]["place"][3] == want


def test_patch_sha_covers_shape_and_bytes():
    a = np.zeros((2, 8), np.uint8)
    assert L.patch_sha(a) != L.patch_sha(a.reshape(4, 4))
    assert L.patch_sha(a) == hashlib.sha256(b"2x8:" + a.tobytes()).hexdigest()


# ---- the real rendering (must equal what the builder draws) ----
def _images(seed=0):
    rng = np.random.default_rng(seed)
    return {c: [rng.integers(0, 256, (R.PATCH, R.PATCH)).astype(np.uint8) for _ in range(20)] for c in CATS}


def test_rendered_patches_match_loc_frames_pixel_for_pixel():
    cfg = load_config()
    ims = _images()
    ents = L.rendered_loc_patches(ims, cfg)
    clip = next(c for c in R.plan(cfg) if c.family == "LOC" and c.i == 4)
    twin = next(c for c in R.plan(cfg) if c.family == "LOC_SCR" and c.i == 4)
    fr = R.loc_frames(clip, ims)
    fr2 = R.loc_frames(twin, ims)
    y0, x0 = (R.H - R.PATCH) // 2, (R.W - R.PATCH) // 2
    crop = lambda f: f[y0:y0 + R.PATCH, x0:x0 + R.PATCH]  # noqa: E731
    for e in clip.events:
        mine = {x["kind"]: x["patch"] for x in ents if x["clip"] == "loc_04" and x["k"] == e["k"]}
        t_in = int((e["onset"] + 0.5) * R.FPS)
        assert np.array_equal(mine["intact"], crop(fr[t_in]))
        assert np.array_equal(mine["swap"], crop(fr2[t_in]))
        seg = [n for n in range(int(R.DUR * R.FPS)) if R._in_event(n / R.FPS, clip) is None
               and R._segment(n / R.FPS, clip) == e["k"]]
        assert np.array_equal(mine["scramble"], crop(fr[seg[0]]))


def test_rendered_entries_cover_every_slot_and_kind():
    cfg = load_config()
    ents = L.rendered_loc_patches(_images(1), cfg)
    for c in CATS:
        for k in range(20):
            kinds = {e["kind"] for e in ents if e["category"] == c and e["slot"] == k}
            assert kinds == {"intact", "scramble", "swap"}


# ---- config (owner rulings recorded a priori) ----
def test_config_records_the_owner_rulings():
    d = load_config()["controls"]["refclips_d087"]
    assert d["screen"]["categories"] == ["body", "place"]
    assert d["screen"]["face_intact"] == "descriptive"
    assert d["screen"]["scramble_kinds"] == ["scramble", "swap"]
    assert d["screen"]["scramble_categories"] == CATS
    pe = d["pre_excluded"]
    assert pe == [{"category": "place", "slot": 14, "title": PLACE14,
                   "trigger": "outputs/runs/refclips_v1_d085_build2/STOP_NOTE.md"}]
    v4 = json.loads((ROOT / "data/refstim/image_place_manifest.json").read_text())
    assert v4[14]["title"] == PLACE14
    ri = d["rebuild_identity"]
    assert ri["build1"]["families"] == ["GREY_CTRL", "FLASH", "MOT", "MOT_STAT"]
    assert ri["loc"] == {"families": ["LOC", "LOC_SCR"], "against": "screen_record.patch_sha256"}
    assert d["continuation"]["committed_before_rescreen"] is True
    assert d["continuation"]["cap_or_exhaustion"] == "stop_owner_final"
    assert d["screen_record"] == "data/refstim/loc_screen_v2.json"


# ---- the pod driver (scripts/locscreen_v2.py) ----
def _cfg_frozen():
    cfg = copy.deepcopy(load_config())
    cfg["frozen"] = cfg["frozen"] + [{"key": "controls.refclips_d087", "frozen_at": "x"}]
    return cfg


def _write_logs(root, n_pass):
    d = root / "data" / "refstim"
    d.mkdir(parents=True, exist_ok=True)
    for c in CATS:
        rows = []
        for j in range(n_pass[c]):
            rows.append({"title": f"{c}_{j}", "decision": "reject", "url": "u.jpg"})
            rows.append({"title": f"{c}_p{j}", "decision": "pass", "url": f"https://x/{c}{j}.jpg",
                         "descriptionurl": "d", "pageid": j, "revid": 1, "snapshot_revid": 1,
                         "licence": "CC0",
                         "licence_template": "Cc-zero", "artist": "a", "credit": "c",
                         "source_sha256": hashlib.sha256(f"{c}{j}".encode()).hexdigest(),
                         "crop_box": [0, 0, 8], "source": "s"})
        (d / f"image_{c}_auto_log_v4.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def _driver_fakes(scr_bad=()):
    def patch_from(row):
        a = np.zeros((4, 4), np.uint8)
        a[0, 0], a[0, 1] = CATS.index(row["category"]), int(row["title"].split("_p")[1])
        return a

    def yunet(bgr, thr):
        return [{"score": 0.7}] if int(bgr[0, 0, 0]) == 9 else []
    return patch_from, yunet


def test_driver_runs_continuation_then_asks_for_a_commit_before_rescreening(tmp_path):
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    _write_logs(tmp_path, {"face": 20, "body": 20, "place": 20})
    cfg = _cfg_frozen()
    cfg["controls"]["refclips_d087"]["pre_excluded"] = [{"category": "place", "slot": 14,
                                                         "title": "place_p14", "trigger": "t"}]
    calls = []

    def cont(cat, n):
        calls.append((cat, n))
        p = tmp_path / "data/refstim" / f"image_{cat}_auto_log_v4.jsonl"
        p.write_text(p.read_text() + json.dumps({"title": f"{cat}_p{n - 1}", "decision": "pass",
                                                 "url": "https://x/z.jpg", "crop_box": [0, 0, 8],
                                                 "source_sha256": "0" * 64}) + "\n")
    patch_from, yunet = _driver_fakes()
    rc = drv.run_screen(cfg, tmp_path, patch_from, ident, yunet, cont, committed=lambda paths: True,
                      to_bgr=to_bgr, render=None)
    assert rc == 75 and calls == [("place", 21)]
    rec = json.loads((tmp_path / "data/refstim/loc_screen_v2_continuation.json").read_text())
    assert rec["category"] == "place" and rec["target"] == 21 and rec["prefix_identical"] is True
    with pytest.raises(SystemExit, match="commit"):
        drv.run_screen(cfg, tmp_path, patch_from, ident, yunet, cont, committed=lambda paths: False,
                     to_bgr=to_bgr, render=None)
    rc = drv.run_screen(cfg, tmp_path, patch_from, ident, yunet, cont, committed=lambda paths: True,
                      to_bgr=to_bgr, render=None)
    assert rc == 0
    scr = json.loads((tmp_path / "data/refstim/loc_screen_v2.json").read_text())
    assert scr["replacements"][0]["reason"] == "pre_excluded"
    man = json.loads((tmp_path / "data/refstim/image_place_manifest_v2.json").read_text())
    assert len(man) == 20 and man[14]["title"] == "place_p20"
    assert all(r["s3_key"].startswith("sources/images/place/v2/") for r in man)
    assert set(scr["patch_sha256"]) == set(CATS)


def test_driver_refuses_a_continuation_that_rewrites_existing_rows(tmp_path):
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    _write_logs(tmp_path, {"face": 20, "body": 20, "place": 20})
    cfg = _cfg_frozen()
    cfg["controls"]["refclips_d087"]["pre_excluded"] = [{"category": "place", "slot": 14,
                                                         "title": "place_p14", "trigger": "t"}]

    def bad_cont(cat, n):
        p = tmp_path / "data/refstim" / f"image_{cat}_auto_log_v4.jsonl"
        p.write_text("x" + p.read_text())
    patch_from, yunet = _driver_fakes()
    with pytest.raises(SystemExit, match="byte-identical"):
        drv.run_screen(cfg, tmp_path, patch_from, ident, yunet, bad_cont, committed=lambda paths: True,
                     to_bgr=to_bgr, render=None)


def test_driver_continuation_cap_is_a_final_stop(tmp_path):
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    _write_logs(tmp_path, {"face": 20, "body": 20, "place": 20})
    cfg = _cfg_frozen()
    cfg["controls"]["refclips_d087"]["continuation"]["max_extra_per_category"] = 0
    cfg["controls"]["refclips_d087"]["pre_excluded"] = [{"category": "place", "slot": 14,
                                                         "title": "place_p14", "trigger": "t"}]
    patch_from, yunet = _driver_fakes()
    with pytest.raises(SystemExit, match="final STOP"):
        drv.run_screen(cfg, tmp_path, patch_from, ident, yunet, lambda c, n: None,
                     committed=lambda paths: True, to_bgr=to_bgr, render=None)


def test_driver_refuses_until_d087_is_frozen(tmp_path):
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg = load_config()
    cfg["frozen"] = [f for f in cfg["frozen"] if not f["key"].startswith("controls.refclips_d087")]
    with pytest.raises(SystemExit, match="not frozen"):
        drv.run_screen(cfg, tmp_path, None, None, None, None, committed=lambda p: True)


# ---- builder v2 path (scripts/refclips_build.py) ----
def _builder():
    return _mod("refclips_build", "scripts/refclips_build.py")


def test_v2_manifests_refused_until_frozen_and_sha_matches(tmp_path):
    bld = _builder()
    from _pre_d087 import pre_d087
    cfg = pre_d087(copy.deepcopy(load_config()))   # the state before the D-087 freeze (24bf885 / eb458aa)
    with pytest.raises(SystemExit, match="not frozen"):
        bld.check_image_manifests_v2(cfg, tmp_path)


def test_v2_manifests_accepted_at_the_frozen_repo_state():
    bld = _builder()
    mans, screen = bld.check_image_manifests_v2(load_config())   # frozen shas == the committed files
    assert {c: len(mans[c]) for c in CATS} == {c: 20 for c in CATS}
    assert screen["rounds"] >= 1


def test_v2_patch_identity_mismatch_is_reported():
    bld = _builder()
    ims = {c: [np.full((3, 3), j, np.uint8) for j in range(2)] for c in CATS}
    rec = {"patch_sha256": {c: [L.patch_sha(p) for p in ims[c]] for c in CATS}}
    assert bld.patch_identity_mismatches(ims, rec) == []
    rec["patch_sha256"]["body"][1] = "0" * 64
    assert bld.patch_identity_mismatches(ims, rec) == ["body[1]"]


def test_v2_rebuild_identity_compares_only_the_build1_families():
    bld = _builder()
    recs = {"loc_00": {"sha256": {"mp4": "a", "wav": "b", "tsv": "c"}},
            "mot_00": {"sha256": {"mp4": "m", "wav": "w", "tsv": "t"}}}
    rec1 = {"loc_00.mp4": "Z", "loc_00.wav": "Z", "loc_00.tsv": "Z",
            "mot_00.mp4": "m", "mot_00.wav": "w", "mot_00.tsv": "t", "grey_ctrl_00.mp4": "g"}
    r1, d1 = bld.restrict_build1(rec1, {}, ["MOT"]), {}
    assert set(r1) == {"mot_00.mp4", "mot_00.wav", "mot_00.tsv"}
    sub = bld.restrict_recs(recs, ["MOT"])
    assert bld.name_set_mismatches(sub, r1) == [] and bld.rebuild_mismatches(sub, r1, d1) == []


# ---- T-DRV-V2: the v2 cap in guard_launch ----
def _launch(iid, name, t, price=2.0):
    return {"event": "launch", "id": iid, "name": name, "usd_per_hour": price, "t": t, "deadline": t + 6300}


def _term(iid, t):
    return {"event": "terminate", "id": iid, "t": t, "reason": "job_done"}


def test_campaign_cap_is_the_d087_cap_once_frozen():
    cfg = _cfg_frozen()
    cfg["controls"]["refclips_d087"]["cost_cap_usd"] = 10
    assert rcmp.campaign_cap(cfg) == 10
    cfg2 = load_config()
    cfg2["frozen"] = [f for f in cfg2["frozen"] if not f["key"].startswith("controls.refclips_d087")]
    assert rcmp.campaign_cap(cfg2) == cfg2["controls"]["refclips"]["campaign_cap_usd"]


def test_guard_launch_counts_the_carried_nat_spend_against_the_v2_cap():
    cfg = _cfg_frozen()
    recs = [_launch("n", "yct-p4b-ref-nat0", 0.0, price=1.99), _term("n", 701.0)]   # ~$0.39
    lines = [json.dumps(r) for r in recs]
    base = rcmp.make_baseline([], 0.0, 0.0)
    with pytest.raises(rcmp.CampaignCapError, match="cap"):
        rcmp.guard_launch(cfg, recs, lines, base, price=1.0, max_hours=74.9, now=1000.0, ack=True)
    out = rcmp.guard_launch(cfg, recs, lines, base, price=1.0, max_hours=74.0, now=1000.0, ack=True)
    assert out["cap_usd"] == 75 and out["campaign_spend_usd"] >= cfg["controls"]["refclips_d087"][
        "spend_carried_usd"] - 0.01


def test_guard_launch_refuses_when_ledger_spend_is_below_the_carried_spend():
    cfg = _cfg_frozen()
    base = rcmp.make_baseline([], 0.0, 0.0)
    with pytest.raises(rcmp.CampaignCapError, match="carried"):
        rcmp.guard_launch(cfg, [], [], base, price=1.0, max_hours=1.0, now=1000.0)
