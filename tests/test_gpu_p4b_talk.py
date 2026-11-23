"""D-085 part 2 step 4: the TALKFACE session driver and helpers, dry run only (fake Lambda API, fake box,
in-memory store). No network, no GPU, no launch."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run import talkface as T  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gpu_p4b_talk", ROOT / "scripts" / "gpu_p4b_talk.py")
talk = importlib.util.module_from_spec(spec)
sys.modules["gpu_p4b_talk"] = talk
spec.loader.exec_module(talk)
p4 = talk.ref.p4
from _pre_d087 import pre_d087  # noqa: E402

HEAD = "c" * 40
_LOG = ROOT / "data/refstim/image_face_auto_log_v4.jsonl"
FACE_LOG = [json.loads(x) for x in _LOG.read_text().splitlines() if x.strip()]
CONT = json.loads((ROOT / T.CONT).read_text())


def cfg():
    return pre_d087(copy.deepcopy(load_config()))


def inputs(c):
    a = c["controls"]["refclips_artifacts"]
    return {"face_source_sha256": a["talkface_face_sha256"], "selection_sha256": a["speech_selection_sha256"],
            "static_png_sha256": "a" * 64, "clip16k_wav_sha256": "b" * 64, "rendered48k_sha256": "c" * 64,
            "windows": [[10.0, 12.0], [26.0, 28.5], [42.0, 45.0]]}


class Store:
    def __init__(self):
        self.d = {}

    def s3_get_text(self, k):
        return self.d.get(k)

    def s3_put_text(self, k, t):
        self.d[k] = t

    def s3_list(self, prefix):
        return {k: 1 for k in self.d if k.startswith(prefix)}


class Box:
    def __init__(self, fail=None, msg="box died", exc=None):
        self.fail, self.msg, self.exc, self.calls = fail, msg, exc, []

    def start(self, iid, deadline):
        self.calls.append("start")

    def step(self, name, inp):
        self.calls.append(name)
        if name == self.fail:
            raise self.exc or RuntimeError(self.msg)
        if name == "fetch_frames":          # D-090: the frame copy-back is its own step
            return {"pod_dir": "/x", "record": {"n_frames_total": 1740}}


@pytest.fixture
def env(tmp_path):
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    return SimpleNamespace(clock=clock, lg=lg, store=Store(), tmp=tmp_path)


def args(env, **kw):
    a = {"max_hours": 1.75, "usd_limit": 8.0, "external_terminator_at": env.clock() + 1.75 * 3600 + 1000,
         "ci_green_sha": HEAD, "ack_cap_80": False, "run_id": "p4btalk_test"}
    a.update(kw)
    return SimpleNamespace(**a)


def run(env, c=None, box=None, head=HEAD, pushed=True, finish=None, inp="default", **kw):
    c = c or cfg()
    recon = talk.nat.reconcile(env.lg, c, env.clock)
    fin = finish or (lambda out: {"pass": True, "n": out["record"]["n_frames_total"]})
    return talk.run_session(args(env, **kw), c, env.lg, env.store, box or Box(), env.clock, head, pushed,
                            recon, inputs(c) if inp == "default" else inp, FACE_LOG, CONT, fin,
                            env.tmp / "skips.jsonl", env.tmp / "result.json")


# ------------------------------------------------------------------ frozen state and face
def test_check_frozen_passes_on_the_committed_state():
    tk = T.check_frozen(load_config(), ROOT)
    assert tk["publish"] is False and tk["weights_file"] == "Wav2Lip-SD-NOGAN.pt"


@pytest.mark.parametrize("mut,match", [
    (lambda c: c["controls"]["refclips_d085"]["talkface"].update(publish=True), "publish"),
    (lambda c: c["controls"]["refclips_d085"]["talkface"].update(weights_file="Wav2Lip-SD-GAN.pt"), "NOGAN"),
    (lambda c: c["controls"]["refclips_d085"]["talkface"]["loader"].update(blob_sha1="0" * 40), "blob"),
    (lambda c: c.update(frozen=[f for f in c["frozen"] if f["key"] != T.FACE_KEY]), "not frozen"),
])
def test_check_frozen_refuses(mut, match):
    c = load_config()
    mut(c)
    with pytest.raises(SystemExit, match=match):
        T.check_frozen(c, ROOT)


def test_face_is_the_frozen_rank_499_pass():
    row = T.face_row(FACE_LOG, load_config(), CONT)
    assert row["decision"] == "pass" and row["source_sha256"] == CONT["talkface_face_source_sha256"]
    assert T.licence_adaptable(row["licence"], load_config()["controls"]["refclips"]["image_licences"])


def test_face_row_refuses_a_loc_rank_or_a_wrong_sha():
    with pytest.raises(SystemExit, match="after_rank"):
        T.face_row(FACE_LOG, load_config(), {**CONT, "talkface_face_rank": 400})
    bad = load_config()
    bad["controls"]["refclips_artifacts"]["talkface_face_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="sha"):
        T.face_row(FACE_LOG, bad, CONT)


@pytest.mark.parametrize("lic,ok", [("CC-BY-4.0", True), ("CC0", True), ("CC-BY-ND-4.0", False),
                                    ("CC-BY-SA-4.0", False), ("PD-old", True)])
def test_licence_adaptable(lic, ok):
    assert T.licence_adaptable(lic, load_config()["controls"]["refclips"]["image_licences"]) is ok


# ------------------------------------------------------------------ launch rules (dry)
def test_full_dry_session_terminates_and_records(env):
    box = Box()
    rc, res = run(env, box=box)
    assert rc == 0, res
    assert box.calls == ["start", *talk.STEPS]
    (iid,) = env.lg.launched
    assert env.lg.api.inst[iid]["name"].startswith("yct-p4b-ref-talk")
    assert env.lg.status[iid] == "terminated" and res["pre_launch"]["projection"]["cap_usd"] == 75
    assert json.loads((env.tmp / "result.json").read_text())["status"] == "done"


@pytest.mark.parametrize("kw,match", [
    ({"max_hours": 2.0}, "launcher_max_hours"),
    ({"usd_limit": 9.0}, "usd-limit"),
    ({"usd_limit": 3.0}, "exceeds"),
    ({"external_terminator_at": None}, "external-terminator"),
    ({"external_terminator_at": 1_800_000_000.0 + 1.75 * 3600}, "must fire between"),
    ({"ci_green_sha": "d" * 40}, "CI-green"),
])
def test_preflight_refusals(env, kw, match):
    rc, res = run(env, **kw)
    assert rc == 1 and res["status"] == "refused" and match in res["error"]
    assert not env.lg.launched


def test_refused_when_not_pushed_or_inputs_missing_or_done(env):
    rc, res = run(env, pushed=False)
    assert rc == 1 and "remote" in res["error"]
    rc, res = run(env, inp=None)
    assert rc == 1 and "--prepare" in res["error"]
    (env.tmp / "result.json").write_text(json.dumps({"status": "done"}))
    rc, res = run(env)
    assert rc == 1 and "already recorded" in res["error"]
    assert not env.lg.launched


def test_projection_over_cap_refuses(env):
    c = cfg()
    c["controls"]["refclips_d084"]["main_campaign_plan_usd"] = 74.0
    rc, res = run(env, c=c)
    assert rc == 1 and "projection" in res["error"] and not env.lg.launched


def test_box_failure_before_wav2lip_is_75_and_terminated(env):
    rc, res = run(env, box=Box(fail="setup_w2l"))
    assert rc == 75 and res["status"] == "box_failed"
    (iid,) = env.lg.launched
    assert env.lg.status[iid] == "terminated"
    assert not (env.tmp / "skips.jsonl").exists()


def test_no_face_is_a_logged_skip(env):
    rc, res = run(env, box=Box(fail="wav2lip", exc=talk.BoxExit(10, "ValueError: Face not detected! Ensure")))
    assert rc == 1 and res["status"] == "skip" and res["skip_on"] == "s3fd_no_face"
    rec = json.loads((env.tmp / "skips.jsonl").read_text())
    assert rec["skip_on"] == "s3fd_no_face" and rec["rank"] == 499
    (iid,) = env.lg.launched
    assert env.lg.status[iid] == "terminated"


def test_qc_failure_is_a_final_stop(env):
    rc, res = run(env, finish=lambda out: {"pass": False})
    assert rc == 1 and res["status"] == "stop" and "final STOP" in res["error"]
    assert not (env.tmp / "result.json").exists()


def test_launch_is_disabled_until_the_council(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    with pytest.raises(SystemExit, match="council"):
        talk.main(["--external-terminator-at", "2026-01-01T00:00:00Z", "--ci-green-sha", HEAD])


def test_ship_list_has_the_box_wrapper_and_loader():
    import gpu_p0_rerun as g  # noqa: F401

    ship = talk.ship_list()
    assert "src/yct/tribe_run" in ship and "infra/gpu_deadman.sh" in ship
    assert (ROOT / "src/yct/tribe_run/talkface_box.py").exists()


def test_setup_script_pins_revision_and_file_shas():
    c = load_config()
    rec = c["controls"]["refclips_d085"]["talkface"]["loader"]["check_record"]
    check = json.loads((ROOT / rec).read_text())
    s = talk.setup_script(c, check, "/b")
    assert c["controls"]["refclips_d085"]["talkface"]["revision"] in s and "sha256sum -c" in s
    assert check["inference_py_sha256"] in s and "--require-hashes" in s and "talkface_lock.txt" in s


def test_wav2lip_cmd_uses_frozen_weights_and_fps_30():
    c = load_config()
    s = talk.wav2lip_cmd(c, "/b", {"windows": [[1.0, 2.0]], "static_png_sha256": "a" * 64,
                                   "clip16k_wav_sha256": "b" * 64})
    assert "Wav2Lip-SD-NOGAN.pt" in s and "--fps 30" in s and "GAN.pt " not in s.replace("NOGAN.pt", "")


# ------------------------------------------------------------------ compose and QC
BOX = [190, 220, 290, 350]                   # y1, y2, x1, x2 (D-090 QC is relative to the face box)


def _frames():
    static = np.full((R.H, R.W), 128, np.uint8)
    win = [(10.0, 11.0), (26.0, 27.0), (42.0, 43.0)]
    w2l = {}
    for i in T.window_frames(win):
        f = static.copy()
        f[200:210, 300:340] = 60 + i % 7
        w2l[i] = f
    return static, win, w2l


def _q(fr, static, win, gate):
    rec = {"n_mel_chunks": 1736, "n_frames_total": 1736, "n_frames_kept": len(T.window_frames(win)),
           "face_box": BOX}
    exp = load_config()["controls"]["refclips_d090"]["expected"]
    return T.qc(fr, static, win, face_box=BOX, record=rec, expected=exp, speech_gate=gate,
                decode_identity={"pass": True})


def test_compose_keeps_static_outside_windows_and_qc_passes():
    static, win, w2l = _frames()
    fr = T.compose(static, w2l, win)
    q = _q(fr, static, win, {"pass": True})
    assert len(fr) == 1740 and q["pass"], q


def test_compose_refuses_missing_in_window_frames():
    static, win, w2l = _frames()
    w2l.pop(min(w2l))
    with pytest.raises(SystemExit, match="lacks"):
        T.compose(static, w2l, win)


def test_qc_fails_on_motion_outside_windows_or_no_motion():
    static, win, w2l = _frames()
    fr = T.compose(static, w2l, win)
    fr[5] = fr[5].copy()
    fr[5][0, 0] = 1
    assert not _q(fr, static, win, {"pass": True})["checks"]["outside_window_static"]["pass"]
    still = T.compose(static, {i: static for i in w2l}, win)
    assert not _q(still, static, win, {"pass": True})["checks"]["w2l_rendered"]["pass"]  # was lip_motion
    assert not _q(T.compose(static, w2l, win), static, win, {"pass": False})["pass"]


def test_classify_failure_and_skip_record():
    assert T.classify_box_exit(10) == "s3fd_no_face"           # D-090: classified by the box exit code
    assert T.classify_box_exit(30) == "stop"                    # a CUDA / model error is a STOP, not a skip
    with pytest.raises(SystemExit, match="pre-stated"):
        T.skip_record({"source_sha256": "x"}, 499, "looks_odd", "r")


def test_public_numbers_never_serialise_frames():
    s = T.public_numbers({"a": np.zeros((2, 2), np.uint8), "b": 1})
    assert '"a": null' in s and '"b": 1' in s
