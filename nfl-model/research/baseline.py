"""Faithful re-implementation of the ORIGINAL model (nfl_power_rankings / build_pr.py) for historical backtesting.

Reproduced as in the workbook, rebuilt from scratch each season (no carry-over), regular season only:
  Market  : ridge on this season's closing lines, half-life 3 wks, ridge 0.5, HFA 1.5 subtracted
  Results : ridge on damped margins (14*ln(1+|m|/14)), half-life 5, ridge 3, minus 50% fumble luck
  Elo     : 538-style, K=20, starts from Week-1 market ratings, 25 Elo = 1 pt
  EPA     : season-to-date opponent-adjusted net EPA/play, garbage time (wp<5% or >95%) removed
  Tips engine : 50% market + 50% efficiency (each on the market's scale) + HFA 1.5 (0 at neutral sites)
                + 0.3/day rest edge (cap 7) + 0.7 off-bye + 0.2/1000 travel miles + 0.5 body clock
                Week 1 = the closing line itself (as in the workbook).
  PR score    : 40% market, 40% efficiency, 5% results, 5% Elo, 10% trend (consistency/momentum) + HFA 1.5
What cannot be reproduced for past seasons (no historical record exists in the original files):
  FTN DVOA (paywalled, only 2026 Weeks 1-8 typed in), hand-valued injuries / QB absences, eye-test, "your ranking".
  Efficiency is therefore 100% EPA here (the workbook used 75% EPA + 25% DVOA).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # nfl-model/ on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nflmodel.common import RESULTS, INPUTS, config
import numpy as np, pandas as pd
from scipy.stats import norm
from nflmodel.common import TEAMS, TIDX, load_games, DATA
from nflmodel.ratings import load_team_games

N = len(TEAMS); HFA = 1.5


def ridge(h, a, y, w, lam):
    X = np.zeros((len(y), N)); X[np.arange(len(y)), h] = 1; X[np.arange(len(y)), a] -= 1
    b = np.linalg.solve(X.T @ (X * w[:, None]) + lam * np.eye(N), X.T @ (w * y)); return b - b.mean()


def zs(v, ref):
    s = v.std(); return (v - v.mean()) / s * ref.std() if s > 0 else v * 0


def season_ratings(g, tg, season):
    """Per-week ratings (after week w) for one season. Returns dict w -> dict of arrays."""
    gs = g[(g.season == season) & (g.game_type == 'REG')]
    t = tg[(tg.season == season) & (tg.game_type == 'REG')]
    maxw = int(gs.week.max()); out = {}
    h = gs.home_team.map(TIDX).values; a = gs.away_team.map(TIDX).values; W = gs.week.values
    line = gs.spread_line.values.astype(float); res = gs.result.values.astype(float)
    R = None
    for w in range(1, maxw + 1):
        m = (W <= w) & ~np.isnan(line)
        MC = ridge(h[m], a[m], line[m] - HFA, 0.5 ** ((w - W[m]) / 3), 0.5) if m.any() else np.zeros(N)
        pm = (W <= w) & ~np.isnan(res)
        if not pm.any():
            break
        dm = np.sign(res[pm]) * 14 * np.log1p(np.abs(res[pm]) / 14)
        RR = ridge(h[pm], a[pm], dm - HFA, 0.5 ** ((w - W[pm]) / 5), 3.0)
        # fumble luck (pts per game), as luck_hist.json: 4*((0.46*fum - lost) + (opp_lost - 0.46*opp_fum))/games
        x = t[t.week <= w]
        of = x.groupby('team').fumbles.sum(); ol = x.groupby('team').fumbles_lost.sum()
        df_ = x.groupby('opp').fumbles.sum(); dl = x.groupby('opp').fumbles_lost.sum(); gp = x.groupby('team').size()
        luck = np.array([4 * ((0.46 * of.get(tm, 0) - ol.get(tm, 0)) + (dl.get(tm, 0) - 0.46 * df_.get(tm, 0))) / gp.get(tm, 1) for tm in TEAMS])
        RC = RR - 0.5 * luck
        # Elo
        if w == 1:
            R = 1500 + 25 * MC
        for j in np.where(pm & (W == w))[0]:
            d = R[h[j]] - R[a[j]] + 25 * HFA; e = 1 / (1 + 10 ** (-d / 400)); mg = res[j]; s = 1 if mg > 0 else 0 if mg < 0 else .5
            mult = np.log(abs(mg) + 1) * 2.2 / ((d if mg > 0 else -d) * 0.001 + 2.2); ch = 20 * mult * (s - e); R[h[j]] += ch; R[a[j]] -= ch
        EP = (R - R.mean()) / 25 - 0.5 * luck
        # opponent-adjusted EPA (garbage time removed), iterative as w8data/hist.py
        off = x.groupby('team').apply(lambda z: z.epa_gt.sum() / max(1, z.plays_gt.sum()), include_groups=False)
        de = x.groupby('opp').apply(lambda z: z.epa_gt.sum() / max(1, z.plays_gt.sum()), include_groups=False)
        raw = np.array([off.get(tm, 0) - de.get(tm, 0) for tm in TEAMS])
        opps = [list(x[x.team == tm].opp.map(TIDX)) for tm in TEAMS]
        adj = raw.copy()
        for _ in range(200):
            adj = np.array([raw[i] + (np.mean(adj[opps[i]]) if opps[i] else 0) for i in range(N)]); adj -= adj.mean()
        EFN = zs(adj, MC); RN = RC / RC.std() * MC.std(); EN = EP / EP.std() * MC.std()
        BASE = (0.4 * MC + 0.4 * EFN + 0.05 * RN + 0.05 * EN) / 0.9
        out[w] = dict(MC=MC, EFN=EFN, RN=RN, EN=EN, BASE=BASE, TIP=0.5 * MC + 0.5 * EFN)
    # trend: consistency (avg base to date) + momentum (recency-weighted slope, half-life 3)
    for w in out:
        ks = np.array([k for k in out if k <= w]); B = np.array([out[k]['BASE'] for k in ks])
        CONS = B.mean(0)
        v = 0.5 ** ((w - ks) / 3); kb = (v * ks).sum() / v.sum(); den = (v * (ks - kb) ** 2).sum()
        MOM = ((v * (ks - kb))[:, None] * B).sum(0) / den if w >= 2 else np.zeros(N)
        MC = out[w]['MC']
        CONSN = zs(CONS, MC); MOMN = zs(MOM, MC) if w >= 2 else np.zeros(N)
        out[w]['PRE'] = 0.4 * MC + 0.4 * out[w]['EFN'] + 0.05 * out[w]['RN'] + 0.05 * out[w]['EN'] + 0.1 * (0.5 * CONSN + 0.5 * MOMN)
    return out


def body_clock(r):
    """Workbook rule (travel.py): west-coast team in a 1pm-ET game out east, or east-coast team in a late game out west."""
    if r.neutral: return 0.0
    if r.tz_a == 3 and r.ko_local <= 13.5: return 1.0          # away from Pacific, early East kickoff
    if r.tz_a == -3 and (r.ko_clock_a >= 20 or r.ko_clock_a < 4): return 1.0
    return 0.0


def predict(seasons, g=None, tg=None):
    g = load_games() if g is None else g
    tg = load_team_games(f'{DATA}/team_games.csv', g) if tg is None else tg
    rows = []
    for s in seasons:
        R = season_ratings(g, tg, s)
        gs = g[(g.season == s) & (g.game_type == 'REG')]
        played_wk = {}
        for r in gs.itertuples():
            played_wk.setdefault(r.week, set()).update([r.home_team, r.away_team])
        for r in gs.itertuples():
            hi, ai = TIDX[r.home_team], TIDX[r.away_team]
            bye = lambda t: 1.0 if (r.week > 1 and t not in played_wk.get(r.week - 1, set())) else 0.0
            if r.week == 1 or (r.week - 1) not in R:
                tip = r.spread_line; pr = np.nan
            else:
                P = R[r.week - 1]
                rest = 0.0 if r.week == 1 else 0.3 * np.clip(r.home_rest - r.away_rest, -7, 7)
                tip = (HFA * (1 - r.neutral) + P['TIP'][hi] - P['TIP'][ai] + rest + 0.7 * (bye(r.home_team) - bye(r.away_team))
                       + 0.2 * (r.miles_a - r.miles_h) / 1000 + 0.5 * body_clock(r))
                pr = P['PRE'][hi] - P['PRE'][ai] + HFA
            rows.append(dict(game_id=r.game_id, season=s, week=r.week, home_team=r.home_team, away_team=r.away_team,
                             result=r.result, spread_line=r.spread_line, home_moneyline=r.home_moneyline,
                             away_moneyline=r.away_moneyline, pred=tip, pr_pred=pr))
    d = pd.DataFrame(rows)
    d['prob'] = norm.cdf(d.pred / 13.0); d['pr_prob'] = norm.cdf(d.pr_pred / 13.0)
    return d


if __name__ == '__main__':
    import sys
    from nflmodel.metrics import evaluate, fmt, line_as_model
    seasons = list(range(2009, 2027))
    d = predict(seasons)
    d.round(4).to_csv(os.path.join(RESULTS, 'baseline_predictions.csv'), index=False)
    print('original tips engine:', fmt(evaluate(d)))
    print('closing line        :', fmt(evaluate(line_as_model(d))))
