#!/usr/bin/env python3
"""D-087 (p4b_ref/v2) pod driver of the pre-build localiser screen (council cycle 1, B3).

  python scripts/locscreen_v2.py MODEL_DIR SCRATCH [--sources DIR] [--yunet-onnx PATH]

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
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

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
    fname = f"{cat}_v2_{k:02d}_r{cand['rank']:04d}{Path(str(r.get('url', ''))).suffix.lower()}"
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
               to_bgr: Callable | None = None, render=DEFAULT_RENDER) -> int:
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
              "inputs": {c: _sha(log_path(root, c).read_bytes()) for c in cats},
              "image_manifest_v2_sha256": _sha(blob)}
    (root / d["screen_record"]).write_text(json.dumps(record, indent=1, sort_keys=True, default=float) + "\n")
    print("image_manifest_v2_sha256", _sha(blob))
    print("screen_record_sha256", _sha((root / d["screen_record"]).read_bytes()))
    return 0


def _git_committed(paths: list[Path]) -> bool:
    for p in paths:
        rel = str(p.relative_to(ROOT))
        if subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode != 0:
            return False
        if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", rel]).returncode != 0:
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir", type=Path)
    ap.add_argument("scratch", type=Path)
    ap.add_argument("--sources", type=Path, default=Path("/work/yct/refclips_sources_v2"))
    ap.add_argument("--local", type=Path, nargs="*", default=[Path("/work/yct/refstim_auto_scratch")])
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
    load = bld.fetch_sources(srcrows, cfg, a.sources, local=a.local)

    def patch_of(cand: dict):
        return locimg.patch(load(v2_row(cand["category"], 0, cand)), cand["row"]["crop_box"])

    def continuation(cat: str, n: int) -> None:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "refstim_auto_run.py"), "run",
                        str(a.model_dir), str(a.scratch), "--target", f"{cat}={n}"], check=True)

    yunet = refclips_qc85.t_lic_yunet(cfg, a.yunet_onnx)
    return run_screen(cfg, ROOT, patch_of, lambda ims: locimg.shine(ims, rc["shine"]), yunet, continuation,
                      _git_committed)


if __name__ == "__main__":
    sys.exit(main())
