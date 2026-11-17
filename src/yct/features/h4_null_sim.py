"""P5b H4 null-size check for the D-037 Q(M0) span (v2.md §5 P5b; DECISIONS D-037; Biostat G-D032 c2 B3).

Scenario "a term that is NOT in Q drives both M1 and y" (Biostat c2: FPR 0.285 at N = 40 under the
withdrawn D-036 rule). The synthetic outcome depends on M0 only, so TRIBE adds nothing beyond the
stimulus features; but if the driving term g(M0) is outside the span of Q(M0), residualising M1 on Q
leaves g in R and the H4 permutation test rejects. The conditional permutation is valid only up to
the span Q actually contains, so P5b reports, at the final N and final Q:

* ``included_term`` -- g = the last term inside Q (an optional term, else a forced speech quadratic):
  the size must be nominal;
* ``dropped_term``  -- g = the first fixed-order optional term NOT in Q: the "size outside the span".
  The report names this exact span as the meaning of "beyond M0" (v2.5).

Everything here is synthetic and label-free with respect to the study (no real labels are read). The
ΔAUC is the out-of-fold AUC difference AUC(M0 + R) - AUC(M0) of an L2-logistic model (fixed C; the
production pipeline nests C), R rows permuted within era blocks, p = (b + 1) / (B + 1). The fast
version (small B, few replicates) runs in the test-suite; the P5b run uses 500 replicates, B = 500.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from yct.features import m0 as m0m


def _logistic_fit(x: np.ndarray, y: np.ndarray, lam: float = 1.0, iters: int = 30) -> np.ndarray:
    """L2-penalised logistic regression (intercept unpenalised) by Newton's method."""
    x1 = np.column_stack([np.ones(len(x)), x])
    w = np.zeros(x1.shape[1])
    pen = lam * np.eye(len(w))
    pen[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(x1 @ w, -30, 30)))
        grad = x1.T @ (p - y) + pen @ w
        hess = (x1 * (p * (1 - p))[:, None]).T @ x1 + pen + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def auc(score: np.ndarray, y: np.ndarray) -> float:
    """Mann-Whitney AUC (ties averaged)."""
    r = pd.Series(score).rank().to_numpy()
    n1 = float(y.sum())
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def stratified_folds(y: np.ndarray, rng: np.random.Generator, k: int = 5,
                     repeats: int = 1) -> list[np.ndarray]:
    out = []
    for _ in range(repeats):
        f = np.empty(len(y), int)
        for c in (0, 1):
            idx = np.flatnonzero(y == c)
            rng.shuffle(idx)
            f[idx] = np.arange(len(idx)) % k
        out.append(f)
    return out


def cv_auc(x: np.ndarray, y: np.ndarray, folds: list[np.ndarray], lam: float = 1.0) -> float:
    """Mean over repeats of the pooled out-of-fold AUC (features standardised within the training fold)."""
    vals = []
    for f in folds:
        s = np.empty(len(y))
        for k in np.unique(f):
            te = f == k
            tr = ~te
            mu = x[tr].mean(0)
            sd = x[tr].std(0)
            sd[sd == 0] = 1.0
            w = _logistic_fit((x[tr] - mu) / sd, y[tr], lam)
            s[te] = np.column_stack([np.ones(te.sum()), (x[te] - mu) / sd]) @ w
        vals.append(auc(s, y))
    return float(np.mean(vals))


def synthetic_m0(n: int, rng: np.random.Generator, n_era: int = 3,
                 cfg: dict[str, Any] | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """Correlated synthetic M0 with the frozen feature names + ``voiced_any``, and era strata."""
    feats = m0m.m0_feature_list(cfg)
    p = len(feats)
    mix = rng.normal(size=(p, p)) * 0.5 + np.eye(p)
    df = pd.DataFrame(rng.normal(size=(n, p)) @ mix, columns=feats)
    df[m0m.VOICED] = (rng.uniform(size=n) > 0.15).astype(float)
    era = pd.Series(np.array([f"E{i + 1}" for i in range(n_era)])[rng.permutation(np.arange(n) % n_era)])
    return df, era


def _term(plan: m0m.QPlan, scenario: str) -> str:
    if scenario == "dropped_term":
        if not plan.excluded_terms:
            raise ValueError("every candidate term is in Q: no term outside the span at this N")
        return plan.excluded_terms[0]
    if scenario == "included_term":
        return plan.optional[-1] if plan.optional else plan.forced_quadratic[0]
    raise ValueError(f"unknown scenario {scenario!r}")


def _term_values(plan: m0m.QPlan, term: str, ddof: int = 0) -> np.ndarray:
    x = plan.m0_used
    if "*" in term:
        a, b = term.split("*")
        return m0m.zscore(x[[a]].to_numpy(), ddof)[:, 0] * m0m.zscore(x[[b]].to_numpy(), ddof)[:, 0]
    c = term.removesuffix("^2")
    return m0m.zscore(x[[c]].to_numpy(), ddof)[:, 0] ** 2


@dataclass
class NullSimResult:
    scenario: str
    n: int
    term: str
    term_in_q: bool
    q_columns: list[str]
    p_values: np.ndarray
    alpha: float

    @property
    def fpr(self) -> float:
        return float((self.p_values <= self.alpha).mean())

    @property
    def mc_se(self) -> float:
        return float(np.sqrt(self.fpr * (1 - self.fpr) / len(self.p_values)))


def simulate_h4_null(n: int, scenario: str = "dropped_term", n_reps: int = 500, n_perm: int = 500,
                     seed: int = 0, k_m1: int = 7, m1_loading: float = 1.5, y_strength: float = 2.5,
                     repeats: int = 1, alpha: float = 0.05,
                     cfg: dict[str, Any] | None = None) -> NullSimResult:
    """H4 rejection rate when y and M1 are driven by one quadratic term of M0 (in or outside Q).

    Per replicate: synthetic M0 (frozen names) + era; Q = :func:`yct.features.m0.q_m0`; g = the chosen
    term (z-scored); M1 = m1_loading * g * u' + N(0, 1) noise (k_m1 columns); y ~ Bernoulli(logit(
    y_strength * g)); R = M1 residualised on Q; ΔAUC observed vs n_perm within-era row permutations
    of R; p = (b + 1) / (B + 1).
    """
    rng = np.random.default_rng(seed)
    pvals = []
    term = ""
    in_q = False
    cols: list[str] = []
    for _ in range(n_reps):
        m0, era = synthetic_m0(n, rng, cfg=cfg)
        plan = m0m.q_m0(m0, era=era, cfg=cfg)
        term = _term(plan, scenario)
        in_q = term in plan.columns
        cols = plan.columns
        g = m0m.zscore(_term_values(plan, term)[:, None])[:, 0]
        m1 = m1_loading * np.outer(g, rng.normal(size=k_m1)) + rng.normal(size=(n, k_m1))
        lin = g * y_strength
        y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-(lin - np.median(lin))))).astype(float)
        if min(y.sum(), n - y.sum()) < 8:
            y = (lin > np.median(lin)).astype(float)
        r = m0m.residualize(m1, plan.q)
        x0 = plan.q[:, [i for i, c in enumerate(plan.columns) if c in plan.linear]]   # M0, linear
        folds = stratified_folds(y, rng, repeats=repeats)
        a0 = cv_auc(x0, y, folds)
        obs = cv_auc(np.column_stack([x0, r]), y, folds) - a0
        e = era.to_numpy()
        b = 0
        for _ in range(n_perm):
            rp = r.copy()
            for lev in np.unique(e):
                idx = np.flatnonzero(e == lev)
                rp[idx] = r[rng.permutation(idx)]
            b += cv_auc(np.column_stack([x0, rp]), y, folds) - a0 >= obs
        pvals.append((b + 1) / (n_perm + 1))
    return NullSimResult(scenario=scenario, n=n, term=term, term_in_q=in_q, q_columns=cols,
                         p_values=np.asarray(pvals), alpha=alpha)
