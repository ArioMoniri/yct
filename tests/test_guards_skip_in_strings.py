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


# ---------------------------------------------------------------- FIX-C3-ENG: tokenize-based recall
# Every evasion found by Watchdog / QA at G-D032 cycle 2 must be caught; pure data strings must not.
import pytest  # noqa: E402

EVASIONS = [
    'x = f"{pytest.skip(\'no gpu\')}"',                     # Watchdog: skip inside an f-string expression
    '"""doc"""; pytest.skip("evade2")',                      # Watchdog: docstring then skip on one line
    '"""; pytest.skip("x")',                                 # QA: closes a triple-quoted string, then skips
    'exec("pytest.skip(\'x\')")',                           # QA: skip inside exec
    'eval(compile("pytest.skip(1)", "f", "exec"))',          # eval/compile string
    "pytest.importorskip('torch')",                          # QA: importorskip
    'raise pytest.skip.Exception("x")',                      # Watchdog: raise pytest.skip.Exception
    'request.node.add_marker("skip")',                       # QA: add_marker("skip")
    "request.node.add_marker(pytest.mark.xfail)",
    "from pytest import skip",
    'getattr(pytest, "skip")("x")',
    'self.skipTest("x")',
    '@unittest.skip("x")',
    "@mark.skipif(True, reason='x')",
]
DATA = [
    'x = "pytest.skip(\'x\')"',
    "y = 'importorskip and add_marker(\"skip\") are words here'",
    'return repo.commit("s", {"tests/_h.py": "def f():\\n    pytest.skip(\'x\')\\n"})',
    '# pytest.skip("comment")',
    "skip = 3",
]


@pytest.mark.parametrize("line", EVASIONS)
def test_evasion_is_caught(line):
    assert any("skip/xfail" in f for f in ctw.analyse(_diff(line))), line


@pytest.mark.parametrize("line", DATA)
def test_pure_data_is_ignored(line):
    assert ctw.analyse(_diff(line)) == [], line


def test_whole_file_mode_catches_skip_after_multiline_string():
    old = 'def test_a():\n    """doc\n    """\n    assert 1\n'
    new = 'def test_a():\n    """doc\n    """; pytest.skip("x")\n    assert 1\n'
    diff = ("diff --git a/tests/t.py b/tests/t.py\n--- a/tests/t.py\n+++ b/tests/t.py\n"
            '-    """\n+    """; pytest.skip("x")\n')
    assert any("skip/xfail" in f for f in ctw.analyse(diff, {"tests/t.py": (old, new)}))


def test_whole_file_mode_ignores_skip_text_inside_multiline_string():
    old = 'FIXTURE = """\ndef f():\n    return 1\n"""\n'
    new = 'FIXTURE = """\ndef f():\n    pytest.skip("x")\n"""\n'
    diff = ("diff --git a/tests/t.py b/tests/t.py\n--- a/tests/t.py\n+++ b/tests/t.py\n"
            '-    return 1\n+    pytest.skip("x")\n')
    assert ctw.analyse(diff, {"tests/t.py": (old, new)}) == []


def test_moving_a_skip_is_not_an_addition():
    old = 'import pytest\n\n\ndef f():\n    pytest.skip("x")\n'
    new = 'import pytest\n\n\ndef g():\n    pass\n\n\ndef f():\n    pytest.skip("x")\n'
    diff = "diff --git a/tests/t.py b/tests/t.py\n--- a/tests/t.py\n+++ b/tests/t.py\n+def g():\n+    pass\n"
    assert ctw.analyse(diff, {"tests/t.py": (old, new)}) == []


def test_real_git_commit_with_fstring_skip_fails(repo):
    base = repo.commit("t", {"tests/test_a.py": "def test_a():\n    assert 1\n"})
    body = 'import pytest\n\n\ndef test_a():\n    x = f"{pytest.skip(\'e\')}"\n    assert 1\n'
    repo.commit("evade", {"tests/test_a.py": body})
    res = repo.run_script("check_test_weakening.py", "--base", base)
    assert res.returncode == 1 and "skip/xfail" in res.stdout
