"""Owner-only (human) actions, read from AWS SSM Parameter Store (DECISIONS D-030).

The owner writes these parameters; IAM gives agents/pods read-only access to /yct/owner/*:

    /yct/owner/owner_arn       IAM ARN of the owner (the only allowed writer)
    /yct/owner/budget_usd      GPU budget cap in USD (default 50 until set)
    /yct/owner/unblind_token   issued at P6 after unanimous GO; absent before
    /yct/owner/data_decision   the signed-off data decision text; absent before
    /yct/owner/age_pub         the owner's age public key (blinding root); docs/owner_age.pub must equal it

Defence in depth on top of IAM: every value read here is checked against get_parameter_history,
and the version being returned must have LastModifiedUser == owner_arn. owner_arn itself must have
been last written by that same ARN, and must equal the pinned owner ARN: config.yaml `owner.arn_pin`
(recorded at the first verified run; frozen by scripts/check_guard_config.py) and, if set, env
YCT_OWNER_ARN (both must match; no pin at all is an error). Anything else raises OwnerActionError
(callers must stop).
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

PREFIX = "/yct/owner/"
DEFAULT_BUDGET_USD = 50.0
DEFAULT_REGION = "eu-central-1"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
AGE_PUB_PATH = Path(__file__).resolve().parents[2] / "docs" / "owner_age.pub"


class OwnerActionError(RuntimeError):
    """An owner-only parameter is missing where required, malformed, or not written by the owner."""


def _client(client: Any = None) -> Any:
    if client is not None:
        return client
    import boto3  # lazy: unit tests and laptops without boto3 never import it

    return boto3.client("ssm", region_name=os.environ.get("AWS_REGION", DEFAULT_REGION))


def _is_not_found(client: Any, exc: Exception) -> bool:
    nf = getattr(getattr(client, "exceptions", None), "ParameterNotFound", None)
    if nf is not None and isinstance(exc, nf):
        return True
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
    return code == "ParameterNotFound"


def _history(client: Any, name: str) -> list[dict]:
    rows, token = [], None
    while True:
        kw = {"Name": name, "WithDecryption": True}
        if token:
            kw["NextToken"] = token
        page = client.get_parameter_history(**kw)
        rows.extend(page.get("Parameters", []))
        token = page.get("NextToken")
        if not token:
            return rows


def _read(client: Any, name: str) -> dict | None:
    """Current parameter dict incl. LastModifiedUser of its version, or None if absent."""
    full = PREFIX + name
    try:
        cur = client.get_parameter(Name=full, WithDecryption=True)["Parameter"]
    except Exception as exc:
        if _is_not_found(client, exc):
            return None
        raise
    hist = _history(client, full)
    match = [h for h in hist if h.get("Version") == cur.get("Version")]
    if not match:
        raise OwnerActionError(f"{full}: version {cur.get('Version')} not found in parameter history")
    ver = match[-1]
    if ver.get("Value") != cur.get("Value"):
        raise OwnerActionError(f"{full}: value differs from its history entry")
    latest = max(hist, key=lambda h: h.get("Version", 0))
    if latest.get("Version") != cur.get("Version"):
        raise OwnerActionError(f"{full}: parameter changed while reading; retry")
    return {**cur, "LastModifiedUser": ver.get("LastModifiedUser")}


def owner_arn(client: Any = None) -> str:
    c = _client(client)
    p = _read(c, "owner_arn")
    if p is None or not p.get("Value"):
        raise OwnerActionError(f"{PREFIX}owner_arn is not set; owner setup incomplete")
    if p.get("LastModifiedUser") != p["Value"]:
        raise OwnerActionError(f"{PREFIX}owner_arn was last modified by {p.get('LastModifiedUser')!r}, "
                               "not by the owner it names")
    # A self-consistent rewrite (attacker sets owner_arn to itself) is caught by requiring every
    # historical version to name, and be written by, the same principal. Rotating the owner means
    # deleting and recreating the parameter, which the owner does by hand.
    for h in _history(c, PREFIX + "owner_arn"):
        if h.get("Value") != p["Value"] or h.get("LastModifiedUser") != p["Value"]:
            raise OwnerActionError(f"{PREFIX}owner_arn history has version {h.get('Version')} "
                                   f"by {h.get('LastModifiedUser')!r}; owner identity changed")
    pins = {"YCT_OWNER_ARN": os.environ.get("YCT_OWNER_ARN"), "config owner.arn_pin": _config_pin()}
    if not any(pins.values()):
        raise OwnerActionError("no owner ARN pin (config.yaml owner.arn_pin / YCT_OWNER_ARN); refusing "
                               "trust-on-first-use")
    for where, pinned in pins.items():
        if pinned and pinned != p["Value"]:
            raise OwnerActionError(f"{PREFIX}owner_arn does not match pinned {where}")
    return p["Value"]


def _config_pin() -> str | None:
    """owner.arn_pin from config.yaml (None if the file or key is absent)."""
    try:
        import yaml

        cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except FileNotFoundError:
        return None
    v = (cfg.get("owner") or {}).get("arn_pin")
    return str(v) if v else None


def get_owner_param(name: str, client: Any = None) -> str | None:
    """Value of /yct/owner/<name> if set by the owner, None if absent; raises if written by anyone else."""
    c = _client(client)
    owner = owner_arn(c)
    p = _read(c, name)
    if p is None:
        return None
    if p.get("LastModifiedUser") != owner:
        raise OwnerActionError(f"{PREFIX}{name} was last modified by {p.get('LastModifiedUser')!r}, "
                               f"not the owner {owner!r}")
    return p["Value"]


def budget_usd(client: Any = None) -> float:
    raw = get_owner_param("budget_usd", client)
    if raw is None:
        return DEFAULT_BUDGET_USD
    try:
        val = float(raw.strip())
    except ValueError as exc:
        raise OwnerActionError(f"{PREFIX}budget_usd is not a number: {raw!r}") from exc
    if not (math.isfinite(val) and val > 0):
        raise OwnerActionError(f"{PREFIX}budget_usd must be a positive finite number, got {raw!r}")
    return val


def unblind_token(client: Any = None) -> str | None:
    return get_owner_param("unblind_token", client)


def data_decision(client: Any = None) -> str | None:
    return get_owner_param("data_decision", client)


def age_pub(client: Any = None) -> str | None:
    return get_owner_param("age_pub", client)


def verify_age_pub(path: str | Path = AGE_PUB_PATH, client: Any = None) -> str:
    """The repo copy of the owner's age key must equal the owner-written SSM value (QA G-D032 c2 #2).

    Call before encrypting anything to docs/owner_age.pub (e.g. sealed labels, D-029). Returns the key."""
    want = age_pub(client)
    if not want:
        raise OwnerActionError(f"{PREFIX}age_pub is not set by the owner")
    got = Path(path).read_text().strip()
    if got != want.strip():
        raise OwnerActionError(f"{path} does not match the owner's {PREFIX}age_pub; do not encrypt to it")
    return got
