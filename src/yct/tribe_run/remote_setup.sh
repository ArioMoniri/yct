#!/usr/bin/env bash
# Build the pinned TRIBE v2 environment on a fresh Lambda GPU box (Ubuntu, user ubuntu).
# Pins: docs/tribe_requirements.md §0-1. Idempotent. Requires ~/.cache/huggingface/token to be
# placed beforehand (piped from the pod; never echoed). Usage: bash remote_setup.sh [WORKDIR]
set -euo pipefail
W="${1:-$HOME/yct}"
TRIBE_COMMIT=af58661791a351a448a489042a28f6c37e1c14b7
HF_REV=f894e783020944dcd96e5568550afe2aa9743f9f
CKPT_SHA=9c79ffff6b642b7b0c71d558c935fb3fa33f2788bfb509feead94fafbba2f321
mkdir -p "$W"; cd "$W"

# System deps (wait for boot-time apt locks).
for i in $(seq 1 60); do sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break; sleep 5; done
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq update
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq install -y ffmpeg espeak-ng git >/dev/null

# uv lives in its own dir so it can be dropped from PATH at run time (no `uvx whisperx`).
if [ ! -x "$HOME/.uvbin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$HOME/.uvbin" UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
UV="$HOME/.uvbin/uv"

[ -d tribev2/.git ] || git clone -q https://github.com/facebookresearch/tribev2.git
git -C tribev2 fetch -q origin "$TRIBE_COMMIT" 2>/dev/null || true
git -C tribev2 checkout -q "$TRIBE_COMMIT"
[ -d venv ] || "$UV" venv -q -p 3.11 venv
# shellcheck disable=SC1091
source venv/bin/activate
# transformers is unpinned upstream; pin the version measured in P0 smoke run smoke_20261117T142354Z.
"$UV" pip install -q -e ./tribev2 "torch>=2.5.1,<2.7" "exca==0.5.20" "transformers==5.17.0" "spacy==3.8.14" nilearn pandas
python -c 'import transformers as t; assert t.__version__ == "5.17.0", t.__version__'
"$UV" pip freeze > "$W/pip_freeze.txt"

python - "$HF_REV" "$W/weights" <<'PY'
import sys
from huggingface_hub import snapshot_download
snapshot_download("facebook/tribev2", revision=sys.argv[1], local_dir=sys.argv[2],
                  allow_patterns=["config.yaml", "best.ckpt", "LICENSE", "README.md"])
PY
# spaCy model used by neuralset's text transform (get_spacy_model("english") -> en_core_web_lg). Without this
# neuralset calls spacy.cli.download() AT RUN TIME (unpinned network fetch; caught by no_network() in the
# FIX-C3-ENG GPU re-run). Pinned wheel + sha256.
SPACY_WHL=en_core_web_lg-3.8.0-py3-none-any.whl
SPACY_SHA=293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63
[ -f "$SPACY_WHL" ] || curl -sSL -o "$SPACY_WHL" "https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/$SPACY_WHL"
[ "$(sha256sum "$SPACY_WHL" | cut -d' ' -f1)" = "$SPACY_SHA" ] || { echo "SPACY MODEL SHA MISMATCH"; exit 4; }
"$UV" pip install -q "./$SPACY_WHL"
python -c 'import spacy; assert spacy.__version__ == "3.8.14", spacy.__version__; assert spacy.util.is_package("en_core_web_lg")'
"$UV" pip freeze > "$W/pip_freeze.txt"
# BUG-003: backbones at pinned revisions, refs/main -> pinned sha (runs are HF_HUB_OFFLINE=1 + no network).
# Requires the repo's src/ at $W/src (yct.tribe_run.offline holds the pins).
PYTHONPATH="$W/src" python -m yct.tribe_run.offline
got=$(sha256sum weights/best.ckpt | cut -d' ' -f1)
[ "$got" = "$CKPT_SHA" ] || { echo "CKPT SHA MISMATCH $got"; exit 3; }
echo "SETUP_OK ckpt_sha256=$got"
