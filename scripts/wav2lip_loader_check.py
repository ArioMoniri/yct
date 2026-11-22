"""D-085 part 2 loader check on a SYNTHETIC fixture only (no real face, no audio). Prints numbers only."""
import hashlib
import json
import sys

import torch

W, REPO = sys.argv[1], sys.argv[2]
sys.path.insert(0, REPO)
out = {"torch": torch.__version__}
blob = open(W, "rb").read()
out["weights_sha256"] = hashlib.sha256(blob).hexdigest()
out["weights_bytes"] = len(blob)
from models import Wav2Lip  # noqa: E402  (the pinned upstream class at bac9a81)

torch.manual_seed(0)
B = 2
mel = torch.randn(B, 1, 80, 16)
face = torch.rand(B, 6, 96, 96)
try:
    jm = torch.jit.load(W, map_location="cpu")
    out["jit_load"] = "ok"
    sd = jm.state_dict()
    m = Wav2Lip()
    want = m.state_dict()
    out["n_keys_archive"], out["n_keys_pinned"] = len(sd), len(want)
    out["keys_equal"] = sorted(sd) == sorted(want)
    out["shape_mismatch"] = [k for k in want if k in sd and tuple(sd[k].shape) != tuple(want[k].shape)][:5]
    out["missing"] = [k for k in want if k not in sd][:5]
    out["unexpected"] = [k for k in sd if k not in want][:5]
    try:
        m.load_state_dict(sd, strict=True)
        out["strict_load"] = "ok"
        m.eval()
        with torch.no_grad():
            y = m(mel, face)
        out["strict_out_shape"] = list(y.shape)
        out["strict_out_finite"] = bool(torch.isfinite(y).all())
        out["strict_out_range"] = [round(float(y.min()), 4), round(float(y.max()), 4)]
        jm.eval()
        with torch.no_grad():
            yj = jm(mel, face)
        out["jit_out_shape"] = list(yj.shape)
        out["max_abs_diff_pinned_vs_jit"] = float((y - yj).abs().max())
    except Exception as e:  # noqa: BLE001
        out["strict_load"] = f"fail: {type(e).__name__}: {str(e)[:300]}"
except Exception as e:  # noqa: BLE001
    out["jit_load"] = f"fail: {type(e).__name__}: {str(e)[:300]}"
print(json.dumps(out))
