"""Watchdog W-COST guards for the Lambda GPU wrapper; no network calls."""
import importlib

import pytest


@pytest.fixture
def lg(tmp_path, monkeypatch):
    mod = importlib.import_module("infra.lambda_gpu")
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(mod, "types", lambda: {"gpu_1x_a10": {"usd_per_hour": 1.29, "regions": ["r"]}})
    return mod


def test_name_prefix_required(lg):
    with pytest.raises(SystemExit):
        lg.launch("gpu_1x_a10", "other-name", 1, None, None)


def test_max_hours_cap(lg):
    with pytest.raises(SystemExit):
        lg.launch("gpu_1x_a10", "yct-x", lg.BUDGET_MAX_HOURS + 1, None, None)


def test_budget_cap(lg, monkeypatch):
    monkeypatch.setattr(lg, "BUDGET_USD", 1.0)
    with pytest.raises(SystemExit):
        lg.launch("gpu_1x_a10", "yct-x", 1, None, None)


def test_spent_counts_open_instances(lg):
    import time
    lg._append({"event": "launch", "id": "a", "usd_per_hour": 3600.0, "t": time.time() - 2, "deadline": 0})
    assert lg.spent_usd() >= 2.0
