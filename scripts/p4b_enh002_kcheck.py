"""D-071 (f) pre-launch disclosure: run the frozen kernel code (yct.controls.kernels) on the ENH-002 summary
courses (P0 reference run wave1p2b_20261118T002855Z: 5 flash events -> V1_V3, 5 speech bursts -> AUD, one
120 s two-chunk clip each). Descriptive only; changes no frozen rule.

The ENH-002 design differs from p4b_ref/v1: one clip per family, so the 5 events stand in for clips (halves =
even/odd event index); no NAT clips (K1' not computable), no inter-event spans (K3' not computable), no MOT
(K6 not computable). Those rules get neutral placeholders and are reported as not_computable.

Usage: python scripts/p4b_enh002_kcheck.py [LATENCY_JSON] [OUT_JSON]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yct.config import load_config  # noqa: E402
from yct.controls.kernels import KernelInput, evaluate  # noqa: E402

SRC = ROOT / "outputs" / "runs" / "wave1p2b_20261118T002855Z" / "enh002_latency.json"
NOT_COMPUTABLE = ("K1p", "K3p")


def run(src: Path = SRC) -> dict:
    cfg = load_config()
    lat = json.loads(Path(src).read_text())
    out = {"source": str(Path(src).resolve().relative_to(ROOT)),
           "note": __doc__.split("\n\n")[1].replace("\n", " "), "kernels": {}}
    for clip, roi in (("ref_flash", "V1_V3"), ("ref_speech", "AUD")):
        std = np.asarray(lat["maps"]["spatially_standardised"][clip]["event_courses"], float)
        raw = np.asarray(lat["maps"]["raw"][clip]["event_courses"], float)
        n = std.shape[0]
        inp = KernelInput(roi, std, np.arange(n), d_raw=raw,
                          span_means=np.where(np.arange(n) % 2 == 0, 1.0, -1.0),   # placeholder, K3' n/c
                          sigma_nat=1e-9)                                          # placeholder, K1' n/c
        r = evaluate(inp, cfg)
        for k in NOT_COMPUTABLE:
            if k in r.get("rules", {}):
                r["rules"][k] = {"result": "not_computable"}
        computable = {k: v["result"] for k, v in r.get("rules", {}).items() if k not in NOT_COMPUTABLE}
        r["status_computable_rules"] = ("PASS" if computable and all(v == "PASS" for v in computable.values())
                                        else ("STOP_INVALID" if r["status"] == "STOP_INVALID" else "FAIL"))
        r.pop("status")
        out["kernels"][f"{clip}->{roi}"] = r
    out["K6"] = "not_computable (no MOT family in ENH-002)"
    return out


if __name__ == "__main__":
    res = run(Path(sys.argv[1]) if len(sys.argv) > 1 else SRC)
    text = json.dumps(res, indent=1)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text)
    print(text)
