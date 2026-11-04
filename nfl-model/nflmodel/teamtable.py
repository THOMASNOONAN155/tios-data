"""Team-by-week table: every rating component for every team BEFORE each week (walk-forward), plus the model's
power score using that season's walk-forward weights. Used for power rankings, strength of schedule and simulation."""
import os
import numpy as np, pandas as pd
from scipy.stats import norm
from nflmodel.common import TEAMS, TIDX, DATA, config
from nflmodel.ratings import market_ratings, results_ratings, epa_ratings
from nflmodel.extra import team_game_frame, rate_ratings, FIX
from nflmodel.features import walk_forward

N = len(TEAMS)


def nfelo_team_table(g):
    """Latest nfelo QB-Elo (and plain Elo) for each team before each (season, week), in points vs average."""
    n = pd.read_csv(f'{DATA}/nfelo.csv')
    n['week'] = n.game_id.str.split('_').str[1].astype(int)
    rows = []
    for c in ('1', '2'):
        x = n[['season', 'week', 'team' + c, 'qbelo' + c + '_pre', 'qb' + c + '_adj', 'elo' + c + '_pre']].copy()
        x.columns = ['season', 'week', 'team', 'qbelo', 'qbadj', 'elo']; rows.append(x)
    x = pd.concat(rows); x['team'] = FIX(x.team); x['val'] = x.qbelo + x.qbadj
    out = {}
    for (s, w), grp in x.groupby(['season', 'week']):
        out[(s, w)] = grp.set_index('team')
    return x


def build_team_table(f, data, seasons, cfg=None):
    """f: feature frame (build_features + build_extra). Returns long DataFrame (season, week, team, components, power)."""
    cfg = cfg or config(); P = cfg['ratings']; g, tg = data[0], data[1]
    first = min(seasons)
    M = market_ratings(g, first, P['m_hl'], P['m_off'], P['m_lam'])
    R = results_ratings(g, first, P['r_hl'], P['r_off'], P['r_lam'])
    E = epa_ratings(tg, first, P['e_hl'], P['e_off'], P['e_lam'], gt=P['e_gt'], schedule=g)
    t = team_game_frame(g, tg)
    ST = rate_ratings(t, 'st_epa', 'one', g, first, opp=False, hl=6.0, lam=3.0)
    GO = rate_ratings(t, 'go4', 'n4', g, first, opp=False, hl=6.0, lam=3.0)
    wf = walk_forward(f, cfg['features'], seasons, **cfg.get('opts', {}))
    betas = wf.groupby('season').first()[[c for c in wf.columns if c.startswith('b_')]]
    sig = wf.groupby('season').sigma.first()
    nf = nfelo_team_table(g)
    # this week's QB adjustment for teams that play (from the game rows)
    qb = pd.concat([f[['season', 'week', 'home_team', 'qb_h']].set_axis(['season', 'week', 'team', 'qb'], axis=1),
                    f[['season', 'week', 'away_team', 'qb_a']].set_axis(['season', 'week', 'team', 'qb'], axis=1)])
    qb = qb.groupby(['season', 'week', 'team']).qb.first()
    rows = []
    for s in seasons:
        if s not in betas.index: continue
        b = betas.loc[s]; maxw = int(g[(g.season == s) & (g.game_type == 'REG')].week.max())
        ns = nf[nf.season == s].sort_values('week')
        for w in range(1, maxw + 1):
            k = (s, w)
            if k not in M or k not in E: continue
            # nfelo value: each team's latest pre-game value up to this week (prior season's last value in week 1 if needed)
            last = ns[ns.week <= w].groupby('team').val.last()
            if last.empty:
                prev = nf[nf.season == s - 1].groupby('team').val.last(); last = prev
            mu = last.mean()
            nfp = np.array([norm.ppf(1 / (1 + 10 ** (-(last.get(tm, mu) - mu) / 400))) * 13.5 for tm in TEAMS])
            comp = dict(market=b.b_mkt_d * M[k][0], results=b.b_res_d * R[k][0], epa_off=b.b_epa_off_d * E[k][1],
                        epa_def=b.b_epa_def_d * E[k][2], special_teams=b.b_st_d * ST[k][0] if k in ST else np.zeros(N),
                        fourth_down=b.b_go4_d * GO[k][0] if k in GO else np.zeros(N), nfelo=b.b_nfelo_pts * nfp)
            for i, tm in enumerate(TEAMS):
                r = dict(season=s, week=w, team=tm, **{c: float(v[i]) for c, v in comp.items()})
                r['mkt_raw'] = float(M[k][0][i]); r['res_raw'] = float(R[k][0][i]); r['epa_raw'] = float(E[k][0][i])
                r['epa_off_raw'] = float(E[k][1][i]); r['epa_def_raw'] = float(E[k][2][i]); r['nfelo_raw'] = float(nfp[i])
                q = qb.get((s, w, tm), np.nan)
                r['qb_now'] = float(b.b_qb_d * q) if not np.isnan(q) else np.nan
                r['hfa'] = float(b.b_home); r['sigma'] = float(sig.loc[s])
                rows.append(r)
    T = pd.DataFrame(rows)
    T['power'] = T[['market', 'results', 'epa_off', 'epa_def', 'special_teams', 'fourth_down', 'nfelo']].sum(1)
    # QB adjustment carried for bye weeks: last known value this season
    T = T.sort_values(['season', 'team', 'week'])
    T['qb_now'] = T.groupby(['season', 'team']).qb_now.ffill().fillna(0.0)
    T['power_qb'] = T.power + T.qb_now
    return T.sort_values(['season', 'week', 'team']).reset_index(drop=True)
