"""New model: walk-forward ratings -> per-game features -> linear blend fit only on earlier seasons.

predict margin (home - away) = sum_k beta_k * feature_k ; betas re-fit before every test season using only past seasons.
win probability = Phi(margin / sigma), sigma = residual SD on the training seasons.
"""
import json, os, hashlib
import numpy as np, pandas as pd
from scipy.stats import norm
from nflmodel.common import TEAMS, TIDX, DATA, INPUTS, load_games, FRANCHISE
from nflmodel.ratings import market_ratings, results_ratings, epa_ratings, load_team_games, qb_values

FIRST_RATED = 2008   # ratings warm up on 2006-07 games
CACHE = os.path.join(DATA, 'features'); os.makedirs(CACHE, exist_ok=True)

DEFAULT = dict(m_hl=4.0, m_off=6.0, m_lam=2.0,
               r_hl=6.0, r_off=10.0, r_lam=8.0,
               e_hl=8.0, e_off=10.0, e_lam=10.0, e_gt=True,
               qb_hl=40.0, qb_prior_n=250.0, qb_prior=-0.05)


def _key(p):
    return hashlib.md5(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10]


def apply_qb_overrides(g, path=None):
    """data/qb_overrides.csv (season,week,team,qb_name): who will START an upcoming game. nflverse only fills the
    starting QB once a game is played, so without an override the model assumes last game's starter."""
    path = path or os.path.join(INPUTS, 'qb_overrides.csv')
    if not os.path.exists(path): return g
    o = pd.read_csv(path, comment='#')
    if o.empty: return g
    names = pd.concat([g[['home_qb_name', 'home_qb_id']].set_axis(['n', 'i'], axis=1), g[['away_qb_name', 'away_qb_id']].set_axis(['n', 'i'], axis=1)]).dropna()
    nm = names.drop_duplicates('n', keep='last').set_index('n').i.to_dict()
    for r in o.itertuples():
        t = FRANCHISE.get(r.team, r.team); t = {'LAR': 'LA', 'WSH': 'WAS'}.get(t, t)
        pid = nm.get(r.qb_name, 'override:' + r.qb_name)   # unknown QB (e.g. debut) -> treated as replacement level
        m = (g.season == r.season) & (g.week == r.week)
        g.loc[m & (g.home_team == t), 'home_qb_id'] = pid; g.loc[m & (g.away_team == t), 'away_qb_id'] = pid
        g.loc[m & (g.home_team == t), 'home_qb_name'] = r.qb_name; g.loc[m & (g.away_team == t), 'away_qb_name'] = r.qb_name
    return g


def load_all():
    g = apply_qb_overrides(load_games())
    tg = load_team_games(f'{DATA}/team_games.csv', g)
    qbg = pd.read_csv(f'{DATA}/qb_games.csv')
    inj = pd.read_csv(f'{DATA}/injury_out.csv') if os.path.exists(f'{DATA}/injury_out.csv') else None
    return g, tg, qbg, inj


def injury_features(g, inj):
    """Sum of snap shares of players ruled Out/Doubtful (QBs excluded: handled by the QB feature)."""
    if inj is None:
        return pd.DataFrame(columns=['season', 'week', 'team', 'inj_off', 'inj_def'])
    x = inj[inj.pos != 'QB'].copy()
    x['team'] = x.team.replace(FRANCHISE).replace({'LAR': 'LA', 'JAC': 'JAX', 'WSH': 'WAS'})
    w = np.where(x.status == 'Doubtful', 0.75, 1.0)
    x['inj_off'] = x.off_share * w; x['inj_def'] = x.def_share * w
    return x.groupby(['season', 'week', 'team'])[['inj_off', 'inj_def']].sum().reset_index()


def build_features(p=None, data=None, force=False):
    p = dict(DEFAULT, **(p or {}))
    path = os.path.join(CACHE, f'feat_{_key(p)}.pkl')
    g, tg, qbg, inj = data or load_all()
    srcs = [f'{DATA}/{x}' for x in ('games.csv', 'starters.csv', 'qb_games.csv') if os.path.exists(f'{DATA}/{x}')] + [os.path.join(INPUTS, 'qb_overrides.csv')]
    newest = max(os.path.getmtime(x) for x in srcs if os.path.exists(x))
    if not force and os.path.exists(path) and os.path.getmtime(path) > newest:
        return pd.read_pickle(path)
    M = market_ratings(g, FIRST_RATED, p['m_hl'], p['m_off'], p['m_lam'])
    R = results_ratings(g, FIRST_RATED, p['r_hl'], p['r_off'], p['r_lam'])
    E = epa_ratings(tg, FIRST_RATED, p['e_hl'], p['e_off'], p['e_lam'], gt=p['e_gt'], schedule=g)
    SR = epa_ratings(tg, FIRST_RATED, p['e_hl'], p['e_off'], p['e_lam'] * 0.25, gt=p['e_gt'], metric='succ', schedule=g)
    Mf = market_ratings(g, FIRST_RATED, 1.5, 30.0, p['m_lam'])          # 'recent form' versions: short memory
    Ef = epa_ratings(tg, FIRST_RATED, 3.0, 30.0, p['e_lam'], gt=p['e_gt'], schedule=g)
    # warm/dome teams: home stadium indoor or south of 34N latitude (season by season)
    from nflmodel.common import STADIUMS
    hg = g[g.location == 'Home'].groupby(['season', 'home_team']).agg(sid=('stadium_id', lambda x: x.value_counts().index[0]),
                                                                     ind=('indoor', 'mean'))
    warm = {k: float(v.ind > 0.5 or STADIUMS[v.sid][0] < 34.0) for k, v in hg.iterrows()}
    Q = qb_values(g, qbg, p['qb_hl'], 10.0, p['qb_prior_n'], p['qb_prior']).set_index('game_id')
    IJ = injury_features(g, inj).set_index(['season', 'week', 'team'])
    rows = []
    gg = g[g.season >= FIRST_RATED]
    # bye: team did not play the previous week of the same season (week > 1)
    pw = {(r.season, r.week): set() for r in gg.itertuples()}
    for r in gg.itertuples(): pw[(r.season, r.week)].update([r.home_team, r.away_team])
    for r in gg.itertuples():
        k = (r.season, r.week)
        if k not in M or k not in E: continue
        hi, ai = TIDX[r.home_team], TIDX[r.away_team]
        mr, mh = M[k]; rr, rh = R.get(k, (np.zeros(len(TEAMS)), 0))
        en, eo, ed = E[k]; sn = SR[k][0]
        q = Q.loc[r.game_id]
        fm = Mf.get(k, (np.zeros(len(TEAMS)), 0))[0]; fe = Ef.get(k, (np.zeros(len(TEAMS)),))[0]
        wa = warm.get((r.season, r.away_team), warm.get((r.season - 1, r.away_team), 0.0))
        wh = warm.get((r.season, r.home_team), warm.get((r.season - 1, r.home_team), 0.0))
        cold = float(r.indoor == 0 and not np.isnan(r.temp) and r.temp <= 35)
        def inj_(t, c):
            try: return float(IJ.loc[(r.season, r.week, t), c])
            except KeyError: return 0.0
        bye = lambda t: float(r.week > 1 and (r.season, r.week - 1) in pw and t not in pw[(r.season, r.week - 1)])
        rows.append(dict(
            game_id=r.game_id, season=r.season, week=r.week, game_type=r.game_type, home_team=r.home_team, away_team=r.away_team,
            result=r.result, spread_line=r.spread_line, total_line=r.total_line, home_moneyline=r.home_moneyline, away_moneyline=r.away_moneyline,
            home=1.0 - r.neutral, mkt_hfa=mh, mkt_d=mr[hi] - mr[ai], res_d=rr[hi] - rr[ai],
            epa_d=en[hi] - en[ai], epa_off_d=eo[hi] - eo[ai], epa_def_d=ed[hi] - ed[ai], sr_d=sn[hi] - sn[ai],
            qb_h=q.qb_h - q.qbbase_h, qb_a=q.qb_a - q.qbbase_a, qbid_h=q.qbid_h, qbid_a=q.qbid_a,
            inj_off_d=inj_(r.home_team, 'inj_off') - inj_(r.away_team, 'inj_off'),
            inj_def_d=inj_(r.home_team, 'inj_def') - inj_(r.away_team, 'inj_def'),
            inj_avail=float(r.season >= 2013),
            rest_d=float(np.clip((r.home_rest - r.away_rest) if r.week > 1 else 0, -7, 7)),
            bye_d=bye(r.home_team) - bye(r.away_team),
            short_d=float(r.home_rest <= 5) - float(r.away_rest <= 5) if r.week > 1 else 0.0,
            miles_d=(r.miles_a - r.miles_h) / 1000.0,
            tz_d=abs(r.tz_a) - abs(r.tz_h),
            clock_d=float(r.tz_a >= 2 and r.ko_local <= 13.6) - float(r.tz_h >= 2 and r.ko_local <= 13.6),
            night_west=float(r.tz_a <= -2 and r.ko_clock_a >= 20) - float(r.tz_h <= -2 and r.ko_clock_h >= 20),
            mkt_fast_d=fm[hi] - fm[ai], epa_fast_d=fe[hi] - fe[ai],
            cold_warm_d=cold * (wa - (wh if r.neutral else 0.0)),
            div=float(r.div), wind=r.wind, temp=r.temp, indoor=r.indoor, neutral=r.neutral))
    f = pd.DataFrame(rows)
    f['qb_d'] = f.qb_h - f.qb_a
    f.to_pickle(path)
    return f


def design(f, feats):
    """Feature matrix. Derived/interaction features are built here."""
    X = pd.DataFrame(index=f.index)
    wk = f.week.clip(upper=18)
    early = np.exp(-(wk - 1) / 4.0)   # 1 in week 1, 0.47 in week 4, 0.1 in week 10
    for k in feats:
        if k == 'mkt_hfa_home': X[k] = f.mkt_hfa * f.home
        elif k == 'mkt_d_early': X[k] = f.mkt_d * early
        elif k == 'epa_d_early': X[k] = f.epa_d * early
        elif k == 'mkt_d_div': X[k] = f.mkt_d * f['div']
        elif k == 'wind_x_epa': X[k] = f.wind.fillna(0).clip(upper=30) * f.epa_d
        elif k == 'wind_x_mkt': X[k] = (f.wind.fillna(0).clip(upper=30) > 15) * f.mkt_d
        elif k == 'inj_off_d': X[k] = f.inj_off_d
        elif k == 'inj_def_d': X[k] = f.inj_def_d
        else: X[k] = f[k].astype(float).fillna(0)
    return X


def walk_forward(f, feats, test_seasons, train_from=2009, ridge=0.0, reg_only_train=True, weight_recent=None, sigma_early=False):
    """Fit betas on seasons < S, predict season S. Returns DataFrame with pred, prob."""
    out = []
    for S in test_seasons:
        tr = f[(f.season >= train_from) & (f.season < S) & f.result.notna()]
        if reg_only_train: tr = tr[tr.game_type == 'REG']
        te = f[(f.season == S) & (f.game_type == 'REG')].copy()
        if te.empty: continue
        X = design(tr, feats).values; y = tr.result.values
        w = np.ones(len(y)) if weight_recent is None else 0.5 ** ((S - 1 - tr.season.values) / weight_recent)
        A = X.T @ (X * w[:, None]) + ridge * np.eye(X.shape[1])
        b = np.linalg.lstsq(A, X.T @ (w * y), rcond=None)[0]   # lstsq: features absent in early training seasons get 0
        sigma = np.sqrt(np.average((y - X @ b) ** 2, weights=w))
        te['pred'] = design(te, feats).values @ b
        te['sigma'] = sigma
        if sigma_early:   # separate result-spread for weeks 1-4 (ratings least certain then)
            e = tr.week.values <= 4; r2 = (y - X @ b) ** 2
            s1 = np.sqrt(np.average(r2[e], weights=w[e])); s2 = np.sqrt(np.average(r2[~e], weights=w[~e]))
            te['sigma'] = np.where(te.week <= 4, s1, s2)
        te['prob'] = norm.cdf(te.pred / te.sigma)
        for k, v in zip(feats, b): te['b_' + k] = v
        out.append(te)
    return pd.concat(out) if out else pd.DataFrame()
