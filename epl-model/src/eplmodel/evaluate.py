"""Walk-forward prediction and accuracy metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from .models import grid_markets, score_grid


# --------------------------------------------------------------------------------------------
# Walk-forward
# --------------------------------------------------------------------------------------------
def promoted_prior(tr: pd.DataFrame, promoted: dict, as_of) -> tuple[float, float] | None:
    """Average (attack, defence) log-ratings of promoted clubs in *completed past seasons* only."""
    cur = data.season_of(as_of)
    rows = tr[tr["season"] < cur]
    if rows.empty:
        return None
    gf, ga, n = 0.0, 0.0, 0
    for s, teams in promoted.items():
        if s >= cur:
            continue
        g = rows[rows["season"] == s]
        if g.empty:
            continue
        for t in teams:
            h, a = g[g["home"] == t], g[g["away"] == t]
            gf += h["hg"].sum() + a["ag"].sum()
            ga += h["ag"].sum() + a["hg"].sum()
            n += len(h) + len(a)
    if n == 0:
        return None
    avg = (rows["hg"].sum() + rows["ag"].sum()) / (2 * len(rows))
    return float(np.log(gf / n / avg)), float(-np.log(ga / n / avg))


def walk_forward(model, m: pd.DataFrame, start: str, end: str | None = None, extra_rows: pd.DataFrame | None = None):
    """Refit `model` before every match date from `start`, using only matches played on earlier dates.
    Returns DataFrame indexed like the predicted rows with lh, la, rho.  `extra_rows` (future fixtures)
    are predicted with the final fit."""
    promoted = data.promoted_teams(m)
    played = m[m["hg"].notna()]
    target = played[(played["date"] >= start) & ((played["date"] <= end) if end else True)]
    out = []
    for d, te in target.groupby("date", sort=True):
        tr = played[played["date"] < d]
        season = data.season_of(d)
        teams_now = set(m.loc[m["season"] == season, "home"])
        ctx = {"teams_now": teams_now, "new_teams": promoted.get(season, set()),
               "season_of_date": data.season_of, "promoted_prior": None}
        if getattr(model, "promoted_prior", False):
            ctx["promoted_prior"] = promoted_prior(tr, promoted, d)
        model.fit(tr, d, ctx)
        lh, la, rho = model.predict(te)
        out.append(pd.DataFrame({"lh": lh, "la": la, "rho": rho}, index=te.index))
    if extra_rows is not None and len(extra_rows):
        d = extra_rows["date"].min()
        tr = played[played["date"] < d]
        season = data.season_of(d)
        ctx = {"teams_now": set(extra_rows["home"]) | set(extra_rows["away"]), "new_teams": promoted.get(season, set()),
               "season_of_date": data.season_of,
               "promoted_prior": promoted_prior(tr, promoted, d) if getattr(model, "promoted_prior", False) else None}
        model.fit(tr, d, ctx)
        lh, la, rho = model.predict(extra_rows)
        out.append(pd.DataFrame({"lh": lh, "la": la, "rho": rho}, index=extra_rows.index))
    return pd.concat(out) if out else pd.DataFrame(columns=["lh", "la", "rho"])


# --------------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------------
def outcome(m):
    return np.select([m["hg"] > m["ag"], m["hg"] == m["ag"]], [0, 1], 2)


def rps(p, o):
    """Ranked probability score for ordered outcomes (home, draw, away). p: (n,3); o: int (n,)."""
    oh = np.eye(3)[o]
    c = np.cumsum(p, 1)[:, :2] - np.cumsum(oh, 1)[:, :2]
    return 0.5 * (c ** 2).sum(1)


def probs_from_pred(pred: pd.DataFrame) -> pd.DataFrame:
    g = score_grid(pred["lh"].values, pred["la"].values, pred["rho"].values,
                   pred["dmult"].values if "dmult" in pred else None)
    mk = grid_markets(g)
    flat = g.reshape(len(g), -1).argmax(1)
    out = pd.DataFrame(mk, index=pred.index)
    out["ml_h"], out["ml_a"] = flat // g.shape[2], flat % g.shape[2]
    out["lh"], out["la"] = pred["lh"].values, pred["la"].values
    return out


def metrics(p: pd.DataFrame, m: pd.DataFrame) -> dict:
    """p has pH,pD,pA (+ optional pOver, pBTTS, ml_h, ml_a, lh, la); m has hg, ag."""
    o = outcome(m)
    P = np.clip(p[["pH", "pD", "pA"]].to_numpy(float), 1e-12, 1)
    P = P / P.sum(1, keepdims=True)
    res = {"n": len(p), "RPS": rps(P, o).mean(), "LogLoss": -np.log(P[np.arange(len(o)), o]).mean(),
           "Brier": ((P - np.eye(3)[o]) ** 2).sum(1).mean(), "Correct%": (P.argmax(1) == o).mean() * 100,
           "DrawPred%": P[:, 1].mean() * 100, "DrawActual%": (o == 1).mean() * 100}
    tot = (m["hg"] + m["ag"]).to_numpy()
    if "pOver" in p and p["pOver"].notna().all():
        q = np.clip(p["pOver"].to_numpy(float), 1e-9, 1 - 1e-9)
        y = tot > 2.5
        res["OU_LogLoss"] = -np.mean(np.where(y, np.log(q), np.log(1 - q)))
    if "pBTTS" in p and p["pBTTS"].notna().all():
        q = np.clip(p["pBTTS"].to_numpy(float), 1e-9, 1 - 1e-9)
        y = (m["hg"] > 0) & (m["ag"] > 0)
        res["BTTS_LogLoss"] = -np.mean(np.where(y, np.log(q), np.log(1 - q)))
    if "ml_h" in p:
        res["ExactScore%"] = ((p["ml_h"].values == m["hg"].values) & (p["ml_a"].values == m["ag"].values)).mean() * 100
    if "lh" in p and p["lh"].notna().all():
        res["GoalMAE"] = (np.abs(p["lh"].values - m["hg"].values) + np.abs(p["la"].values - m["ag"].values)).mean() / 2
        res["TotalMAE"] = np.abs(p["lh"].values + p["la"].values - tot).mean()
    return res


def calibration(p: pd.DataFrame, m: pd.DataFrame, bins=(0, .1, .2, .3, .4, .5, .6, .7, .8, 1.0)) -> pd.DataFrame:
    """Pool home/draw/away probabilities: predicted vs observed frequency by probability bin."""
    o = outcome(m)
    P = p[["pH", "pD", "pA"]].to_numpy(float)
    Y = np.eye(3)[o]
    df = pd.DataFrame({"p": P.ravel(), "y": Y.ravel()})
    df["bin"] = pd.cut(df["p"], bins, include_lowest=True)
    t = df.groupby("bin", observed=True).agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean"))
    return t.reset_index()


def stage(gw):
    gw = np.asarray(gw, float)
    return np.select([gw <= 5, gw <= 12, gw <= 19, gw <= 29], ["GW1-5", "GW6-12", "GW13-19", "GW20-29"], "GW30-38")
