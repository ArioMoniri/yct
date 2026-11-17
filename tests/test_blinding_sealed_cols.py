"""BUG-024: sealed label-proxy columns are caught in tracked CSV/JSON headers and stored diffs."""
import importlib.util
import pathlib

_p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_blinding.py"
_s = importlib.util.spec_from_file_location("cb", _p)
cb = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cb)


def test_csv_header_with_sealed_column_caught():
    assert cb.header_hits("x.csv", "video_id,discovery_method\nyct_0001,k\n") == ["discovery_method"]


def test_json_key_with_sealed_column_caught():
    assert cb.header_hits("x.json", '{"label_confidence": "A"}') == ["label_confidence"]


def test_patch_with_sealed_column_caught():
    diff = "+video_id,url,label_confidence,evidence_url\n"
    assert set(cb.header_hits("outputs/runs/r/git_diff.patch", diff)) >= {"label_confidence", "evidence_url"}


def test_clean_files_pass():
    assert cb.header_hits("x.csv", "video_id,url,in_primary\n") == []
    assert cb.header_hits("x.patch", "+print('hello')\n") == []
