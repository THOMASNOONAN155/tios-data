"""Monte Carlo simulation of the rest of a regular season, and actual playoff outcomes for calibration.

Each simulation: every team gets one hidden strength error ~ N(0, tau) for the rest of the season (so a team that is
really better than its rating wins more of ALL its remaining games), then each game's margin ~ N(expected, game_sd).
Expected margin = power(home) - power(away) + home field (0 at neutral sites), using ratings known before `week`.
Tiebreakers are simplified: wins, then division win %, then conference win %, then a coin flip
(the NFL's head-to-head, common-games and strength-of-victory steps are not modelled).
"""
import numpy as np, pandas as pd
from nflmodel.common import TEAMS, TIDX, DIVISIONS

N = len(TEAMS)
DIV_OF = {t: d for d, v in DIVISIONS.items() for t in v.split()}
CONF_OF = {t: d.split()[0] for t, d in DIV_OF.items()}
DIV_LIST = sorted(DIVISIONS)


def simulate(games, season, week, power, hfa, sigma, tau=2.0, n=5000, seed=0, return_sims=False):
    """games: games.csv frame (franchise-mapped). power: dict team -> rating (points). Returns per-team summary DataFrame."""
    rng = np.random.default_rng(seed)
    g = games[(games.season == season) & (games.game_type == 'REG')]
    done = g[(g.week < week) & g.result.notna()]; todo = g[~g.index.isin(done.index)]
    h = todo.home_team.map(TIDX).values; a = todo.away_team.map(TIDX).values
    pw = np.array([power[t] for t in TEAMS])
    mean = pw[h] - pw[a] + hfa * (1 - todo.neutral.values)
    gsd = np.sqrt(max(sigma ** 2 - 2 * tau ** 2, 25.0))
    Z = rng.normal(0, tau, (n, N)) if tau > 0 else np.zeros((n, N))
    marg = mean[None, :] + Z[:, h] - Z[:, a] + rng.normal(0, gsd, (n, len(todo)))
    hw = (marg > 0).astype(float)
    # accumulate wins / division wins / conference wins (games played so far count for real)
    def onehot(idx):
        M = np.zeros((len(idx), N)); M[np.arange(len(idx)), idx] = 1; return M
    Hm, Am = onehot(h), onehot(a)
    div_g = np.array([DIV_OF[x] == DIV_OF[y] for x, y in zip(todo.home_team, todo.away_team)], float)
    conf_g = np.array([CONF_OF[x] == CONF_OF[y] for x, y in zip(todo.home_team, todo.away_team)], float)
    wins = hw @ Hm + (1 - hw) @ Am
    dw = (hw * div_g) @ Hm + ((1 - hw) * div_g) @ Am; dn = div_g @ Hm + div_g @ Am
    cw = (hw * conf_g) @ Hm + ((1 - hw) * conf_g) @ Am; cn = conf_g @ Hm + conf_g @ Am
    base_w = np.zeros(N); base_dw = np.zeros(N); base_dn = np.zeros(N); base_cw = np.zeros(N); base_cn = np.zeros(N)
    for r in done.itertuples():
        hi, ai = TIDX[r.home_team], TIDX[r.away_team]; res = 1.0 if r.result > 0 else 0.0 if r.result < 0 else 0.5
        base_w[hi] += res; base_w[ai] += 1 - res
        if DIV_OF[r.home_team] == DIV_OF[r.away_team]:
            base_dw[hi] += res; base_dw[ai] += 1 - res; base_dn[hi] += 1; base_dn[ai] += 1
        if CONF_OF[r.home_team] == CONF_OF[r.away_team]:
            base_cw[hi] += res; base_cw[ai] += 1 - res; base_cn[hi] += 1; base_cn[ai] += 1
    W = wins + base_w
    score = W + 0.01 * (dw + base_dw) / np.maximum(dn + base_dn, 1) + 0.001 * (cw + base_cw) / np.maximum(cn + base_cn, 1) + 1e-5 * rng.random((n, N))
    n_wc = 3 if season >= 2020 else 2
    divwin = np.zeros((n, N)); playoff = np.zeros((n, N)); seed1 = np.zeros((n, N)); bye = np.zeros((n, N))
    for conf in ('AFC', 'NFC'):
        winners = []
        for d in DIV_LIST:
            if not d.startswith(conf): continue
            idx = np.array([TIDX[t] for t in DIVISIONS[d].split()])
            win = idx[np.argmax(score[:, idx], axis=1)]; winners.append(win)
            divwin[np.arange(n), win] = 1
        winners = np.stack(winners, 1)                            # n x 4
        ws = np.take_along_axis(score, winners, 1)
        order = np.argsort(-ws, 1); seeds = np.take_along_axis(winners, order, 1)
        seed1[np.arange(n), seeds[:, 0]] = 1
        bye[np.arange(n), seeds[:, 0]] = 1
        if season < 2020: bye[np.arange(n), seeds[:, 1]] = 1
        cidx = np.array([TIDX[t] for t in TEAMS if CONF_OF[t] == conf])
        sc = score[:, cidx].copy(); isw = divwin[:, cidx] == 1; sc[isw] = -1e9
        wc = cidx[np.argsort(-sc, 1)[:, :n_wc]]
        for k in range(n_wc): playoff[np.arange(n), wc[:, k]] = 1
        playoff[divwin == 1] = 1
    out = pd.DataFrame({'team': TEAMS, 'wins_now': base_w, 'exp_wins': W.mean(0), 'wins_p10': np.percentile(W, 10, 0),
                        'wins_p90': np.percentile(W, 90, 0), 'p_division': divwin.mean(0), 'p_playoffs': playoff.mean(0),
                        'p_seed1': seed1.mean(0), 'p_bye': bye.mean(0)})
    if return_sims:
        return out, dict(W=W, playoff=playoff, hw=hw, todo=todo)
    return out


def actual_outcomes(games, season):
    """Real division winners, playoff teams, byes and #1 seeds (from who played in which playoff round), and final wins."""
    g = games[games.season == season]
    reg = g[(g.game_type == 'REG') & g.result.notna()]
    wins = {t: 0.0 for t in TEAMS}
    for r in reg.itertuples():
        res = 1.0 if r.result > 0 else 0.0 if r.result < 0 else 0.5
        wins[r.home_team] += res; wins[r.away_team] += 1 - res
    wc = g[g.game_type == 'WC']; dv = g[g.game_type == 'DIV']
    if wc.empty: return None
    wc_t = set(wc.home_team) | set(wc.away_team); dv_t = set(dv.home_team) | set(dv.away_team)
    byes = dv_t - wc_t; divw = set(wc.home_team) | byes; po = wc_t | byes
    seed1 = byes if season >= 2020 else set()
    return pd.DataFrame({'team': TEAMS, 'wins': [wins[t] for t in TEAMS], 'division': [t in divw for t in TEAMS],
                         'playoffs': [t in po for t in TEAMS], 'seed1': [t in seed1 for t in TEAMS], 'bye': [t in byes for t in TEAMS]})


def game_leverage(sims, n_top=5):
    """Upcoming games whose result swings playoff chances the most (difference in P(playoffs) win vs lose, both teams)."""
    hw, todo, po = sims['hw'], sims['todo'], sims['playoff']
    wk = todo.week.min(); rows = []
    for j, r in enumerate(todo.itertuples()):
        if r.week != wk: continue
        m = hw[:, j] == 1
        if m.all() or (~m).all(): continue
        hi, ai = TIDX[r.home_team], TIDX[r.away_team]
        dh = po[m, hi].mean() - po[~m, hi].mean(); da = po[~m, ai].mean() - po[m, ai].mean()
        rows.append(dict(game_id=r.game_id, home=r.home_team, away=r.away_team, swing_home=dh, swing_away=da, total=dh + da))
    return pd.DataFrame(rows).sort_values('total', ascending=False).head(n_top)
