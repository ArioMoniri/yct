#!/usr/bin/env python3
"""D-087 (p4b_ref/v2) pod driver of the pre-build localiser screen (council cycle 1, B3).

  python scripts/locscreen_v2.py MODEL_DIR SCRATCH [--sources DIR] [--local DIR ...] [--yunet-onnx PATH]
  python scripts/locscreen_v2.py smoke MODEL_DIR SCRATCH --out JSON [--sources DIR] [--yunet-onnx PATH]

Refuses until controls.refclips_d087 is frozen. One invocation:
1. Requires the three v4 logs (and any continuation record) to be committed at HEAD: the continuation is
   audited and committed before the screen ever re-runs (council: committed_before_rescreen).
2. Candidates = the passes of each v4 log in log order (locscreen.pass_candidates).
3. locscreen.select with the real pieces: locimg.patch on the sha-verified source (refclips_build
   .fetch_sources), joint locimg.shine(controls.refclips.shine) over all 60, the rendered patches the builder
   draws (locscreen.rendered_loc_patches: intact, scramble, swap), the sha-pinned T-LIC YuNet, the frozen
   gate (locscreen.gate_from_cfg) and the round-0 pre-exclusion (controls.refclips_d087.pre_excluded).
4. NeedMorePasses(cat, n): more than continuation.max_extra_per_category extra passes -> final STOP. Else
   the v4 filter continuation runs (refstim_auto_run.py run ... --target cat=n); the log must keep every
   existing byte (append only) and reach n passes (else: snapshot exhausted -> final STOP). A continuation
   record is written and the driver exits 75: commit the appended log + record, then re-run (from round 1).
5. ScreenStop (still flagged after max_rounds): STOP_NOTE, final STOP to the owner (no v3).
6. Success: writes the v2 manifests (controls.refclips_d087.manifests; s3_key under sources/images/<cat>/v2/,
   so no v1 key is ever touched) and the screen record (controls.refclips_d087.screen_record: rounds, flags,
   replacements, descriptive face detections, face_absent, per-slot patch_sha256, inputs). Prints the v2
   manifest sha; the shas are set in config in one commit and frozen in the next.
The screen never sees a built clip frame (D-085 C1).

smoke (D-087 v2 re-check, a freeze precondition; outcome-blind, needs no freeze, writes nothing under
data/refstim and nothing to S3): (a) every source the screen can reach (all logged passes of the three v4
logs) loads and sha-checks through the real loader; (b) on the known v1 selection, the real locimg.patch +
joint SHINE equal locimg.loc_images and rendered_loc_patches equal refclips58.loc_frames pixel for pixel
(180 entries); (c) the sha-pinned T-LIC YuNet reproduces the logged T-LIC counts on non-candidate reject rows
(face F1, place P2) and finds nothing on a uniform grey patch through to_bgr640; YuNet is never called on a
slot or candidate patch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.tribe_run import locscreen as L  # noqa: E402,N812

CONT_REC = "data/refstim/loc_screen_v2_continuation.json"
STOP_DIR = "outputs/runs/refclips_v2_screen"
DEFAULT_RENDER = object()


def log_path(root: Path, cat: str) -> Path:
    return root / "data" / "refstim" / f"image_{cat}_auto_log_v4.jsonl"


def read_rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def v2_row(cat: str, k: int, cand: dict) -> dict:
    r = cand["row"]
    # smoke finding: the Commons url carries a ?utm_... query string; the suffix comes from the url path only
    fname = f"{cat}_v2_{k:02d}_r{cand['rank']:04d}{Path(urlparse(str(r.get('url', ''))).path).suffix.lower()}"
    return {"file": fname, "category": cat, "slot": k, "rank": cand["rank"], "title": cand["title"],
            "url": r.get("descriptionurl"), "download_url": r.get("url"), "pageid": r.get("pageid"),
            "revid": r.get("revid"), "snapshot_revid": r.get("snapshot_revid"), "licence": r.get("licence"),
            "licence_template": r.get("licence_template"), "artist": r.get("artist"),
            "credit": r.get("credit"),
            "sha256": r.get("source_sha256"), "crop_box": r.get("crop_box"), "source": r.get("source"),
            "s3_key": f"sources/images/{cat}/v2/{fname}"}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _stop(root: Path, msg: str) -> None:
    d = root / STOP_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "STOP_NOTE.md").write_text(f"# p4b_ref/v2 D-087 screen: final STOP to the owner (no v3)\n- {msg}\n")
    raise SystemExit(f"{msg}: final STOP to the owner")


def run_screen(cfg: dict, root: Path, patch_of: Callable, shine_fn: Callable, yunet: Callable,
               continuation: Callable[[str, int], None], committed: Callable[[list[Path]], bool],
               to_bgr: Callable | None = None, render=DEFAULT_RENDER, versions: dict | None = None) -> int:
    L.require_frozen(cfg)
    d = cfg["controls"]["refclips_d087"]
    rc = cfg["controls"]["refclips"]
    cats, n = list(rc["loc_categories"]), int(rc["loc_per_category"])
    logs = [log_path(root, c) for c in cats]
    tracked = logs + ([root / CONT_REC] if (root / CONT_REC).exists() else [])
    if not committed(tracked):
        raise SystemExit("commit the v4 logs and the continuation record before the screen re-runs")
    rows = {c: read_rows(log_path(root, c)) for c in cats}
    cands = {c: L.pass_candidates(rows[c], c) for c in cats}
    s = d["screen"]
    if render is DEFAULT_RENDER:
        def render(by_cat, slots):
            return L.rendered_loc_patches(by_cat, cfg)
    kw = {} if to_bgr is None else {"to_bgr": to_bgr}
    try:
        res = L.select(cands, n, patch_of, shine_fn, yunet, thr=float(s["score_threshold"]),
                       long_side=int(s["input_long_side"]), max_rounds=int(s["max_rounds"]), cats=cats,
                       render=render, gate=L.gate_from_cfg(cfg),
                       pre_excluded=[p["title"] for p in d["pre_excluded"]], **kw)
    except L.NeedMorePasses as e:
        extra, cap = e.n_passes - n, int(d["continuation"]["max_extra_per_category"])
        if extra > cap:
            _stop(root, f"{e.category}: {extra} extra passes > the continuation cap {cap}")
        p = log_path(root, e.category)
        old = p.read_bytes()
        continuation(e.category, e.n_passes)
        new = p.read_bytes()
        if not new.startswith(old):
            raise SystemExit(f"{p.name}: the continuation did not keep the existing rows byte-identical"
                             ) from None
        got = sum(r["decision"] == "pass" for r in read_rows(p))
        if got < e.n_passes:
            _stop(root, f"{e.category}: snapshot exhausted at {got} passes (< {e.n_passes})")
        rec = {"category": e.category, "target": e.n_passes, "passes": got, "prefix_identical": True,
               "old_sha256": _sha(old), "new_sha256": _sha(new), "old_bytes": len(old),
               "new_rows": len(read_rows(p)) - len(old.splitlines())}
        (root / CONT_REC).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(f"continuation {e.category} -> {e.n_passes} passes; commit the log + {CONT_REC}, then re-run",
              flush=True)
        return 75
    except L.ScreenStop as e:
        _stop(root, str(e))
    mans = {c: [v2_row(c, k, cand) for k, cand in enumerate(res["slots"][c])] for c in cats}
    blob = b""
    for c in cats:
        p = root / d["manifests"][c]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(mans[c], indent=1, ensure_ascii=False) + "\n")
        blob += p.read_bytes()
    record = {"decision": "D-087", "redesign": "p4b_ref/v2", "rounds": res["rounds"],
              "replacements": res["replacements"], "excluded": res["excluded"],
              "max_consumed_rank": res["max_consumed_rank"], "face_absent": res["face_absent"],
              "round_log": res["round_log"], "patch_sha256": res["patch_sha256"],
              "slots": {c: [{"title": r["title"], "rank": r["rank"]} for r in res["slots"][c]] for c in cats},
              "inputs": {**{c: _sha(log_path(root, c).read_bytes()) for c in cats},
                         **({"toolchain": versions} if versions is not None else {})},
              "image_manifest_v2_sha256": _sha(blob)}
    (root / d["screen_record"]).write_text(json.dumps(record, indent=1, sort_keys=True, default=float) + "\n")
    print("image_manifest_v2_sha256", _sha(blob))
    print("screen_record_sha256", _sha((root / d["screen_record"]).read_bytes()))
    return 0


DEFAULT_LOCAL = Path("/work/yct/refstim_auto_scratch")


def local_dirs(local: list[Path] | None, scratch: Path) -> list[Path]:
    """--local default plus the continuation SCRATCH (council re-check: appended passes must resolve)."""
    out = list(local) if local is not None else [DEFAULT_LOCAL]
    return out + ([scratch] if scratch not in out else [])


def _ffmpeg_line() -> str:
    return subprocess.run(["ffmpeg", "-nostdin", "-version"], capture_output=True, text=True,
                          check=True).stdout.splitlines()[0]


def versions(ffmpeg: Callable[[], str] = _ffmpeg_line) -> dict[str, str]:
    """cv2, onnxruntime and ffmpeg of the screen run (biostat re-check (c)); recorded in the screen record."""
    import importlib.metadata

    import cv2
    try:
        ort = importlib.metadata.version("onnxruntime")
    except importlib.metadata.PackageNotFoundError:
        ort = "not installed (cv2.dnn runs the onnx)"
    return {"cv2": cv2.__version__, "onnxruntime": ort, "ffmpeg": ffmpeg()}


# ---------------------------------------------------------------- smoke (outcome-blind, pre-freeze)
def smoke_sources(rows: dict[str, list[dict]], load: Callable[[dict], object]) -> dict[str, dict[str, int]]:
    """(a): every logged pass of every v4 log loads and sha-checks (load raises otherwise)."""
    out = {}
    for c, rs in rows.items():
        cands = L.pass_candidates(rs, c)
        for cand in cands:
            load(v2_row(c, 0, cand))
        out[c] = {"passes": len(cands), "loaded": len(cands)}
    return out


def smoke_render(cfg: dict, mans: dict[str, list[dict]], rows: dict[str, list[dict]],
                 load_v1: Callable[[dict], object], load_cand: Callable[[dict], object],
                 max_clips: int | None = None) -> dict:
    """(b): on the v1 selection (known from build 1), the screen's real patch path equals the builder's.
    max_clips limits the loc_frames comparison (unit tests only; the pod smoke checks every LOC clip)."""
    import numpy as np

    from yct.tribe_run import locimg
    from yct.tribe_run import refclips58 as R  # noqa: N812

    rc = cfg["controls"]["refclips"]
    cats, n = list(rc["loc_categories"]), int(rc["loc_per_category"])
    picked = []
    for c in cats:
        by = {cand["row"].get("source_sha256"): cand for cand in L.pass_candidates(rows[c], c)}
        for r in mans[c]:
            if r["sha256"] not in by:
                raise SystemExit(f"v1 {c} image {r['title']!r} is not a v4 pass (by source sha256)")
            picked.append(by[r["sha256"]])
    proc = locimg.shine([locimg.patch(load_cand(cand), cand["row"]["crop_box"]) for cand in picked],
                        rc["shine"])
    by_cat = {c: proc[j * n:(j + 1) * n] for j, c in enumerate(cats)}
    ref = locimg.loc_images(mans, load_v1, cfg)
    for c in cats:
        for k in range(n):
            a, b = by_cat[c][k], ref[c][k]
            if a.shape != b.shape or a.dtype != b.dtype or not np.array_equal(a, b):
                raise SystemExit(f"smoke (b): {c} slot {k} differs from locimg.loc_images")
    ents = L.rendered_loc_patches(by_cat, cfg)
    y0, x0 = (R.H - R.PATCH) // 2, (R.W - R.PATCH) // 2
    plan = R.plan(cfg)
    locs = [c for c in plan if c.family == "LOC"]
    checked = locs if max_clips is None else locs[:max_clips]
    for clip in checked:
        twin = next(c for c in plan if c.family == "LOC_SCR" and c.i == clip.i)
        fr, fr2 = R.loc_frames(clip, by_cat), R.loc_frames(twin, by_cat)
        nfr = len(fr)
        for e in clip.events:
            mine = {x["kind"]: x["patch"] for x in ents if x["clip"] == clip.name and x["k"] == e["k"]}
            t_in = int((e["onset"] + 0.5) * R.FPS)
            seg = next(m for m in range(nfr) if R._in_event(m / R.FPS, clip) is None
                       and R._segment(m / R.FPS, clip) == e["k"])
            for kind, f in (("intact", fr[t_in]), ("swap", fr2[t_in]), ("scramble", fr[seg])):
                if not np.array_equal(mine[kind], f[y0:y0 + R.PATCH, x0:x0 + R.PATCH]):
                    raise SystemExit(f"smoke (b): {clip.name} k={e['k']} {kind} differs from loc_frames")
        del fr, fr2
    p0 = ents[0]["patch"]
    return {"n_entries": len(ents), "n_loc_clips": len(locs), "n_clips_checked_vs_loc_frames": len(checked),
            "shape": list(p0.shape), "dtype": str(p0.dtype), "equal_to_loc_images": True,
            "equal_to_loc_frames": True,
            "v1_patch_sha256": {c: [L.patch_sha(p) for p in by_cat[c]] for c in cats}}


def smoke_yunet(cfg: dict, rows: dict[str, list[dict]], load_reject: Callable[[str, dict], object],
                yunet: Callable, n_face: int = 3) -> dict:
    """(c): the driver's sha-pinned T-LIC YuNet reproduces the logged T-LIC counts on non-candidate reject
    rows (T-LIC input: the full decoded image, ra.resize_long to the long side, BGR) and finds no face on a
    uniform grey patch through to_bgr640. Never called on a pass (slot or candidate) image."""
    import numpy as np

    from yct.curate.refstim_auto import resize_long
    from yct.tribe_run.refclips_qc85 import to_bgr640

    fd = cfg["controls"]["refclips_auto"]["face_detector"]
    picks = ([("face", r, "yunet_n", fd["score_threshold"]) for r in rows.get("face", [])
              if r["decision"] == "reject" and r.get("rule") == "F1"][:n_face] +
             [("place", r, "yunet_n_excl", fd["exclusion_score_threshold"]) for r in rows.get("place", [])
              if r["decision"] == "reject" and r.get("rule") == "P2"])
    out = []
    for cat, r, key, thr in picks:
        if r["decision"] != "reject":
            raise SystemExit("smoke (c): YuNet only on reject rows")
        rgb = np.asarray(load_reject(cat, r))
        b640, _ = resize_long(np.ascontiguousarray(rgb[..., ::-1]), fd["input_long_side"])
        got, want = len(yunet(b640, thr)), int(r["values"][key])
        out.append({"category": cat, "rule": r["rule"], "reason": r["reason"], "title": r["title"],
                    "logged": want, "got": got, "threshold": thr, "match": got == want})
    bad = [o for o in out if not o["match"]]
    if bad:
        raise SystemExit(f"smoke (c): YuNet does not reproduce the logged T-LIC counts: {bad}")
    grey = np.full((316, 316), 128, np.uint8)
    thr = float(cfg["controls"]["refclips_d087"]["screen"]["score_threshold"])
    nd = len(yunet(to_bgr640(grey, 640), thr))
    if nd:
        raise SystemExit(f"smoke (c): {nd} YuNet detections on a uniform grey patch")
    return {"rows": out, "grey_patch_detections": nd}


def _git_committed(paths: list[Path]) -> bool:
    for p in paths:
        rel = str(p.relative_to(ROOT))
        if subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode != 0:
            return False
        if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", rel]).returncode != 0:
            return False
    return True


def smoke_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="locscreen_v2.py smoke")
    ap.add_argument("model_dir", type=Path)
    ap.add_argument("scratch", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sources", type=Path, default=Path("/work/yct/refclips_sources_smoke"))
    ap.add_argument("--local", type=Path, nargs="*", default=None)
    ap.add_argument("--yunet-onnx", type=Path,
                    default=Path("/work/yct/refstim_models/face_detection_yunet_2023mar.onnx"))
    a = ap.parse_args(argv)
    import importlib.util

    import cv2

    from yct.curate import refstim as rs
    from yct.tribe_run import refclips_qc85

    cfg = load_config()
    refstim_dir = ROOT / "data" / "refstim"
    before = {p: _sha(p.read_bytes()) for p in sorted(refstim_dir.rglob("*")) if p.is_file()}
    spec = importlib.util.spec_from_file_location("refclips_build", ROOT / "scripts" / "refclips_build.py")
    bld = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bld)
    cats = list(cfg["controls"]["refclips"]["loc_categories"])
    rows = {c: read_rows(log_path(ROOT, c)) for c in cats}
    local = local_dirs(a.local, a.scratch)
    load = bld.fetch_sources({}, cfg, a.sources, local=local, upload=False)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    res: dict = {"decision": "D-087 smoke", "local": [str(x) for x in local], "versions": versions(),
                 "run_commit": head}
    res["a_sources"] = smoke_sources(rows, load)
    print("smoke (a) ok", res["a_sources"], flush=True)
    mans = {c: json.loads((refstim_dir / f"image_{c}_manifest.json").read_text()) for c in cats}
    load_v1 = bld.fetch_sources(mans, cfg, a.sources, local=local, upload=False)
    res["b_render"] = smoke_render(cfg, mans, rows, load_v1,
                                   lambda cand: load(v2_row(cand["category"], 0, cand)))
    print("smoke (b) ok", res["b_render"]["n_entries"], flush=True)
    yunet = refclips_qc85.t_lic_yunet(cfg, a.yunet_onnx)

    def load_reject(cat: str, r: dict):
        hits = sorted((a.scratch / cat).glob(f"{rs.title_key(r['title'])[:16]}.*"))
        if not hits:
            raise SystemExit(f"smoke (c): no scratch file for reject {r['title']!r}")
        b = hits[0].read_bytes()
        if hashlib.sha1(b).hexdigest() != r["sha1"]:   # noqa: S324 - the Commons identity is sha1
            raise SystemExit(f"smoke (c): scratch file sha1 differs for {r['title']!r}")
        bgr = cv2.imread(str(hits[0]), cv2.IMREAD_COLOR)
        if bgr is None:
            raise SystemExit(f"smoke (c): decode failed for {r['title']!r}")
        return bgr[..., ::-1]
    res["c_yunet"] = smoke_yunet(cfg, rows, load_reject, yunet)
    print("smoke (c) ok", flush=True)
    after = {p: _sha(p.read_bytes()) for p in sorted(refstim_dir.rglob("*")) if p.is_file()}
    if after != before:
        raise SystemExit("smoke wrote under data/refstim")
    res["data_refstim_unchanged"] = True
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1, sort_keys=True, default=float) + "\n")
    print("smoke ok", a.out, flush=True)
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        return smoke_main(sys.argv[2:])
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir", type=Path)
    ap.add_argument("scratch", type=Path)
    ap.add_argument("--sources", type=Path, default=Path("/work/yct/refclips_sources_v2"))
    ap.add_argument("--local", type=Path, nargs="*", default=None)   # None: DEFAULT_LOCAL; SCRATCH added
    ap.add_argument("--yunet-onnx", type=Path,
                    default=Path("/work/yct/refstim_models/face_detection_yunet_2023mar.onnx"))
    a = ap.parse_args()
    cfg = load_config()
    L.require_frozen(cfg)
    import importlib.util

    from yct.tribe_run import locimg, refclips_qc85

    spec = importlib.util.spec_from_file_location("refclips_build", ROOT / "scripts" / "refclips_build.py")
    bld = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bld)
    rc = cfg["controls"]["refclips"]
    cats = list(rc["loc_categories"])
    rows = {c: read_rows(log_path(ROOT, c)) for c in cats}
    srcrows = {c: [v2_row(c, 0, cand) for cand in L.pass_candidates(rows[c], c)] for c in cats}
    # watchdog re-check: no upload during the screen (slot-0 keys would be orphans); the builder uploads each
    # final v2 source to its manifest s3_key
    load = bld.fetch_sources(srcrows, cfg, a.sources, local=local_dirs(a.local, a.scratch), upload=False)

    def patch_of(cand: dict):
        return locimg.patch(load(v2_row(cand["category"], 0, cand)), cand["row"]["crop_box"])

    def continuation(cat: str, n: int) -> None:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "refstim_auto_run.py"), "run",
                        str(a.model_dir), str(a.scratch), "--target", f"{cat}={n}"], check=True)

    yunet = refclips_qc85.t_lic_yunet(cfg, a.yunet_onnx)
    return run_screen(cfg, ROOT, patch_of, lambda ims: locimg.shine(ims, rc["shine"]), yunet, continuation,
                      _git_committed, versions=versions())


if __name__ == "__main__":
    sys.exit(main())
