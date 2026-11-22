"""D-085 part 2 council (wf_de28150c-be9): engine-pin check, Wav2Lip NOGAN loader, TALKFACE face continuation.

Written before the code (TDD). Nothing here synthesises corpus text or touches a real face: the espeak tests
use a fake engine tree, the Wav2Lip tests use a fake torch, the continuation tests use config copies.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import types
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.config_schema import validate_config

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
D85 = CFG["controls"]["refclips_d085"]
SP, TF = D85["speech"], D85["talkface"]
NOGAN = "7ab9249147fd8d7884983567883222b7a86b6f94282354887825dfee7d608999"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ espeak-ng engine pin (B1)
def _fake_tree(tmp: Path) -> dict[str, Path]:
    d = tmp / "espeak-ng-data"
    (d / "voices" / "!v").mkdir(parents=True)
    (d / "en_dict").write_bytes(b"dict")
    (d / "phontab").write_bytes(b"ph")
    (d / "voices" / "!v" / "f1").write_bytes(b"v")
    b, lib = tmp / "espeak-ng", tmp / "libespeak-ng.so.1.1.51"
    b.write_bytes(b"bin")
    lib.write_bytes(b"lib")
    return {"binary": b, "lib": lib, "data_dir": d}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_data_tree_hash_equals_the_recorded_shell_method(tmp_path):
    """The pod value was `cd DATA && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`."""
    from yct.tribe_run import espeak_engine as E  # noqa: N812

    p = _fake_tree(tmp_path)
    rels = sorted(["./en_dict", "./phontab", "./voices/!v/f1"], key=lambda s: s.encode())
    lines = "".join(f"{_sha((p['data_dir'] / r[2:]).read_bytes())}  {r}\n" for r in rels)
    assert E.data_tree_sha256(p["data_dir"]) == _sha(lines.encode())


def test_engine_pin_mismatch_is_a_stop_and_match_passes(tmp_path):
    from yct.tribe_run import espeak_engine as E  # noqa: N812

    p = _fake_tree(tmp_path)
    pin = {"binary_sha256": _sha(b"bin"), "lib_sha256": _sha(b"lib"),
           "data_tree_sha256": E.data_tree_sha256(p["data_dir"]), "native_sr": 22050}
    assert E.verify_engine(pin, p) == {"binary": pin["binary_sha256"], "lib": pin["lib_sha256"],
                                       "data_tree": pin["data_tree_sha256"]}
    for k, bad in (("binary", b"BIN"), ("lib", b"LIB")):
        q = _fake_tree(tmp_path / k)
        q[k].write_bytes(bad)
        with pytest.raises(SystemExit, match="STOP"):
            E.verify_engine(pin, q)
    q = _fake_tree(tmp_path / "data")
    (q["data_dir"] / "en_dict").write_bytes(b"changed")
    with pytest.raises(SystemExit, match="STOP"):
        E.verify_engine(pin, q)


def test_synth_verifies_the_pin_before_any_call_and_never_reinstalls(tmp_path, monkeypatch):
    from yct.tribe_run import espeak_engine as E  # noqa: N812

    p = _fake_tree(tmp_path)
    pin = {"binary_sha256": _sha(b"WRONG"), "lib_sha256": _sha(b"lib"),
           "data_tree_sha256": E.data_tree_sha256(p["data_dir"]), "native_sr": 22050}
    calls = []
    monkeypatch.setattr(E.subprocess, "run", lambda *a, **k: calls.append(a))
    spec = {**SP, "engine_pin": pin}
    with pytest.raises(SystemExit, match="STOP"):
        E.EspeakSynth(spec, p)
    assert calls == []                      # no synthesis, no apt call before the pin passes


def test_synth_args_and_selection_rate(tmp_path, monkeypatch):
    from yct.tribe_run import espeak_engine as E  # noqa: N812

    p = _fake_tree(tmp_path)
    pin = {"binary_sha256": _sha(b"bin"), "lib_sha256": _sha(b"lib"),
           "data_tree_sha256": E.data_tree_sha256(p["data_dir"]), "native_sr": 22050}
    seen = {}

    def fake_wav(cmd, **kw):
        seen["cmd"] = cmd
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            t = np.arange(2205) / 22050
            w.writeframes((np.sin(2 * np.pi * 220 * t) * 16000).astype("<i2").tobytes())
        return types.SimpleNamespace(stdout=buf.getvalue(), returncode=0)

    monkeypatch.setattr(E.subprocess, "run", fake_wav)
    s = E.EspeakSynth({**SP, "engine_pin": pin}, p)
    x, sr = s("a test")
    assert seen["cmd"][:9] == [str(p["binary"]), "-v", "en-us", "-s", "175", "-p", "50", "-a", "100"]
    assert "--stdout" in seen["cmd"]
    assert sr == SP["selection_sr"] == 48000          # selection span on the build's 48 kHz band-limited path
    assert abs(len(x) - 4800) <= 2 and np.max(np.abs(x)) <= 1.0


def test_engine_pin_is_required_by_the_schema():
    cfg = copy.deepcopy(CFG)
    del cfg["controls"]["refclips_d085"]["speech"]["engine_pin"]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        validate_config(cfg)
    assert SP["engine_paths"]["data_dir"] == "/usr/lib/x86_64-linux-gnu/espeak-ng-data"


def test_espeak_pin_script_prints_the_three_shas(tmp_path, capsys):
    mod = _load_script("espeak_pin")
    p = _fake_tree(tmp_path)
    mod.main(["--binary", str(p["binary"]), "--lib", str(p["lib"]), "--data-dir", str(p["data_dir"])])
    out = json.loads(capsys.readouterr().out)
    assert out["binary_sha256"] == _sha(b"bin") and out["lib_sha256"] == _sha(b"lib")
    assert out["n_data_files"] == 3


# ------------------------------------------------------------------ Wav2Lip NOGAN (B2/B3)
def test_talkface_weights_pinned_to_nogan_and_the_fallback_record():
    assert TF["weights_file"] == "Wav2Lip-SD-NOGAN.pt" and TF["weights_sha256"] == NOGAN
    w = TF["weights_option"]
    assert w["council"] == "b" and w["applied"] == "a"
    assert w["reason"] == "no_upstream_sd_loader"   # master HEAD == pinned revision; no SD loader
    assert TF["revision"] == "bac9a81e63ecc153202353372e5724b83d9e6322"
    assert TF["loader"]["path"] == "strict_state_dict"   # decided on the synthetic fixture only
    assert TF["loader"]["gan_allowed"] is False
    rec = json.loads((ROOT / TF["loader"]["check_record"]).read_text())
    assert rec["weights_sha256"] == NOGAN and rec["strict_load"] == "ok"
    assert rec["keys_equal"] is True
    assert rec["strict_out_shape"] == [2, 3, 96, 96] and rec["fixture"] == "synthetic"
    assert rec["max_abs_diff_pinned_vs_jit"] == 0.0


def _fake_torch(sd_keys, want_keys, strict_ok=True):
    class Mod:
        def __init__(self, keys):
            self._k = keys

        def state_dict(self):
            return {k: types.SimpleNamespace(shape=(1,)) for k in self._k}

        def load_state_dict(self, sd, strict=True):
            if strict and sorted(sd) != sorted(self._k):
                raise RuntimeError("Error(s) in loading state_dict")
            return types.SimpleNamespace(missing_keys=[], unexpected_keys=[])

        def eval(self):
            return self

    jit = types.SimpleNamespace(load=lambda path, map_location=None: Mod(sd_keys))
    return types.SimpleNamespace(jit=jit), (lambda: Mod(want_keys))


def test_loader_refuses_a_wrong_sha_and_gan(tmp_path):
    from yct.tribe_run import wav2lip_loader as L  # noqa: N812

    w = tmp_path / "Wav2Lip-SD-NOGAN.pt"
    w.write_bytes(b"not the archive")
    torch, cls = _fake_torch(["a"], ["a"])
    with pytest.raises(SystemExit, match="STOP"):
        L.load_nogan(w, NOGAN, cls, torch)
    g = tmp_path / "Wav2Lip-SD-GAN.pt"
    g.write_bytes(b"x")
    with pytest.raises(SystemExit, match="GAN"):
        L.load_nogan(g, _sha(b"x"), cls, torch)


def test_loader_strict_state_dict_into_the_pinned_class(tmp_path):
    from yct.tribe_run import wav2lip_loader as L  # noqa: N812

    w = tmp_path / "Wav2Lip-SD-NOGAN.pt"
    w.write_bytes(b"archive")
    torch, cls = _fake_torch(["a", "b"], ["a", "b"])
    m, rec = L.load_nogan(w, _sha(b"archive"), cls, torch)
    assert rec == {"path": "strict_state_dict", "n_keys": 2}
    torch, cls = _fake_torch(["a", "c"], ["a", "b"])
    with pytest.raises(SystemExit, match="strict"):       # no silent jit fallback: decided on the fixture
        L.load_nogan(w, _sha(b"archive"), cls, torch)


# ------------------------------------------------------------------ TALKFACE face continuation (B2/B3 of 4)
def test_face_continuation_key_terms():
    fc = TF["face_continuation"]
    assert fc == {
        "authority": "D-085 part 2", "separate_from": "D-087", "log": "v4_face_log",
        "first_target": 21, "plus_one_per_skip": True, "max_skips": 5, "max_extra_passes": 20,
        "after_rank": 492, "same_frozen_rules": True, "append_only": True,
        "existing_rows_byte_identical": True, "committed_before_wav2lip": True,
        "yunet_replacement": False, "on_exhausted": "stop_owner"}


def _cfg_frozen(keys):
    c = copy.deepcopy(CFG)
    c["frozen"] = [f for f in c.get("frozen", [])
                   if not f.get("key", "").startswith("controls.refclips_d087")]
    c["frozen"] += [{"key": k, "frozen_at": "x"} for k in keys]
    return c


def test_talkface_purpose_needs_part2_frozen_and_has_its_own_budget():
    r = _load_script("refstim_auto_run")
    unfrozen = _cfg_frozen([])
    with pytest.raises(SystemExit, match="refclips_d085.talkface is not frozen"):
        r.effective_need("face", {"face": 21}, 20, unfrozen, purpose="talkface")
    frozen = _cfg_frozen(["controls.refclips_d085.talkface"])
    assert r.effective_need("face", {"face": 21}, 20, frozen, purpose="talkface") == 21
    assert r.effective_need("face", {"face": 26}, 20, frozen, purpose="talkface") == 26   # 21 + 5 skips
    with pytest.raises(SystemExit, match="STOP"):
        r.effective_need("face", {"face": 27}, 20, frozen, purpose="talkface")   # > 5 skips
    with pytest.raises(SystemExit, match="face only"):
        r.effective_need("body", {"body": 21}, 20, frozen, purpose="talkface")
    # the D-087 path is unchanged and needs D-087, not D-085 part 2
    with pytest.raises(SystemExit, match="refclips_d087 is not frozen"):
        r.effective_need("face", {"face": 21}, 20, frozen)


def test_parse_purpose_flag():
    r = _load_script("refstim_auto_run")
    cats = ["face", "body", "place"]
    got = r.parse_run_args(["--purpose", "talkface", "--target", "face=21"], cats)
    assert got == ({"face": 21}, "talkface")
    assert r.parse_run_args(["--target", "place=22"], cats) == ({"place": 22}, "loc")
    with pytest.raises(SystemExit):
        r.parse_run_args(["--purpose", "other"], cats)


def test_face_log_append_only_check(tmp_path):
    r = _load_script("refstim_auto_run")
    before = b'{"a":1}\n{"b":2}\n'
    log = tmp_path / "l.jsonl"
    log.write_bytes(before + b'{"c":3}\n')
    r.assert_byte_prefix(_sha(before), len(before), log)
    log.write_bytes(b'{"a":9}\n{"b":2}\n{"c":3}\n')
    with pytest.raises(SystemExit, match="STOP"):
        r.assert_byte_prefix(_sha(before), len(before), log)


def test_part2_keys_still_unfrozen_until_council_resign():
    for k in D85["freeze_plan"]["part2"]:
        fr = [f for f in CFG.get("frozen", []) if f.get("key") == k]
        assert fr == [], k


# ------------------------------------------------------------------ re-sign-off (wf_77475312-b35)
def test_loader_blob_and_check_record_shas_are_pinned():
    import subprocess

    ld = TF["loader"]
    blob = subprocess.run(["git", "hash-object", str(ROOT / ld["module"])], capture_output=True, text=True,
                          check=True).stdout.strip()
    assert ld["blob_sha1"] == blob
    assert ld["check_record_sha256"] == _sha((ROOT / ld["check_record"]).read_bytes())


def test_select_refuses_an_unverified_synth():
    from yct.tribe_run import speech_corpus as S  # noqa: N812

    def bare(text):
        return np.zeros(10), 48000

    with pytest.raises(SystemExit, match="verified"):
        S.select([], bare, SP)


def test_target_above_21_needs_a_logged_skip_per_extra_pass():
    r = _load_script("refstim_auto_run")
    frozen = _cfg_frozen(["controls.refclips_d085.talkface"])
    with pytest.raises(SystemExit, match="skip"):
        r.effective_need("face", {"face": 23}, 20, frozen, purpose="talkface", skips=[])
    ok = [{"title": "File:a.jpg", "reason": "s3fd_no_face"}, {"title": "File:b.jpg", "reason": "wav2lip_error"}]
    assert r.effective_need("face", {"face": 23}, 20, frozen, purpose="talkface", skips=ok) == 23
    bad = [{"title": "File:a.jpg", "reason": "looked_wrong"}, ok[1]]
    with pytest.raises(SystemExit, match="skip"):
        r.effective_need("face", {"face": 23}, 20, frozen, purpose="talkface", skips=bad)
