"""Council TALKFACE (wf_f194ca9f-6a0, REVISE x5) + owner 2026-11-23 ("Accept both", "As reviewers propose"):
the D-090 draft TALKFACE build rules. Pure helpers, the narrowed failure mapping, the env lock, --prepare and
the post-session finish on fixture inputs (real file I/O, real ffmpeg; no GPU, no network, no real face)."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import locimg
from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run import talkface as T  # noqa: N812
from yct.tribe_run import talkface_box as TB  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gpu_p4b_talk", ROOT / "scripts" / "gpu_p4b_talk.py")
talk = importlib.util.module_from_spec(spec)
sys.modules["gpu_p4b_talk"] = talk
spec.loader.exec_module(talk)
p4 = talk.ref.p4
from _pre_d087 import pre_d087  # noqa: E402

D90 = load_config()["controls"]["refclips_d090"]
FACE_BOX = [150, 250, 270, 370]          # y1, y2, x1, x2 (the pinned coords order)
WIN = [(9.0, 10.4), (29.0, 31.2), (49.0, 52.5)]


# ------------------------------------------------------------------ frame count (council: 1736, not 1740)
def test_expected_mel_chunks_is_1736_on_58_s():
    assert T.expected_n_chunks(928000, 30) == 1736 == D90["expected"]["n_mel_chunks"]
    assert D90["driving_audio"]["n_samples"] == int(R.DUR * D90["driving_audio"]["sr"])
    assert abs(D90["expected"]["window_end_max_s"] - 1735 / 30) < 1e-3


def test_pinned_chunking_line_for_line():
    """The count equals the pinned inference.main loop on an n_mel-frame mel (hop 200, center=True)."""
    n_mel = 1 + 928000 // 200
    chunks, i = 0, 0
    while True:
        if int(i * 80. / 30) + 16 > n_mel:
            chunks += 1
            break
        chunks += 1
        i += 1
    assert chunks == T.expected_n_chunks(928000, 30)


def test_windows_ending_after_the_last_chunk_are_refused():
    T.check_windows(WIN, 1736, 30)
    with pytest.raises(SystemExit, match="after"):
        T.check_windows([(55.0, 57.9)], 1736, 30)


# ------------------------------------------------------------------ luma identity (box vs locimg.grey709)
def test_box_luma_equals_grey709_bit_for_bit():
    rng = np.random.default_rng(0)
    bgr = rng.integers(0, 256, (R.H, R.W, 3), dtype=np.uint8)
    assert np.array_equal(TB.box_grey(bgr), locimg.grey709(bgr[..., ::-1]))
    assert np.array_equal(TB.box_grey(bgr), T.to_grey(bgr))


def test_three_channel_grey_static_round_trips_exactly():
    v = np.arange(256, dtype=np.uint8).reshape(16, 16)
    assert np.array_equal(TB.box_grey(np.repeat(v[..., None], 3, 2)), v)


# ------------------------------------------------------------------ QC v2
def _fixture(n=1740):
    static = np.full((R.H, R.W), 128, np.uint8)
    static[100:300, 200:440] = 150
    keep = T.window_frames(WIN, 30, n)
    w2l = {}
    y1, y2, x1, x2 = FACE_BOX
    for i in keep:
        f = static.copy()
        f[y1 + 60:y2, x1 + 20:x2 - 20] = 60 + (i % 9)
        w2l[i] = f
    rec = {"n_mel_chunks": 1736, "n_frames_total": 1736, "n_frames_kept": len(keep), "face_box": FACE_BOX}
    return static, w2l, rec


def _qc(frames, static, rec, gate=None, dec=None):
    return T.qc(frames, static, WIN, face_box=FACE_BOX, record=rec, expected=D90["expected"],
                speech_gate=gate or {"pass": True}, decode_identity=dec or {"pass": True})


def test_qc_v2_passes_on_a_clean_fixture_and_names_the_gates():
    static, w2l, rec = _fixture()
    q = _qc(T.compose(static, w2l, WIN), static, rec)
    assert q["pass"], q
    gating = {k for k, v in q["checks"].items() if v.get("gating", True) is not False}
    assert gating == set(D90["qc"]["gating"]) and "lip_motion" not in q["checks"]
    for k in ("window_mean_abs_diff", "edge_step", "mouth_vs_upper_mad"):
        assert q["checks"][k]["gating"] is False


def test_qc_fails_on_a_pixel_change_outside_the_face_box_inside_a_window():
    static, w2l, rec = _fixture()
    fr = T.compose(static, w2l, WIN)
    i = T.window_frames(WIN)[3]
    fr[i] = fr[i].copy()
    fr[i][0, 0] = 1
    q = _qc(fr, static, rec)
    assert not q["checks"]["outside_face_box_static"]["pass"] and not q["pass"]


def test_qc_fails_without_articulation_or_rendering():
    static, w2l, rec = _fixture()
    frozen_mouth = {i: w2l[min(w2l)] for i in w2l}
    q = _qc(T.compose(static, frozen_mouth, WIN), static, rec)
    assert not q["checks"]["inbox_articulation"]["pass"] and not q["pass"]
    still = {i: static for i in w2l}
    q = _qc(T.compose(static, still, WIN), static, rec)
    assert not q["checks"]["w2l_rendered"]["pass"]


@pytest.mark.parametrize("field,val", [("n_mel_chunks", 1740), ("n_frames_total", 1735),
                                       ("n_frames_kept", 3)])
def test_qc_fails_on_chunk_or_kept_counts(field, val):
    static, w2l, rec = _fixture()
    rec = {**rec, field: val}
    q = _qc(T.compose(static, w2l, WIN), static, rec)
    assert not q["pass"]


def test_qc_fails_on_decode_or_speech_gate():
    static, w2l, rec = _fixture()
    fr = T.compose(static, w2l, WIN)
    assert not _qc(fr, static, rec, dec={"pass": False})["pass"]
    assert not _qc(fr, static, rec, gate={"pass": False})["pass"]


# ------------------------------------------------------------------ narrowed failure mapping
def test_box_exit_classification():
    assert T.classify_box_exit(0) == "ok"
    assert T.classify_box_exit(10) == "s3fd_no_face"
    for rc in (30, 1, 137, 2):
        assert T.classify_box_exit(rc) == "stop"


def test_only_face_not_detected_is_a_skip():
    assert T.skip_record({"source_sha256": "x"}, 499, "s3fd_no_face", "r")["skip_on"] == "s3fd_no_face"
    with pytest.raises(SystemExit, match="pre-stated"):
        T.skip_record({"source_sha256": "x"}, 499, "wav2lip_error", "r")


def test_box_main_maps_face_not_detected_to_10_and_others_to_30(monkeypatch, tmp_path):
    monkeypatch.setattr(TB, "_run", lambda a: (_ for _ in ()).throw(ValueError("Face not detected! Ensure")))
    assert TB.main(_box_args(tmp_path)) == 10
    monkeypatch.setattr(TB, "_run", lambda a: (_ for _ in ()).throw(RuntimeError("CUDA out of memory")))
    assert TB.main(_box_args(tmp_path)) == 30
    monkeypatch.setattr(TB, "_run", lambda a: (_ for _ in ()).throw(SystemExit("Mel contains nan")))
    assert TB.main(_box_args(tmp_path)) == 30


def test_box_refuses_input_sha_mismatch(tmp_path):
    a = _box_args(tmp_path)
    (tmp_path / "s.png").write_bytes(b"x")
    (tmp_path / "a.wav").write_bytes(b"y")
    assert TB.main(a) == 30


def _box_args(tmp_path):
    return ["--repo", str(tmp_path), "--weights", str(tmp_path / "w"), "--weights-sha", "0" * 64,
            "--face", str(tmp_path / "s.png"), "--face-sha", "1" * 64, "--audio", str(tmp_path / "a.wav"),
            "--audio-sha", "2" * 64, "--out", str(tmp_path / "f.npz"), "--record", str(tmp_path / "r.json"),
            "--windows", "[[1.0, 2.0]]"]


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
    def __init__(self, fail=None, exc=None):
        self.fail, self.exc, self.calls = fail, exc, []

    def start(self, iid, deadline):
        self.calls.append("start")

    def step(self, name, inp):
        self.calls.append(name)
        if name == self.fail:
            raise self.exc
        if name == "fetch_frames":
            return {"pod_dir": "/x", "record": {"n_frames_total": 1736}}
        return None


def _run(tmp_path, box):
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    c = pre_d087(copy.deepcopy(load_config()))
    a = c["controls"]["refclips_artifacts"]
    inp = {"face_source_sha256": a["talkface_face_sha256"], "selection_sha256": a["speech_selection_sha256"],
           "static_png_sha256": "a" * 64, "clip16k_wav_sha256": "b" * 64, "rendered48k_sha256": "c" * 64,
           "windows": [list(w) for w in WIN]}
    face_log = [json.loads(x) for x in (ROOT / "data/refstim/image_face_auto_log_v4.jsonl").read_text()
                .splitlines() if x.strip()]
    cont = json.loads((ROOT / T.CONT).read_text())
    args = SimpleNamespace(max_hours=1.75, usd_limit=8.0, external_terminator_at=clock() + 1.75 * 3600 + 1000,
                           ci_green_sha="c" * 40, ack_cap_80=False, run_id="p4btalk_test")
    recon = talk.nat.reconcile(lg, c, clock)
    rc, res = talk.run_session(args, c, lg, Store(), box, clock, "c" * 40, True, recon, inp, face_log, cont,
                               lambda out: {"pass": True}, tmp_path / "skips.jsonl", tmp_path / "result.json")
    return rc, res, lg


def test_steps_split_the_frame_copy_out_of_the_wav2lip_step():
    assert talk.STEPS == ("setup_w2l", "check_env", "push_inputs", "wav2lip", "fetch_frames")


def test_face_not_detected_box_exit_is_the_only_logged_skip(tmp_path):
    rc, res, lg = _run(tmp_path, Box("wav2lip", talk.BoxExit(10, "ValueError: Face not detected!")))
    assert rc == 1 and res["status"] == "skip" and res["skip_on"] == "s3fd_no_face"
    assert json.loads((tmp_path / "skips.jsonl").read_text())["skip_on"] == "s3fd_no_face"
    assert all(s == "terminated" for s in lg.status.values())


@pytest.mark.parametrize("exc", [talk.BoxExit(30, "Mel contains nan"), talk.BoxExit(137, "killed (OOM)"),
                                 talk.BoxExit(30, "sha mismatch"), talk.EnvMismatch("torch 2.9.0 != 2.8.0")])
def test_stop_classes_log_nothing_and_exit_1(tmp_path, exc):
    step = "check_env" if isinstance(exc, talk.EnvMismatch) else "wav2lip"
    rc, res, lg = _run(tmp_path, Box(step, exc))
    assert rc == 1 and res["status"] == "stop", res
    assert not (tmp_path / "skips.jsonl").exists()
    assert all(s == "terminated" for s in lg.status.values())


@pytest.mark.parametrize("step,exc", [("wav2lip", TimeoutError("step w2l exceeded 3600 s")),
                                      ("fetch_frames", RuntimeError("ssh: connection reset")),
                                      ("push_inputs", RuntimeError("aws s3 cp failed"))])
def test_infrastructure_failures_are_75_and_never_a_skip(tmp_path, step, exc):
    rc, res, lg = _run(tmp_path, Box(step, exc))
    assert rc == 75 and res["status"] == "box_failed"
    assert not (tmp_path / "skips.jsonl").exists()


def test_full_session_runs_every_step(tmp_path):
    box = Box()
    rc, res, lg = _run(tmp_path, box)
    assert rc == 0 and box.calls == ["start", *talk.STEPS], res


# ------------------------------------------------------------------ env lock (TALK_PIP moved to config)
def test_lock_file_sha_matches_config_and_holds_every_requirement_with_hashes():
    lock = (ROOT / D90["env"]["lock"]).read_text()
    assert hashlib.sha256(lock.encode()).hexdigest() == D90["env"]["lock_sha256"]
    pins = T.freeze_pins(lock)
    req = [x.strip() for x in (ROOT / D90["env"]["requirements"]).read_text().splitlines() if x.strip()]
    for r in req:
        name, ver = r.split("==")
        assert pins[name] == ver, r
    for block in lock.split("\n\n"):
        if "==" in block:
            assert "--hash=sha256:" in block
    assert pins["torch"] == D90["env"]["torch"]["version"]
    assert not hasattr(talk, "TALK_PIP")


def test_reference_freeze_equals_the_lock_and_drift_is_detected():
    lock = (ROOT / D90["env"]["lock"]).read_text()
    ref = (ROOT / D90["env"]["reference_freeze"]).read_text()
    assert hashlib.sha256(ref.encode()).hexdigest() == D90["env"]["reference_freeze_sha256"]
    ok, diff = T.freeze_matches(lock, ref)
    assert ok and not diff
    ok, diff = T.freeze_matches(lock, ref.replace("torch==2.8.0", "torch==2.9.0"))
    assert not ok and any("torch" in d for d in diff)


def test_setup_script_installs_the_hashed_lock_only():
    c = load_config()
    rec = c["controls"]["refclips_d085"]["talkface"]["loader"]["check_record"]
    check = json.loads((ROOT / rec).read_text())
    s = talk.setup_script(c, check, "/b")
    assert "--require-hashes" in s and "talkface_lock.txt" in s and "torch==" not in s
    assert "infra/talkface_lock.txt" in talk.ship_list()


def test_push_fetches_only_nogan_and_s3fd_from_the_mirror_root():
    c = load_config()
    s = talk.push_cmd(c, "/b")
    mirror = c["controls"]["refclips_d085"]["talkface"]["mirror_s3"]
    assert f"{mirror}Wav2Lip-SD-NOGAN.pt" in s and f"{mirror}s3fd-619a316812.pth" in s
    assert "SD-GAN" not in s and " sync " not in s and "weights/" not in s


def test_wav2lip_cmd_checks_the_input_shas():
    c = load_config()
    s = talk.wav2lip_cmd(c, "/b", {"windows": [[1.0, 2.0]], "static_png_sha256": "a" * 64,
                                   "clip16k_wav_sha256": "b" * 64})
    assert "--face-sha " + "a" * 64 in s and "--audio-sha " + "b" * 64 in s
    assert "talk/mirror/Wav2Lip-SD-NOGAN.pt" in s


# ------------------------------------------------------------------ --prepare and finish (fixture, real I/O)
def _fixture_clip():
    c = load_config()
    (clip,) = [x for x in R.plan(c) if x.family == "TALKFACE"]
    return c, clip


def _prov(family, idx):
    rng = np.random.default_rng(100 + idx)
    n = int((1.2 + 0.4 * idx) * R.SR)
    t = np.arange(n) / R.SR
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)
    x = 0.3 * np.sin(2 * np.pi * 180 * t) * env + 0.01 * rng.standard_normal(n)
    return x, ["w"] * 3


def _face_rgb():
    yy, xx = np.mgrid[0:800, 0:700]
    g = ((xx * 7 + yy * 3) % 251).astype(np.uint8)
    return np.stack([g, (g // 2 + 40).astype(np.uint8), (255 - g).astype(np.uint8)], -1)


def test_prepare_writes_private_inputs_and_a_numbers_only_record(tmp_path):
    c, clip = _fixture_clip()
    rec = T.prepare_inputs(c, clip, _prov, _face_rgb(), [50, 60, 600], tmp_path)
    for f in ("static.png", "clip16k.wav", "rendered48k.wav", "utterances.npz", "rows.json"):
        assert (tmp_path / f).exists(), f
    import wave

    import cv2

    png = cv2.imread(str(tmp_path / "static.png"))
    assert png.shape == (R.H, R.W, 3) and np.array_equal(png[..., 0], png[..., 1])
    with wave.open(str(tmp_path / "clip16k.wav")) as w:
        assert w.getframerate() == 16000 and w.getnframes() == 928000 and w.getnchannels() == 1
    assert rec["n_mel_chunks_expected"] == 1736 and len(rec["windows"]) == 3
    assert rec["crop_box"] == [50, 60, 600] and set(rec["static_luma_vs_loc"]) >= {"mean", "rms", "loc_mean"}
    text = json.dumps(rec)
    for k in ("static_png_sha256", "clip16k_wav_sha256", "rendered48k_sha256"):
        assert len(rec[k]) == 64
    assert '"w"' not in text and "rows" not in rec


def test_prepare_refuses_a_window_past_the_last_mel_chunk(tmp_path):
    c, clip = _fixture_clip()
    clip = copy.deepcopy(clip)
    clip.events[-1]["onset"] = 56.7               # a 1.2 s utterance ends ~57.9 s > 1735 / 30 = 57.83 s
    with pytest.raises(SystemExit, match="after"):
        T.prepare_inputs(c, clip, lambda f, i: _prov(f, 0), _face_rgb(), [50, 60, 600], tmp_path)


def test_finish_on_fixture_frames_end_to_end(tmp_path):
    import cv2

    c, clip = _fixture_clip()
    inp = tmp_path / "inputs"
    rec = T.prepare_inputs(c, clip, _prov, _face_rgb(), [50, 60, 600], inp)
    static = cv2.imread(str(inp / "static.png"))[..., 0]
    keep = T.window_frames([tuple(w) for w in rec["windows"]])
    y1, y2, x1, x2 = FACE_BOX
    frames = {}
    for i in keep:
        f = static.copy()
        f[y1 + 60:y2, x1 + 20:x2 - 20] = 40 + (i % 11)
        frames[f"f{i:05d}"] = f
    talkd = tmp_path / "talk"
    talkd.mkdir()
    np.savez_compressed(talkd / "frames.npz", **frames)
    w2l = {"n_mel_chunks": 1736, "n_frames_total": 1736, "n_frames_kept": len(keep), "face_box": FACE_BOX,
           "frames_sha256": hashlib.sha256((talkd / "frames.npz").read_bytes()).hexdigest()}
    (talkd / "w2l_record.json").write_text(json.dumps(w2l))
    out = T.finish_local(c, inp, talkd, tmp_path / "out")
    assert out["qc"]["pass"], out["qc"]
    assert out["qc"]["checks"]["decode_identity"]["pass"]
    assert out["qc"]["checks"]["speech_gate"]["pass"]
    assert (tmp_path / "out" / "talkface_00.mp4").exists()
    s = T.public_numbers(out)
    assert '"w"' not in s and "frames" not in out


def test_finish_refuses_a_frames_sha_mismatch(tmp_path):
    c, clip = _fixture_clip()
    inp = tmp_path / "inputs"
    T.prepare_inputs(c, clip, _prov, _face_rgb(), [50, 60, 600], inp)
    talkd = tmp_path / "talk"
    talkd.mkdir()
    np.savez_compressed(talkd / "frames.npz", f00000=np.zeros((R.H, R.W), np.uint8))
    (talkd / "w2l_record.json").write_text(json.dumps({"frames_sha256": "0" * 64, "face_box": FACE_BOX}))
    with pytest.raises(SystemExit, match="frames.npz sha"):
        T.finish_local(c, inp, talkd, tmp_path / "out")


@pytest.mark.parametrize("argv", [["--prepare"], ["--finish", "/tmp/nowhere"]])
def test_prepare_and_finish_refuse_until_d090_is_frozen(monkeypatch, argv):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    c = copy.deepcopy(load_config())        # the pre-freeze state: drop the D-090 freeze row
    c["frozen"] = [f for f in c["frozen"] if not f["key"].startswith("controls.refclips_d090")]
    monkeypatch.setattr(talk, "load_config", lambda: c)
    with pytest.raises(SystemExit, match="refclips_d090 is not frozen"):
        talk.main(argv)


def test_bug046_lock_pins_a_setuptools_with_pkg_resources():
    """librosa 0.9.2 imports pkg_resources (removed from setuptools >= 81): the lock must pin an older one."""
    pins = T.freeze_pins((ROOT / D90["env"]["lock"]).read_text())
    assert int(pins["setuptools"].split(".")[0]) < 81


def test_bug048_box_resolves_relative_paths_before_chdir(monkeypatch, tmp_path):
    """BUG-048: the box chdirs into the Wav2Lip repo; relative --weights/--face/--audio/--out paths given by
    wav2lip_cmd (talk/...) must be resolved against the launch cwd first."""
    monkeypatch.chdir(tmp_path)
    a = TB._args(["--repo", "Wav2Lip", "--weights", "talk/mirror/w.pt", "--weights-sha", "0" * 64,
                  "--face", "talk/inputs/static.png", "--face-sha", "1" * 64, "--audio", "talk/inputs/a.wav",
                  "--audio-sha", "2" * 64, "--out", "talk/frames.npz", "--record", "talk/r.json",
                  "--s3fd", "talk/mirror/s.pth", "--windows", "[[1.0, 2.0]]"])
    for k in ("repo", "weights", "face", "audio", "out", "record", "s3fd"):
        p = Path(getattr(a, k))
        assert p.is_absolute() and str(p).startswith(str(tmp_path)), k
