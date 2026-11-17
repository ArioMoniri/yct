"""GPU env setup pins (FIX-D032-1): transformers pinned to the P0-measured 5.17.0; exca exact."""
import re
from pathlib import Path

SETUP = Path(__file__).resolve().parents[1] / "src/yct/tribe_run/remote_setup.sh"


def _install_line() -> str:
    lines = [ln for ln in SETUP.read_text().splitlines() if "pip install" in ln and "tribev2" in ln]
    assert len(lines) == 1, lines
    return lines[0]


def test_transformers_pinned_exactly():
    assert re.search(r'"transformers==5\.17\.0"', _install_line())
    assert 'assert t.__version__ == "5.17.0"' in SETUP.read_text()


def test_exca_pinned_exactly():
    assert '"exca==0.5.20"' in _install_line()


def test_run_clip_uses_feature_cache_and_asr_guard():
    src = (SETUP.parent / "run_clip.py").read_text()
    assert "run_cached(" in src and "FeatureStore(" in src
    fc = (SETUP.parent / "feature_cache.py").read_text()
    assert fc.count("with asr_guard():") >= 3  # extraction, cached prediction, drift
