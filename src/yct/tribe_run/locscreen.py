"""D-087 draft (p4b_ref/v2, the single D-071 (h) redesign): the pre-build post-SHINE YuNet screen of the
60 localiser images, with the slot replacement loop.

Rule (fixed before any v2 YuNet run, owner 2026-11-23 "Redesign v2"):
- Candidates: the passes of each category in the frozen v4 log order (rank = 1-based log row), extended by
  the v4 filter continuation (scripts/refstim_auto_run.py --target) under the same frozen rules.
- Start: slot k of each category holds the k-th pass (the v1 selection).
- Each round: the 60 slot images -> locimg.patch (done by patch_of) -> joint SHINE over all 60 in
  loc_categories order -> the frozen T-LIC YuNet (refclips_auto.face_detector, score >= the D-085 qc
  threshold) on every post-SHINE patch, resized as T-LIC (refclips_qc85.to_bgr640).
- Only categories in screen_cats gate (draft: body, place; a face patch is expected to carry a face, so
  its detections are recorded as descriptive); every flagged slot (category order, then slot order)
  gets the next unused pass of its category by rank; a flagged image never returns. A round with no
  flag ends the loop.
- At most max_rounds rounds: still flagged after the last -> ScreenStop (to the owner, final; no v3).
- Not enough logged passes -> NeedMorePasses(category, n): the driver runs the continuation to n passes
  and re-runs this loop from round 1 (deterministic: same inputs, same result).
The screen runs on rendered patches only, never on a built clip frame (D-085 C1).

D-087 v2 (council cycle 1 + owner rulings 2026-11-23):
- pre_excluded titles are replaced in their slot by the same rule in round 0, before any screen (owner
  "Pre-exclude place_14", disclosed as post_hoc).
- render(by_cat, slots) gives the rendered patches the builder will draw (rendered_loc_patches: the intact
  _u8(_norm(.)) patch and, per LOC event, its scramble and swap from the per-slot seeds); gate(entry)
  decides which detections replace a slot (make_gate: intact body/place, scramble and swap of every slot,
  face included). Detections outside the gate are recorded as descriptive; face_absent lists the face
  slots whose intact rendered patch has no detection (descriptive, never gating).
- The result carries patch_sha256 (per slot, the final-round post-SHINE patch), the identity the v2
  builder checks before any clip is built.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run.refclips_qc85 import to_bgr640

KEY = "controls.refclips_d087"


class ScreenStop(SystemExit):
    pass


class NeedMorePasses(Exception):  # noqa: N818
    def __init__(self, category: str, n_passes: int):
        super().__init__(f"{category}: need {n_passes} logged passes (v4 filter continuation)")
        self.category, self.n_passes = category, n_passes


def _frozen(cfg: dict, key: str) -> bool:
    return any(key == f.get("key") or key.startswith(f.get("key", "") + ".") for f in cfg.get("frozen", []))


def require_frozen(cfg: dict) -> None:
    if not _frozen(cfg, KEY):
        raise SystemExit(f"{KEY} is not frozen: the D-087 screen rule must be frozen before any v2 YuNet run")


def pass_candidates(rows: Sequence[dict], category: str) -> list[dict]:
    """The passes of one v4 log in log order; rank = 1-based row position in the log."""
    return [{"title": r["title"], "rank": i + 1, "category": category, "row": r}
            for i, r in enumerate(rows) if r["decision"] == "pass"]


def screen(patches: Sequence[np.ndarray], yunet: Callable, thr: float, long_side: int,
           to_bgr: Callable = to_bgr640) -> list[list[float]]:
    """Per image, the YuNet scores >= thr on the post-SHINE patch."""
    return [[float(f["score"]) for f in yunet(to_bgr(p, long_side), thr)] for p in patches]


def patch_sha(p: np.ndarray) -> str:
    a = np.ascontiguousarray(np.asarray(p, np.uint8))
    return hashlib.sha256(f"{a.shape[0]}x{a.shape[1]}:".encode() + a.tobytes()).hexdigest()


def make_gate(intact_cats: Sequence[str], scramble_kinds: Sequence[str], scramble_cats: Sequence[str]
              ) -> Callable[[dict], bool]:
    ic, sk, sc = set(intact_cats), set(scramble_kinds), set(scramble_cats)

    def gate(e: dict) -> bool:
        if e["kind"] == "intact":
            return e["category"] in ic
        return e["kind"] in sk and e["category"] in sc
    return gate


def gate_from_cfg(cfg: dict) -> Callable[[dict], bool]:
    s = cfg["controls"]["refclips_d087"]["screen"]
    return make_gate(s["categories"], s["scramble_kinds"], s["scramble_categories"])


def rendered_loc_patches(images: dict[str, list[np.ndarray]], cfg: dict) -> list[dict]:
    """The patches the builder draws (refclips58.loc_frames): per LOC clip and event, the intact patch
    _u8(_norm(img)), its scramble (scramble_seed, shown outside events in LOC and LOC_SCR) and its swap
    (swap_seed, shown at the LOC_SCR events). Seeds stay per slot (clip i, event k)."""
    out = []
    for clip in R.plan(cfg):
        if clip.family != "LOC":
            continue
        for e in clip.events:
            intact = R._norm(images[e["category"]][e["image"]].astype(np.float64))
            base = {"category": e["category"], "slot": e["image"], "clip": clip.name, "k": e["k"]}
            out.append({**base, "kind": "intact", "patch": R._u8(intact)})
            for kind, seed in (("scramble", e["scramble_seed"]), ("swap", e["swap_seed"])):
                out.append({**base, "kind": kind, "patch": R._u8(R.phase_scramble(intact, seed))})
    return out


def _intact_only(by_cat: dict, slots: dict) -> list[dict]:
    return [{"category": c, "slot": k, "kind": "intact", "clip": None, "k": None, "patch": p}
            for c, ps in by_cat.items() for k, p in enumerate(ps)]


def select(candidates: dict[str, list[dict]], n: int, patch_of: Callable[[dict], np.ndarray],
           shine_fn: Callable[[list[np.ndarray]], list[np.ndarray]], yunet: Callable, thr: float,
           long_side: int, max_rounds: int, cats: Sequence[str],
           to_bgr: Callable = to_bgr640, screen_cats: Sequence[str] | None = None,
           render: Callable | None = None, gate: Callable[[dict], bool] | None = None,
           pre_excluded: Sequence[str] = ()) -> dict[str, Any]:
    order = {c: list(candidates[c]) for c in cats}      # never mutated; rank order as logged
    for c in cats:
        if any(a["rank"] >= b["rank"] for a, b in zip(order[c], order[c][1:], strict=False)):
            raise ValueError(f"{c}: candidates are not in strictly increasing rank order")
        if len(order[c]) < n:
            raise NeedMorePasses(c, n)
    if gate is None:
        g = set(cats if screen_cats is None else screen_cats)

        def gate(e: dict) -> bool:
            return e["kind"] == "intact" and e["category"] in g
    render = render or _intact_only
    slots = {c: order[c][:n] for c in cats}
    nxt = {c: n for c in cats}
    excluded: list[str] = []
    repl: list[dict] = []
    log: list[dict] = []

    def replace(rnd: int, c: str, k: int, scores: list, reason: str | None = None,
                kinds: list | None = None) -> None:
        if nxt[c] >= len(order[c]):
            raise NeedMorePasses(c, nxt[c] + 1)
        out, new = slots[c][k], order[c][nxt[c]]
        nxt[c] += 1
        excluded.append(out["title"])
        slots[c] = slots[c][:k] + [new] + slots[c][k + 1:]
        r = {"round": rnd, "category": c, "slot": k, "out": out["title"], "in": new["title"],
             "scores": scores}
        if reason is not None:
            r["reason"] = reason
        if kinds is not None:
            r["kinds"] = kinds
        repl.append(r)

    for t in pre_excluded:                               # round 0 (owner "Pre-exclude place_14")
        hit = [(c, k) for c in cats for k, r in enumerate(slots[c]) if r["title"] == t]
        if not hit:
            raise ValueError(f"pre_excluded {t!r} is not among the slot images")
        replace(0, *hit[0], scores=[], reason="pre_excluded")
    for rnd in range(1, max_rounds + 1):
        flat = [r for c in cats for r in slots[c]]
        processed = shine_fn([patch_of(r) for r in flat])
        by_cat = {c: processed[j * n:(j + 1) * n] for j, c in enumerate(cats)}
        ents = render(by_cat, slots)
        flagged: dict[tuple[str, int], dict] = {}
        desc, face_hit = [], set()
        for e in ents:
            s = [float(f["score"]) for f in yunet(to_bgr(e["patch"], long_side), thr)]
            if not s:
                continue
            title = slots[e["category"]][e["slot"]]["title"]
            rec = ({"title": title, "scores": s} if render is _intact_only else   # the D-087 draft shape
                   {"title": title, "category": e["category"], "slot": e["slot"], "kind": e["kind"],
                    "clip": e["clip"], "k": e["k"], "scores": s})
            if e["kind"] == "intact" and e["category"] == "face":
                face_hit.add(e["slot"])
            if gate(e):
                f = flagged.setdefault((e["category"], e["slot"]), {"scores": [], "kinds": [], "hits": []})
                f["scores"] += s
                if e["kind"] not in f["kinds"]:
                    f["kinds"].append(e["kind"])
                f["hits"].append(rec)
            else:
                desc.append(rec)
        ordered = sorted(flagged, key=lambda ck: (list(cats).index(ck[0]), ck[1]))
        log.append({"round": rnd, "images": [r["title"] for r in flat],
                    "flagged": [h for ck in ordered for h in flagged[ck]["hits"]], "descriptive": desc})
        if not flagged:
            consumed = {c: max([r["rank"] for r in slots[c]] +
                               [r["rank"] for r in order[c] if r["title"] in excluded]) for c in cats}
            absent = ([slots["face"][k]["title"] for k in range(n) if k not in face_hit]
                      if "face" in cats else [])
            return {"rounds": rnd, "slots": slots, "replacements": repl, "excluded": excluded,
                    "max_consumed_rank": consumed, "round_log": log, "face_absent": absent,
                    "patch_sha256": {c: [patch_sha(p) for p in by_cat[c]] for c in cats}}
        if rnd == max_rounds:
            raise ScreenStop(f"D-087 screen: still flagged after {max_rounds} rounds "
                             f"({[slots[c][k]['title'] for c, k in ordered]}): final STOP to the owner")
        for c, k in ordered:
            f = flagged[(c, k)]
            replace(rnd, c, k, f["scores"], kinds=f["kinds"] if render is not _intact_only else None)
    raise AssertionError("unreachable")
