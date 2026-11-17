"""BUG-010: skip detection must ignore skip code that appears only inside string literals,
while still catching every real skip/xfail marker (stricter precision, no loss of recall)."""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "ctw", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_test_weakening.py")
ctw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctw)


def _diff(added: str) -> str:
    return f"diff --git a/tests/t.py b/tests/t.py\n--- a/tests/t.py\n+++ b/tests/t.py\n+{added}\n"


def test_skip_inside_string_literal_ignored():
    line = 'return repo.commit("add skip", {"tests/_h.py": "def f():\\n    pytest.skip(\'x\')\\n"})'
    assert ctw.analyse(_diff(line)) == []


def test_real_skip_call_still_caught():
    assert any("skip" in f for f in ctw.analyse(_diff('    pytest.skip("no network")')))


def test_real_skip_marker_still_caught():
    assert any("skip" in f for f in ctw.analyse(_diff('@pytest.mark.skipif(True, reason="x")')))


def test_real_xfail_still_caught():
    assert any("skip" in f for f in ctw.analyse(_diff("@pytest.mark.xfail")))
