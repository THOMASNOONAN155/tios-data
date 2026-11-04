"""Tipping engine: everything the original NFL_Tipping workbook worked out with formulas, recomputed in Python from
inputs/tipping_inputs.xlsx, with the same rules:
  fair price  = ROUND(2 / (1/open + 1/close), 2)             (only one entered -> that one)
  fair line   = midpoint of open and close; a quarter-point midpoint goes to the .5 (INT(sum/2)+0.5)
  tips are paid at the FAIR win odds; spreads / totals at the FAIR line and price; pushes return the stake
  locks of the week: that tip / spread bet / over-under bet is staked at Settings x the normal stake
Tippers: you, every expert (in Tippers order), the bots (panel consensus, always the favourite, always the home team,
always the underdog), the old typed 'Stats model' row, and two new ones from nfl-model: Model and Vegas line.
"""
import math
from decimal import Decimal, ROUND_HALF_UP
import numpy as np, pandas as pd
from scipy.stats import norm

NW = 18
BOT_CONSENSUS, BOT_FAV, BOT_HOME, BOT_DOG = 'Panel consensus', 'Always the favourite', 'Always the home team', 'Always the underdog'
MODEL, LINE = 'Model (nfl-model)', 'Vegas line'
TOTALS_SD = 13.42   # original Model!B2: SD of (points scored - closing total), 7,276 games 1999-2025


def xround(x, n=2):
    """Excel ROUND: halves away from zero (Python's round() is banker's rounding)."""
    if x is None or (isinstance(x, float) and math.isnan(x)): return np.nan
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def fair_price(o, c):
    o, c = (np.nan if o is None else o), (np.nan if c is None else c)
    if np.isnan(o) and np.isnan(c): return np.nan
    if np.isnan(o): return c
    if np.isnan(c): return o
    return xround(2 / (1 / o + 1 / c), 2)


def fair_line(o, c):
    if np.isnan(o) and np.isnan(c): return np.nan
    if np.isnan(o): return c
    if np.isnan(c): return o
    s = o + c
    return math.floor(s / 2) + 0.5 if (s % 1) != 0 else s / 2


def to_decimal(p):
    """The original converts American prices (>=100 or <=-100) to decimal; decimal prices pass through."""
    if np.isnan(p): return np.nan
    return 1 + p / 100 if p >= 100 else (1 + 100 / abs(p) if p <= -100 else p)


def _division(t):
    from nflmodel.tipping_inputs import TEAMS
    return TEAMS.get(t, ('', ''))[1]


def slot_type(slot, kickoff):
    s = slot or ''
    if s in ('Kickoff', 'TNF', 'SNF', 'MNF', 'Thanksgiving', 'Christmas', 'Saturday'): return 'Prime time'
    if s in ('London', 'Rio', 'International') or '14:30' in (kickoff or ''): return 'International'
    return 'Sunday slate'


def price_band(p):
    if np.isnan(p): return ''
    return 'Heavy fav' if p < 1.4 else 'Favourite' if p < 1.7 else 'Slight fav' if p < 2 else 'Slight dog' if p < 2.5 else 'Underdog' if p < 3.5 else 'Long shot'


def game_log(inp):
    """One row per game: fair prices/lines, result, fav/dog, your bets with P/L (flat and with locks), value numbers."""
    S = inp['settings']; rows = []
    for wk, w in inp['weeks'].items():
        g = w['games']
        for r in (g.itertuples() if len(g) else []):
            d = r._asdict(); d.pop('Index', None)
            d['aodds'] = fair_price(r.open_aml, r.close_aml); d['hodds'] = fair_price(r.open_hml, r.close_hml)
            d['hline'] = fair_line(r.open_hline, r.close_hline); d['aline'] = -d['hline'] if not np.isnan(d['hline']) else np.nan
            d['sp_aprice'] = fair_price(r.open_aprice, r.close_aprice); d['sp_hprice'] = fair_price(r.open_hprice, r.close_hprice)
            d['total'] = fair_line(r.open_total, r.close_total)
            d['o_price'] = fair_price(r.open_oprice, r.close_oprice); d['u_price'] = fair_price(r.open_uprice, r.close_uprice)
            # value-engine inputs: CLOSING odds (true chances) with open as fallback
            d['c_aodds'] = r.close_aml if r.close_aml > 1 else (r.open_aml if r.open_aml > 1 else np.nan)
            d['c_hodds'] = r.close_hml if r.close_hml > 1 else (r.open_hml if r.open_hml > 1 else np.nan)
            d['c_hline'] = r.close_hline if not np.isnan(r.close_hline) else r.open_hline
            d['c_total'] = r.close_total if not np.isnan(r.close_total) else r.open_total
            played = not (np.isnan(r.away_pts) or np.isnan(r.home_pts))
            d['played'] = played
            d['winner'] = (r.away if r.away_pts > r.home_pts else r.home if r.home_pts > r.away_pts else 'TIE') if played else None
            d['fav'] = (r.away if d['aodds'] < d['hodds'] else r.home) if not (np.isnan(d['aodds']) or np.isnan(d['hodds'])) else None
            d['dog'] = (r.home if d['fav'] == r.away else r.away) if d['fav'] else None
            d['division'] = _division(r.away) == _division(r.home) and _division(r.away) != ''
            d['slot_type'] = slot_type(r.slot, r.kickoff)
            d['home_margin'] = (r.home_pts - r.away_pts) if played else np.nan
            d['ats_graded'] = played and not np.isnan(d['hline'])
            d['home_ats'] = d['home_margin'] + d['hline'] if d['ats_graded'] else np.nan     # > 0 = home covered
            d['total_pts'] = (r.away_pts + r.home_pts) if played else np.nan
            rows.append(d)
    G = pd.DataFrame(rows)
    if G.empty: return G
    L = inp['weeks']
    lock = lambda wk, k: L[wk]['locks'].get(k)
    out = []
    for r in G.itertuples():
        d = {}
        # ---- your tip
        odds = r.aodds if r.tip == r.away else (r.hodds if r.tip == r.home else np.nan)
        d['tip_odds'] = odds
        d['tip_res'] = None if (not r.tip or not r.played) else ('✓' if r.tip == r.winner else '✗')
        d['tip_pl'] = (S['tip'] * (odds - 1) if d['tip_res'] == '✓' else -S['tip']) if (d['tip_res'] and odds and not np.isnan(odds) and odds != 0) else np.nan
        d['tip_lock'] = 1.0 * (S['lock'] if (r.tip and r.tip == lock(r.week, 'tip')) else 1)
        # ---- your spread bet
        if r.spread_bet in (r.away, r.home):
            price = to_decimal(r.sp_aprice if r.spread_bet == r.away else r.sp_hprice)
            line = r.aline if r.spread_bet == r.away else r.hline
            d['sp_price'], d['sp_line'] = price, line
            d['sp_towin'] = S['spread'] * (price - 1) if (not np.isnan(price) and price > 1) else np.nan
            m = ((r.away_pts - r.home_pts) if r.spread_bet == r.away else (r.home_pts - r.away_pts)) + line if (r.played and not np.isnan(line)) else np.nan
            d['sp_margin'] = m
            d['sp_res'] = None if np.isnan(m) else ('✓' if m > 0 else '✗' if m < 0 else 'Push')
            d['sp_pl'] = np.nan if d['sp_res'] is None else ((0 if np.isnan(d['sp_towin']) else d['sp_towin']) if d['sp_res'] == '✓' else (-S['spread'] if d['sp_res'] == '✗' else 0.0))
        else:
            d.update(sp_price=np.nan, sp_line=np.nan, sp_towin=np.nan, sp_margin=np.nan, sp_res=None, sp_pl=np.nan)
        d['sp_lock'] = 1.0 * (S['lock'] if (r.spread_bet and r.spread_bet == lock(r.week, 'spread')) else 1)
        # ---- your over / under
        if r.ou_bet in ('Over', 'Under'):
            price = to_decimal(r.o_price if r.ou_bet == 'Over' else r.u_price); line = r.total
            d['ou_price'], d['ou_line'] = price, line
            d['ou_towin'] = S['ou'] * (price - 1) if (not np.isnan(price) and price > 1) else np.nan
            if r.played and not np.isnan(line):
                res = ('✓' if r.ou_bet == 'Over' else '✗') if r.total_pts > line else (('✓' if r.ou_bet == 'Under' else '✗') if r.total_pts < line else 'Push')
            else:
                res = None
            d['ou_res'] = res
            d['ou_pl'] = np.nan if res is None else ((0 if np.isnan(d['ou_towin']) else d['ou_towin']) if res == '✓' else (-S['ou'] if res == '✗' else 0.0))
        else:
            d.update(ou_price=np.nan, ou_line=np.nan, ou_towin=np.nan, ou_res=None, ou_pl=np.nan)
        ol = lock(r.week, 'ou')
        d['ou_lock'] = 1.0 * (S['lock'] if (r.ou_bet and ol and ol in (r.away, r.home)) else 1)
        # ---- value engine (true chances from the CLOSING odds, EV at your fair prices)
        ta = (1 / r.c_aodds) / (1 / r.c_aodds + 1 / r.c_hodds) if not (np.isnan(r.c_aodds) or np.isnan(r.c_hodds)) else np.nan
        d['true_a'], d['true_h'] = ta, (1 - ta if not np.isnan(ta) else np.nan)
        d['ev_a'] = ta * r.aodds - 1 if not (np.isnan(ta) or np.isnan(r.aodds)) else np.nan
        d['ev_h'] = d['true_h'] * r.hodds - 1 if not (np.isnan(ta) or np.isnan(r.hodds)) else np.nan
        out.append(d)
    G = pd.concat([G, pd.DataFrame(out, index=G.index)], axis=1)
    G['tip_pl_real'] = G.tip_pl * G.tip_lock; G['sp_pl_real'] = G.sp_pl * G.sp_lock; G['ou_pl_real'] = G.ou_pl * G.ou_lock
    G['gid'] = G.week.astype(str) + '_' + G.game.astype(str)
    return G


def spread_cover(table, close_hline, fair_hline):
    """Original Value Log: P(home covers / away covers) at the fair line, from the real-margin table for that CLOSING line."""
    if table is None or np.isnan(close_hline) or np.isnan(fair_hline): return np.nan, np.nan
    row = max(-20, min(20, xround(close_hline * 2, 0) / 2))
    k = -fair_hline
    P = table.loc[row]
    h = P[max(-45, min(45, math.floor(k)))]
    a = 1 - P[max(-45, min(45, -math.floor(-k) - 1))]
    return h, a


def total_chances(close_total, fair_total, sd=TOTALS_SD):
    if np.isnan(close_total) or np.isnan(fair_total): return np.nan, np.nan
    over = 1 - norm.cdf((math.floor(fair_total) + 0.5 - close_total) / sd)
    under = norm.cdf((-math.floor(-fair_total) - 0.5 - close_total) / sd)
    return over, under


def add_value(G, inp, table):
    """Spread / total EVs and the value bot (bets every side with positive EV), as the original Value Log."""
    S = inp['settings']; rows = []
    for r in G.itertuples():
        h, a = spread_cover(table, r.c_hline, r.hline)
        ev_hs = h * (r.sp_hprice - 1) - a if not (np.isnan(h) or np.isnan(r.sp_hprice)) else np.nan
        ev_as = a * (r.sp_aprice - 1) - h if not (np.isnan(a) or np.isnan(r.sp_aprice)) else np.nan
        o, u = total_chances(r.c_total, r.total)
        ev_o = o * (r.o_price - 1) - u if not (np.isnan(o) or np.isnan(r.o_price)) else np.nan
        ev_u = u * (r.u_price - 1) - o if not (np.isnan(u) or np.isnan(r.u_price)) else np.nan
        best_tip = (r.away if r.ev_a >= r.ev_h else r.home) if not (np.isnan(r.ev_a) or np.isnan(r.ev_h)) else None
        best_sp = (r.home if ev_hs >= ev_as else r.away) if not (np.isnan(ev_hs) or np.isnan(ev_as)) else None
        best_tot = ('Over' if ev_o >= ev_u else 'Under') if not (np.isnan(ev_o) or np.isnan(ev_u)) else None
        d = dict(cov_h=h, cov_a=a, ev_hs=ev_hs, ev_as=ev_as, p_over=o, p_under=u, ev_o=ev_o, ev_u=ev_u,
                 best_tip=best_tip, best_tip_ev=max(r.ev_a, r.ev_h) if best_tip else np.nan,
                 best_sp=best_sp, best_sp_ev=max(ev_hs, ev_as) if best_sp else np.nan,
                 best_tot=best_tot, best_tot_ev=max(ev_o, ev_u) if best_tot else np.nan)
        d['my_tip_ev'] = r.ev_a if r.tip == r.away else (r.ev_h if r.tip == r.home else np.nan)
        d['my_sp_ev'] = ev_as if r.spread_bet == r.away else (ev_hs if r.spread_bet == r.home else np.nan)
        d['my_ou_ev'] = ev_o if r.ou_bet == 'Over' else (ev_u if r.ou_bet == 'Under' else np.nan)
        d['my_tip_true'] = r.true_a if r.tip == r.away else (r.true_h if r.tip == r.home else np.nan)
        # value bot
        d['bot_tip_pl'] = (S['tip'] * ((r.aodds if best_tip == r.away else r.hodds) - 1) if r.winner == best_tip else -S['tip']) if (r.winner and best_tip) else np.nan
        if r.played and best_sp and d['best_sp_ev'] > 0:
            m = (1 if best_sp == r.home else -1) * (r.home_pts - r.away_pts + r.hline)
            d['bot_sp_pl'] = S['spread'] * ((r.sp_hprice if best_sp == r.home else r.sp_aprice) - 1) if m > 0 else (0.0 if (r.home_pts - r.away_pts + r.hline) == 0 else -S['spread'])
        else:
            d['bot_sp_pl'] = np.nan
        if r.played and best_tot and d['best_tot_ev'] > 0:
            m = (1 if best_tot == 'Over' else -1) * (r.total_pts - r.total)
            d['bot_ou_pl'] = S['ou'] * ((r.o_price if best_tot == 'Over' else r.u_price) - 1) if m > 0 else (0.0 if r.total_pts == r.total else -S['ou'])
        else:
            d['bot_ou_pl'] = np.nan
        rows.append(d)
    return pd.concat([G, pd.DataFrame(rows, index=G.index)], axis=1)


def picks(G, inp, model_picks=None, include_new=True):
    """Every tipper's pick for every game, as a DataFrame (rows = games, columns = tippers in display order)."""
    names = [n for n, _ in inp['tippers']]
    you, experts_all = names[0], names[1:]
    typed_bots = [n for n, o in inp['tippers'][1:] if str(o).strip() == 'Bot']
    experts = [n for n in experts_all if n not in typed_bots]
    P = pd.DataFrame(index=G.index)
    P[you] = G.tip.values
    for e in experts_all:
        P[e] = [inp['weeks'][r.week]['experts'].get(e, {}).get(r.game) for r in G.itertuples()]
    cons = []
    for i, r in zip(G.index, G.itertuples()):
        v = [P.at[i, e] for e in experts if isinstance(P.at[i, e], str) and P.at[i, e]]
        if not v: cons.append(None); continue
        na, nh = v.count(r.away), v.count(r.home)
        cons.append(r.away if na > nh else r.home if nh > na else r.fav)
    order = [you] + experts
    P[BOT_CONSENSUS] = cons; P[BOT_FAV] = G.fav.values; P[BOT_HOME] = G.home.values; P[BOT_DOG] = G.dog.values
    order += [BOT_CONSENSUS, BOT_FAV, BOT_HOME, BOT_DOG] + typed_bots
    if include_new:
        P[MODEL] = model_picks.reindex(G.gid).values if model_picks is not None else None
        lp = []
        for r in G.itertuples():
            if np.isnan(r.hline): lp.append(r.fav)
            else: lp.append(r.home if r.hline < 0 else (r.away if r.hline > 0 else r.fav))
        P[LINE] = lp
        order += [MODEL, LINE]
    P = P[order]
    P = P.where(P.notna(), None)
    return P


def outlets(inp, P):
    o = {n: out for n, out in inp['tippers']}
    for b in (BOT_CONSENSUS, BOT_FAV, BOT_HOME, BOT_DOG): o[b] = 'Bot'
    o[MODEL] = 'nfl-model'; o[LINE] = 'Betting line'
    return {n: o.get(n, '') for n in P.columns}
