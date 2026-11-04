"""Round-2 candidate features. Every value for a game uses only data from before that game's week.

All features are 'home minus away' unless noted. Built on top of model.build_features().
"""
import os, json
import numpy as np, pandas as pd
from nflmodel.common import TEAMS, TIDX, DATA, FRANCHISE
from nflmodel.ratings import slots, _decay, GW

N = len(TEAMS)
FIX = lambda s: s.replace(FRANCHISE).replace({'LAR': 'LA', 'JAC': 'JAX', 'WSH': 'WAS'})


def rate_ratings(tx, num, den, sched, first, hl=3.0, off=2.0, lam=3.0, window=3, opp=True):
    """Ridge rating of num/den per game. opp=True: offence & opponent-defence terms (returns off - def, off, def).
    opp=False: plain decayed team average (returns value, value, 0)."""
    d = tx[tx[den] > 0]
    y = (d[num] / d[den]).values; wbase = (d[den] / d[den].mean()).values
    o = d.team.map(TIDX).values; dd = d.opp.map(TIDX).values; hm = d.home.values.astype(float)
    S = d.season.values; W = d.week.values; out = {}
    for s, w in slots(sched, first):
        m = ((S < s) | ((S == s) & (W < w))) & (S >= s - window); k = m.sum()
        if k == 0: continue
        wt = _decay(s, w, S[m], W[m], hl, off) * wbase[m]; idx = np.arange(k)
        if opp:
            X = np.zeros((k, 2 * N + 2)); X[idx, o[m]] = 1; X[idx, N + dd[m]] = 1; X[:, 2 * N] = 1; X[:, 2 * N + 1] = hm[m]
            P = np.diag(np.r_[np.full(2 * N, lam), 1e-6, 1e-6])
        else:
            X = np.zeros((k, N + 1)); X[idx, o[m]] = 1; X[:, N] = 1
            P = np.diag(np.r_[np.full(N, lam), 1e-6])
        Xw = X * wt[:, None]; b = np.linalg.solve(X.T @ Xw + P, Xw.T @ y[m])
        if opp:
            a, c = b[:N] - b[:N].mean(), b[N:2 * N] - b[N:2 * N].mean(); out[(s, w)] = (a - c, a, c)
        else:
            a = b[:N] - b[:N].mean(); out[(s, w)] = (a, a, np.zeros(N))
    return out


def diff(f, R, idx=0, name=None):
    v = np.full(len(f), np.nan)
    for i, r in enumerate(f.itertuples()):
        x = R.get((r.season, r.week))
        if x is not None: v[i] = x[idx][TIDX[r.home_team]] - x[idx][TIDX[r.away_team]]
    return v


def team_game_frame(g, tg):
    """Base team-game rows (with opp/home) joined to the extra pbp aggregates and per-game results."""
    tx = pd.read_csv(f'{DATA}/team_games_x.csv'); tx['team'] = FIX(tx.team)
    tx = tx.drop(columns=[c for c in tx.columns if c in tg.columns and c not in ('game_id', 'team')])
    t = tg.merge(tx, on=['game_id', 'team'], how='left')
    # per-game outcome terms from the team's side
    gg = g[g.result.notna()][['game_id', 'home_team', 'result']]
    t = t.merge(gg.rename(columns={'home_team': 'ht'}), on='game_id', how='left')
    t['margin'] = np.where(t.team == t.ht, t.result, -t.result)
    t['close_luck'] = np.where(t.margin.abs() <= 8, np.sign(t.margin) * 0.5, 0.0)      # one-score W = +.5, L = -.5
    o = t[['game_id', 'team', 'fumbles', 'fumbles_lost']].rename(columns={'team': 'opp', 'fumbles': 'of', 'fumbles_lost': 'ol'})
    t = t.merge(o, on=['game_id', 'opp'], how='left')
    t['fum_luck'] = (0.5 * t.fumbles - t.fumbles_lost) + (t.ol - 0.5 * t.of)          # recoveries above a 50/50 coin
    t['one'] = 1.0
    t['pass_rush_n'] = t.plays - t.pass_plays
    return t


def player_injury_features(g):
    """Out/Doubtful players valued by how much they matter, grouped by position (QBs excluded)."""
    inj = pd.read_csv(f'{DATA}/injury_out.csv'); inj['team'] = FIX(inj.team)
    pw = pd.read_csv(f'{DATA}/player_weeks.csv'); pw['team'] = FIX(pw.team)
    pw = pw[pw.game_id.str.contains('_') & (pw.week <= 22)]
    # cumulative season-to-date shares, from games BEFORE the injury week
    a = pw.groupby(['season', 'team', 'week', 'gsis_id'])[['targets', 'pressures']].sum().reset_index().sort_values('week')
    a[['ct', 'cp']] = a.groupby(['season', 'team', 'gsis_id'])[['targets', 'pressures']].cumsum()
    tot = a.groupby(['season', 'team', 'week'])[['targets', 'pressures']].sum().groupby(level=[0, 1]).cumsum().reset_index() \
           .rename(columns={'targets': 'tt', 'pressures': 'tp'}).sort_values('week')
    x = inj.copy(); x['wk0'] = x.week - 1; x = x.sort_values('wk0')
    a2 = a[['season', 'team', 'week', 'gsis_id', 'ct', 'cp']].rename(columns={'week': 'wk0'}).sort_values('wk0')
    x = pd.merge_asof(x, a2, on='wk0', by=['season', 'team', 'gsis_id'], direction='backward')
    x = pd.merge_asof(x.sort_values('wk0'), tot.rename(columns={'week': 'wk0'}), on='wk0', by=['season', 'team'], direction='backward')
    x['tshare'] = (x.ct / x.tt).fillna(0); x['pshare'] = (x.cp / x.tp).fillna(0)
    sw = np.where(x.status == 'Doubtful', 0.75, 1.0)
    pos = x.pos.fillna('')
    grp = {'inj_ol': pos.isin(['T', 'G', 'C', 'OT', 'OG', 'OL']) * x.off_share,
           'inj_wrte': pos.isin(['WR', 'TE']) * x.tshare,
           'inj_rb': pos.isin(['RB', 'FB']) * x.off_share,
           'inj_rush': pos.isin(['DE', 'DT', 'NT', 'OLB', 'DL', 'EDGE']) * x.pshare,
           'inj_cb': pos.isin(['CB', 'DB']) * x.def_share,
           'inj_s': pos.isin(['S', 'FS', 'SS']) * x.def_share,
           'inj_lb': pos.isin(['LB', 'ILB', 'MLB']) * x.def_share}
    for k, v in grp.items(): x[k] = v * sw
    x['inj_starters'] = ((x.off_share >= 0.6) | (x.def_share >= 0.6)) & (pos != 'QB')
    x['inj_starters'] = x.inj_starters * sw
    return x.groupby(['season', 'week', 'team'])[list(grp) + ['inj_starters']].sum()


def coach_features(g):
    """New head coach this season (different from the team's last coach of the previous season) / mid-season change."""
    rows = []
    for t in TEAMS:
        side = pd.concat([g[g.home_team == t][['season', 'week', 'game_id', 'home_coach']].rename(columns={'home_coach': 'c'}),
                          g[g.away_team == t][['season', 'week', 'game_id', 'away_coach']].rename(columns={'away_coach': 'c'})]).sort_values(['season', 'week'])
        prev_c, prev_s, last_season_c = None, None, {}
        for r in side.itertuples():
            if prev_s is not None and r.season != prev_s: last_season_c[r.season] = prev_c
            new = float(r.season in last_season_c and r.c != last_season_c[r.season])
            mid = float(prev_s == r.season and prev_c is not None and r.c != prev_c)
            rows.append((r.game_id, t, new, mid)); prev_c, prev_s = r.c, r.season
    c = pd.DataFrame(rows, columns=['game_id', 'team', 'newcoach', 'midchange'])
    # mid-season change flag persists for the rest of that season
    c = c.merge(g[['game_id', 'season', 'week']], on='game_id')
    c['midchange'] = c.sort_values('week').groupby(['season', 'team']).midchange.cummax()
    return c.set_index(['game_id', 'team'])


def build_extra(f, g, tg, cache=True):
    path = os.path.join(DATA, 'features', 'extra.pkl')
    if cache and os.path.exists(path) and os.path.getmtime(path) > os.path.getmtime(f'{DATA}/team_games_x.csv') \
            and os.path.getmtime(path) > os.path.getmtime(f'{DATA}/games.csv'):
        x = pd.read_pickle(path)
        if len(x) == len(f): return f.merge(x, on='game_id', how='left')
    t = team_game_frame(g, tg); F0 = 2008; X = pd.DataFrame({'game_id': f.game_id.values})
    E = lambda num, den, **kw: rate_ratings(t, num, den, g, F0, **kw)
    # --- EPA variants (opponent-adjusted)
    for nm, num, den in (('epa_early', 'epa_early', 'n_early'), ('epa_rz', 'epa_rz', 'n_rz'), ('epa_to50', 'epa_to50', 'n'),
                         ('epa_fl50', 'epa_fl50', 'n'), ('epa_noto', 'epa_noto', 'n'), ('epa_pass', 'pass_epa', 'pass_plays'),
                         ('epa_run', 'rush_epa', 'pass_rush_n'), ('epa_gt', 'epa_gt', 'plays_gt')):
        R = E(num, den)
        X[nm + '_d'] = diff(f, R, 0); X[nm + '_off_d'] = diff(f, R, 1); X[nm + '_def_d'] = diff(f, R, 2)
    X['epa_raw_d'] = diff(f, E('epa', 'plays', opp=False), 0) - diff(f, rate_ratings(t.assign(team=t.opp), 'epa', 'plays', g, F0, opp=False), 0)
    # --- play calling / style (plain decayed team averages)
    for nm, num, den in (('proe', 'proe', 'n_neu'), ('pace', 'secs', 'n_pace'), ('nohuddle', 'no_huddle', 'n'), ('go4', 'go4', 'n4'),
                         ('pen', 'pen_yds', 'one'), ('st', 'st_epa', 'one'), ('close_luck', 'close_luck', 'one'), ('fum_luck', 'fum_luck', 'one')):
        X[nm + '_d'] = diff(f, E(num, den, opp=False, hl=6.0, lam=3.0), 0)
    X['st_opp_d'] = diff(f, E('st_epa', 'one', hl=6.0), 0)                    # special teams, opponent-adjusted
    X['pen_long_d'] = diff(f, E('pen_yds', 'one', opp=False, hl=20.0, off=0.0, lam=3.0), 0)
    X['close_luck_season_d'] = diff(f, E('close_luck', 'one', opp=False, hl=50.0, off=200.0, lam=0.5), 0)   # ~season-to-date
    # --- player-level injuries
    pj = player_injury_features(g)
    for c in pj.columns:
        hv = [pj[c].get((r.season, r.week, r.home_team), 0.0) for r in f.itertuples()]
        av = [pj[c].get((r.season, r.week, r.away_team), 0.0) for r in f.itertuples()]
        X[c + '_d'] = np.array(hv) - np.array(av)
    # --- coaching
    cf = coach_features(g)
    for c in ('newcoach', 'midchange'):
        X[c + '_d'] = [cf[c].get((r.game_id, r.home_team), 0.0) - cf[c].get((r.game_id, r.away_team), 0.0) for r in f.itertuples()]
    # --- nfelo (538-style Elo and QB-Elo, pre-game)
    canon = {'OAK': 'LV', 'SD': 'LAC', 'STL': 'LA', 'LAR': 'LA', 'WSH': 'WAS', 'JAC': 'JAX'}
    key = lambda gid: '_'.join(p if i < 2 else canon.get(p, p) for i, p in enumerate(str(gid).split('_')))
    ne = pd.read_csv(f'{DATA}/nfelo.csv'); ne['game_id'] = ne.game_id.map(key); ne = ne.drop_duplicates('game_id').set_index('game_id')
    ne['t1'] = FIX(ne.team1)
    m = ne.reindex(f.game_id.map(key).values)
    flip = (m.t1.values != f.home_team.values)
    eh = np.where(flip, m.qbelo2_pre + m.qb2_adj, m.qbelo1_pre + m.qb1_adj); ea = np.where(flip, m.qbelo1_pre + m.qb1_adj, m.qbelo2_pre + m.qb2_adj)
    X['nfelo_qb_d'] = (eh - ea) / 25.0
    ph = np.where(flip, 1 - m.qbelo_prob1, m.qbelo_prob1)
    X['nfelo_prob'] = ph
    from scipy.stats import norm
    X['nfelo_pts'] = norm.ppf(np.clip(ph, 0.01, 0.99)) * 13.5        # nfelo's own forecast as a margin
    X.to_pickle(path)
    return f.merge(X, on='game_id', how='left')


def team_extra_ratings(g, tg, season):
    """Per-team special-teams and 4th-down ratings for each week of `season` (same settings as build_extra)."""
    t = team_game_frame(g, tg)
    st = rate_ratings(t, 'st_epa', 'one', g, season, opp=False, hl=6.0, lam=3.0)
    go = rate_ratings(t, 'go4', 'n4', g, season, opp=False, hl=6.0, lam=3.0)
    return st, go


def nfelo_team_points(g, season, week):
    """Each team's latest nfelo QB-Elo before `week`, as points vs an average team on a neutral field."""
    from scipy.stats import norm
    n = pd.read_csv(f'{DATA}/nfelo.csv'); n = n[n.season == season]
    n['week'] = n.game_id.str.split('_').str[1].astype(int)
    n = n[n.week <= week].sort_values('week')
    v = {}
    for r in n.itertuples():
        v[FIX(pd.Series([r.team1]))[0]] = r.qbelo1_pre + r.qb1_adj; v[FIX(pd.Series([r.team2]))[0]] = r.qbelo2_pre + r.qb2_adj
    if not v: return {t: 0.0 for t in TEAMS}
    mu = np.mean(list(v.values()))
    return {t: float(norm.ppf(1 / (1 + 10 ** (-(v.get(t, mu) - mu) / 400))) * 13.5) for t in TEAMS}


def adjusted_line(f, season, feats=('st_opp_d', 'mkt_d')):
    """Closing line + small fitted adjustment (fit on 2010..season-1). Returns (pred, sigma, coefs) for that season's rows."""
    from scipy.stats import norm
    tr = f[(f.season >= 2010) & (f.season < season) & f.result.notna() & (f.game_type == 'REG') & f.spread_line.notna()]
    X = np.nan_to_num(tr[list(feats)].values.astype(float)); y = (tr.result - tr.spread_line).values
    b = np.linalg.lstsq(X, y, rcond=None)[0]; sig = float(np.sqrt(np.mean((y - X @ b) ** 2)))
    te = f[(f.season == season) & (f.game_type == 'REG')].copy()
    te['adj'] = np.nan_to_num(te[list(feats)].values.astype(float)) @ b
    te['pred_adj'] = te.spread_line + te.adj; te['prob_adj'] = norm.cdf(te.pred_adj / sig)
    return te, sig, dict(zip(feats, b))
