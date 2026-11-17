"""BUG-003: pinned backbones + no network during TRIBE feature extraction / prediction.

TRIBE's ``from_pretrained`` ignores ``revision`` and its extractors load the three backbones by repo id
(``main``). We therefore (1) pre-populate the HF cache at the pinned revisions below and point
``refs/main`` at them (``remote_setup.sh``), (2) set ``HF_HUB_OFFLINE=1`` / ``TRANSFORMERS_OFFLINE=1``
before any HF import (``enforce_offline``), (3) verify the cache pins before running
(``check_hf_cache_pins``) and (4) block every non-loopback socket connection while extracting and
predicting (``no_network``), so an unpinned download cannot happen silently.
"""
from __future__ import annotations

import contextlib
import ipaddress
import os
import socket
from collections.abc import Iterator
from pathlib import Path

# Revisions resolved in P0 run smoke_20261117T142354Z (docs/tribe_requirements.md §10).
BACKBONE_REVISIONS = {
    "facebook/vjepa2-vitg-fpc64-256": "875c192b7b704b87d1e1d99345769632dd5f739a",
    "facebook/w2v-bert-2.0": "da985ba0987f70aaeb84a80f2851cfac8c697a7b",
    "meta-llama/Llama-3.2-3B": "13afe5124825b4f3751f836b40dafda64c1ed062",
}
TRIBE_WEIGHTS_REVISION = "f894e783020944dcd96e5568550afe2aa9743f9f"
OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"}


PROXY_VARS = {"http_proxy", "https_proxy", "all_proxy"}


class NetworkBlockedError(RuntimeError):
    """A network connection was attempted inside ``no_network()``."""


class PinError(RuntimeError):
    """The HF cache does not resolve a backbone to its pinned revision."""


def enforce_offline(environ: dict | None = None) -> dict:
    """Set the HF offline variables (must run before huggingface_hub/transformers are imported)."""
    env = os.environ if environ is None else environ
    env.update(OFFLINE_ENV)
    return {k: env[k] for k in OFFLINE_ENV}


def _hub_dir(hf_home: str | Path | None = None) -> Path:
    if hf_home is not None:
        return Path(hf_home) / "hub"
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def resolved_revisions(hf_home: str | Path | None = None) -> dict[str, str | None]:
    """refs/main of each pinned backbone in the local HF cache (None if absent)."""
    out: dict[str, str | None] = {}
    for repo in BACKBONE_REVISIONS:
        ref = _hub_dir(hf_home) / ("models--" + repo.replace("/", "--")) / "refs" / "main"
        out[repo] = ref.read_text().strip() if ref.exists() else None
    return out


def check_hf_cache_pins(hf_home: str | Path | None = None) -> dict[str, str]:
    """Raise PinError unless every backbone's refs/main == pinned revision and its snapshot exists."""
    got = resolved_revisions(hf_home)
    bad = []
    for repo, want in BACKBONE_REVISIONS.items():
        snap = _hub_dir(hf_home) / ("models--" + repo.replace("/", "--")) / "snapshots" / want
        if got[repo] != want:
            bad.append(f"{repo}: refs/main={got[repo]} != pinned {want}")
        elif not snap.is_dir():
            bad.append(f"{repo}: snapshot {want} missing")
    if bad:
        raise PinError("; ".join(bad))
    return dict(BACKBONE_REVISIONS)


def _is_local(address) -> bool:
    if isinstance(address, str | bytes):  # AF_UNIX path
        return True
    host = address[0] if isinstance(address, tuple) and address else address
    if host in ("localhost", "", None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@contextlib.contextmanager
def no_network() -> Iterator[None]:
    """Block every non-loopback socket connect / DNS lookup in this process (BUG-003 no-network test)."""
    orig_connect, orig_connect_ex = socket.socket.connect, socket.socket.connect_ex
    orig_gai = socket.getaddrinfo

    def connect(self, address):
        if not _is_local(address):
            raise NetworkBlockedError(f"network connection to {address!r} blocked (offline run)")
        return orig_connect(self, address)

    def connect_ex(self, address):
        if not _is_local(address):
            raise NetworkBlockedError(f"network connection to {address!r} blocked (offline run)")
        return orig_connect_ex(self, address)

    def getaddrinfo(host, *a, **k):
        if not _is_local((host,)):
            raise NetworkBlockedError(f"DNS lookup of {host!r} blocked (offline run)")
        return orig_gai(host, *a, **k)

    # A loopback HTTP(S) proxy would otherwise be an allowed path to the internet.
    proxies = {k: os.environ.pop(k) for k in list(os.environ) if k.lower() in PROXY_VARS}
    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex = orig_connect, orig_connect_ex
        socket.getaddrinfo = orig_gai
        os.environ.update(proxies)


ALLOW_PATTERNS = ["*.json", "*.safetensors", "tokenizer*", "*.model", "*.txt"]  # no original/*.pth, *.pt


def prefetch_backbones(hf_home: str | Path | None = None) -> dict[str, str]:
    """GPU-box setup only (network ON): download each backbone at its pinned revision and point
    refs/main at it, so offline loads of the bare repo id resolve to the pinned snapshot."""
    from huggingface_hub import snapshot_download

    for repo, rev in BACKBONE_REVISIONS.items():
        snap = Path(snapshot_download(repo, revision=rev, allow_patterns=ALLOW_PATTERNS,
                                      cache_dir=None if hf_home is None else _hub_dir(hf_home)))
        ref = snap.parents[1] / "refs" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(rev)
    return check_hf_cache_pins(hf_home)


if __name__ == "__main__":  # python -m yct.tribe_run.offline  (remote_setup.sh)
    import json

    print(json.dumps(prefetch_backbones()))
