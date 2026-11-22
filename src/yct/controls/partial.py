"""P4b (a) partial correlation with the D-071 (a) nuisance set, amended by D-086 (owner Q1, R-11 A-18).

partial_r(y, x, others, terms) = corr of the residuals of y and x after OLS on
[nuisance_design(n, terms) | others]. D-071 (a) froze "plus an intercept"; D-086 adds one Legendre
order-1 drift column (config controls.partial_out_nuisance = [intercept, legendre_1]) before any reference
output exists. It is never extended after a FAIL. Fails closed on non-finite input or a rank-deficient design.
"""
from __future__ import annotations

import numpy as np

TERMS = ("intercept", "legendre_1")


def nuisance_design(n: int, terms: list[str]) -> np.ndarray:
    """(n, len(terms)) columns over the n TRs: intercept = 1, legendre_1 = P1 on [-1, 1] (linear drift)."""
    bad = [t for t in terms if t not in TERMS]
    if bad:
        raise ValueError(f"unknown nuisance term(s) {bad}; allowed {TERMS}")
    t = np.linspace(-1.0, 1.0, n)
    cols = {"intercept": np.ones(n), "legendre_1": t}
    return np.column_stack([cols[k] for k in terms]) if terms else np.zeros((n, 0))


def partial_r(y: np.ndarray, x: np.ndarray, others: np.ndarray, terms: list[str]) -> float:
    y, x = np.asarray(y, float).ravel(), np.asarray(x, float).ravel()
    n = y.size
    o = np.asarray(others, float).reshape(n, -1)
    if x.size != n:
        raise ValueError("y and x lengths differ")
    if not (np.isfinite(y).all() and np.isfinite(x).all() and np.isfinite(o).all()):
        raise ValueError("non-finite input to partial_r")
    nmat = np.column_stack([nuisance_design(n, terms), o])
    full = np.column_stack([nmat, x])
    if np.linalg.matrix_rank(full) < full.shape[1]:
        raise ValueError("rank-deficient partial-out design (target collinear with nuisance)")

    def res(v):
        return v - nmat @ np.linalg.lstsq(nmat, v, rcond=None)[0]
    ry, rx = res(y), res(x)
    if ry.std() == 0 or rx.std() == 0:
        raise ValueError("zero residual variance in partial_r")
    return float(np.corrcoef(ry, rx)[0, 1])
