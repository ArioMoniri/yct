"""BUG-050b: compare two feature-cache entry tars by member metadata and per-member sha256 only.

Usage: python -I scripts/bug050b_members.py A.tar B.tar
Prints JSON: tar shas, members only in one, and per-member differences in mode/size/mtime/uid/content sha.
File contents are hashed, never parsed or printed.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tarfile


def members(path: str) -> tuple[str, dict]:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    out = {}
    with tarfile.open(path) as tf:
        for m in tf.getmembers():
            d = {"mode": oct(m.mode), "size": m.size, "mtime": m.mtime, "uid": m.uid, "gid": m.gid,
                 "uname": m.uname, "gname": m.gname, "type": m.type.decode(errors="replace"),
                 "pax_keys": sorted(m.pax_headers)}
            if m.isfile():
                fh = hashlib.sha256()
                f = tf.extractfile(m)
                while b := f.read(1 << 20):
                    fh.update(b)
                d["sha256"] = fh.hexdigest()
            out[m.name.split("/", 1)[1] if "/" in m.name else m.name] = d
    return h.hexdigest(), out


def main(a: str, b: str) -> dict:
    sa, ma = members(a)
    sb, mb = members(b)
    diff = {}
    for k in sorted(set(ma) & set(mb)):
        fields = {f: [ma[k][f], mb[k][f]] for f in ma[k] if ma[k][f] != mb[k].get(f)}
        if fields:
            diff[k[-90:]] = fields
    return {"a_tar_sha256": sa, "b_tar_sha256": sb, "n_a": len(ma), "n_b": len(mb),
            "only_a": [k[-90:] for k in sorted(set(ma) - set(mb))],
            "only_b": [k[-90:] for k in sorted(set(mb) - set(ma))], "differ": diff}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1))
