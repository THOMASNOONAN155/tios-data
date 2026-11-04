"""Factor adjustments on top of a base model's expected goals.

A factor is a set of pre-kickoff features. Goal features multiply expected goals:
    lambda_home' = lambda_home * exp(Xh @ beta),  lambda_away' = lambda_away * exp(Xa @ beta)
Draw features scale the draw cells of the scoreline grid by exp(Xd @ delta).
Coefficients are fitted by maximum likelihood on the tuning seasons only and then frozen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .evaluate import outcome
from .models import score_grid

# role: own = the side's own feature, opp = the opponent's, match = same value for both sides,
# home = applies to the home side only, shrink = early-season pull of both sides towards each other
FACTORS = {
    "rest_days":        {"goals": [("short_rest", "own"), ("short_rest", "opp")]},
    "rest_diff":        {"goals": [("rest_diff_h", "home")]},
    "euro_congestion":  {"goals": [("euro_before", "own"), ("euro_before", "opp"), ("euro_after", "own")]},
    "manager_change":   {"goals": [("new_mgr", "own"), ("new_mgr", "opp")]},
    "early_season":     {"goals": [("early", "shrink")]},
    "promoted_early":   {"goals": [("promoted_early", "own"), ("promoted_early", "opp")]},
    "derby":            {"goals": [("derby", "match")], "draw": ["derby"]},
    "motivation":       {"goals": [("ntp", "own"), ("ntp", "opp")], "draw": ["both_ntp"]},
    "finishing_luck":   {"goals": [("fin_luck", "own"), ("def_luck", "opp")]},
    "penalty_skill":    {"goals": [("pen_rate", "own")]},
    "red_card_rate":    {"goals": [("red_rate", "own"), ("red_rate", "opp")]},
    "set_pieces":       {"goals": [("corner_diff", "own"), ("corner_diff", "opp")]},
    "form":             {"goals": [("form_xgd5", "own"), ("form_xgd5", "opp")]},
    "lineup_strength":  {"goals": [("xi_rel", "own"), ("xi_rel", "opp")]},
    "draw_bias":        {"draw": ["const"]},
}


def prepare(f: pd.DataFrame, m: pd.DataFrame, promoted: dict) -> pd.DataFrame:
    """Derived feature columns used by FACTORS."""
    f = f.copy()
    f["early_h"] = f["early_a"] = np.clip((8 - f["gw"]) / 7, 0, 1)
    new = [(h in promoted.get(s, set()), a in promoted.get(s, set())) for s, h, a in zip(m["season"], m["home"], m["away"])]
    early = np.clip((12 - f["gw"]) / 11, 0, 1)
    f["promoted_early_h"] = np.array([n[0] for n in new], float) * early
    f["promoted_early_a"] = np.array([n[1] for n in new], float) * early
    f["both_ntp"] = f["ntp_h"] * f["ntp_a"]
    f["rest_diff_h"] = f["rest_diff"]
    f["const"] = 1.0
    for c in list(f.columns):
        if f[c].dtype == bool:
            f[c] = f[c].astype(float)
    return f


def _col(f, name, side):
    c = f"{name}_{side}"
    return f[c] if c in f else f[name]


def design(f, pred, spec, centers=None):
    goals = spec.get("goals", [])
    n = len(pred)
    Xh, Xa = np.zeros((n, len(goals))), np.zeros((n, len(goals)))
    for k, (name, role) in enumerate(goals):
        if role == "own":
            Xh[:, k], Xa[:, k] = _col(f, name, "h"), _col(f, name, "a")
        elif role == "opp":
            Xh[:, k], Xa[:, k] = _col(f, name, "a"), _col(f, name, "h")
        elif role == "match":
            Xh[:, k] = Xa[:, k] = f[name]
        elif role == "home":
            Xh[:, k] = f[name]
        elif role == "shrink":
            gap = np.log(pred["lh"].to_numpy()) - np.log(pred["la"].to_numpy())
            Xh[:, k], Xa[:, k] = f[f"{name}_h"] * gap, -f[f"{name}_h"] * gap
    Xd = np.column_stack([f[c].to_numpy(float) for c in spec.get("draw", [])]) if spec.get("draw") else np.zeros((n, 0))
    if centers is None:
        centers = {"h": np.nanmean(np.r_[Xh, Xa], 0) if len(goals) else np.zeros(0)}
        # binary/shrink features are already zero-centred in meaning; only centre continuous ones
        for k, (name, role) in enumerate(goals):
            vals = np.r_[Xh[:, k], Xa[:, k]]
            if role in ("shrink", "home", "match") or set(np.unique(vals[~np.isnan(vals)])) <= {0.0, 1.0}:
                centers["h"][k] = 0.0
    Xh, Xa = np.nan_to_num(Xh - centers["h"]), np.nan_to_num(Xa - centers["h"])
    for k, (name, role) in enumerate(goals):
        if role == "home":
            Xa[:, k] = 0.0
    return Xh, Xa, np.nan_to_num(Xd), centers


def fit(f, pred, m, spec):
    Xh, Xa, Xd, centers = design(f, pred, spec)
    k = Xh.shape[1]
    beta = np.zeros(k)
    if k:
        X = np.vstack([Xh, Xa])
        y = np.r_[m["hg"].to_numpy(float), m["ag"].to_numpy(float)]
        off = np.log(np.r_[pred["lh"].to_numpy(), pred["la"].to_numpy()])
        for _ in range(30):
            lam = np.exp(off + X @ beta)
            step = np.linalg.solve((X * lam[:, None]).T @ X + 1.0 * np.eye(k), X.T @ (y - lam) - 1.0 * beta)
            beta += step
            if np.abs(step).max() < 1e-8:
                break
    delta = np.zeros(Xd.shape[1])
    if Xd.shape[1]:
        lh, la = pred["lh"].to_numpy() * np.exp(Xh @ beta), pred["la"].to_numpy() * np.exp(Xa @ beta)
        g = score_grid(lh, la, pred["rho"].to_numpy())
        pd_ = np.trace(g, axis1=1, axis2=2)
        o = outcome(m)
        for _ in range(3):  # coordinate search, each delta on a fine grid
            for j in range(len(delta)):
                best, best_ll = delta[j], -np.inf
                for v in np.arange(-0.5, 0.501, 0.01):
                    d = delta.copy()
                    d[j] = v
                    mult = np.exp(Xd @ d)
                    pdraw = pd_ * mult / (1 - pd_ + pd_ * mult)
                    other = (1 - pdraw) / np.maximum(1 - pd_, 1e-12)
                    ph = np.where(o == 1, pdraw, other)  # prob of observed class up to non-draw split
                    ll = np.log(np.maximum(ph, 1e-12)).sum()
                    if ll > best_ll:
                        best, best_ll = v, ll
                delta[j] = best
    return {"beta": beta.tolist(), "delta": delta.tolist(), "centers": centers["h"].tolist(), "spec": spec}


def apply(f, pred, params):
    spec = params["spec"]
    Xh, Xa, Xd, _ = design(f, pred, spec, {"h": np.array(params["centers"])})
    out = pred.copy()
    beta, delta = np.array(params["beta"]), np.array(params["delta"])
    if len(beta):
        out["lh"] = pred["lh"].to_numpy() * np.exp(Xh @ beta)
        out["la"] = pred["la"].to_numpy() * np.exp(Xa @ beta)
    dm = np.exp(Xd @ delta) if len(delta) else np.ones(len(pred))
    out["dmult"] = (pred["dmult"].to_numpy() if "dmult" in pred else 1.0) * dm
    return out


def merge_specs(names):
    spec = {"goals": [], "draw": []}
    for n in names:
        for key in ("goals", "draw"):
            for item in FACTORS[n].get(key, []):
                if item not in spec[key]:
                    spec[key].append(item)
    return spec
