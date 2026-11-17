"""yct.owner_actions: owner-only values come from SSM /yct/owner/* and must be last written by the owner."""
import pytest

from yct import owner_actions as oa

OWNER = "arn:aws:iam::123456789012:user/owner"
AGENT = "arn:aws:sts::123456789012:assumed-role/yct-pod/i-0abc"


class ParameterNotFound(Exception):  # noqa: N818 - mirrors the boto3 name
    pass


class StubSSM:
    """Stands in for boto3.client('ssm'); history is a list of (value, modifier) per name, oldest first."""

    class exceptions:  # noqa: N801 - mirrors boto3 client attribute
        ParameterNotFound = ParameterNotFound

    def __init__(self, history: dict[str, list[tuple[str, str]]], page_size: int = 2):
        self.history = history
        self.page_size = page_size

    def get_parameter(self, Name, WithDecryption=False):  # noqa: N803
        if Name not in self.history:
            raise ParameterNotFound(Name)
        value, user = self.history[Name][-1]
        return {"Parameter": {"Name": Name, "Value": value, "Version": len(self.history[Name])}}

    def get_parameter_history(self, Name, WithDecryption=False, NextToken=None):  # noqa: N803
        if Name not in self.history:
            raise ParameterNotFound(Name)
        rows = [{"Name": Name, "Value": v, "Version": i + 1, "LastModifiedUser": u}
                for i, (v, u) in enumerate(self.history[Name])]
        start = int(NextToken or 0)
        out = {"Parameters": rows[start:start + self.page_size]}
        if start + self.page_size < len(rows):
            out["NextToken"] = str(start + self.page_size)
        return out


def _ssm(**params):
    hist = {"/yct/owner/owner_arn": [(OWNER, OWNER)]}
    for k, v in params.items():
        hist[f"/yct/owner/{k}"] = v
    return StubSSM(hist)


def test_budget_from_owner(monkeypatch):
    c = _ssm(budget_usd=[("50", OWNER), ("200", OWNER)])
    assert oa.budget_usd(client=c) == 200.0


def test_budget_default_when_absent():
    assert oa.budget_usd(client=_ssm()) == oa.DEFAULT_BUDGET_USD == 50.0


def test_budget_last_written_by_agent_raises():
    c = _ssm(budget_usd=[("50", OWNER), ("9999", AGENT)])
    with pytest.raises(oa.OwnerActionError, match="budget_usd"):
        oa.budget_usd(client=c)


def test_history_is_paginated():
    c = _ssm(budget_usd=[("1", AGENT), ("2", OWNER), ("3", OWNER), ("4", OWNER), ("5", AGENT)])
    with pytest.raises(oa.OwnerActionError):
        oa.budget_usd(client=c)
    c = _ssm(budget_usd=[("1", AGENT), ("2", OWNER), ("3", OWNER), ("4", OWNER), ("5", OWNER)])
    assert oa.budget_usd(client=c) == 5.0


def test_bad_budget_value_raises():
    with pytest.raises(oa.OwnerActionError):
        oa.budget_usd(client=_ssm(budget_usd=[("lots", OWNER)]))
    with pytest.raises(oa.OwnerActionError):
        oa.budget_usd(client=_ssm(budget_usd=[("-5", OWNER)]))


def test_unblind_token_absent_is_none():
    assert oa.unblind_token(client=_ssm()) is None


def test_unblind_token_by_owner():
    assert oa.unblind_token(client=_ssm(unblind_token=[("tok", OWNER)])) == "tok"


def test_unblind_token_by_agent_raises():
    with pytest.raises(oa.OwnerActionError, match="unblind_token"):
        oa.unblind_token(client=_ssm(unblind_token=[("tok", AGENT)]))


def test_data_decision():
    assert oa.data_decision(client=_ssm()) is None
    assert oa.data_decision(client=_ssm(data_decision=[("approved", OWNER)])) == "approved"
    with pytest.raises(oa.OwnerActionError):
        oa.data_decision(client=_ssm(data_decision=[("approved", AGENT)]))


def test_owner_arn_missing_raises():
    c = StubSSM({"/yct/owner/budget_usd": [("100", OWNER)]})
    with pytest.raises(oa.OwnerActionError, match="owner_arn"):
        oa.budget_usd(client=c)


def test_owner_arn_rewritten_by_agent_raises():
    c = StubSSM({"/yct/owner/owner_arn": [(OWNER, OWNER), (AGENT, AGENT)],
                 "/yct/owner/budget_usd": [("100", AGENT)]})
    with pytest.raises(oa.OwnerActionError, match="owner_arn"):
        oa.budget_usd(client=c)


def test_value_mismatch_with_history_raises():
    c = _ssm(budget_usd=[("100", OWNER)])
    real = c.get_parameter

    def racy(Name, WithDecryption=False):  # noqa: N803
        r = real(Name, WithDecryption)
        if Name.endswith("budget_usd"):
            r["Parameter"]["Version"] = 99
        return r

    c.get_parameter = racy
    with pytest.raises(oa.OwnerActionError):
        oa.budget_usd(client=c)


def test_owner_arn_pinned_by_env(monkeypatch):
    c = _ssm(budget_usd=[("100", OWNER)])
    monkeypatch.setenv("YCT_OWNER_ARN", "arn:aws:iam::1:user/someone-else")
    with pytest.raises(oa.OwnerActionError, match="pinned"):
        oa.budget_usd(client=c)
    monkeypatch.setenv("YCT_OWNER_ARN", OWNER)
    assert oa.budget_usd(client=c) == 100.0
