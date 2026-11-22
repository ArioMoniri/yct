"""T-NAT0 session-0 logic: N1/N2/N3 selection, STOP below nat_n, NAT manifest, box helpers (fakes only)."""
import numpy as np
import pytest
import yaml

from yct.config import load_config
from yct.curate import nat0_box as nb
from yct.curate import natstim as ns
from yct.curate import refstim_auto as ra

CFG = load_config()
EN = {"en": 0.97, "de": 0.01}
ONE = [[0.0, 50.0, "S0"], [51.0, 52.0, "S1"]]          # main 50/51 s = 0.98, other 1 s


def gpu(ids, bad=()):
    return {i: {"lang_probs": {"en": 0.5} if i in bad else EN, "segments": ONE} for i in ids}


def test_n3_window_mean_and_fail_closed():
    x = np.zeros(58)
    x[5:45] = 1.0
    assert ns.n3_value(x, CFG) == 1.0
    x[5:25] = 0.0
    assert ns.n3_value(x, CFG) == 0.5
    with pytest.raises(ra.StopError):
        ns.n3_value(np.ones(30), CFG)
    with pytest.raises(ra.StopError):
        ns.n3_value(np.full(58, np.nan), CFG)


def test_selects_first_15_in_order_with_rejects():
    ids = [f"c{i:02d}" for i in range(40)]
    called = []

    def n3(i):
        called.append(i)
        return 0.2 if i == "c03" else 0.9

    rows = ns.session0_rows(ids, gpu(ids, bad={"c01"}), n3, CFG)
    passes = [r["t1_name"] for r in rows if r["decision"] == "pass"]
    assert len(passes) == CFG["controls"]["refclips"]["nat_n"] == 15
    assert rows[1]["reason"] == "not_english" and rows[3]["reason"] == "low_face_present"
    assert rows[3]["rule"] == "N3" and "c01" not in called         # N3 only after N1/N2 pass
    assert rows[-1]["decision"] == "pass" and len(rows) == 17
    assert all(r["stage"] == "session0" for r in rows)
    ok = CFG["controls"]["refclips"]["reject_reasons"]
    assert all(r["reason"] is None or r["reason"] in ok for r in rows)


def test_two_speakers_rejected():
    two = {"lang_probs": EN, "segments": [[0, 30, "A"], [30, 50, "B"]]}
    d = ra.nat_decide(two["lang_probs"], [tuple(s) for s in two["segments"]], CFG)
    assert d["reason"] == "not_single_speaker"
    assert ra.nat_decide(EN, [], CFG)["reason"] == "not_single_speaker"


def test_fewer_than_15_is_a_stop_with_rows():
    ids = [f"c{i:02d}" for i in range(20)]
    with pytest.raises(ns.Session0Stop) as e:
        ns.session0_rows(ids, gpu(ids, bad=set(ids[:6])), lambda i: 0.9, CFG)
    assert len(e.value.rows) == 20 and sum(r["decision"] == "pass" for r in e.value.rows) == 14


def test_missing_gpu_output_is_a_stop():
    with pytest.raises(ra.StopError, match="no N1/N2"):
        ns.session0_rows(["a", "b"], gpu(["a"]), lambda i: 0.9, CFG)


def test_nat_manifest_joins_cpu_rows():
    ids = [f"c{i:02d}" for i in range(16)]
    cpu = [{"stage": "cpu", "decision": "pass", "t1_name": i, "title": f"File:{i}.webm", "url": "u",
            "values": {"licence": "CC0", "licence_template": "Template:Cc-zero"}} for i in ids]
    s0 = ns.session0_rows(ids, gpu(ids), lambda i: 0.9, CFG)
    m = ns.nat_manifest(cpu + s0, CFG)
    assert [r["t1_name"] for r in m] == ids[:15] and m[0]["licence"] == "CC0"
    with pytest.raises(ra.StopError):
        ns.nat_manifest(cpu + s0[:-1], CFG)


def test_dir_sha_deterministic_and_ignores_cache(tmp_path):
    d = tmp_path / "m"
    (d / "sub").mkdir(parents=True)
    (d / "a.bin").write_bytes(b"1")
    (d / "sub" / "b.yaml").write_text("x")
    s = nb.dir_sha(d)
    (d / ".cache").mkdir()
    (d / ".cache" / "meta").write_text("t")
    assert nb.dir_sha(d) == s
    (d / "a.bin").write_bytes(b"2")
    assert nb.dir_sha(d) != s
    with pytest.raises(RuntimeError):
        nb.dir_sha(tmp_path / "empty_does_not_exist")


def test_patched_config_points_at_mirror(tmp_path):
    m = tmp_path / "mirror"
    (m / nb.REPOS["diarization"]).mkdir(parents=True)
    (m / nb.REPOS["diarization"] / "config.yaml").write_text(yaml.safe_dump(
        {"pipeline": {"name": "pyannote.audio.pipelines.SpeakerDiarization",
                      "params": {"clustering": "AgglomerativeClustering",
                                 "segmentation": "pyannote/segmentation-3.0",
                                 "embedding": "pyannote/wespeaker-voxceleb-resnet34-LM"}}}))
    (m / nb.REPOS["plda"] / "plda").mkdir(parents=True)      # D-082 draft: mirrored PLDA
    for f in nb.PLDA_FILES:
        (m / nb.REPOS["plda"] / "plda" / f).write_bytes(b"x")
    f = nb.patched_config(m, tmp_path / "w")
    p = yaml.safe_load(f.read_text())["pipeline"]["params"]
    assert p["segmentation"].startswith(str(m)) and p["embedding"]["checkpoint"].endswith("pytorch_model.bin")


def test_patched_config_refuses_unexpected_models(tmp_path):
    m = tmp_path / "mirror"
    (m / nb.REPOS["diarization"]).mkdir(parents=True)
    (m / nb.REPOS["diarization"] / "config.yaml").write_text(yaml.safe_dump(
        {"pipeline": {"params": {"segmentation": "other/model", "embedding": "x"}}}))
    with pytest.raises(SystemExit):
        nb.patched_config(m, tmp_path / "w")


def test_lang_probs_uses_first_30_s():
    seen = {}

    class M:
        def detect_language(self, x):
            seen["n"] = len(x)
            return "en", 0.95, [("en", 0.95), ("fr", 0.05)]

    x = np.zeros(58 * nb.SR, np.float32)
    assert nb.lang_probs(M(), x, [0, 30]) == {"en": 0.95, "fr": 0.05}
    assert seen["n"] == 30 * nb.SR


def test_diarize_reads_annotation_or_diarize_output():
    class Seg:
        def __init__(self, s, e):
            self.start, self.end = s, e

    class Ann:
        def itertracks(self, yield_label):
            return [(Seg(0.0, 1.5), "t", "SPEAKER_00")]

    class Out:
        speaker_diarization = Ann()

    x = np.zeros(10, np.float32)
    assert nb.diarize(lambda d: Ann(), x, waveform=lambda a: a) == [[0.0, 1.5, "SPEAKER_00"]]
    assert nb.diarize(lambda d: Out(), x, waveform=lambda a: a) == [[0.0, 1.5, "SPEAKER_00"]]
