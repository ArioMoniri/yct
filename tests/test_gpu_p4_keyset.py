"""T-REFRUN refactor guard (D-071): the P4 dry run writes exactly the same S3 key set before and after the
driver's campaign/constructor refactor. Golden set: tests/data/p4_dryrun_keyset.txt, generated from the
pre-refactor driver (d706707). Cache keys are content hashes, so the set is deterministic."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from yct.config import load_config, with_overrides

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "data" / "p4_dryrun_keyset.txt"

SMALL = {"p4": {"launcher_max_hours": 4, "run_set_t1": ["yct_0016", "yct_0040", "yct_0043"],
                "run_set_t3": ["yct_0016", "yct_0040", "yct_0043", "yct_0483"],
                "t1_excluded": {"yct_0483": "short"}, "d038_clips": ["yct_0016"],
                "flags": {"low_fps_source": {"rule": "r", "videos": [], "sensitivity": "S-LOWFPS"}}}}


def _load():
    spec = importlib.util.spec_from_file_location("gpu_wave1_p4", ROOT / "scripts" / "gpu_wave1_p4.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_wave1_p4"] = mod
    spec.loader.exec_module(mod)
    return mod


def dry_run_keyset(tmp: Path) -> list[str]:
    p4 = _load()
    cfg = with_overrides(load_config(), SMALL)
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp / "ledger.jsonl")
    b = p4.DryRunBackend(tmp / "dry", cfg, clock)
    a = p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id="p4_keyset")
    rc, res = p4.run_session(a, cfg, lg, b, clock, tmp / "runs" / "p4_keyset")
    assert rc == 0, res
    return sorted(b.s3_list(""))


def test_p4_dry_run_key_set_is_unchanged(tmp_path):
    assert dry_run_keyset(tmp_path) == GOLDEN.read_text().split()


if __name__ == "__main__":         # regenerate (only from the pre-refactor driver)
    import tempfile
    print("\n".join(dry_run_keyset(Path(tempfile.mkdtemp()))))
