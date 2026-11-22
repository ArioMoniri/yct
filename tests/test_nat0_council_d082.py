"""Council on D-082 + session-0 readiness (wf_f6c3f08d-716; reviews/phase_p4b/council_d082_*.md): the
blocking items, test-first. Dry run only (fakes), no network, no GPU."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from yct.config import load_config
from yct.curate import nat0_box as nb
from yct.curate import natstim as ns

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gpu_p4b_nat0", ROOT / "scripts" / "gpu_p4b_nat0.py")
nat0 = sys.modules.get("gpu_p4b_nat0")
if nat0 is None:
    nat0 = importlib.util.module_from_spec(spec)
    sys.modules["gpu_p4b_nat0"] = nat0
    spec.loader.exec_module(nat0)
p4 = nat0.ref.p4
HEAD = "c" * 40
EN, ONE = {"en": 0.99}, [[0.0, 50.0, "S0"]]
CFG = load_config()


def cfg():
    c = copy.deepcopy(CFG)
    for k in nat0.PYANNOTE_KEYS:
        c["controls"]["refclips_auto_artifacts"][k] = "a" * 64
        c["frozen"].append({"key": f"controls.refclips_auto_artifacts.{k}", "frozen_at": "x"})
    c["frozen"].append({"key": "controls.refclips_d082", "frozen_at": "x"})
    return c


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
    def __init__(self, fail=None):
        self.fail, self.calls = fail, []

    def start(self, iid, deadline):
        self.calls.append("start")

    def step(self, name, buffer):
        self.calls.append(name)
        if name == self.fail:
            raise RuntimeError("box died")
        if name == "nat0":
            return {"results": {i: {"lang_probs": EN, "segments": ONE} for i in buffer}}

    def n3(self, i):
        return 0.9


def write_log(path, n_pass, exhausted=False):
    rows = [{"stage": "cpu", "decision": "pass", "t1_name": f"t1_{i:02d}", "title": f"File:{i}",
             "values": {"licence": "CC0", "licence_template": "Template:Cc-zero"}} for i in range(n_pass)]
    if exhausted:
        rows.append({"stage": ns.STAGE_CPU_END, "reason": "snapshot_exhausted", "n_evaluated": n_pass,
                     "n_pass": n_pass, "n_order": n_pass})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def env(tmp_path):
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    log = tmp_path / "nat_auto_log.jsonl"
    write_log(log, 40)
    return SimpleNamespace(clock=clock, lg=lg, log=log, store=Store(), tmp=tmp_path)


def args(env, **kw):
    a = {"max_hours": 1.75, "usd_limit": 8.0, "external_terminator_at": env.clock() + 1.75 * 3600 + 1000,
         "ci_green_sha": HEAD, "ack_cap_80": False, "run_id": "p4bnat0_test"}
    a.update(kw)
    return SimpleNamespace(**a)


def run(env, box=None, recon="fresh", cpu_state="fresh", c=None, **kw):
    c = c or cfg()
    if recon == "fresh":
        recon = nat0.reconcile(env.lg, c, env.clock)
    if cpu_state == "fresh":
        cpu_state = {"alive": False, "pod_log_sha256": sha(env.log)}
    return nat0.run_session0(args(env, **kw), c, env.lg, env.store, box or Box(), env.clock, env.log, HEAD,
                             True, recon=recon, cpu_state=cpu_state)


def s0_rows(env):
    return [json.loads(x) for x in env.log.read_text().splitlines()
            if json.loads(x).get("stage") == ns.STAGE_S0]


# ---------------------------------------------------------------- W2 / B1: no launch on a partial buffer
def test_partial_39_pass_buffer_is_refused(env):
    write_log(env.log, 39)
    rc, res = run(env)
    assert rc == 1 and res["status"] == "refused" and "39" in res["error"] and "40" in res["error"]
    assert env.lg.launched == []


def test_39_pass_buffer_with_logged_snapshot_exhausted_record_is_accepted(env):
    write_log(env.log, 39, exhausted=True)
    rc, res = run(env)
    assert rc == 0, res
    assert res["n_buffer"] == 39


def test_full_40_buffer_is_accepted(env):
    rc, res = run(env)
    assert rc == 0 and res["n_buffer"] == 40


def test_exhausted_record_must_match_the_logged_counts(env):
    write_log(env.log, 39, exhausted=True)
    rows = [json.loads(x) for x in env.log.read_text().splitlines()]
    rows[-1]["n_pass"] = 38
    env.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rc, res = run(env)
    assert rc == 1 and "39" in res["error"]


def test_run_cpu_logs_a_terminal_snapshot_exhausted_record(tmp_path):
    from tests.test_natstim import runner

    _, log, out = runner(tmp_path, n=10)
    rows = ns.load_log(log)
    assert len(out) == 10 and rows[-1] == {"stage": ns.STAGE_CPU_END, "reason": "snapshot_exhausted",
                                           "n_evaluated": 10, "n_pass": 10, "n_order": 10}
    assert ns.buffer_complete(rows, CFG)
    runner(tmp_path, n=10)                       # a resume writes no second terminal record
    assert sum(r.get("stage") == ns.STAGE_CPU_END for r in ns.load_log(log)) == 1


def test_run_cpu_full_buffer_has_no_terminal_record(tmp_path):
    from tests.test_natstim import runner

    _, log, _ = runner(tmp_path, n=60)
    assert all(r.get("stage") == ns.STAGE_CPU for r in ns.load_log(log))


def test_cpu_stage_still_alive_is_refused(env):
    rc, res = run(env, cpu_state={"alive": True, "pod_log_sha256": sha(env.log)})
    assert rc == 1 and "CPU stage" in res["error"] and env.lg.launched == []


def test_pod_log_differs_from_the_committed_log_is_refused(env):
    rc, res = run(env, cpu_state={"alive": False, "pod_log_sha256": "0" * 64})
    assert rc == 1 and "pod" in res["error"] and env.lg.launched == []


def test_missing_cpu_state_is_refused(env):
    rc, res = run(env, cpu_state=None)
    assert rc == 1 and env.lg.launched == []


# ---------------------------------------------------------------- B2 (biostat) / referee 5: no masked failure
def test_asr_failure_after_nat0_is_exit_75_nothing_logged_instance_terminated(env):
    rc, res = run(env, box=Box(fail="asr"))
    assert rc == 75 and res["status"] == "box_failed" and s0_rows(env) == []
    (iid,) = env.lg.launched
    assert env.lg.status[iid] == "terminated"
    assert res["steps"].get("asr") != "ok"


# ---------------------------------------------------------------- referee 7: L4 ledger reconciliation
def test_missing_reconcile_record_is_refused(env):
    rc, res = run(env, recon=None)
    assert rc == 1 and "reconcil" in res["error"] and env.lg.launched == []


def test_stale_reconcile_record_is_refused(env):
    rec = nat0.reconcile(env.lg, cfg(), env.clock)
    env.lg.mod._append({"event": "launch", "id": "x1", "name": "yct-other", "usd_per_hour": 1.0,
                        "t": env.clock() - 10})
    env.lg.mod._append({"event": "terminate", "id": "x1", "t": env.clock() - 5})
    rc, res = run(env, recon=rec)
    assert rc == 1 and "reconcil" in res["error"]


def test_reconcile_refuses_an_open_launch(env):
    env.lg.mod._append({"event": "launch", "id": "x2", "name": "yct-other", "usd_per_hour": 1.0,
                        "t": env.clock() - 10})
    with pytest.raises(SystemExit, match="open"):
        nat0.reconcile(env.lg, cfg(), env.clock)


def test_reconcile_record_fields(env):
    rec = nat0.reconcile(env.lg, cfg(), env.clock)
    for k in ("ledger_n_lines", "ledger_sha256", "open_launches", "live", "spent_usd", "budget_cap_usd",
              "campaign_spend_usd", "t"):
        assert k in rec
    assert rec["open_launches"] == [] and rec["live"] == []


# ---------------------------------------------------------------- B1 (referee/neuro/QA): ship list
def _module_file(mod: str) -> Path | None:
    parts = mod.split(".")
    if parts[0] != "yct":
        return None
    base = ROOT / "src" / Path(*parts)
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    return None


def _closure(entries: list[str]) -> set[str]:
    seen, todo = set(), list(entries)
    while todo:
        m = todo.pop()
        f = _module_file(m)
        if f is None or m in seen:
            continue
        seen.add(m)
        parts = m.split(".")
        for i in range(1, len(parts)):                       # parent packages
            todo.append(".".join(parts[:i]))
        if f.name == "__main__.py":
            pass
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                todo.append(node.module)
                todo += [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                todo += [a.name for a in node.names]
    return {str(_module_file(m).relative_to(ROOT)) for m in seen}


def _tar_names(data: bytes) -> set[str]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        return {m.name for m in tf.getmembers() if m.isfile()}


def test_ship_tarball_holds_every_module_a_box_step_runs_and_the_freeze():
    names = _tar_names(nat0.ship_tarball(nat0.ship_list()))
    need = _closure(["yct.curate.nat0_box", "yct.transcribe.__main__", "yct.transcribe"])
    assert "src/yct/curate/nat0_box.py" in need and "src/yct/curate/__init__.py" in need
    missing = sorted(need - names)
    assert not missing, missing
    for f in ("config.yaml", nat0.PodBox.FREEZE, "infra/gpu_deadman.sh", "infra/gpu_heartbeat.sh"):
        assert f in names, f


def test_ship_list_does_not_mutate_the_shared_p0_ship_list():
    import gpu_p0_rerun as g

    before = list(g.SHIP)
    nat0.ship_list()
    nat0.ship_list()
    assert g.SHIP == before
    assert len(nat0.ship_list()) == len(set(nat0.ship_list()))


# ---------------------------------------------------------------- box scripts (referee 2/3, QA B2/B4)
class FakeG:
    B = "/home/ubuntu/yct"

    def __init__(self, big: str):
        self.cmds, self.big = [], big

    def pod(self, cmd, timeout=900, check=True):
        self.cmds.append(cmd)
        return ""

    def pod_file(self, path, missing_ok=False):
        self.cmds.append(f"POD_FILE {path}")
        return self.big


class FakeBoxSSH:
    def __init__(self):
        self.scripts, self.ssh = {}, "ssh box"

    def start(self, name, script):
        self.scripts[name] = script

    def wait(self, name, t):
        return 0

    def run(self, script, timeout=900):
        return '{"truncated'                         # what an SSM-truncated cat would give

    def cat(self, p):
        return ""


def podbox(big=""):
    pb = nat0.PodBox(cfg(), "p4bnat0_test", 1.75)
    pb.g, pb.box = FakeG(big), FakeBoxSSH()
    return pb


def test_nat0_results_over_24kb_are_read_via_pod_file_not_ssm_stdout():
    big = json.dumps({"versions": {}, "results": {f"t1_{i:02d}": {"lang_probs": {f"l{j}": 0.001 for j in
                                                                              range(99)}, "segments": ONE}
                                                   for i in range(40)}})
    assert len(big) > 24000
    pb = podbox(big)
    out = pb.step("nat0", [f"t1_{i:02d}" for i in range(40)])
    assert out == json.loads(big)
    assert any(c.startswith("POD_FILE ") for c in pb.g.cmds)


def test_box_steps_export_cuda_libs_install_uv_ffmpeg_and_punkt():
    pb = podbox("{}")
    pb.step("setup_wx", [])
    s = pb.box.scripts["wxsetup"]
    assert "astral.sh/uv/install.sh" in s and "UV_INSTALL_DIR" in s and "ffmpeg" in s
    assert "punkt_tab" in s and nat0.PodBox.FREEZE in s
    pb.step("nat0", ["t1_00"])
    pb.step("asr", ["t1_00"])
    for name in ("nat0", "asr"):
        assert "nvidia/cudnn/lib" in pb.box.scripts[name] and "nvidia/cublas/lib" in pb.box.scripts[name]


# ---------------------------------------------------------------- referee 4: offline before pyannote loads
def test_enforce_offline_sets_the_already_imported_hub_constant(monkeypatch):
    consts = types.SimpleNamespace(HF_HUB_OFFLINE=False)
    hub = types.ModuleType("huggingface_hub")
    hub.constants = consts
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", consts)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    nb.enforce_offline()
    assert consts.HF_HUB_OFFLINE is True
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_main_resolves_whisper_then_goes_offline_before_loading_pyannote(monkeypatch, tmp_path):
    order = []
    fw = types.ModuleType("faster_whisper")

    class WM:
        def __init__(self, path, device, compute_type):
            order.append(("whisper", path))

        def detect_language(self, x):
            return "en", 0.99, [("en", 0.99)]

    fw.WhisperModel = WM
    fwu = types.ModuleType("faster_whisper.utils")
    fwu.download_model = lambda name: order.append(("download", name)) or str(tmp_path / "snap" / "abc123")
    fw.utils = fwu
    monkeypatch.setitem(sys.modules, "faster_whisper", fw)
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", fwu)
    monkeypatch.setattr(nb, "enforce_offline", lambda: order.append(("offline",)))
    monkeypatch.setattr(nb, "check_mirror", lambda m, w: None)
    monkeypatch.setattr(nb, "load_pipeline", lambda m, w, d: order.append(("pyannote",)) or object())
    monkeypatch.setattr(nb, "diarize", lambda p, x: ONE)
    import importlib.metadata as md

    monkeypatch.setattr(md, "version", lambda p: {"faster-whisper": "1.2.1", "pyannote.audio": "4.1.0"}[p])
    import numpy as np

    (tmp_path / "w").mkdir()
    nb.write_wav(tmp_path / "w" / "a.wav", np.zeros(16000, np.float32))
    out = tmp_path / "o.json"
    assert nb.main(["--wavs", str(tmp_path / "w"), "--mirror", str(tmp_path), "--shas", "{}",
                    "--out", str(out), "--device", "cpu"]) == 0
    tags = [o[0] for o in order]
    assert tags == ["download", "whisper", "offline", "pyannote"], order
    res = json.loads(out.read_text())
    assert res["whisper_model"] == {"name": "large-v3", "snapshot": "abc123"}
    assert "\n" not in out.read_text().strip(), "compact JSON"


# ---------------------------------------------------------------- neuro non-blocking: single-voice fixture
def test_setup_verify_requires_one_speaker_on_the_single_voice_fixture():
    spec2 = importlib.util.spec_from_file_location("nat0_setup_c",
                                                   ROOT / "scripts" / "nat0_pyannote_setup.py")
    setup = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(setup)
    one = [[0.0, 3.0, "A"], [3.5, 6.0, "A"]]
    two = [[0.0, 3.0, "A"], [3.5, 6.0, "B"]]
    assert setup.fixture_ok(one, 1) and not setup.fixture_ok(two, 1)
    assert setup.fixture_ok(two, 2) and not setup.fixture_ok(one, 2)
    assert hasattr(setup, "one_voice_fixture")


# ---------------------------------------------------------------- BUG-042 (pod rehearsal): embedding loader
def test_patched_config_passes_the_embedding_as_a_checkpoint_dict(tmp_path):
    """pyannote.audio 4.1.0 PretrainedSpeakerEmbedding picks the loader by substring: a str path containing
    'wespeaker' but not 'pyannote' goes to the ONNX WeSpeaker loader and fails on the pinned .bin. A dict
    {checkpoint: path} always takes the pyannote Model loader, whatever the mirror dir is called."""
    import yaml

    from tests.test_nat0_d082 import mirror

    m = mirror(tmp_path / "nat")                         # a box-like path with no 'pyannote' in it
    p = yaml.safe_load(nb.patched_config(m, tmp_path / "w").read_text())["pipeline"]["params"]
    assert p["embedding"] == {"checkpoint": str(m / nb.REPOS["embedding"] / "pytorch_model.bin")}
    assert "pyannote" not in str(m)


def test_load_pipeline_refuses_a_non_pyannote_embedding_loader(monkeypatch, tmp_path):
    torch = types.ModuleType("torch")
    torch.device = lambda d: d
    pa = types.ModuleType("pyannote.audio")

    class Onnx:
        pass

    class Pipe:
        _embedding = Onnx()

        def to(self, d):
            return self

    pa.Pipeline = types.SimpleNamespace(from_pretrained=lambda p: Pipe())
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setitem(sys.modules, "pyannote.audio", pa)
    monkeypatch.setattr(nb, "enforce_offline", lambda: None)
    monkeypatch.setattr(nb, "patched_config", lambda m, w: tmp_path / "c.yaml")
    with pytest.raises(SystemExit, match="embedding loader"):
        nb.load_pipeline(tmp_path, tmp_path, "cpu")
    Onnx.__name__ = "PyannoteAudioPretrainedSpeakerEmbedding"
    assert isinstance(nb.load_pipeline(tmp_path, tmp_path, "cpu"), Pipe)


def test_enforce_offline_imports_the_constants_submodule(monkeypatch):
    """huggingface_hub is a lazy module: `huggingface_hub.constants` is not an attribute until the submodule
    is imported (the pod rehearsal hit AttributeError)."""
    consts = types.SimpleNamespace(HF_HUB_OFFLINE=False)
    hub = types.ModuleType("huggingface_hub")         # no .constants attribute, like the lazy module
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", consts)
    nb.enforce_offline()
    assert consts.HF_HUB_OFFLINE is True


# ---------------------------------------------------------------- BUG-043 (rehearsal run 2): peak memory
def test_main_runs_n1_for_all_wavs_and_frees_the_model_before_loading_pyannote(monkeypatch, tmp_path):
    """The pod (7 GB) OOM-killed nat0_box holding large-v3 and pyannote together. N1 now runs over every wav,
    the Whisper model is released, and only then is pyannote loaded for N2 (same outputs)."""
    import gc
    import importlib.metadata as md
    import weakref

    import numpy as np

    events, refs = [], []
    fw = types.ModuleType("faster_whisper")

    class WM:
        def __init__(self, path, device, compute_type):
            refs.append(weakref.ref(self))

        def detect_language(self, x):
            events.append("n1")
            return "en", 0.99, [("en", 0.99)]

    fw.WhisperModel = WM
    fwu = types.ModuleType("faster_whisper.utils")
    fwu.download_model = lambda name: str(tmp_path / "snap" / "abc")
    monkeypatch.setitem(sys.modules, "faster_whisper", fw)
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", fwu)
    monkeypatch.setattr(nb, "enforce_offline", lambda: None)
    monkeypatch.setattr(nb, "check_mirror", lambda m, w: None)

    def load(m, w, d):
        gc.collect()
        events.append("pyannote_alive" if refs[0]() is not None else "pyannote")
        return object()

    monkeypatch.setattr(nb, "load_pipeline", load)
    monkeypatch.setattr(nb, "diarize", lambda p, x: events.append("n2") or ONE)
    monkeypatch.setattr(md, "version", lambda p: {"faster-whisper": "1.2.1", "pyannote.audio": "4.1.0"}[p])
    (tmp_path / "w").mkdir()
    for i in range(3):
        nb.write_wav(tmp_path / "w" / f"t{i}.wav", np.zeros(16000, np.float32))
    out = tmp_path / "o.json"
    assert nb.main(["--wavs", str(tmp_path / "w"), "--mirror", str(tmp_path), "--shas", "{}",
                    "--out", str(out), "--device", "cpu"]) == 0
    assert events == ["n1", "n1", "n1", "pyannote", "n2", "n2", "n2"], events
    r = json.loads(out.read_text())["results"]
    assert sorted(r) == ["t0", "t1", "t2"]
    assert all(v["lang_probs"] == {"en": 0.99} and v["segments"] == ONE and v["n_samples"] == 16000
               for v in r.values())
