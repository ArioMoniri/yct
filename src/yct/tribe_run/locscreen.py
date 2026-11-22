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
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

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


def select(candidates: dict[str, list[dict]], n: int, patch_of: Callable[[dict], np.ndarray],
           shine_fn: Callable[[list[np.ndarray]], list[np.ndarray]], yunet: Callable, thr: float,
           long_side: int, max_rounds: int, cats: Sequence[str],
           to_bgr: Callable = to_bgr640, screen_cats: Sequence[str] | None = None) -> dict[str, Any]:
    order = {c: list(candidates[c]) for c in cats}      # never mutated; rank order as logged
    for c in cats:
        if any(a["rank"] >= b["rank"] for a, b in zip(order[c], order[c][1:], strict=False)):
            raise ValueError(f"{c}: candidates are not in strictly increasing rank order")
        if len(order[c]) < n:
            raise NeedMorePasses(c, n)
    slots = {c: order[c][:n] for c in cats}
    nxt = {c: n for c in cats}
    excluded: list[str] = []
    repl: list[dict] = []
    log: list[dict] = []
    for rnd in range(1, max_rounds + 1):
        flat = [r for c in cats for r in slots[c]]
        processed = shine_fn([patch_of(r) for r in flat])
        scores = screen(processed, yunet, thr, long_side, to_bgr)
        gate = set(cats if screen_cats is None else screen_cats)
        flagged = [(i, s) for i, s in enumerate(scores) if s and cats[i // n] in gate]
        log.append({"round": rnd, "images": [r["title"] for r in flat],
                    "flagged": [{"title": flat[i]["title"], "scores": s} for i, s in flagged],
                    "descriptive": [{"title": flat[i]["title"], "scores": s} for i, s in enumerate(scores)
                                    if s and cats[i // n] not in gate]})
        if not flagged:
            consumed = {c: max([r["rank"] for r in slots[c]] +
                               [r["rank"] for r in order[c] if r["title"] in excluded]) for c in cats}
            return {"rounds": rnd, "slots": slots, "replacements": repl, "excluded": excluded,
                    "max_consumed_rank": consumed, "round_log": log}
        if rnd == max_rounds:
            raise ScreenStop(f"D-087 screen: still flagged after {max_rounds} rounds "
                             f"({[flat[i]['title'] for i, _ in flagged]}): final STOP to the owner")
        for i, s in flagged:
            c, k = cats[i // n], i % n
            if nxt[c] >= len(order[c]):
                raise NeedMorePasses(c, nxt[c] + 1)
            out, new = slots[c][k], order[c][nxt[c]]
            nxt[c] += 1
            excluded.append(out["title"])
            slots[c] = slots[c][:k] + [new] + slots[c][k + 1:]
            repl.append({"round": rnd, "category": c, "slot": k, "out": out["title"], "in": new["title"],
                         "scores": s})
    raise AssertionError("unreachable")
