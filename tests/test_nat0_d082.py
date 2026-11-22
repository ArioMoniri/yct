"""D-082 draft (BUG-040): the pinned community-1 PLDA, passed explicitly to the 3.1 pipeline under
pyannote.audio 4.1.0 and loaded from the mirror; unused by AgglomerativeClustering (fakes only)."""
import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

from yct.config import load_config
from yct.curate import nat0_box as nb

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
PIN = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def mirror(tmp_path, clustering="AgglomerativeClustering", plda_files=("plda.npz", "xvec_transform.npz")):
    m = tmp_path / "mirror"
    (m / nb.REPOS["diarization"]).mkdir(parents=True)
    (m / nb.REPOS["diarization"] / "config.yaml").write_text(yaml.safe_dump(
        {"pipeline": {"name": "pyannote.audio.pipelines.SpeakerDiarization",
                      "params": {"clustering": clustering, "segmentation": "pyannote/segmentation-3.0",
                                 "embedding": "pyannote/wespeaker-voxceleb-resnet34-LM"}}}))
    d = m / nb.REPOS["plda"] / "plda"
    d.mkdir(parents=True)
    for f in plda_files:
        (d / f).write_bytes(b"x")
    return m


def test_config_pins_community1_plda_at_an_immutable_revision():
    p = CFG["controls"]["refclips_d082"]["plda"]
    assert p == {"repo": "pyannote/speaker-diarization-community-1", "revision": PIN, "subfolder": "plda",
                 "files": ["plda.npz", "xvec_transform.npz"]}
    assert CFG["controls"]["refclips_d082"]["decision"] == "D-082"
    assert "pyannote_plda_sha256" in CFG["controls"]["refclips_auto_artifacts"]


def test_schema_refuses_a_branch_name_revision():
    from yct.config_schema import RefClipsD082

    d = copy.deepcopy(CFG["controls"]["refclips_d082"])
    d["plda"]["revision"] = "main"
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RefClipsD082.model_validate(d)


def test_repos_include_the_plda_mirror_dir():
    assert nb.REPOS["plda"] == "speaker-diarization-community-1"


def test_patched_config_passes_the_mirrored_plda_explicitly(tmp_path):
    m = mirror(tmp_path)
    p = yaml.safe_load(nb.patched_config(m, tmp_path / "w").read_text())["pipeline"]["params"]
    assert p["plda"] == str(m / nb.REPOS["plda"] / "plda")
    assert p["clustering"] == "AgglomerativeClustering"


def test_patched_config_refuses_vbx_clustering_which_would_use_the_plda(tmp_path):
    with pytest.raises(SystemExit, match="clustering"):
        nb.patched_config(mirror(tmp_path, clustering="VBxClustering"), tmp_path / "w")


def test_patched_config_refuses_an_incomplete_plda_mirror(tmp_path):
    with pytest.raises(SystemExit, match="plda"):
        nb.patched_config(mirror(tmp_path, plda_files=("plda.npz",)), tmp_path / "w")


def test_check_mirror_requires_the_plda_sha(tmp_path):
    m = mirror(tmp_path)
    for k in ("segmentation", "embedding"):
        (m / nb.REPOS[k]).mkdir()
        (m / nb.REPOS[k] / "pytorch_model.bin").write_bytes(b"w")
    want = {k: nb.dir_sha(m / n) for k, n in nb.REPOS.items()}
    nb.check_mirror(m, want)
    with pytest.raises(KeyError):
        nb.check_mirror(m, {k: v for k, v in want.items() if k != "plda"})
    with pytest.raises(SystemExit):
        nb.check_mirror(m, {**want, "plda": "0" * 64})


def test_setup_pins_include_plda_with_subfolder_only():
    setup = _load("nat0_setup", "scripts/nat0_pyannote_setup.py")
    p = setup.pins(CFG)
    assert p["plda"] == ("pyannote/speaker-diarization-community-1", PIN)
    assert setup.allow_patterns("plda") == ["plda/*"]
    assert setup.allow_patterns("diarization") is None


def test_setup_verify_requires_two_speakers_on_the_two_voice_fixture():
    setup = _load("nat0_setup2", "scripts/nat0_pyannote_setup.py")
    one = [[0.0, 3.0, "A"], [3.5, 6.0, "A"]]
    two = [[0.0, 3.0, "A"], [3.5, 6.0, "B"], [6.5, 9.0, "A"]]
    assert setup.fixture_ok(two)
    assert not setup.fixture_ok(one)
    assert not setup.fixture_ok([])


def test_session0_refuses_without_the_plda_sha():
    nat0 = _load("nat0_drv", "scripts/gpu_p4b_nat0.py")
    assert "pyannote_plda_sha256" in nat0.PYANNOTE_KEYS
    c = copy.deepcopy(CFG)
    for k in nat0.PYANNOTE_KEYS:
        if k != "pyannote_plda_sha256":
            c["controls"]["refclips_auto_artifacts"][k] = "a" * 64
            c["frozen"].append({"key": f"controls.refclips_auto_artifacts.{k}", "frozen_at": "x"})
    c["frozen"].append({"key": "controls.refclips_d082", "frozen_at": "x"})
    c["frozen"].append({"key": "controls.refclips_artifacts.nat_snapshot_sha256", "frozen_at": "x"})
    with pytest.raises(SystemExit, match="pyannote_plda_sha256"):
        nat0.check_frozen(c)


def test_session0_requires_d082_frozen():
    nat0 = _load("nat0_drv2", "scripts/gpu_p4b_nat0.py")
    c = copy.deepcopy(CFG)
    for k in nat0.PYANNOTE_KEYS:
        c["controls"]["refclips_auto_artifacts"][k] = "a" * 64
        c["frozen"].append({"key": f"controls.refclips_auto_artifacts.{k}", "frozen_at": "x"})
    c["frozen"].append({"key": "controls.refclips_artifacts.nat_snapshot_sha256", "frozen_at": "x"})
    c["frozen"] = [r for r in c["frozen"] if r["key"] != "controls.refclips_d082"]
    with pytest.raises(SystemExit, match="refclips_d082"):
        nat0.check_frozen(c)
