"""Records and every stat shown on the tipping sheets (same definitions as the original workbook's Records / Game Log)."""
import numpy as np, pandas as pd
from nflmodel.tipping import NW, BOT_CONSENSUS, BOT_FAV, BOT_HOME, BOT_DOG, MODEL, LINE


def week_meta(G):
    m = pd.DataFrame(index=range(1, NW + 1))
    m['games'] = G.groupby('week').size().reindex(m.index).fillna(0).astype(int)
    m['played'] = G[G.played].groupby('week').size().reindex(m.index).fillna(0).astype(int)
    m['complete'] = (m.games > 0) & (m.played == m.games)
    return m


def records(G, P, S, experts):
    """Per tipper: weekly wins / graded, season record, P/L, ATS, weeks won, best / worst week, form, dog calls, etc."""
    meta = week_meta(G); last = int(meta[meta.played > 0].index.max()) if (meta.played > 0).any() else 0
    you = P.columns[0]; out = []
    W = pd.DataFrame(index=P.columns, columns=range(1, NW + 1), dtype=float); N = W.copy()
    for t in P.columns:
        p = P[t]; graded = p.notna() & G.winner.notna(); right = graded & (p == G.winner)
        for wk in range(1, NW + 1):
            if meta.played[wk] == 0: continue
            m = G.week == wk
            W.at[t, wk] = right[m].sum(); N.at[t, wk] = graded[m].sum()
    for t in P.columns:
        p = P[t]; graded = p.notna() & G.winner.notna(); right = graded & (p == G.winner)
        odds = np.where(p == G.away, G.aodds.fillna(0), np.where(p == G.home, G.hodds.fillna(0), 0))
        w, n = int(right.sum()), int(graded.sum())
        pl = S['tip'] * (float(np.sum(odds * right)) - n)
        ats_w = int((G.ats_graded & (((p == G.home) & (G.home_ats > 0)) | ((p == G.away) & (G.home_ats < 0)))).sum())
        ats_l = int((G.ats_graded & (((p == G.home) & (G.home_ats < 0)) | ((p == G.away) & (G.home_ats > 0)))).sum())
        wk = W.loc[t]; comp = [x for x in range(1, NW + 1) if meta.complete[x]]
        weeks_won = int(sum((meta.played[x] > 0) and (wk[x] == W[x].max()) for x in range(1, NW + 1) if not np.isnan(wk[x])))
        form = sum(0 if np.isnan(wk.get(x, np.nan)) else wk[x] for x in (last, last - 1, last - 2) if x >= 1) if last else np.nan
        dog_picks = int((p.notna() & (p == G.dog) & G.dog.notna() & G.winner.notna()).sum())
        dog_wins = int((p.notna() & (p == G.dog) & G.dog.notna() & (p == G.winner)).sum())
        same = int(((p == P[you]) & P[you].notna()).sum())
        out.append(dict(tipper=t, W=w, L=n - w, graded=n, win_pct=w / n if n else np.nan, pl=pl, roi=pl / (n * S['tip']) if n else np.nan,
                        ats_w=ats_w, ats_l=ats_l, ats_pct=ats_w / (ats_w + ats_l) if ats_w + ats_l else np.nan, weeks_won=weeks_won,
                        best_wk=np.nanmax(wk.values) if wk.notna().any() else np.nan,
                        worst_wk=min(wk[x] for x in comp) if comp else np.nan, tens=int(sum(wk[x] >= 10 for x in comp)),
                        pace=round(w / n * 272) if n else np.nan, form3=form, last_wk=wk.get(last, np.nan) if last else np.nan,
                        dog_picks=dog_picks, dog_wins=dog_wins, same_as_you=same, picks=int(p.notna().sum())))
    R = pd.DataFrame(out).set_index('tipper')
    R['row'] = range(len(R))
    key = {'Wins': R.W * 100000 + R.pl / 10, 'Win %': R.win_pct.fillna(0) * 1000000 + R.W, 'Profit': R.pl * 100 + R.W}[S.get('rank_by', 'Wins')]
    R['order_key'] = key - R.row / 1000
    R['order'] = R.order_key.rank(ascending=False, method='first').astype(int)
    R['rank'] = R.W.apply(lambda x: 1 + int((R.W > x).sum()))
    ek = R.W * 100000 + R.pl / 10 - R.row / 1000
    top = ek[[e for e in experts if e in R.index]].sort_values(ascending=False).head(5).index
    R['top5'] = R.index.isin(top)
    R['same_pct'] = np.where(R.index == you, np.nan, R.same_as_you / max(1, R.at[you, 'picks']))
    return R, W, N, meta, last


def race(G, P, W, meta, experts, you):
    """Leaderboard 'the race': per week, cumulative leader, you, gap, your rank, top expert, consensus, favourites."""
    rows = []; cum = W.fillna(0).cumsum(axis=1)
    for wk in range(1, NW + 1):
        if meta.played[wk] == 0: rows.append(dict(week=wk)); continue
        c = cum[wk]; mx = c.max(); leaders = c[c == mx].index
        ce = c[[e for e in experts if e in c.index]]; te = ce.idxmax()
        rows.append(dict(week=wk, leader=leaders[0] + (f' +{len(leaders) - 1}' if len(leaders) > 1 else ''), leader_wins=mx, you=c[you], gap=c[you] - mx,
                         your_rank=1 + int((c > c[you]).sum()), top_expert=f'{te} ({int(ce.max())})', consensus=c.get(BOT_CONSENSUS), favourites=c.get(BOT_FAV)))
    return pd.DataFrame(rows)
