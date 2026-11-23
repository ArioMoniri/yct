"""Reference session 1 pre-launch items (council refcampaign wf_06444af7-0cf, D-091): the read-only manifest
adapter on the real frozen file (U1), the measured duration (U1b), the NAT tsv sidecar (U2), the copy-only
upload plan (U3), the main-campaign projection (U4), the shared CI-green / L4 launch gate (U5), the
integration dry run of the session-1 plan, and the non-blocking checks (D-038 STOP, P4 manifest unchanged,
zero-word tsv, constant-array reliability). CPU only; no network, no GPU, no transcript text."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import test_gpu_p4b_ref as t

from yct.config import load_config, with_overrides
from yct.tribe_run import launch_checks as lc
from yct.tribe_run import nat_tsv as nt
from yct.tribe_run import ref_campaign as rcmp
from yct.tribe_run import ref_manifest as rm
from yct.tribe_run import refclips_upload as ru
from yct.tribe_run.feature_cache import feature_reliability, reliability
from yct.tribe_run.qc import clip_gate
from yct.tribe_run.word_events import _read_tsv, absolute_word_events, check_word_events, n_words_past_end

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/refstim/refclips_manifest.json"
ref, p4 = t.ref, t.p4


def _real():
    text = MANIFEST.read_text()
    return text, json.loads(text)


def _sidecar(manifest: dict, **over) -> dict:
    rows = []
    for c in manifest["clips"]:
        if c["family"] == "NAT":
            rows.append({"clip_id": f"NAT_{c['i']:02d}", "tsv_valid": True, "n_words": 100,
                         "tsv_sha256": hashlib.sha256(c["name"].encode()).hexdigest(), **over})
    return {"decision": "D-091", "rows": rows}


# ---------------------------------------------------------------- U1: adapter on the real frozen file
def test_real_frozen_manifest_sha_is_the_config_value():
    text, _ = _real()
    assert hashlib.sha256(text.encode()).hexdigest() == \
        load_config()["controls"]["refclips_artifacts"]["manifest_sha256"]


def test_adapter_on_the_real_frozen_manifest():
    _, m = _real()
    before = json.dumps(m, sort_keys=True)
    side = _sidecar(m)
    a = rm.adapt(m, side)
    assert json.dumps(m, sort_keys=True) == before, "the adapter is pure (input untouched)"
    ids = [c["clip_id"] for c in a["clips"]]
    assert len(ids) == len(set(ids)) == 120 and set(rm.D038_CLIPS) <= set(ids)
    by = {c["clip_id"]: c for c in a["clips"]}
    raw = {c["name"]: c for c in m["clips"]}
    for cid, c in by.items():
        r = raw[c["name"]]
        assert c["name"].upper() == cid and c["mp4_sha256"] == r["sha256"]["mp4"]
        if c["family"] == "NAT":
            assert c["tsv_sha256"] == {x["clip_id"]: x for x in side["rows"]}[cid]["tsv_sha256"]
        else:
            assert c["tsv_sha256"] == r["sha256"]["tsv"]
    assert by["SPK_00"]["control"] == "grey_ctrl_00" and by["SPK_00"]["onsets"] == [9.0, 29.0, 49.0]
    assert "duration_s" not in by["GREY_CTRL_00"], "no invented duration"


def test_real_manifest_without_the_nat_sidecar_is_refused():
    _, m = _real()
    with pytest.raises(rm.ManifestAdapterError, match="NAT_00"):
        rm.adapt(m)


def _mut(fn):
    _, m = _real()
    m = copy.deepcopy(m)
    fn(m)
    return m


@pytest.mark.parametrize("fn,why", [
    (lambda m: m["clips"][0].__setitem__("name", "grey_ctrl_01"), "name"),
    (lambda m: m["clips"][0]["sha256"].pop("mp4"), "mp4"),
    (lambda m: next(c for c in m["clips"] if c["family"] == "SPK")["sha256"].pop("tsv"), "tsv"),
    (lambda m: m["clips"][0].pop("i"), "lacks"),
    (lambda m: m["clips"].append(copy.deepcopy(m["clips"][0])), "unique"),
    (lambda m: [c.__setitem__("i", c["i"] + 1) or c.__setitem__("name", f"mot_{c['i']:02d}")
                for c in m["clips"] if c["family"] == "MOT"], "indices"),
    (lambda m: next(c for c in m["clips"] if c["name"] == "nat_00")["sha256"].__setitem__("tsv", "f" * 64),
     "exactly one"),
])
def test_mutated_manifest_copies_are_refused(fn, why):
    m = _mut(fn)
    with pytest.raises(rm.ManifestAdapterError, match=why):
        rm.adapt(m, _sidecar(_real()[1]))


@pytest.mark.parametrize("over,why", [({"tsv_valid": False}, "invalid"), ({"n_words": 0}, "no words"),
                                      ({"tsv_sha256": None}, "tsv_sha256")])
def test_invalid_or_empty_sidecar_rows_are_refused(over, why):
    _, m = _real()
    with pytest.raises(rm.ManifestAdapterError, match=why):
        rm.adapt(m, _sidecar(m, **over))


def test_sidecar_naming_a_non_nat_clip_is_refused():
    _, m = _real()
    side = _sidecar(m)
    side["rows"].append({"clip_id": "SPK_00", "tsv_valid": True, "n_words": 3, "tsv_sha256": "a" * 64})
    with pytest.raises(rm.ManifestAdapterError, match="non-NAT"):
        rm.adapt(m, side)


def _cfg_with_sidecar(side_text: str | None):
    over = {"controls": {"refclips_artifacts": {"nat_tsv_manifest_sha256":
                                                ref.sha256_text(side_text) if side_text else None}}}
    return with_overrides(load_config(), over)


def test_load_clip_manifest_checks_the_sidecar_sha_against_the_frozen_key():
    text, m = _real()
    side_text = json.dumps(_sidecar(m))
    adapted = ref.load_clip_manifest(text, _cfg_with_sidecar(side_text), side_text)
    assert len(adapted["clips"]) == 120
    with pytest.raises(SystemExit, match="sidecar sha256"):
        ref.load_clip_manifest(text, _cfg_with_sidecar(side_text), side_text + " ")
    with pytest.raises(SystemExit, match="sidecar sha256"):
        ref.load_clip_manifest(text, _cfg_with_sidecar(None), side_text)


def test_integration_dry_run_plan_on_the_real_manifest_is_the_d038_clips_first():
    text, m = _real()
    side_text = json.dumps(_sidecar(m))
    cfg = _cfg_with_sidecar(side_text)
    jobs = ref.plan_ref_jobs(cfg, ref.load_clip_manifest(text, cfg, side_text))
    assert [j.id for j in jobs[:3]] == ["GREY_CTRL_00.ref", "SPK_00.ref", "MOT_00.ref"]
    assert all(j.d038 for j in jobs[:3]) and not any(j.d038 for j in jobs[3:])
    assert len({j.id for j in jobs}) == 120 + 2 * 20


# ---------------------------------------------------------------- U1b: measured duration
def test_pod_inputs_parse_the_ffprobe_duration_and_a_missing_one_is_refused():
    d = "/work/yct/p4b_ref/v1/clips"
    out = f"GREY_CTRL_00 {'a' * 64} {'b' * 64} 58.000000\nSPK_00 {'c' * 64} {'d' * 64} N/A\n"
    inp = ref.parse_inputs(out, ["GREY_CTRL_00", "SPK_00"], d)
    assert inp["GREY_CTRL_00"]["ref"]["duration_s"] == 58.0 and "SPK_00" not in inp
    assert "ffprobe" in ref.inputs_cmd(d, ["X"]) and "58.0" not in ref.inputs_cmd(d, ["X"])
    man = {"clips": [{"clip_id": "GREY_CTRL_00", "mp4_sha256": "a" * 64, "tsv_sha256": "b" * 64}]}
    ref.check_inputs(inp, man)
    inp["GREY_CTRL_00"]["ref"]["duration_s"] = None
    with pytest.raises(SystemExit, match="measured duration"):
        ref.check_inputs(inp, man)


def test_pod_backend_has_no_hard_coded_duration():
    src = (ROOT / "scripts/gpu_p4b_ref.py").read_text()
    pod = src[src.index("class RefPodBackend"):src.index("RECONCILE_PATH = ")]
    assert "58.0" not in pod and "SYNTH_DURATION_S" not in pod
    assert ref.pod_clips_dir(load_config()) == load_config()["controls"]["refclips_d091"]["upload"]["pod_dir"]


# ---------------------------------------------------------------- U2: NAT tsv sidecar
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _nat_fixture(tmp: Path, words_per_clip=(3, 2)):
    jd, t1 = tmp / "asr", tmp / "t1"
    (t1 / "audio16k").mkdir(parents=True)
    jd.mkdir()
    rows = []
    for i, nw in enumerate(words_per_clip):
        name = f"t1name{i}"
        seg = {"text": " ".join(f"alpha{k}" for k in range(nw)),
               "words": [{"word": f"alpha{k}", "start": 1.0 + k, "end": 1.5 + k} for k in range(nw)]}
        (jd / f"{name}.json").write_text(json.dumps({"segments": [seg] if nw else []}))
        (t1 / f"{name}.mp4").write_bytes(f"mp4 {i}".encode())
        (t1 / "audio16k" / f"{name}.wav").write_bytes(f"wav {i}".encode())
        rows.append({"family": "NAT", "i": i, "name": f"nat_{i:02d}", "t1_name": name,
                     "sha256": {"mp4": _sha(t1 / f"{name}.mp4"), "wav": _sha(t1 / "audio16k" / f"{name}.wav"),
                                "transcript": _sha(jd / f"{name}.json")}})
    w1 = tmp / "wave1_transcripts"
    w1.mkdir()
    (w1 / "manifest.csv").write_text("video_id,tsv_sha256\nyct_0001," + "e" * 64 + "\n")
    return rows, jd, t1, w1


def test_nat_tsv_build_writes_valid_tsvs_and_leaves_the_wave1_manifest_unchanged(tmp_path):
    rows, jd, t1, w1 = _nat_fixture(tmp_path)
    w1_sha = _sha(w1 / "manifest.csv")
    sc = nt.build(rows, jd, t1, tmp_path / "nat_tsv", lambda p: 58.0, load_config(), wave1_dir=w1)
    assert sc["stop"] == [] and [r["n_words"] for r in sc["rows"]] == [3, 2]
    assert all(r["tsv_valid"] and r["tsv_sha256"] == _sha(tmp_path / "nat_tsv" / f"{r['clip_id']}.tsv")
               for r in sc["rows"])
    assert _sha(w1 / "manifest.csv") == w1_sha == sc["wave1_manifest_sha256"]
    text = nt.sidecar_text(sc)
    assert "alpha" not in text, "no transcript text in the sidecar"
    sc2 = nt.build(rows, jd, t1, tmp_path / "run2", lambda p: 58.0, load_config(), wave1_dir=w1)
    assert nt.sidecar_text(sc2) == text, "deterministic: two builds give the same sidecar"
    assert rm.nat_tsv_index(json.loads(text))["NAT_00"]["n_words"] == 3


def test_nat_tsv_zero_words_or_invalid_is_a_stop(tmp_path):
    rows, jd, t1, w1 = _nat_fixture(tmp_path, (3, 0))
    sc = nt.build(rows, jd, t1, tmp_path / "nat_tsv", lambda p: 58.0, load_config(), wave1_dir=w1)
    assert sc["stop"] == ["NAT_01"]
    sc = nt.build(rows[:1], jd, t1, tmp_path / "nat_tsv_b", lambda p: 2.0, load_config(), wave1_dir=w1)
    assert sc["stop"] == ["NAT_00"] and sc["rows"][0]["tsv_valid"] is False, "words past the media end"


def test_nat_tsv_refuses_provenance_mismatch_and_the_wave1_store(tmp_path):
    rows, jd, t1, w1 = _nat_fixture(tmp_path)
    with pytest.raises(nt.NatTsvError, match="inside the wave-1"):
        nt.build(rows, jd, t1, w1 / "nat", lambda p: 58.0, load_config(), wave1_dir=w1)
    (t1 / "audio16k" / "t1name0.wav").write_bytes(b"another wav")
    with pytest.raises(nt.NatTsvError, match="wav sha256"):
        nt.build(rows, jd, t1, tmp_path / "x", lambda p: 58.0, load_config(), wave1_dir=w1)


def test_nat_tsv_config_never_points_at_the_wave1_store():
    from yct.config_schema import RefClipsD091

    d = load_config()["controls"]["refclips_d091"]
    assert not d["nat_tsv"]["out_dir"].startswith("/work/yct/transcripts") and d["nat_tsv"]["runs"] == 2
    bad = copy.deepcopy(d)
    bad["nat_tsv"]["out_dir"] = "/work/yct/transcripts/nat"
    with pytest.raises(ValueError):
        RefClipsD091.model_validate(bad)


# ---------------------------------------------------------------- U3: copy-only upload plan
def test_upload_plan_sources_and_names():
    text, m = _real()
    a = rm.adapt(m, _sidecar(m))
    dirs = {"visual_dir": "/V", "speech_dir": "/S", "t1_dir": "/T", "nat_tsv_dir": "/N",
            "talkface_s3": "s3://b/talk/", "pod_dir": "/P"}
    rows = ru.plan(a, dirs)
    by = {(r["clip_id"], r["ext"]): r for r in rows}
    assert len(rows) == 360 and all(Path(r["dst"]).stem == r["clip_id"] for r in rows)
    assert by[("LOC_00", "mp4")]["src"] == "/V/loc_00.mp4" and by[("SPK_00", "tsv")]["src"] == "/S/spk_00.tsv"
    t1 = next(c for c in a["clips"] if c["clip_id"] == "NAT_00")["t1_name"]
    assert by[("NAT_00", "mp4")]["src"] == f"/T/{t1}.mp4" and by[("NAT_00", "wav")]["src"] == \
        f"/T/audio16k/{t1}.wav" and by[("NAT_00", "tsv")]["src"] == "/N/NAT_00.tsv"
    assert by[("TALKFACE_00", "mp4")]["src_kind"] == "s3" and \
        by[("TALKFACE_00", "mp4")]["src"] == "s3://b/talk/clip/talkface_00.mp4"
    meas = {f"{r['clip_id']}.{r['ext']}": r["sha256"] for r in rows}
    assert ru.verify(rows, meas, "pod") == []
    meas["LOC_00.mp4"] = "0" * 64
    assert ru.verify(rows, meas, "pod") == ["pod:LOC_00.mp4"]
    rec = ru.record(rows, [], [], "s3://x/clips/")
    assert rec["ok"] and rec["n_clips"] == 120 and "src" not in json.dumps(rec)


def test_upload_script_copies_and_never_builds():
    src = (ROOT / "scripts/refclips_upload.py").read_text()
    for word in ("build_clip", "make_reference_clips", "espeak", "ffmpeg ", "refclips58"):
        assert word not in src
    assert "shutil.copyfile" in src and "verify(rows, s3_meas" in src


# ---------------------------------------------------------------- U4: main-campaign projection
def _d091_frozen(cfg: dict) -> dict:
    cfg["frozen"] = [*cfg["frozen"], {"key": "controls.refclips_d091", "frozen_at": "test"}]
    return cfg


def test_main_projection_is_stated_in_advance_and_refuses_over_the_cap():
    cfg = load_config()
    out = rcmp.main_projection(cfg, [], price=1.99, max_hours=1.75, now=0.0, n_done_full=0)
    assert out["remaining_plan_usd"] == 61.0 and out["projection_usd"] == pytest.approx(61 + 1.99 * 1.75)
    assert rcmp.main_projection(cfg, [], price=1.99, max_hours=1.75, now=0.0,
                                n_done_full=200)["remaining_plan_usd"] == 0.0, "floored at 0"
    assert rcmp.main_projection(cfg, [], price=1.99, max_hours=1.75, now=0.0,
                                n_done_full=10)["remaining_plan_usd"] == pytest.approx(61 - 4.5)
    spend = [{"event": "launch", "id": "a", "name": "yct-p4b-ref-nat0", "t": 0.0, "usd_per_hour": 20.0}]
    with pytest.raises(rcmp.CampaignCapError, match="projection"):
        rcmp.main_projection(cfg, spend, price=1.99, max_hours=1.75, now=3600.0, n_done_full=0)


renv = t.env   # the T-REFRUN dry-run fixture (in-memory Lambda, local pod/box/S3)


def test_session_pre_launch_has_the_projection_when_d091_is_frozen(renv):
    renv["cfg"] = _d091_frozen(renv["cfg"])
    rc, res = t._run(renv, limit=3)
    assert rc == p4.EXIT_INCOMPLETE, res
    proj = res["pre_launch"]["projection"]
    assert proj["remaining_plan_usd"] == 61.0 and proj["n_done_full"] == 0 and proj["cap_usd"] == 75
    rc, res = t._run(renv, run_id="ref_s2", limit=1)
    assert res["pre_launch"]["projection"]["n_done_full"] == 3


def test_session_is_refused_when_the_projection_exceeds_the_cap(renv):
    renv["cfg"] = _d091_frozen(renv["cfg"])
    t._run(renv, limit=3)
    n = len(renv["lg"].launched)
    t._fake_ref_spend(renv, 20.0)
    with pytest.raises(SystemExit, match="projection"):
        t._run(renv, run_id="ref_s2", ack=True)
    assert len(renv["lg"].launched) == n


# ---------------------------------------------------------------- U5: shared launch gate
def test_drivers_share_one_launch_check_implementation():
    import importlib.util
    import sys

    nat0 = sys.modules.get("gpu_p4b_nat0")
    if nat0 is None:
        spec = importlib.util.spec_from_file_location("gpu_p4b_nat0", ROOT / "scripts" / "gpu_p4b_nat0.py")
        nat0 = importlib.util.module_from_spec(spec)
        sys.modules["gpu_p4b_nat0"] = nat0
        spec.loader.exec_module(nat0)
    assert nat0.Refused is lc.Refused and nat0.check_commit is lc.check_commit
    assert nat0.reconcile is lc.reconcile and nat0.check_reconcile is lc.check_reconcile
    src = (ROOT / "scripts/gpu_p4b_ref.py").read_text()
    assert "lc.check_commit" in src and "lc.check_reconcile" in src and "def check_commit" not in src


def test_launch_gate_refusals_and_pass(renv):
    lg = renv["lg"]
    recon = lc.reconcile(lg, renv["cfg"], renv["clock"])
    ok = {"head": "a" * 40, "ci_green_sha": "a" * 40, "pushed": True, "recon": recon}
    assert ref.check_launch_gate(ok, lg)["reconcile_ledger_sha256"] == recon["ledger_sha256"]
    for bad, why in (({"ci_green_sha": "b" * 40}, "CI-green"), ({"pushed": False}, "remote"),
                     ({"recon": None}, "reconciliation"),
                     ({"recon": {**recon, "ledger_n_lines": recon["ledger_n_lines"] + 1}}, "stale")):
        with pytest.raises(lc.Refused, match=why):
            ref.check_launch_gate({**ok, **bad}, lg)


def test_gate_runs_before_any_launch_in_the_session(renv):
    lg = renv["lg"]
    gate = {"head": "a" * 40, "ci_green_sha": "b" * 40, "pushed": True, "recon": None}
    with pytest.raises(lc.Refused):
        ref.run_ref_session(p4.SessionArgs(3.5, 25.0, None, "g"), renv["cfg"], lg, renv["backend"],
                            renv["p4"], renv["clock"], renv["tmp"] / "runs" / "g", renv["text"], gate=gate)
    assert t._no_new_launch(renv)


def test_check_only_runs_every_precondition_and_launches_nothing(renv):
    rc, res = ref.run_ref_session(p4.SessionArgs(1.75, 8.0, None, "chk"), _d091_frozen(renv["cfg"]),
                                  renv["lg"], renv["backend"], renv["p4"], renv["clock"],
                                  renv["tmp"] / "runs" / "chk", renv["text"], check_only=True)
    assert rc == 0 and res["status"] == "check_only" and t._no_new_launch(renv)
    assert res["plan_first3"] == ["GREY_CTRL_00.ref", "SPK_00.ref", "MOT_00.ref"]
    assert res["projection"]["remaining_plan_usd"] == 61.0 and res["p4_manifest_sha256"]


# ---------------------------------------------------------------- non-blocking
def test_d038_gate_failure_on_grey_ctrl_is_exit_1_and_a_latched_stop(renv):
    renv["backend"].faults["GREY_CTRL_00.ref"] = "rerun_differs"
    rc, res = t._run(renv, limit=3)
    assert rc == p4.EXIT_FAIL
    renv["backend"].faults.clear()
    with pytest.raises(SystemExit, match="STOP"):
        t._run(renv, run_id="ref_s2", limit=3)


def test_a_changed_p4_manifest_after_the_session_is_exit_1(renv):
    class Mutating:
        def __init__(self, inner):
            self.inner, self.n = inner, 0

        def s3_get_text(self, key):
            v = self.inner.s3_get_text(key)
            if key == "manifest.jsonl":
                self.n += 1
                if self.n > 2:
                    return v + "\n"
            return v

        def __getattr__(self, k):
            return getattr(self.inner, k)

    renv["p4"] = Mutating(renv["p4"])
    rc, res = t._run(renv, limit=3)
    assert rc == p4.EXIT_FAIL and "P4 manifest" in res["stop"]


def test_a_header_only_zero_word_tsv_is_handled_like_a_silent_clip(tmp_path):
    p = tmp_path / "GREY_CTRL_00.tsv"
    p.write_text("text\tstart\tduration\tsequence_id\tsentence\n")
    df = _read_tsv(p)
    assert len(df) == 0 and n_words_past_end(df, 58.0) == 0
    audio = pd.DataFrame([{"type": "Audio", "filepath": str(p.with_suffix(".wav")), "start": 0.0,
                           "duration": 58.0, "offset": 0.0}])
    assert absolute_word_events(audio, {str(p.with_suffix(".wav")): df}, "english", 58.0) == []
    wc = check_word_events(pd.DataFrame({"type": ["Audio", "Video"], "start": [0.0, 0.0]}), len(df), 58.0)
    assert wc["ok"] is True and wc["n_words"] == 0
    from test_tribe_qc_gate import GOOD
    m = {**copy.deepcopy(GOOD), "bug018_word_check": {**wc, "bug018_fix": True}, "n_words": 0,
         "event_types": {"Audio": 1, "Video": 1}}
    g = clip_gate(m, "t1")
    assert g["pass"] is True, g["failures"]


def test_reliability_excludes_differing_constant_arrays(tmp_path):
    assert reliability(np.zeros(5), np.ones(5)) is None, "constant and different: excluded, never passed"
    assert reliability(np.ones(5), np.ones(5)) == 1.0, "constant and bit-identical: 1.0"
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    np.save(a / "x.npy", np.zeros(4))
    np.save(b / "x.npy", np.ones(4))
    np.save(a / "y.npy", np.arange(4.0))
    np.save(b / "y.npy", np.arange(4.0))
    fr = feature_reliability(a, b)
    excluded = sum(1 for v in fr["arrays"].values() if v.get("shape_match") and v.get("reliability") is None)
    assert excluded == 1 and fr["reliability_min"] == 1.0
