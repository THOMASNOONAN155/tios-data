"""Season view: power rankings, ranking history, luck table, strength of schedule, fixture difficulty."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import predictor
from .models import grid_markets, score_grid


def all_pairings(teams, date):
    rows = [(h, a) for h in teams for a in teams if h != a]
    return pd.DataFrame(rows, columns=["home", "away"]).assign(date=date, season="", hg=np.nan, ag=np.nan)


def ratings(spec, m_played, teams, as_of) -> pd.DataFrame:
    """Attack = expected goals scored per game against the current league (home and away averaged),
    defence = expected goals conceded; net = expected goal difference per game."""
    pairs = all_pairings(teams, as_of)
    pairs.index = pd.RangeIndex(10**6, 10**6 + len(pairs))
    pr = predictor.fit_predict(spec, m_played, pairs, as_of, with_factors=False)
    pairs = pairs.join(pr)
    att = (pairs.groupby("home")["lh"].mean() + pairs.groupby("away")["la"].mean()) / 2
    dfn = (pairs.groupby("home")["la"].mean() + pairs.groupby("away")["lh"].mean()) / 2
    g = score_grid(pairs["lh"].values, pairs["la"].values, pairs["rho"].values)
    mk = grid_markets(g)
    pairs["xpts_h"] = 3 * mk["pH"] + mk["pD"]
    pairs["xpts_a"] = 3 * mk["pA"] + mk["pD"]
    xp = (pairs.groupby("home")["xpts_h"].mean() + pairs.groupby("away")["xpts_a"].mean()) / 2
    r = pd.DataFrame({"attack": att, "defence": dfn, "net": att - dfn, "xpts_per_game": xp})
    r["rank"] = r["net"].rank(ascending=False, method="first").astype(int)
    return r.sort_values("rank"), pairs


def power_rankings(spec, m, season, fixtures_future) -> dict:
    """Current rankings, history by gameweek and movement since the previous gameweek."""
    played = m[m["hg"].notna()]
    cur = played[played["season"] == season]
    teams = sorted(set(fixtures_future["home"]) | set(fixtures_future["away"]) | set(cur["home"]))
    gws = sorted(cur["gw"].unique())
    hist = {}
    for gw in gws + [max(gws, default=0) + 1]:
        if gw == max(gws, default=0) + 1:
            as_of = fixtures_future["date"].min() if len(fixtures_future) else played["date"].max() + pd.Timedelta(days=1)
        else:
            as_of = cur.loc[cur["gw"] == gw, "date"].min()
        r, _ = ratings(spec, played, teams, as_of)
        hist[f"Pre-GW{int(gw)}"] = r["rank"]
    history = pd.DataFrame(hist)
    history.index.name = None
    now, pairs = ratings(spec, played, teams, fixtures_future["date"].min() if len(fixtures_future) else
                         played["date"].max() + pd.Timedelta(days=1))
    prev_col = history.columns[-2] if history.shape[1] >= 2 else history.columns[-1]
    now["prev_rank"] = history[prev_col].reindex(now.index)
    now["movement"] = now["prev_rank"] - now["rank"]
    # actual xG difference per game this season
    xs = []
    for t in now.index:
        h, a = cur[cur["home"] == t], cur[cur["away"] == t]
        n = len(h) + len(a)
        xs.append({"team": t, "played": n,
                   "xgd_pg": ((h["hxg"].sum() - h["axg"].sum()) + (a["axg"].sum() - a["hxg"].sum())) / max(n, 1),
                   "gd_pg": ((h["hg"].sum() - h["ag"].sum()) + (a["ag"].sum() - a["hg"].sum())) / max(n, 1)})
    now = now.join(pd.DataFrame(xs).set_index("team"))
    return {"now": now, "history": history, "pairs": pairs}


def luck_table(m, season) -> pd.DataFrame:
    """Actual points vs expected points from each match's xG (independent Poisson on xG)."""
    cur = m[(m["season"] == season) & m["hg"].notna() & m["hxg"].notna()]
    g = score_grid(cur["hxg"].values, cur["axg"].values, 0.0)
    mk = grid_markets(g)
    rows = {}
    for k, r in enumerate(cur.itertuples()):
        for t, gf, ga, xgf, xga, pw, pd_ in ((r.home, r.hg, r.ag, r.hxg, r.axg, mk["pH"][k], mk["pD"][k]),
                                             (r.away, r.ag, r.hg, r.axg, r.hxg, mk["pA"][k], mk["pD"][k])):
            d = rows.setdefault(t, {"played": 0, "points": 0, "xpts": 0.0, "gf": 0, "ga": 0, "xgf": 0.0, "xga": 0.0})
            d["played"] += 1
            d["points"] += 3 if gf > ga else 1 if gf == ga else 0
            d["xpts"] += 3 * pw + pd_
            d["gf"] += gf
            d["ga"] += ga
            d["xgf"] += xgf
            d["xga"] += xga
    t = pd.DataFrame(rows).T
    t["luck_points"] = t["points"] - t["xpts"]
    t["finishing"] = t["gf"] - t["xgf"]
    t["goalkeeping"] = t["xga"] - t["ga"]
    return t.astype(float).sort_values("luck_points", ascending=False)


def schedule_strength(now: pd.DataFrame, pairs: pd.DataFrame, m, season, remaining) -> pd.DataFrame:
    """Average opponent net rating faced (played) and to come (remaining), venue-adjusted via each
    fixture's expected points: difficulty = 3 - expected points of an average team in that fixture."""
    pairs = pairs.set_index(["home", "away"])
    avg = now["net"].mean()

    def opp_strength(rows, t):
        vals = []
        for r in rows.itertuples():
            opp = r.away if r.home == t else r.home
            vals.append(now.loc[opp, "net"] - avg if opp in now.index else np.nan)
        return np.nanmean(vals) if vals else np.nan

    cur = m[(m["season"] == season) & m["hg"].notna()]
    out = []
    for t in now.index:
        pl = cur[(cur["home"] == t) | (cur["away"] == t)]
        rm = remaining[(remaining["home"] == t) | (remaining["away"] == t)]
        out.append({"team": t, "sos_played": opp_strength(pl, t), "sos_remaining": opp_strength(rm, t),
                    "games_left": len(rm)})
    s = pd.DataFrame(out).set_index("team")
    s["sos_played_rank"] = s["sos_played"].rank(ascending=False).astype("Int64")
    s["sos_remaining_rank"] = s["sos_remaining"].rank(ascending=False).astype("Int64")
    return s


def fixture_difficulty(remaining_pred: pd.DataFrame, n=5) -> pd.DataFrame:
    """Next n fixtures per team with opponent, venue and the model's expected points."""
    g = score_grid(remaining_pred["lh"].values, remaining_pred["la"].values, remaining_pred["rho"].values,
                   remaining_pred["dmult"].values)
    mk = grid_markets(g)
    rp = remaining_pred.assign(xh=3 * mk["pH"] + mk["pD"], xa=3 * mk["pA"] + mk["pD"]).sort_values("date")
    teams = sorted(set(rp["home"]) | set(rp["away"]))
    rows = []
    for t in teams:
        fx = rp[(rp["home"] == t) | (rp["away"] == t)].head(n)
        row = {"team": t}
        for k, r in enumerate(fx.itertuples(), 1):
            home = r.home == t
            row[f"fx{k}"] = f"{r.away if home else r.home} ({'H' if home else 'A'})"
            row[f"xp{k}"] = r.xh if home else r.xa
        row["xpts_next"] = sum(row.get(f"xp{k}", 0) for k in range(1, n + 1))
        rows.append(row)
    return pd.DataFrame(rows).set_index("team").sort_values("xpts_next", ascending=False)
