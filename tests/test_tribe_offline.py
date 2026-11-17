"""BUG-003 (Referee P0 #1): pinned backbones, HF_HUB_OFFLINE=1 enforced in code, no network while running."""
import ast
import socket
import urllib.request
from pathlib import Path

import pytest

from yct.tribe_run import offline as off

TR = Path(__file__).resolve().parents[1] / "src" / "yct" / "tribe_run"


def test_enforce_offline_sets_all_hf_flags():
    env: dict = {}
    got = off.enforce_offline(env)
    assert env == got == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"}


def test_no_network_blocks_dns_tcp_and_http(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")  # a loopback proxy must not be a way out
    with off.no_network():
        with pytest.raises(off.NetworkBlockedError):
            socket.getaddrinfo("huggingface.co", 443)
        with pytest.raises(off.NetworkBlockedError):
            socket.create_connection(("8.8.8.8", 53), timeout=1)
        with pytest.raises(off.NetworkBlockedError):
            urllib.request.urlopen("https://huggingface.co/api/models", timeout=1)
        import os
        assert "HTTPS_PROXY" not in os.environ
    import os
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"  # restored afterwards
    assert socket.socket.connect is not None


def test_no_network_allows_loopback():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    with off.no_network():
        c = socket.create_connection(srv.getsockname(), timeout=2)
        c.close()
    srv.close()


def _fake_cache(root: Path, revs: dict, missing_snapshot: str | None = None) -> Path:
    for repo, rev in revs.items():
        d = root / "hub" / ("models--" + repo.replace("/", "--"))
        (d / "refs").mkdir(parents=True)
        (d / "refs" / "main").write_text(rev)
        if repo != missing_snapshot:
            (d / "snapshots" / rev).mkdir(parents=True)
    return root


def test_pins_ok(tmp_path):
    hf = _fake_cache(tmp_path, off.BACKBONE_REVISIONS)
    assert off.check_hf_cache_pins(hf) == off.BACKBONE_REVISIONS


def test_pins_wrong_ref_or_missing_snapshot_raise(tmp_path):
    revs = dict(off.BACKBONE_REVISIONS)
    revs["facebook/w2v-bert-2.0"] = "0" * 40
    with pytest.raises(off.PinError, match="w2v-bert"):
        off.check_hf_cache_pins(_fake_cache(tmp_path / "a", revs))
    with pytest.raises(off.PinError, match="snapshot"):
        off.check_hf_cache_pins(_fake_cache(tmp_path / "b", off.BACKBONE_REVISIONS,
                                            missing_snapshot="meta-llama/Llama-3.2-3B"))
    with pytest.raises(off.PinError):
        off.check_hf_cache_pins(tmp_path / "empty")


def test_pinned_revisions_match_p0_record():
    assert off.BACKBONE_REVISIONS == {
        "facebook/vjepa2-vitg-fpc64-256": "875c192b7b704b87d1e1d99345769632dd5f739a",
        "facebook/w2v-bert-2.0": "da985ba0987f70aaeb84a80f2851cfac8c697a7b",
        "meta-llama/Llama-3.2-3B": "13afe5124825b4f3751f836b40dafda64c1ed062",
    }


def test_run_clip_goes_offline_before_any_hf_import_and_checks_pins():
    """Static: in run_clip.main, enforce_offline() and check_hf_cache_pins() run before torch/tribev2 are
    imported, run_cached is called with offline=True and the pins are part of the cache revisions."""
    src = (TR / "run_clip.py").read_text()
    main = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "main")
    order = []
    for node in ast.walk(main):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            order.append((node.lineno, node.func.id))
        if isinstance(node, ast.Import):
            order += [(node.lineno, f"import {a.name}") for a in node.names]
    line = {name: ln for ln, name in sorted(order, reverse=True)}
    assert line["enforce_offline"] < line["check_hf_cache_pins"] < line["import torch"]
    assert line["import torch"] < line["import tribev2"]
    assert "offline=True" in src and "_revisions(weights, tribev2, torch, backbones)" in src
    assert '"backbones": backbones' in src


def test_remote_setup_prefetches_pinned_backbones():
    sh = (TR / "remote_setup.sh").read_text()
    assert "python -m yct.tribe_run.offline" in sh


def test_spacy_model_pinned_in_setup_and_checked_by_run_clip():
    """neuralset downloads en_core_web_lg at run time if missing (found by no_network() on the GPU)."""
    sh = (TR / "remote_setup.sh").read_text()
    assert off.SPACY_MODEL["wheel_sha256"] in sh and f"en_core_web_lg-{off.SPACY_MODEL['version']}" in sh
    assert '"spacy==3.8.14"' in sh
    assert "check_spacy_model()" in (TR / "run_clip.py").read_text()


def test_check_spacy_model_raises_when_missing(monkeypatch):
    import importlib.metadata as md

    def nf(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", nf)
    with pytest.raises(off.PinError, match="en_core_web_lg"):
        off.check_spacy_model()
    monkeypatch.setattr(md, "version", lambda name: "3.7.1")
    with pytest.raises(off.PinError, match="pinned"):
        off.check_spacy_model()
