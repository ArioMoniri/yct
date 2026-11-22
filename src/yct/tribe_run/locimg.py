"""T-REF58 LOC image processing (D-071 (b) Processing; config controls.refclips.greyscale / .shine).

patch(): the frozen manifest crop_box (x, y, side) -> BT.709 luma on the gamma-encoded values (the T-LIC
grey709, rounded to uint8) -> cv2 INTER_AREA to the 316-px stimulus patch (the T-LIC "processed" image
uses the same crop, luma and interpolation at 256 px).

shine(): SHINE-style matching over ALL images jointly (not within category), in the configured step order,
`iterations` times:
  specMatch: every image keeps its own Fourier phase and gets the mean amplitude spectrum of the set
             (DC excluded from the target and restored afterwards, so luminance is left to lumMatch);
  lumMatch:  every image is set to the target mean luma and RMS contrast (population SD).
Each step ends on the uint8 grid (round + clip), as the SHINE toolbox writes 8-bit images. Interpretation
choices (DC handling, per-step quantisation) are reported to the council; they are fixed here a priori.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from yct.tribe_run.refclips58 import PATCH

STEPS = ("specMatch", "lumMatch")


def grey709(rgb: np.ndarray) -> np.ndarray:
    return ((0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
            .round().clip(0, 255).astype(np.uint8))


def patch(rgb: np.ndarray, box) -> np.ndarray:
    import cv2

    x, y, s = (int(v) for v in box)
    h, w = rgb.shape[:2]
    if x < 0 or y < 0 or s <= 0 or x + s > w or y + s > h:
        raise ValueError(f"crop_box {box} outside the {w}x{h} image")
    g = grey709(rgb[y:y + s, x:x + s])
    return cv2.resize(g, (PATCH, PATCH), interpolation=cv2.INTER_AREA)


def _q(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(x), 0, 255)


def _spec_match(ims: list[np.ndarray]) -> list[np.ndarray]:
    ffts = [np.fft.fft2(x) for x in ims]
    target = np.mean([np.abs(f) for f in ffts], axis=0)
    out = []
    for f in ffts:
        g = target * np.exp(1j * np.angle(f))
        g[0, 0] = f[0, 0]                    # keep each image's own DC (mean luminance)
        out.append(_q(np.real(np.fft.ifft2(g))))
    return out


def _lum_match(ims: list[np.ndarray], mean: float, rms: float) -> list[np.ndarray]:
    out = []
    for x in ims:
        sd = x.std()
        if sd == 0:
            raise ValueError("lumMatch on a flat image")
        out.append(_q((x - x.mean()) / sd * rms + mean))
    return out


def shine(ims: list[np.ndarray], sh: dict) -> list[np.ndarray]:
    steps = list(sh["steps"])
    if not steps or any(s not in STEPS for s in steps):
        raise ValueError(f"unknown SHINE steps {steps}")
    if len({x.shape for x in ims}) != 1:
        raise ValueError("SHINE needs equal-size images")
    cur = [np.asarray(x, np.float64) for x in ims]
    for _ in range(int(sh["iterations"])):
        for s in steps:
            if s == "specMatch":
                cur = _spec_match(cur)
            else:
                cur = _lum_match(cur, sh["mean_luma"], sh["rms_contrast"])
    return [c.astype(np.uint8) for c in cur]


def loc_images(manifests: dict[str, list[dict]], load_rgb: Callable[[dict], np.ndarray], cfg: dict
               ) -> dict[str, list[np.ndarray]]:
    """{category: [20 processed uint8 patches]} in manifest order, SHINE applied to all 60 jointly
    (loc_categories order). load_rgb(row) returns the sha-verified source image as RGB uint8."""
    rc = cfg["controls"]["refclips"]
    cats, n = list(rc["loc_categories"]), int(rc["loc_per_category"])
    rows = []
    for c in cats:
        m = manifests[c]
        if len(m) != n or any(r["category"] != c for r in m):
            raise ValueError(f"{c}: manifest must hold {n} rows of that category")
        rows += m
    out = shine([patch(load_rgb(r), r["crop_box"]) for r in rows], rc["shine"])
    return {c: out[k * n:(k + 1) * n] for k, c in enumerate(cats)}
