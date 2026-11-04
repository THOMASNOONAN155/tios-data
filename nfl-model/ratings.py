"""Walk-forward team ratings. Every rating for (season, week) uses ONLY games from earlier weeks.

Three rating families, each a weighted ridge regression with exponential time decay that carries across seasons:
  market   - fit to past closing spreads            (points)
  results  - fit to past (damped) scoring margins   (points)
  epa      - offense/defense fit to past EPA/play   (EPA per play; garbage time optional)
Time decay: weight = 0.5 ** (age / half_life); age counts weeks, plus `offseason` extra weeks per season boundary.
"""
import numpy as np, pandas as pd
from common import TEAMS, TIDX, FRANCHISE

N = len(TEAMS)
GW = 23  # calendar slots per season (weeks 1-22 + spare)


def gweek(season, week):
    return season * GW + week


def _decay(now_s, now_w, s, w, hl, off):
    age = (now_s * GW + now_w) - (s * GW + w) + off * (now_s - s)
    return 0.5 ** (age / hl)


def ridge_pair(h, a, y, wt, neutral, lam, hfa_fixed=None):
    """y = hfa*(1-neutral) + r[h] - r[a]. Returns (ratings centred on 0, hfa)."""
    n = len(y)
    X = np.zeros((n, N + 1)); X[np.arange(n), h] = 1; X[np.arange(n), a] -= 1
    if hfa_fixed is None:
        X[:, N] = 1 - neutral
    else:
        y = y - hfa_fixed * (1 - neutral)
    P = np.eye(N + 1) * lam; P[N, N] = 1e-6 if hfa_fixed is None else 1e6
    Xw = X * wt[:, None]
    b = np.linalg.solve(X.T @ Xw + P, Xw.T @ y)
    r = b[:N] - b[:N].mean()
    return r, (b[N] if hfa_fixed is None else hfa_fixed)


def damp(m, scale=14.0):
    return np.sign(m) * scale * np.log1p(np.abs(m) / scale)


def slots(games, first_season):
    s = games[(games.season >= first_season)][['season', 'week']].drop_duplicates().sort_values(['season', 'week'])
    return list(s.itertuples(index=False, name=None))


def market_ratings(games, first_season, hl=4.0, off=10.0, lam=2.0, window=3):
    """Ratings implied by closing lines of earlier games."""
    g = games[games.spread_line.notna()]
    h = g.home_team.map(TIDX).values; a = g.away_team.map(TIDX).values
    y = g.spread_line.values.astype(float); neu = g.neutral.values; S = g.season.values; W = g.week.values
    out = {}
    for s, w in slots(games, first_season):
        m = ((S < s) | ((S == s) & (W < w))) & (S >= s - window)
        if m.sum() == 0: continue
        wt = _decay(s, w, S[m], W[m], hl, off)
        r, hfa = ridge_pair(h[m], a[m], y[m], wt, neu[m], lam)
        out[(s, w)] = (r, hfa)
    return out


def results_ratings(games, first_season, hl=6.0, off=10.0, lam=8.0, window=3, damp_scale=14.0):
    g = games[games.result.notna()]
    h = g.home_team.map(TIDX).values; a = g.away_team.map(TIDX).values
    y = damp(g.result.values.astype(float), damp_scale) if damp_scale else g.result.values.astype(float)
    neu = g.neutral.values; S = g.season.values; W = g.week.values
    out = {}
    for s, w in slots(games, first_season):
        m = ((S < s) | ((S == s) & (W < w))) & (S >= s - window)
        if m.sum() == 0: continue
        wt = _decay(s, w, S[m], W[m], hl, off)
        out[(s, w)] = ridge_pair(h[m], a[m], y[m], wt, neu[m], lam)
    return out


def load_team_games(path, games):
    tg = pd.read_csv(path)
    for c in ('team', 'opp'):
        tg[c] = tg[c].replace(FRANCHISE).replace({'LAR': 'LA', 'JAC': 'JAX', 'WSH': 'WAS'})
    gi = games[['game_id', 'home_team', 'neutral', 'game_type']]
    tg = tg.merge(gi, on='game_id', how='inner')
    tg['home'] = np.where(tg.neutral == 1, 0, np.where(tg.team == tg.home_team, 1, -1))
    return tg


def epa_ratings(tg, first_season, hl=6.0, off=10.0, lam=150.0, window=3, gt=True, metric='epa', def_lam_mult=1.0, schedule=None):
    """Offense/defense ridge on per-game EPA (or success rate) per play. Returns net rating (off - def) per team."""
    if gt:
        y = (tg[metric + '_gt'] / tg.plays_gt.clip(lower=1)).values; n = tg.plays_gt.values
    else:
        y = (tg[metric] / tg.plays.clip(lower=1)).values; n = tg.plays.values
    o = tg.team.map(TIDX).values; d = tg.opp.map(TIDX).values; hm = tg.home.values.astype(float)
    S = tg.season.values; W = tg.week.values
    out = {}
    for s, w in slots(tg if schedule is None else schedule, first_season):   # schedule -> also rate upcoming weeks
        m = ((S < s) | ((S == s) & (W < w))) & (S >= s - window) & (n > 0)
        k = m.sum()
        if k == 0: continue
        X = np.zeros((k, 2 * N + 2)); idx = np.arange(k)
        X[idx, o[m]] = 1; X[idx, N + d[m]] = 1; X[:, 2 * N] = 1; X[:, 2 * N + 1] = hm[m]
        wt = _decay(s, w, S[m], W[m], hl, off) * n[m] / 60.0
        P = np.diag(np.r_[np.full(N, lam), np.full(N, lam * def_lam_mult), 1e-6, 1e-6])
        Xw = X * wt[:, None]
        b = np.linalg.solve(X.T @ Xw + P, Xw.T @ y[m])
        off_r = b[:N] - b[:N].mean(); def_r = b[N:2 * N] - b[N:2 * N].mean()   # def_r > 0 = allows more EPA (bad)
        out[(s, w)] = (off_r - def_r, off_r, def_r)
    return out


def qb_values(games, qbg, hl=40.0, off=10.0, prior_n=250.0, prior_mean=-0.05):
    """Pre-game shrunk EPA/dropback for each game's two starting QBs, and each team's recent-QB baseline.

    value(QB) = (decayed sum of qb_epa + prior_n*prior_mean) / (decayed dropbacks + prior_n), using games before this one.
    baseline(team) = average current value of the starters in the team's previous 8 games (more recent weigh more).
    Returns DataFrame game_id, qb_h, qb_a, qbbase_h, qbbase_a.
    """
    st = {}  # qb -> [sum_epa, n, last_gw]
    q = qbg.groupby(['game_id', 'player_id'])[['dropbacks', 'qb_epa']].sum()
    qd = {}
    for (gid, pid), r in q.iterrows():
        qd.setdefault(gid, []).append((pid, r.dropbacks, r.qb_epa))
    def val(pid, now):
        if pid not in st: return prior_mean
        se, n, last = st[pid]; f = 0.5 ** ((now - last) / hl)
        return (se * f + prior_n * prior_mean) / (n * f + prior_n)
    hist = {t: [] for t in TEAMS}   # team -> list of (gw, qb)
    rows = []
    g = games.sort_values(['season', 'week', 'date']).reset_index(drop=True)
    for (s, w), grp in g.groupby(['season', 'week'], sort=True):
        now = gweek(s, w)
        for r in grp.itertuples():
            out = [r.game_id]
            for side, team, pid in (('h', r.home_team, r.home_qb_id), ('a', r.away_team, r.away_qb_id)):
                if not isinstance(pid, str):   # starter not yet known: assume last game's starter
                    pid = hist[team][-1][1] if hist[team] else None
                v = val(pid, now) if pid else prior_mean
                prev = hist[team][-8:]
                if prev:
                    ws = np.array([0.5 ** ((now - x[0]) / 4.0) for x in prev]); vs = np.array([val(x[1], now) for x in prev])
                    base = float((ws * vs).sum() / ws.sum())
                else:
                    base = v
                out += [pid, v, base]
            rows.append(out)
        for r in grp.itertuples():   # update after the whole week (all games of a week are 'before' next week only)
            if r.played:
                for team, pid in ((r.home_team, r.home_qb_id), (r.away_team, r.away_qb_id)):
                    if isinstance(pid, str): hist[team].append((now, pid))
                for pid, nd, se in qd.get(r.game_id, []):
                    if pid in st:
                        a, b, last = st[pid]; f = 0.5 ** ((now - last) / hl)
                        st[pid] = [a * f + se, b * f + nd, now]
                    else:
                        st[pid] = [se, nd, now]
        # offseason: no extra handling (decay by calendar weeks + off below)
        if w == g[g.season == s].week.max():
            for pid in st: st[pid][2] -= off   # treat offseason as `off` extra weeks of age
    return pd.DataFrame(rows, columns=['game_id', 'qbid_h', 'qb_h', 'qbbase_h', 'qbid_a', 'qb_a', 'qbbase_a'])
