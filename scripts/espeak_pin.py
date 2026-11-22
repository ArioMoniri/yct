#!/usr/bin/env python3
"""D-085 part 2 (council B1): print the espeak-ng engine shas for `speech.engine_pin`.

  python scripts/espeak_pin.py [--binary P] [--lib P] [--data-dir P]

Defaults are `controls.refclips_d085.speech.engine_paths`. The data-tree sha is the recorded pod method
(`cd DATA && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.tribe_run import espeak_engine as E  # noqa: E402,N812


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary")
    ap.add_argument("--lib")
    ap.add_argument("--data-dir")
    a = ap.parse_args(argv)
    if not (a.binary and a.lib and a.data_dir):
        from yct.config import load_config

        dflt = load_config()["controls"]["refclips_d085"]["speech"]["engine_paths"]
    else:
        dflt = {}
    p = {"binary": Path(a.binary or dflt["binary"]), "lib": Path(a.lib or dflt["lib"]),
         "data_dir": Path(a.data_dir or dflt["data_dir"])}
    print(json.dumps({"binary_sha256": E._file_sha(p["binary"]), "lib_sha256": E._file_sha(p["lib"]),
                      "data_tree_sha256": E.data_tree_sha256(p["data_dir"]),
                      "n_data_files": E.n_data_files(p["data_dir"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
