"""BUG-008: tests/_atlas.load_or_skip must FAIL when atlases are unavailable unless YCT_OFFLINE=1."""
import pytest

from tests import _atlas
from yct.features.atlas import AtlasUnavailableError


def _unavailable():
    raise AtlasUnavailableError("no network")


def test_unavailable_atlas_fails_by_default(monkeypatch):
    monkeypatch.delenv("YCT_OFFLINE", raising=False)
    with pytest.raises(pytest.fail.Exception, match="YCT_OFFLINE"):
        _atlas.load_or_skip(_unavailable)


@pytest.mark.parametrize("val", ["0", "", "true", "yes"])
def test_only_exact_offline_flag_allows_skip(monkeypatch, val):
    monkeypatch.setenv("YCT_OFFLINE", val)
    with pytest.raises(pytest.fail.Exception):
        _atlas.load_or_skip(_unavailable)


def test_offline_flag_skips(monkeypatch):
    monkeypatch.setenv("YCT_OFFLINE", "1")
    with pytest.raises(pytest.skip.Exception):
        _atlas.load_or_skip(_unavailable)


def test_available_atlas_is_returned(monkeypatch):
    monkeypatch.delenv("YCT_OFFLINE", raising=False)
    assert _atlas.load_or_skip(lambda: 42) == 42


def test_ci_does_not_set_offline():
    from pathlib import Path

    ci = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
    assert "YCT_OFFLINE" not in ci
