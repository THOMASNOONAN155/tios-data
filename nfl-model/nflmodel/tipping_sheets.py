"""Everything shown on the tipping sheets, computed from the inputs (no spreadsheet formulas needed to get the numbers).
compute() -> ctx dict used by the workbook writer; original_cells(ctx) -> {sheet: {cell: value}} for checking against the
original workbook's own numbers (research/verify_tipping.py)."""
import os
import numpy as np, pandas as pd
from nflmodel.common import DATA, INPUTS
from nflmodel import tipping as T
from nflmodel.tipping_stats import records, race, week_meta

NW = T.NW


def load_table():
    p = os.path.join(INPUTS, 'tipping_spread_table.csv')
    t = pd.read_csv(p, comment='#', index_col=0); t.columns = [int(float(c)) for c in t.columns]; t.index = t.index.astype(float)
    return t


def wl(w, l, p=None):
    return f'{int(w)}–{int(l)}' + (f'–{int(p)}' if p is not None else '')


def money_text(x, dec=0):
    if x is None or (isinstance(x, float) and np.isnan(x)): return '–'
    return ('+' if x >= 0 else '-') + '$' + (f'{abs(x):,.{dec}f}')


def compute(inp, include_new=True, model_picks=None, model_probs=None):
    S = inp['settings']; table = load_table()
    G = T.add_value(T.game_log(inp), inp, table)
    P = T.picks(G, inp, model_picks, include_new)
    names = [n for n, _ in inp['tippers']]; you = names[0]
    typed_bots = [n for n, o in inp['tippers'][1:] if str(o).strip() == 'Bot']
    experts = [n for n in names[1:] if n not in typed_bots]
    R, W, N, meta, last = records(G, P, S, experts)
    ctx = dict(inp=inp, S=S, G=G, P=P, R=R, W=W, N=N, meta=meta, last=last, you=you, experts=experts, outlets=T.outlets(inp, P),
               race=race(G, P, W, meta, experts, you), model_probs=model_probs, table=table)
    ctx['money'] = money(ctx); ctx['spreads'] = spreads_totals(ctx); ctx['mystats'] = my_stats(ctx)
    ctx['scout'] = scout(ctx); ctx['h2h'] = head_to_head(ctx, S.get('h2h')); ctx['value'] = value_report(ctx)
    ctx['edge'] = edge_finder(ctx, S.get('edge_week')); ctx['money_x'] = money_extra(ctx)
    return ctx


# ------------------------------------------------------------------ Money (real money: tips + spreads + O/U, locks at x stake)
def money(ctx):
    G, S, meta = ctx['G'], ctx['S'], ctx['meta']; rows = []; run = 0.0; high = 0.0
    for wk in range(1, NW + 1):
        g = G[G.week == wk]
        if meta.played[wk] == 0 and not g.tip_res.notna().any():
            rows.append(dict(week=wk)); continue
        t = g[g.tip_res.notna()]; s = g[g.sp_res.notna()]; o = g[g.ou_res.notna()]
        d = dict(week=wk, tip_w=(t.tip_res == '✓').sum(), tip_l=(t.tip_res == '✗').sum(), tip_staked=(S['tip'] * t.tip_lock).sum(), tip_pl=t.tip_pl_real.sum(),
                 sp_w=(s.sp_res == '✓').sum(), sp_l=(s.sp_res == '✗').sum(), sp_p=(s.sp_res == 'Push').sum(), sp_staked=(S['spread'] * s.sp_lock).sum(), sp_pl=s.sp_pl_real.sum(),
                 ou_w=(o.ou_res == '✓').sum(), ou_l=(o.ou_res == '✗').sum(), ou_p=(o.ou_res == 'Push').sum(), ou_staked=(S['ou'] * o.ou_lock).sum(), ou_pl=o.ou_pl_real.sum())
        d['staked'] = d['tip_staked'] + d['sp_staked'] + d['ou_staked']; d['pl'] = d['tip_pl'] + d['sp_pl'] + d['ou_pl']
        d['returned'] = d['staked'] + d['pl']; run += d['pl']; high = max(high, run)
        d.update(running=run, high=high, below=run - high)
        rows.append(d)
    return pd.DataFrame(rows).set_index('week')


# ------------------------------------------------------------------ shared helpers
def table_stats(sub, win, graded, prob, pl, staked=None):
    """The standard 'Picks / W / L / Win % / Odds said / +/- wins / P/L / ROI' row used across the original sheets."""
    n = int(graded.sum()); w = int((win & graded).sum())
    if n == 0: return dict(n=0, w=0, l=0, pct=np.nan, said=np.nan, plus=np.nan, pl=float(np.nansum(pl)), roi=np.nan)
    said = float(np.nansum(prob[graded])) / n
    p = float(np.nansum(pl))
    return dict(n=n, w=w, l=n - w, pct=w / n, said=said, plus=w - said * n, pl=p, roi=p / (staked if staked else 1))


def streaks(flags):
    """flags: list of +1 win / -1 loss / 0 not graded (in game order). Returns (current, longest win, longest loss)."""
    cur, best, worst = 0, 0, 0
    for f in flags:
        if f == 0: continue
        cur = (cur + 1 if cur > 0 else 1) if f > 0 else (cur - 1 if cur < 0 else -1)
        best, worst = max(best, cur), min(worst, cur)
    return cur, best, -worst


def bank(pl):
    run = np.nancumsum(np.nan_to_num(pl)); peak = np.maximum.accumulate(np.maximum(run, 0)); return run, peak, run - peak


# ------------------------------------------------------------------ Spreads & Totals (flat stakes, as the original sheet)
def spreads_totals(ctx):
    G, S = ctx['G'], ctx['S']; out = {}
    sp = G[G.spread_bet.notna() & G.sp_res.notna()].copy()
    sp['graded'] = sp.sp_res.isin(['✓', '✗']); sp['win'] = sp.sp_res == '✓'
    sp['prob'] = [(1 / r.sp_price) / (1 / r.sp_aprice + 1 / r.sp_hprice) if not np.isnan(r.sp_price) else np.nan for r in sp.itertuples()]
    sp['side'] = np.where(sp.sp_line < 0, 'Laid', np.where(sp.sp_line > 0, 'Took', 'PK'))
    sp['band'] = [('Under 3' if abs(x) < 3 else 'Exactly 3' if abs(x) == 3 else '3.5-6.5' if abs(x) < 7 else '7+') for x in sp.sp_line]
    sp['ha'] = np.where(sp.spread_bet == sp.home, 'Home', 'Away')
    sp['same'] = np.where(sp.tip.isna(), '', np.where(sp.spread_bet == sp.tip, 'Same', 'Other'))
    ou = G[G.ou_bet.notna() & G.ou_res.notna()].copy()
    ou['graded'] = ou.ou_res.isin(['✓', '✗']); ou['win'] = ou.ou_res == '✓'
    ou['prob'] = [(1 / r.ou_price) / (1 / r.o_price + 1 / r.u_price) if not np.isnan(r.ou_price) else np.nan for r in ou.itertuples()]
    ou['band'] = [('Under 40' if x < 40 else '40-44.5' if x < 45 else '45-49.5' if x < 50 else '50+') for x in ou.ou_line]
    def tb(d, mask, stake):
        x = d[mask]; return table_stats(x, x.win, x.graded, x.prob.values, (x.sp_pl if stake == S['spread'] else x.ou_pl).values, stake * x.graded.sum())
    out['sp_rows'] = {k: tb(sp, sp[c] == v, S['spread']) for k, (c, v) in {'Laid the points (favourite)': ('side', 'Laid'), 'Took the points (underdog)': ('side', 'Took'),
                      "Pick'em": ('side', 'PK'), 'Under 3 points': ('band', 'Under 3'), 'Exactly 3': ('band', 'Exactly 3'), '3.5 to 6.5': ('band', '3.5-6.5'),
                      '7 or more': ('band', '7+'), 'Backed the home team': ('ha', 'Home'), 'Backed the away team': ('ha', 'Away'),
                      'Same team as your head-to-head tip': ('same', 'Same'), 'The other team': ('same', 'Other')}.items()}
    out['ou_rows'] = {k: tb(ou, m, S['ou']) for k, m in {'Backed the over': ou.ou_bet == 'Over', 'Backed the under': ou.ou_bet == 'Under',
                      'Under 40': ou.band == 'Under 40', '40 to 44.5': ou.band == '40-44.5', '45 to 49.5': ou.band == '45-49.5', '50 or more': ou.band == '50+',
                      'Prime time': ou.slot_type == 'Prime time', 'Sunday slate': ou.slot_type == 'Sunday slate', 'International': ou.slot_type == 'International',
                      'Division rivals': ou.division, 'Everyone else': ~ou.division}.items()}
    out['sp'], out['ou'] = sp, ou
    wk = []
    for w in range(1, NW + 1):
        a, b = sp[sp.week == w], ou[ou.week == w]
        if len(a) + len(b) == 0: wk.append(dict(week=w)); continue
        wk.append(dict(week=w, sp=wl((a.sp_res == '✓').sum(), (a.sp_res == '✗').sum(), (a.sp_res == 'Push').sum() or None) if len(a) else '', sp_pl=a.sp_pl.sum() if len(a) else np.nan,
                       ou=wl((b.ou_res == '✓').sum(), (b.ou_res == '✗').sum(), (b.ou_res == 'Push').sum() or None) if len(b) else '', ou_pl=b.ou_pl.sum() if len(b) else np.nan,
                       both=(a.sp_pl.sum() if len(a) else 0) + (b.ou_pl.sum() if len(b) else 0)))
    out['weeks'] = pd.DataFrame(wk).set_index('week')
    allg = G.copy(); allg['bet'] = allg.sp_pl.fillna(0) * allg.spread_bet.notna() + allg.ou_pl.fillna(0) * allg.ou_bet.notna()
    has = allg.sp_res.notna() | allg.ou_res.notna()
    run, peak, dd = bank(np.where(has, allg.bet, 0))
    out['peak'], out['dd'] = float(peak.max()) if len(peak) else 0, float(min(0, dd.min())) if len(dd) else 0
    out['sp_streak'] = streaks([1 if r == '✓' else -1 if r == '✗' else 0 for r in G.sp_res])
    out['ou_streak'] = streaks([1 if r == '✓' else -1 if r == '✗' else 0 for r in G.ou_res])
    return out


# ------------------------------------------------------------------ My Stats (your tips, flat $ stake, like the original)
def my_stats(ctx):
    G, S, P, you, experts = ctx['G'], ctx['S'], ctx['P'], ctx['you'], ctx['experts']
    g = G.copy(); g['pick'] = P[you]; g['graded'] = g.pick.notna() & g.winner.notna(); g['win'] = g.graded & (g.pick == g.winner)
    g['odds'] = np.where(g.pick == g.away, g.aodds, np.where(g.pick == g.home, g.hodds, np.nan))
    g['chance'] = (1 / g.odds) / (1 / g.aodds + 1 / g.hodds)
    g['flat_pl'] = np.where(g.graded, np.where(g.win, S['tip'] * (g.odds - 1), -S['tip']), np.nan)
    g.loc[g.graded & g.odds.isna(), 'flat_pl'] = np.nan
    g['band'] = [T.price_band(x) for x in g.odds]
    g['favdog'] = np.where(g.pick.isna(), '', np.where(g.pick == g.fav, 'Fav', 'Dog'))
    g['ha'] = np.where(g.pick == g.home, 'Home', 'Away')
    ex = P[experts]
    g['n_exp'] = ex.notna().sum(axis=1); g['with_you'] = [int((ex.loc[i] == g.at[i, 'pick']).sum()) if g.at[i, 'pick'] else 0 for i in g.index]
    g['lone'] = np.where(g.n_exp > 0, (g.with_you / g.n_exp.replace(0, np.nan)) <= 0.25, False)
    g['cover'] = [('' if not (r.graded and r.ats_graded) else ('Cover' if (r.home_ats if r.pick == r.home else -r.home_ats) > 0 else ('Miss' if (r.home_ats if r.pick == r.home else -r.home_ats) < 0 else 'Push'))) for r in g.itertuples()]
    g['top_share'] = [max((ex.loc[i] == g.at[i, 'away']).sum(), (ex.loc[i] == g.at[i, 'home']).sum()) / g.at[i, 'n_exp'] if g.at[i, 'n_exp'] else np.nan for i in g.index]
    cons = P[T.BOT_CONSENSUS]; g['cons'] = cons
    g['maj_graded'] = g.cons.notna() & g.winner.notna() & g.top_share.notna(); g['maj_right'] = g.maj_graded & (g.cons == g.winner)
    g['vs_cons'] = g.pick.notna() & g.cons.notna() & (g.pick != g.cons)
    def row(m):
        x = g[m & g.graded]; return table_stats(x, x.win, x.graded, x.chance.values, x.flat_pl.values, S['tip'] * len(x))
    out = dict(g=g)
    out['price'] = {k: row(g.band == b) for k, b in (('Heavy favourite (under 1.40)', 'Heavy fav'), ('Favourite (1.40–1.69)', 'Favourite'), ('Slight favourite (1.70–1.99)', 'Slight fav'),
                                                    ('Slight underdog (2.00–2.49)', 'Slight dog'), ('Underdog (2.50–3.49)', 'Underdog'), ('Long shot (3.50+)', 'Long shot'))}
    out['favdog'] = {'Backed the favourite': row(g.favdog == 'Fav'), 'Backed the underdog': row(g.favdog == 'Dog')}
    out['ha'] = {'Backed the home team': row(g.ha == 'Home'), 'Backed the away team': row(g.ha == 'Away')}
    out['slot'] = {'Prime time (TNF / SNF / MNF / kickoff)': row(g.slot_type == 'Prime time'), 'Sunday slate': row(g.slot_type == 'Sunday slate'), 'International': row(g.slot_type == 'International')}
    out['div'] = {'Division rivals': row(g.division), 'Everyone else': row(~g.division)}
    out['experts'] = {'Lone call (25% or fewer of the experts with you)': row(g.lone.astype(bool)), 'With more of the experts': row(~g.lone.astype(bool))}
    out['ats'] = {'Your pick covered': row(g.cover == 'Cover'), "Your pick didn't cover": row(g.cover == 'Miss'), 'Push': row(g.cover == 'Push')}
    crowd = []
    for lab, lo, hi in (('90%+ of them', 0.9, 1.01), ('75–89%', 0.75, 0.9), ('60–74%', 0.6, 0.75), ('Split (under 60%)', 0, 0.6)):
        m = (g.top_share >= lo) & (g.top_share < hi)
        mg = m & g.maj_graded; ag = m & g.vs_cons & g.graded
        crowd.append(dict(label=lab, games=int(mg.sum()), crowd_right=(g.maj_right & m).sum() / mg.sum() if mg.sum() else np.nan,
                          against=f'{int((ag & g.win).sum())} of {int(ag.sum())}' if ag.sum() else 'none yet', pl=float(np.nansum(g.flat_pl[m & g.vs_cons]))))
    out['crowd'] = crowd
    teams = []
    for t in sorted(set(G.away) | set(G.home)):
        b = g[(g.pick == t)]; a = g[g.pick.notna() & (np.where(g.pick == g.away, g.home, g.away) == t)]
        bw, aw = int((b.graded & b.win).sum()), int((a.graded & a.win).sum())
        teams.append(dict(team=t, backed=int(b.graded.sum()), backed_w=bw, backed_pl=float(np.nansum(b.flat_pl)), against=int(a.graded.sum()), against_w=aw,
                          against_pl=float(np.nansum(a.flat_pl))))
    tm = pd.DataFrame(teams); tm['net'] = tm.backed_pl + tm.against_pl; tm['key'] = tm.net + (tm.backed + tm.against) / 1000
    out['teams'] = tm.sort_values('key', ascending=False)
    flags = [1 if (r.graded and r.win) else (-1 if r.graded else 0) for r in g.itertuples()]
    out['streak'] = streaks(flags)
    run, peak, dd = bank(np.where(g.graded, g.flat_pl, 0)); out['peak'], out['dd'] = float(peak.max()), float(min(0, dd.min()))
    gg = g[g.graded]; out['vs_odds'] = (int(gg.win.sum()) - float(gg.chance.sum()), float(gg.chance.sum()))
    out['avg_price'] = float(gg.odds.mean()); out['breakeven'] = float(gg.chance.mean())
    return out


# ------------------------------------------------------------------ Expert Scout
def scout(ctx):
    G, P, R, last, you = ctx['G'], ctx['P'], ctx['R'], ctx['last'], ctx['you']
    absline = G.hline.abs().fillna(99); cons = P[T.BOT_CONSENSUS]; rows = []
    def rate(p, m):
        g = p.notna() & G.winner.notna() & m
        return (p[g] == G.winner[g]).sum() / g.sum() if g.sum() >= 5 else np.nan
    for t in R.sort_values('order').index:
        p = P[t]
        dogs = p.notna() & G.winner.notna() & (p == G.dog)
        agree = p.notna() & P[you].notna()
        rows.append(dict(tipper=t, overall=R.at[t, 'win_pct'], last3=rate(p, G.week >= last - 2), close=rate(p, absline <= 3), bigfav=rate(p, (absline >= 7) & (absline < 99)),
                         dogs=f'{int((dogs & (p == G.winner)).sum())} of {int(dogs.sum())}', against=rate(p, cons.notna() & (p != cons)), ats=R.at[t, 'ats_pct'],
                         agrees=np.nan if t == you else ((p == P[you]) & agree).sum() / agree.sum() if agree.sum() else np.nan))
    X = pd.DataFrame(rows).set_index('tipper')
    diffs = pd.DataFrame({k: X[k] - X[k].mean() for k in ('last3', 'close', 'bigfav', 'against')}).fillna(-9)
    labels = {'last3': 'Recent form', 'close': 'Close games', 'bigfav': 'Big favourites', 'against': 'Fading the crowd'}
    X['strongest'] = [('—' if diffs.loc[t].max() <= 0 else labels[diffs.loc[t].idxmax()]) for t in X.index]
    return X


# ------------------------------------------------------------------ Head to Head
def head_to_head(ctx, opp):
    G, P, S, you = ctx['G'], ctx['P'], ctx['S'], ctx['you']
    if not opp or opp not in P.columns: opp = ctx['experts'][0]
    a, b = P[you], P[opp]
    def res(p): return pd.Series(np.where(p.notna() & G.winner.notna(), np.where(p == G.winner, 1.0, 0.0), np.nan), index=G.index)
    def pl(p):
        o = np.where(p == G.away, G.aodds, np.where(p == G.home, G.hodds, np.nan)); r = res(p)
        return pd.Series(np.where(r == 1, S['tip'] * (o - 1), np.where(r == 0, -S['tip'], np.nan)), index=G.index)
    ra, rb, pa, pb = res(a), res(b), pl(a), pl(b)
    dis = a.notna() & b.notna() & (a != b)
    weeks = []; run = 0
    for wk in range(1, NW + 1):
        m = G.week == wk
        if ctx['meta'].played[wk] == 0: weeks.append(dict(week=wk)); continue
        y, t = ra[m].sum(), rb[m].sum(); run += y - t
        weeks.append(dict(week=wk, you=y, them=t, edge=y - t, running=run, your_pl=np.nansum(pa[m]), their_pl=np.nansum(pb[m])))
    games = []
    for i in G.index[dis]:
        r = G.loc[i]
        games.append(dict(week=r.week, game=f'{r.away} @ {r.home}' + (f' ({int(r.away_pts)}–{int(r.home_pts)})' if r.played else ''), you=a[i], them=b[i],
                          winner=r.winner or '', right='' if not r.played else ('You' if ra[i] == 1 else ('Them' if rb[i] == 1 else 'Neither (tie)'))))
    every = []
    for e in ctx['experts']:
        d = a.notna() & P[e].notna() & (a != P[e]) & G.winner.notna(); y = int((d & (a == G.winner)).sum()); t = int((d & (P[e] == G.winner)).sum())
        every.append(dict(expert=e, split=int(d.sum()), you=y, them=t, net=y - t, key=(y - t) * 1000 + int(d.sum())))
    ev = pd.DataFrame(every).sort_values('key', ascending=False, kind='stable')
    both = a.notna() & b.notna()
    return dict(opp=opp, you_rec=wl((ra == 1).sum(), (ra == 0).sum()), them_rec=wl((rb == 1).sum(), (rb == 0).sum()),
                dis_rec=wl(int((dis & (ra == 1)).sum()), int((dis & (rb == 1)).sum())), dis_n=int((dis & G.winner.notna()).sum()),
                same=((a == b) & both).sum() / max(1, both.sum()), you_pl=float(np.nansum(pa)), them_pl=float(np.nansum(pb)),
                weeks=pd.DataFrame(weeks).set_index('week'), games=pd.DataFrame(games), every=ev)


# ------------------------------------------------------------------ Value Report
def value_report(ctx):
    G, S = ctx['G'], ctx['S']; rows = []; cum = [0, 0, 0]
    pl_ = G.played
    for wk in range(1, NW + 1):
        g = G[G.week == wk]; gp = g[g.played]
        if g.my_tip_ev.notna().sum() == 0 and g.my_sp_ev.notna().sum() == 0: rows.append(dict(week=wk)); continue
        d = dict(week=wk)
        for k, ev, act, stake in (('tip', 'my_tip_ev', 'tip_pl', S['tip']), ('sp', 'my_sp_ev', 'sp_pl', S['spread']), ('ou', 'my_ou_ev', 'ou_pl', S['ou'])):
            n = g[ev].notna().sum(); d[f'{k}_n'] = n; d[f'{k}_ev'] = g[ev].mean() if n else np.nan
            if gp[ev].notna().sum():
                d[f'{k}_exp'] = stake * gp[ev].sum(); d[f'{k}_act'] = gp[act].sum(); d[f'{k}_luck'] = d[f'{k}_act'] - d[f'{k}_exp']
        if gp.my_tip_ev.notna().sum() or len(gp):
            d.update(bot_tip=gp.bot_tip_pl.sum(), bot_sp=gp.bot_sp_pl.sum(), bot_ou=gp.bot_ou_pl.sum())
            cum[0] += np.nansum([d.get('tip_exp', 0), d.get('sp_exp', 0), d.get('ou_exp', 0)])
            cum[1] += np.nansum([d.get('tip_act', 0), d.get('sp_act', 0), d.get('ou_act', 0)]); cum[2] += d['bot_tip'] + d['bot_sp'] + d['bot_ou']
            d.update(run_exp=cum[0], run_act=cum[1], run_bot=cum[2])
        rows.append(d)
    W = pd.DataFrame(rows).set_index('week')
    gp = G[G.played]
    bands = []
    for lab, lo, hi in (('Long shot  (<35%)', 0, .35), ('Underdog  (35–50%)', .35, .5), ('Slight fav  (50–65%)', .5, .65), ('Favourite  (65–80%)', .65, .8), ('Big fav  (80%+)', .8, 1.01), ('All tips', 0, 1.01)):
        x = gp[(gp.my_tip_true >= lo) & (gp.my_tip_true < hi)]
        won = (x.tip == x.winner).sum()
        bands.append(dict(label=lab, tips=len(x), exp=x.my_tip_true.sum(), act=won, plus=won - x.my_tip_true.sum(), pct=won / len(x) if len(x) else np.nan, pl=x.tip_pl.sum()))
    took = []
    for lab, ev, pl, stake in (('Tips', 'my_tip_ev', 'tip_pl', S['tip']), ('Spreads', 'my_sp_ev', 'sp_pl', S['spread']), ('Totals', 'my_ou_ev', 'ou_pl', S['ou'])):
        for w_, m in (('with value (EV > 0)' if lab == 'Tips' else 'with value', gp[ev] > 0), ('without value', gp[ev] <= 0)):
            x = gp[m]; took.append(dict(label=f'{lab} {w_}', picks=len(x), won=int((x[pl] > 0).sum()), pct=(x[pl] > 0).mean() if len(x) else np.nan,
                                       act=x[pl].sum(), exp=stake * x[ev].sum()))
    return dict(weeks=W, bands=bands, took=took, wins_vs_true=((gp.tip == gp.winner) & gp.tip.notna()).sum() - gp.my_tip_true.sum(),
                true_wins=gp.my_tip_true.sum(), bot_tip=gp.bot_tip_pl.sum(), bot_sb=gp.bot_sp_pl.sum() + gp.bot_ou_pl.sum(),
                bot_tip_exp=S['tip'] * gp.best_tip_ev.sum(), bot_sb_exp=S['spread'] * gp.best_sp_ev[gp.best_sp_ev > 0].sum() + S['ou'] * gp.best_tot_ev[gp.best_tot_ev > 0].sum(),
                bot_sb_n=int((gp.best_sp_ev > 0).sum() + (gp.best_tot_ev > 0).sum()))


# ------------------------------------------------------------------ Edge Finder (one week)
def edge_finder(ctx, week=None):
    G, P, S = ctx['G'], ctx['P'], ctx['S']
    have = G[G[['open_aml', 'close_aml', 'open_hline', 'close_hline']].notna().any(axis=1)]
    wk = week or (int(ctx['meta'][ctx['meta'].played > 0].index.max()) if (ctx['meta'].played > 0).any() else 1)
    if week is None and len(have):
        nxt = have[~have.played].week.min()
        wk = int(nxt) if (not np.isnan(nxt) and have[(have.week == nxt)].tip.notna().any()) else wk
    g = G[G.week == wk].copy()
    # expert lean and skill-weighted lean
    R = ctx['R']; ex = ctx['experts']
    wts = {e: max(0.0, np.log(R.at[e, 'win_pct'] / (1 - R.at[e, 'win_pct']))) if 0 < (R.at[e, 'win_pct'] if not np.isnan(R.at[e, 'win_pct']) else 0) < 1 else 0.0 for e in ex}
    eh, sw = [], []
    for i in g.index:
        picks = {e: P.at[i, e] for e in ex if isinstance(P.at[i, e], str) and P.at[i, e]}
        n = len(picks); h = sum(1 for v in picks.values() if v == g.at[i, 'home'])
        eh.append(h / n if n else np.nan)
        den = sum(wts[e] for e in picks); sw.append(sum(wts[e] for e, v in picks.items() if v == g.at[i, 'home']) / den if den else (h / n if n else np.nan))
    g['exp_home'] = eh; g['skill_home'] = sw
    g['lean'] = [('' if np.isnan(a) or np.isnan(b) else ('Experts ⇧ home' if a - b >= 0.15 else ('Experts ⇩ home' if b - a >= 0.15 else 'In line'))) for a, b in zip(g.exp_home, g.true_h)]
    def top(kind):
        rows = []
        if kind == 'tip':
            for r in g.itertuples():
                if not np.isnan(r.best_tip_ev): rows.append((r.best_tip_ev, f'{r.best_tip} to win', r.aodds if r.best_tip == r.away else r.hodds, r.true_a if r.best_tip == r.away else r.true_h, S['tip'], f'{r.away} @ {r.home}', r.game))
        elif kind == 'sp':
            for r in g.itertuples():
                if not np.isnan(r.best_sp_ev):
                    line = r.hline if r.best_sp == r.home else r.aline
                    rows.append((r.best_sp_ev, f'{r.best_sp} {line:+.1f}', r.sp_hprice if r.best_sp == r.home else r.sp_aprice, r.cov_h if r.best_sp == r.home else r.cov_a, S['spread'], f'{r.away} @ {r.home}', r.game))
        else:
            for r in g.itertuples():
                if not np.isnan(r.best_tot_ev):
                    rows.append((r.best_tot_ev, f'{r.best_tot} {r.total:.1f}', r.o_price if r.best_tot == 'Over' else r.u_price, r.p_over if r.best_tot == 'Over' else r.p_under, S['ou'], f'{r.away} @ {r.home}', r.game))
        rows.sort(key=lambda x: -(x[0] + x[6] / 1e7))   # ties: the later game first, as in the original
        return [dict(play=p, price=pr, true=t, ev=e, exp=st * e, game=gm) for e, p, pr, t, st, gm, _ in rows[:5]]
    return dict(week=wk, g=g, top_tip=top('tip'), top_sp=top('sp'), top_ou=top('ou'))


# ------------------------------------------------------------------ Money extras: tiles, where the money comes from, by price, locks
def money_extra(ctx):
    G, S, M = ctx['G'], ctx['S'], ctx['money']
    t = G[G.tip_res.notna() & G.tip_pl.notna()].copy(); t['res'] = np.where(t.tip_pl > 0, 'W', 'L')
    t['favdog'] = np.where(t.tip_odds <= np.minimum(t.aodds, t.hodds), 'Fav', 'Dog'); t['ha'] = np.where(t.tip == t.home, 'Home', 'Away')
    t['staked'] = S['tip'] * t.tip_lock
    sp = G[G.sp_res.notna()].copy(); sp['res'] = sp.sp_res.map({'✓': 'W', '✗': 'L', 'Push': 'P'}); sp['staked'] = S['spread'] * sp.sp_lock
    sp['side'] = np.where(sp.sp_line < 0, 'Fav', np.where(sp.sp_line > 0, 'Dog', 'Pick')); sp['ha'] = np.where(sp.spread_bet == sp.home, 'Home', 'Away')
    ou = G[G.ou_res.notna()].copy(); ou['res'] = ou.ou_res.map({'✓': 'W', '✗': 'L', 'Push': 'P'}); ou['staked'] = S['ou'] * ou.ou_lock
    def row(x, pl, price):
        w, l, p = (x.res == 'W').sum(), (x.res == 'L').sum(), (x.res == 'P').sum()
        return dict(bets=w + l + p, wlp=wl(w, l, p), pct=w / (w + l) if w + l else np.nan, staked=x.staked.sum(), pl=x[pl].sum(),
                    roi=x[pl].sum() / x.staked.sum() if x.staked.sum() else np.nan, price=x[price].mean() if len(x) else np.nan)
    where = {'Backed the favourite': row(t[t.favdog == 'Fav'], 'tip_pl_real', 'tip_odds'), 'Backed the underdog': row(t[t.favdog == 'Dog'], 'tip_pl_real', 'tip_odds'),
             'Backed the home team': row(t[t.ha == 'Home'], 'tip_pl_real', 'tip_odds'), 'Backed the away team': row(t[t.ha == 'Away'], 'tip_pl_real', 'tip_odds'),
             'Laid the points (fav)': row(sp[sp.side == 'Fav'], 'sp_pl_real', 'sp_price'), 'Took the points (dog)': row(sp[sp.side == 'Dog'], 'sp_pl_real', 'sp_price'),
             "Pick'em (0)": row(sp[sp.side == 'Pick'], 'sp_pl_real', 'sp_price'), 'Home team': row(sp[sp.ha == 'Home'], 'sp_pl_real', 'sp_price'),
             'Away team': row(sp[sp.ha == 'Away'], 'sp_pl_real', 'sp_price'), 'Backed the over': row(ou[ou.ou_bet == 'Over'], 'ou_pl_real', 'ou_price'),
             'Backed the under': row(ou[ou.ou_bet == 'Under'], 'ou_pl_real', 'ou_price')}
    price = []
    for lab, lo, hi in (('Under 1.40', 0, 1.4), ('1.40 – 1.69', 1.4, 1.7), ('1.70 – 1.99', 1.7, 2), ('2.00 – 2.49', 2, 2.5), ('2.50 – 3.49', 2.5, 3.5), ('3.50 +', 3.5, 1e9)):
        x = t[(t.tip_odds >= lo) & (t.tip_odds < hi)]
        w, l = (x.res == 'W').sum(), (x.res == 'L').sum()
        price.append(dict(label=lab, tips=w + l, wl=wl(w, l), pct=w / (w + l) if w + l else np.nan, needed=1 / x.tip_odds.mean() if len(x) else np.nan,
                          staked=x.staked.sum(), pl=x.tip_pl_real.sum(), roi=x.tip_pl_real.sum() / x.staked.sum() if x.staked.sum() else np.nan))
    locks = []
    L = ctx['inp']['weeks']
    for wk in range(1, NW + 1):
        lk = L[wk]['locks']; g = G[G.week == wk]; d = dict(week=wk)
        if lk.get('tip'):
            m = g[(g.away == lk['tip']) | (g.home == lk['tip'])]
            if len(m):
                r = m.iloc[0]; d.update(tip=lk['tip'], tip_game=f'{r.away} @ {r.home}', tip_odds=r.tip_odds if r.tip == lk['tip'] else np.nan,
                                         tip_res=('to play' if r.tip_res is None else ('W' if r.tip_pl > 0 else 'L')) if r.tip == lk['tip'] else '',
                                         tip_pl=r.tip_pl_real if (r.tip == lk['tip'] and r.tip_res) else np.nan, tip_check='' if r.tip == lk['tip'] else "tip lock isn't your tip")
        if lk.get('spread'):
            m = g[(g.away == lk['spread']) | (g.home == lk['spread'])]
            if len(m):
                r = m.iloc[0]; ok = r.spread_bet == lk['spread']
                d.update(sp=lk['spread'], sp_game=f'{r.away} @ {r.home}', sp_line=r.sp_line if ok else np.nan, sp_res=(('to play' if r.sp_res is None else {'✓': 'W', '✗': 'L', 'Push': 'P'}[r.sp_res]) if ok else ''),
                         sp_pl=r.sp_pl_real if (ok and r.sp_res) else np.nan, sp_check='' if ok else "spread lock isn't your bet")
        if lk.get('ou'):
            m = g[(g.away == lk['ou']) | (g.home == lk['ou'])]
            if len(m):
                r = m.iloc[0]; ok = bool(r.ou_bet)
                d.update(ou=lk['ou'], ou_game=f'{r.away} @ {r.home}', ou_bet=r.ou_bet or '', ou_res=(('to play' if r.ou_res is None else {'✓': 'W', '✗': 'L', 'Push': 'P'}[r.ou_res]) if ok else ''),
                         ou_pl=r.ou_pl_real if (ok and r.ou_res) else np.nan, ou_check='' if ok else 'no O/U bet on that game')
        pls = [d.get(k) for k in ('tip_pl', 'sp_pl', 'ou_pl') if d.get(k) is not None and not np.isnan(d.get(k))]
        if pls: d['lock_pl'] = sum(pls); d['extra'] = d['lock_pl'] * (S['lock'] - 1) / S['lock']
        locks.append(d)
    return dict(where=where, price=price, locks=pd.DataFrame(locks).set_index('week'))


# ------------------------------------------------------------------ cells of the original workbook, for verification
def original_cells(ctx):
    G, P, R, W, meta, you = ctx['G'], ctx['P'], ctx['R'], ctx['W'], ctx['meta'], ctx['you']
    cells = {}
    # week tabs
    for wk in range(1, NW + 1):
        c = {}; g = G[G.week == wk]
        for r in g.itertuples():
            i = 10 + r.game - 1; j = 30 + r.game - 1
            c[f'F{i}'] = r.tip_res or ''; c[f'G{i}'] = r.aodds; c[f'H{i}'] = r.hodds; c[f'I{i}'] = r.hline; c[f'J{i}'] = r.total
            c[f'M{i}'] = r.winner or ''; c[f'N{i}'] = r.tip_pl if not np.isnan(r.tip_pl) else ''
            c[f'C{j}'] = r.aline; c[f'D{j}'] = r.sp_aprice; c[f'E{j}'] = r.hline; c[f'F{j}'] = r.sp_hprice
            c[f'K{j}'] = r.total; c[f'L{j}'] = r.o_price; c[f'N{j}'] = r.u_price
            c[f'H{j}'] = r.sp_towin if not np.isnan(r.sp_towin) else ''; c[f'I{j}'] = r.sp_res or ''; c[f'J{j}'] = r.sp_pl if not np.isnan(r.sp_pl) else ''
            c[f'P{j}'] = r.ou_towin if not np.isnan(r.ou_towin) else ''; c[f'Q{j}'] = r.ou_res or ''; c[f'R{j}'] = r.ou_pl if not np.isnan(r.ou_pl) else ''
        cells[f'Wk {wk}'] = c
    # Records weekly wins and season columns
    c = {}
    for i, t in enumerate(R.index[:36]):
        r = 5 + i
        for wk in range(1, 9): c[f'{"CDEFGHIJ"[wk - 1]}{r}'] = W.at[t, wk]
        for col, k in (('BE', 'W'), ('BF', 'L'), ('BG', 'graded'), ('BH', 'win_pct'), ('BI', 'pl'), ('BK', 'ats_w'), ('BL', 'ats_l'), ('BN', 'weeks_won'),
                       ('BO', 'best_wk'), ('BP', 'worst_wk'), ('BQ', 'tens'), ('BR', 'pace'), ('BS', 'form3'), ('BT', 'last_wk'), ('BU', 'dog_picks'), ('BV', 'dog_wins'),
                       ('BW', 'same_as_you'), ('BX', 'picks'), ('CA', 'rank')):
            c[f'{col}{r}'] = R.at[t, k]
    cells['Records'] = c
    # Leaderboard
    c = {}; L = R.sort_values('order')
    for i, (t, r) in enumerate(L.iterrows()):
        x = 5 + i
        c.update({f'A{x}': r['rank'], f'B{x}': t, f'C{x}': ctx['outlets'][t], f'D{x}': r.W, f'E{x}': r.L, f'F{x}': r.win_pct, f'G{x}': R.W.max() - r.W,
                  f'H{x}': r.pace, f'I{x}': r.last_wk, f'J{x}': r.form3, f'K{x}': r.best_wk, f'L{x}': r.worst_wk, f'M{x}': r.tens, f'N{x}': r.weeks_won,
                  f'O{x}': r.pl, f'P{x}': r.roi, f'Q{x}': f'{r.ats_w}–{r.ats_l}', f'R{x}': r.ats_pct, f'S{x}': f'{r.dog_wins} of {r.dog_picks}',
                  f'T{x}': '' if t == you else r.same_pct})
    for _, r in ctx['race'].iterrows():
        x = 46 + int(r.week)
        if 'leader' in r and isinstance(r.get('leader'), str):
            c.update({f'B{x}': r.leader, f'D{x}': r.leader_wins, f'E{x}': r.you, f'F{x}': r.gap, f'G{x}': f'#{int(r.your_rank)}', f'H{x}': r.top_expert,
                      f'K{x}': r.consensus, f'L{x}': r.favourites})
    cells['Leaderboard'] = c
    # Money week-by-week
    c = {}; M = ctx['money']
    for wk, r in M.iterrows():
        x = 12 + wk
        if np.isnan(r.get('staked', np.nan)): continue
        c.update({f'C{x}': wl(r.tip_w, r.tip_l), f'D{x}': r.tip_staked, f'E{x}': r.tip_pl, f'G{x}': wl(r.sp_w, r.sp_l, r.sp_p), f'H{x}': r.sp_staked,
                  f'I{x}': r.sp_pl, f'K{x}': wl(r.ou_w, r.ou_l, r.ou_p), f'L{x}': r.ou_staked, f'M{x}': r.ou_pl, f'O{x}': r.staked, f'P{x}': r.returned,
                  f'Q{x}': r.pl, f'S{x}': r.running, f'T{x}': r.high, f'U{x}': r.below})
    cells['Money'] = c
    # Spreads & Totals
    st = ctx['spreads']; c = {}
    def put(c, r, cols, d):
        for k, v in zip(cols, ('n', 'w', 'l', 'pct', 'said', 'plus', 'pl', 'roi')):
            c[f'{k}{r}'] = d[v] if not (v in ('pct', 'said', 'plus', 'roi') and d['n'] == 0) else ''
    for r, k in zip((20, 21, 22, 28, 29, 30, 31, 37, 38, 45, 46), st['sp_rows']): put(c, r, 'CDEFGHIJ', st['sp_rows'][k])
    for r, k in zip((20, 21, 28, 29, 30, 31, 37, 38, 39, 45, 46), st['ou_rows']): put(c, r, 'OPQRSTUV', st['ou_rows'][k])
    for wk, r in st['weeks'].iterrows():
        if not isinstance(r.get('sp'), str): continue
        col = 'CDEFGHIJKLMNOPQRST'[wk - 1]
        c.update({f'{col}11': r.sp, f'{col}12': r.sp_pl, f'{col}13': r.ou, f'{col}14': r.ou_pl, f'{col}15': r.both})
    sp, ou = st['sp'], st['ou']
    spw, spl, spp = (sp.sp_res == '✓').sum(), (sp.sp_res == '✗').sum(), (sp.sp_res == 'Push').sum()
    ow, ol, op = (ou.ou_res == '✓').sum(), (ou.ou_res == '✗').sum(), (ou.ou_res == 'Push').sum()
    S = ctx['S']; spl_ = sp.sp_pl.sum(); oul = ou.ou_pl.sum()
    fm2 = lambda x: ('+' if x >= 0 else '-') + f'${abs(x):,.2f}'
    pct = lambda x: f'{x * 100:.1f}%'
    roi = lambda x: ('+' if x >= 0 else '-') + f'{abs(x) * 100:.1f}%'
    cur = lambda t: (f'W{t[0]}' if t[0] >= 0 else f'L{-t[0]}')
    c.update({'B5': wl(spw, spl, spp), 'C5': fm2(spl_), 'F5': wl(ow, ol, op), 'I5': fm2(oul), 'M5': fm2(spl_ + oul),
              'B7': pct(spw / (spw + spl)) + ' · need 52.4% at 1.91', 'C7': 'ROI ' + roi(spl_ / ((spw + spl) * S['spread'])), 'F7': pct(ow / (ow + ol)) + ' correct',
              'I7': 'ROI ' + roi(oul / ((ow + ol) * S['ou'])), 'M7': f'{spw + spl + ow + ol} bets · ROI ' + roi((spl_ + oul) / ((spw + spl) * S['spread'] + (ow + ol) * S['ou'])),
              'Q5': f'Spread {cur(st["sp_streak"])} · O/U {cur(st["ou_streak"])}', 'Q7': f'peak +${st["peak"]:,.0f} · deepest drop -${abs(st["dd"]):,.0f}'})
    cells['Spreads & Totals'] = c
    # My Stats
    ms = ctx['mystats']; c = {}
    for r, k in zip(range(18, 24), ms['price']): put(c, r, 'CDEFGHIJ', ms['price'][k])
    for r, k in zip((18, 19), ms['favdog']): put(c, r, 'OPQRSTUV', ms['favdog'][k])
    for r, k in zip((24, 25), ms['ha']): put(c, r, 'OPQRSTUV', ms['ha'][k])
    for r, k in zip((31, 32, 33), ms['slot']): put(c, r, 'CDEFGHIJ', ms['slot'][k])
    for r, k in zip((31, 32), ms['div']): put(c, r, 'OPQRSTUV', ms['div'][k])
    for r, k in zip((39, 40), ms['experts']): put(c, r, 'CDEFGHIJ', ms['experts'][k])
    for r, k in zip((39, 40, 41), ms['ats']): put(c, r, 'OPQRSTUV', ms['ats'][k])
    for r, d in zip(range(47, 51), ms['crowd']): c.update({f'C{r}': d['games'], f'D{r}': d['crowd_right'], f'E{r}': d['against'], f'G{r}': d['pl']})
    tm = ms['teams']; sel = pd.concat([tm.head(4), tm.tail(4).iloc[::-1]])
    from nflmodel.tipping_inputs import TEAMS
    for r, (_, t) in zip(range(47, 55), sel.iterrows()):
        c.update({f'L{r}': f'{t.team}  ·  {TEAMS[t.team][0]}' + ('  ▲' if t.key >= 0 else '  ▼'), f'O{r}': t.backed, f'P{r}': wl(t.backed_w, t.backed - t.backed_w),
                  f'Q{r}': t.backed_pl, f'R{r}': t.against, f'S{r}': wl(t.against_w, t.against - t.against_w), f'T{r}': t.against_pl, f'U{r}': t.net})
    g = ms['g']; gg = g[g.graded]
    fm0 = lambda x: ('+' if x >= 0 else '-') + f'${abs(x):,.0f}'
    c.update({'B5': wl(gg.win.sum(), len(gg) - gg.win.sum()), 'C5': fm0(np.nansum(gg.flat_pl)), 'F5': f'{ms["vs_odds"][0]:+.1f} wins', 'F7': f'the prices expected {ms["vs_odds"][1]:.1f}',
              'I5': f'{ms["avg_price"]:.2f}', 'I7': f'break-even at these prices: {ms["breakeven"] * 100:.0f}%', 'M5': f'W{ms["streak"][1]} / L{ms["streak"][2]}',
              'Q5': fm0(ms['peak']) + ' peak', 'Q7': 'deepest drop ' + ('-$' + f'{abs(ms["dd"]):,.0f}' if ms['dd'] < 0 else '$0')})
    for wk in range(1, NW + 1):
        if ctx['meta'].played[wk] == 0: continue
        col = 'CDEFGHIJKLMNOPQRST'[wk - 1]; x = g[g.week == wk]
        c.update({f'{col}11': W.at[you, wk], f'{col}12': float(np.nansum(x.flat_pl)), f'{col}13': 1 + int((W[wk] > W.at[you, wk]).sum())})
    cells['My Stats'] = c
    extra_cells(ctx, cells)
    return cells


def extra_cells(ctx, cells):
    """Expert Scout, Head to Head, Value Report, Edge Finder and the rest of Money, laid out as in the original workbook."""
    nan = lambda v: '' if v is None or (isinstance(v, float) and np.isnan(v)) else v
    # Expert Scout
    c = {}
    for i, (t, r) in enumerate(ctx['scout'].iterrows()):
        x = 5 + i
        c.update({f'B{x}': t, f'C{x}': ctx['outlets'][t], f'D{x}': nan(r.overall), f'E{x}': nan(r.last3), f'F{x}': nan(r.close), f'G{x}': nan(r.bigfav),
                  f'H{x}': r.dogs, f'I{x}': nan(r.against), f'J{x}': nan(r.ats), f'K{x}': nan(r.agrees), f'L{x}': r.strongest})
    cells['Expert Scout'] = c
    # Head to Head
    h = ctx['h2h']; c = {'D4': h['opp'], 'B7': h['you_rec'], 'D7': h['them_rec'], 'F7': h['dis_rec'],
                         'B9': money_text(h['you_pl']) + ' profit', 'D9': money_text(h['them_pl']) + ' profit', 'F9': f"you–them, over {h['dis_n']} games"}
    for wk, r in h['weeks'].iterrows():
        x = 14 + wk
        if np.isnan(r.get('you', np.nan)): continue
        c.update({f'C{x}': r.you, f'D{x}': r.them, f'E{x}': r.edge, f'F{x}': r.running, f'G{x}': r.your_pl, f'H{x}': r.their_pl})
    for i, r in h['games'].head(40).iterrows():   # the original lists the first 40
        x = 15 + i
        c.update({f'J{x}': i + 1, f'K{x}': f'Wk {r.week}', f'L{x}': r.game, f'M{x}': r.you, f'N{x}': r.them, f'O{x}': r.winner or 'to play',
                  f'P{x}': 'Them' if r.right == 'Neither (tie)' else r.right})   # the original labels a tie 'Them'
    for i, r in enumerate(h['every'].itertuples()):
        x = 37 + i
        c.update({f'B{x}': i + 1, f'C{x}': r.expert, f'E{x}': r.split, f'F{x}': r.you, f'G{x}': r.them, f'H{x}': r.net})
    cells['Head to Head'] = c
    # Value Report
    v = ctx['value']; c = {}; W = v['weeks']
    for wk, r in W.iterrows():
        x = 12 + wk
        if np.isnan(r.get('tip_n', np.nan)): continue
        for cols, k in (('CDEFG', 'tip'), ('HIJKL', 'sp'), ('MNOPQ', 'ou')):
            for col, f in zip(cols, ('n', 'ev', 'exp', 'act', 'luck')): c[f'{col}{x}'] = nan(r[f'{k}_{f}'])
        if not np.isnan(r.get('bot_tip', np.nan)):
            c.update({f'R{x}': r.bot_tip, f'S{x}': r.bot_sp, f'T{x}': r.bot_ou, f'U{x}': r.run_exp, f'V{x}': r.run_act, f'W{x}': r.run_bot, f'X{x}': r.run_act - r.run_exp})
    G = ctx['G']; gp = G[G.played]; S = ctx['S']
    for cols, k, ev, act, st in (('CDEFG', 'tip', 'my_tip_ev', 'tip_pl', S['tip']), ('HIJKL', 'sp', 'my_sp_ev', 'sp_pl', S['spread']), ('MNOPQ', 'ou', 'my_ou_ev', 'ou_pl', S['ou'])):
        n = G[ev].notna().sum(); e = st * gp[ev].sum(); a = gp[act].sum()
        for col, val in zip(cols, (n, G[ev].mean(), e, a, a - e)): c[f'{col}31'] = val
    last = W.dropna(subset=['run_exp']).iloc[-1]
    c.update({'R31': W.bot_tip.sum(), 'S31': W.bot_sp.sum(), 'T31': W.bot_ou.sum(), 'U31': last.run_exp, 'V31': last.run_act, 'W31': last.run_bot, 'X31': last.run_act - last.run_exp})
    c.update({'B6': c['F31'], 'F6': c['K31'], 'J6': c['P31'], 'N6': v['wins_vs_true'], 'R6': v['bot_tip'], 'V6': v['bot_sb']})
    for i, b in enumerate(v['bands']):
        x = 35 + i; c.update({f'B{x}': b['label'], f'D{x}': b['tips'], f'E{x}': b['exp'], f'F{x}': b['act'], f'G{x}': b['plus'], f'H{x}': nan(b['pct']), f'I{x}': b['pl']})
    for i, b in enumerate(v['took']):
        x = 35 + i; c.update({f'P{x}': b['picks'], f'Q{x}': b['won'], f'R{x}': nan(b['pct']), f'S{x}': b['act'], f'T{x}': b['exp']})
    cells['Value Report'] = c
    # Edge Finder
    e = ctx['edge']; c = {}
    cols = dict(D='aodds', E='hodds', F='true_a', G='true_h', H='ev_a', I='ev_h', J='best_tip', K='tip', L='my_tip_ev', M='c_hline', N='hline', O='cov_h', P='cov_a',
                Q='ev_hs', R='ev_as', S='best_sp', T='spread_bet', U='my_sp_ev', V='c_total', W='total', X='p_over', Y='p_under', Z='ev_o', AA='ev_u', AB='best_tot',
                AC='ou_bet', AD='my_ou_ev', AE='exp_home', AF='skill_home', AG='true_h', AH='lean')
    for i, r in enumerate(e['g'].itertuples()):
        x = 14 + i; c[f'B{x}'] = f'{r.away}  @  {r.home}'
        for col, k in cols.items(): c[f'{col}{x}'] = nan(getattr(r, k))
    for (pc, cl), lst in zip((('B', 'CFGHIJ'), ('M', 'NQRSTU'), ('X', 'YABACADAEAF')), (e['top_tip'], e['top_sp'], e['top_ou'])):
        cl = list(cl) if pc != 'X' else ['Y', 'AB', 'AC', 'AD', 'AE', 'AF']
        for i, d in enumerate(lst):
            x = 34 + i; c[f'{pc}{x}'] = i + 1
            for col, k in zip(cl, ('play', 'price', 'true', 'ev', 'exp', 'game')): c[f'{col}{x}'] = d[k]
    cells['Edge Finder'] = c
    # Money: tiles, season row, where the money comes from, tips by price, locks
    M = ctx['money']; mx = ctx['money_x']; c = cells['Money']
    played = M.dropna(subset=['staked'])
    tw, tl = int(played.tip_w.sum()), int(played.tip_l.sum())
    c.update({'B6': played.pl.sum(), 'F6': played.tip_pl.sum(), 'J6': played.sp_pl.sum(), 'N6': played.ou_pl.sum(), 'R6': played.pl.max(), 'V6': played.high.max(),
              'C31': wl(tw, tl), 'D31': played.tip_staked.sum(), 'E31': played.tip_pl.sum(), 'F31': played.tip_pl.sum() / played.tip_staked.sum(),
              'G31': wl(played.sp_w.sum(), played.sp_l.sum(), played.sp_p.sum()), 'H31': played.sp_staked.sum(), 'I31': played.sp_pl.sum(), 'J31': played.sp_pl.sum() / played.sp_staked.sum(),
              'K31': wl(played.ou_w.sum(), played.ou_l.sum(), played.ou_p.sum()), 'L31': played.ou_staked.sum(), 'M31': played.ou_pl.sum(), 'N31': played.ou_pl.sum() / played.ou_staked.sum(),
              'O31': played.staked.sum(), 'P31': played.returned.sum(), 'Q31': played.pl.sum(), 'R31': played.pl.sum() / played.staked.sum(), 'S31': played.running.iloc[-1], 'T31': played.high.max()})
    for x, k in zip((36, 37, 38, 39, 41, 42, 43, 44, 45, 47, 48), mx['where']):
        d = mx['where'][k]; c.update({f'D{x}': d['bets'], f'E{x}': d['wlp'], f'F{x}': nan(d['pct']), f'G{x}': d['staked'], f'H{x}': d['pl'], f'I{x}': nan(d['roi']), f'J{x}': nan(d['price'])})
    for i, d in enumerate(mx['price']):
        x = 35 + i; c.update({f'O{x}': d['tips'], f'P{x}': d['wl'], f'Q{x}': nan(d['pct']), f'R{x}': nan(d['needed']), f'S{x}': d['staked'], f'T{x}': d['pl'], f'U{x}': nan(d['roi'])})
    for wk, r in mx['locks'].iterrows():
        x = 55 + wk
        for col, k in (('C', 'tip'), ('D', 'tip_odds'), ('E', 'tip_res'), ('F', 'tip_pl'), ('G', 'tip_game'), ('H', 'sp'), ('I', 'sp_line'), ('J', 'sp_res'), ('K', 'sp_pl'), ('L', 'sp_game'),
                       ('M', 'ou'), ('N', 'ou_bet'), ('O', 'ou_res'), ('P', 'ou_pl'), ('Q', 'ou_game'), ('R', 'lock_pl'), ('S', 'extra')):
            if k in r.index: c[f'{col}{x}'] = nan(r[k])
