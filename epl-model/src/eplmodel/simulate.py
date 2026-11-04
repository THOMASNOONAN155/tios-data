"""Monte Carlo season simulation with rating uncertainty."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CONFIG, N_SIMS
from .models import dc_tau


def sample_scores(lh, la, rho, dmult, rng):
    """Exact sampling from the Dixon-Coles grid (with draw multiplier) by rejection from Poisson x Poisson:
    accept (i, j) with probability tau(i, j) / tau_max, redraw only the rejected cells. lh, la: (sims, matches)."""
    shape = np.shape(lh)
    rho, dmult = np.broadcast_to(rho, shape).ravel(), np.broadcast_to(dmult, shape).ravel()
    lh, la = np.ravel(lh), np.ravel(la)
    t00, t01, t10, t11 = dc_tau(lh, la, rho)
    tmax = np.maximum.reduce([t00, t01, t10, t11, np.ones_like(lh)]) * np.maximum(dmult, 1.0)
    hg, ag = rng.poisson(lh), rng.poisson(la)
    todo = np.arange(lh.size)
    for _ in range(100):
        h, a = hg[todo], ag[todo]
        tau = np.select([(h == 0) & (a == 0), (h == 0) & (a == 1), (h == 1) & (a == 0), (h == 1) & (a == 1)],
                        [t00[todo], t01[todo], t10[todo], t11[todo]], 1.0) * np.where(h == a, dmult[todo], 1.0)
        rej = rng.random(todo.size) * tmax[todo] > tau
        todo = todo[rej]
        if not todo.size:
            break
        hg[todo], ag[todo] = rng.poisson(lh[todo]), rng.poisson(la[todo])
    return hg, ag


def simulate(season: str, played: pd.DataFrame, remaining: pd.DataFrame, pred: pd.DataFrame,
             n_sims: int = N_SIMS, sigma: float = 0.08, seed: int = 7) -> dict:
    """played: this season's results (home, away, hg, ag). remaining: fixtures with index matching pred.
    sigma: s.d. of per-simulation team attack/defence shocks (log scale) representing rating uncertainty."""
    rng = np.random.default_rng(seed)
    teams = sorted(set(played["home"]) | set(played["away"]) | set(remaining["home"]) | set(remaining["away"]))
    ti = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    adj = pd.read_csv(CONFIG / "points_adjustments.csv")
    pts0, gd0, gf0 = np.zeros(T), np.zeros(T), np.zeros(T)
    for r in played.itertuples():
        h, a = ti[r.home], ti[r.away]
        pts0[h] += 3 if r.hg > r.ag else 1 if r.hg == r.ag else 0
        pts0[a] += 3 if r.ag > r.hg else 1 if r.hg == r.ag else 0
        gd0[h] += r.hg - r.ag
        gd0[a] += r.ag - r.hg
        gf0[h] += r.hg
        gf0[a] += r.ag
    for r in adj[adj["season"] == season].itertuples():
        if r.team in ti:
            pts0[ti[r.team]] += r.points
    hi = remaining["home"].map(ti).to_numpy()
    ai = remaining["away"].map(ti).to_numpy()
    n = len(remaining)
    pts = np.tile(pts0, (n_sims, 1))
    gd = np.tile(gd0, (n_sims, 1))
    gf = np.tile(gf0, (n_sims, 1))
    if n:
        att = rng.normal(0, sigma, (n_sims, T))
        dfn = rng.normal(0, sigma, (n_sims, T))
        lh = pred.loc[remaining.index, "lh"].to_numpy()[None, :] * np.exp(att[:, hi] - dfn[:, ai])
        la = pred.loc[remaining.index, "la"].to_numpy()[None, :] * np.exp(att[:, ai] - dfn[:, hi])
        rho = pred.loc[remaining.index, "rho"].to_numpy()[None, :]
        dm = pred.loc[remaining.index, "dmult"].to_numpy()[None, :] if "dmult" in pred else np.ones((1, n))
        hg, ag = sample_scores(lh, la, rho, dm, rng)
        hg, ag = hg.reshape(lh.shape).astype(np.float32), ag.reshape(lh.shape).astype(np.float32)
        ph = np.where(hg > ag, 3, np.where(hg == ag, 1, 0)).astype(np.float32)
        pa = np.where(ag > hg, 3, np.where(hg == ag, 1, 0)).astype(np.float32)
        Hh = np.zeros((n, T), np.float32)
        Ha = np.zeros((n, T), np.float32)
        Hh[np.arange(n), hi] = 1
        Ha[np.arange(n), ai] = 1
        pts += ph @ Hh + pa @ Ha
        gd += (hg - ag) @ Hh + (ag - hg) @ Ha
        gf += hg @ Hh + ag @ Ha
    key = pts * 1e6 + (gd + 500) * 1e3 + gf + rng.random(pts.shape) * 0.5
    order = np.argsort(-key, axis=1)
    pos = np.empty_like(order)
    pos[np.arange(n_sims)[:, None], order] = np.arange(1, T + 1)[None, :]
    res = pd.DataFrame({
        "team": teams, "points_now": pts0, "exp_points": pts.mean(0), "p10_points": np.percentile(pts, 10, 0),
        "p90_points": np.percentile(pts, 90, 0), "exp_gd": gd.mean(0), "exp_position": pos.mean(0),
        "p_title": (pos == 1).mean(0), "p_top4": (pos <= 4).mean(0), "p_top5": (pos <= 5).mean(0),
        "p_top7": (pos <= 7).mean(0), "p_relegation": (pos >= T - 2).mean(0),
    }).sort_values("exp_points", ascending=False).reset_index(drop=True)
    pos_dist = pd.DataFrame([(pos[:, i][:, None] == np.arange(1, T + 1)).mean(0) for i in range(T)],
                            index=teams, columns=range(1, T + 1))
    return {"table": res, "positions": pos_dist}


def final_table(season_matches: pd.DataFrame, season: str) -> pd.DataFrame:
    """Actual final standings (with recorded points deductions)."""
    adj = pd.read_csv(CONFIG / "points_adjustments.csv")
    rows = {}
    for r in season_matches.itertuples():
        for t, gf, ga in ((r.home, r.hg, r.ag), (r.away, r.ag, r.hg)):
            p = rows.setdefault(t, [0, 0, 0])
            p[0] += 3 if gf > ga else 1 if gf == ga else 0
            p[1] += gf - ga
            p[2] += gf
    for r in adj[adj["season"] == season].itertuples():
        if r.team in rows:
            rows[r.team][0] += r.points
    t = pd.DataFrame([(k, *v) for k, v in rows.items()], columns=["team", "pts", "gd", "gf"])
    t = t.sort_values(["pts", "gd", "gf"], ascending=False).reset_index(drop=True)
    t["pos"] = np.arange(1, len(t) + 1)
    return t
