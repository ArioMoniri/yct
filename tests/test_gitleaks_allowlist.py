"""BUG-020: the gitleaks allowlist must cover only hex cache_key hashes, nothing broader."""
import pathlib
import re
import tomllib

CFG = tomllib.loads((pathlib.Path(__file__).resolve().parents[1] / ".gitleaks.toml").read_text())


def _patterns():
    al = CFG.get("allowlist", {})
    assert al.get("regexTarget") == "line"
    return [re.compile(r) for r in al.get("regexes", [])]


def _allowed(line: str) -> bool:
    return any(p.search(line) for p in _patterns())


def test_default_rules_kept():
    assert CFG["extend"]["useDefault"] is True


def test_hex_cache_key_allowed():
    assert _allowed('    "cache_key": "' + "a1" * 32 + '",')
    assert _allowed('+   "cache_key": "' + "a1" * 32 + '",')  # same line inside a stored git diff
    assert _allowed('++   "cache_key": "' + "a1" * 32 + '",')  # stored diff seen through git log -p


def test_non_hex_or_other_keys_not_allowed():
    assert not _allowed('    "cache_key": "sk-ABCDEFGHIJKLMNOPQRSTUVWX",')
    assert not _allowed('    "api_key": "' + "a1" * 32 + '",')
    assert not _allowed('cache_key = "' + "a1" * 32 + '"  # other format')
