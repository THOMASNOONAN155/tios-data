"""This week's injury picture, for every player (not just QBs). Shown in the workbook's Injuries sheet.

Two sources, both refreshed every run:
  * the official NFL practice / game-status reports (nflverse injuries_<season>.csv, downloaded by fetch_data.py):
    every player on a team's report this week, with his latest practice status and game status;
  * data/injury_notes.csv, typed by hand from team and news reports: players on injured reserve or out long-term,
    who no longer appear on the weekly report, plus anything announced before the official report lists it.

Each player gets his average share of the team's snaps over the season's previous games (nflverse snap counts), so the
list can be read by importance: a 90%-snap starter missing matters, a 5%-snap backup does not.

This is information only. The prediction formula is unchanged: non-QB injuries were tested in research round 1
(snap-share-weighted Out/Doubtful players) and round 2 (player value by position) and made predictions worse in both the
development and holdout seasons, so they were dropped (README, "Kept / Tested and dropped"). They still reach the
prediction through the betting line, which moves on injury news. QBs are handled by the starting-QB value and
data/qb_overrides.csv.
"""
import os
import numpy as np
import pandas as pd

from nflmodel.common import RAW, ROOT

NOTES = os.path.join(ROOT, 'data', 'injury_notes.csv')
FIX = {'LA': 'LAR', 'WAS': 'WSH', 'JAC': 'JAX', 'OAK': 'LV', 'SD': 'LAC', 'STL': 'LAR'}
PRACTICE = {'Did Not Participate In Practice': 'Did not practise', 'Limited Participation in Practice': 'Limited',
            'Full Participation in Practice': 'Full'}


def _team(x):
    return x.replace(FIX) if hasattr(x, 'replace') else FIX.get(x, x)


def _norm(n):
    n = str(n).lower().replace('.', '').replace("'", '').replace('-', ' ')
    return ' '.join(w for w in n.split() if w not in ('jr', 'sr', 'ii', 'iii', 'iv', 'v'))


def _snap_share(season, week):
    """Average share of team snaps (offence or defence, whichever is larger) in the team's games before `week`."""
    f = os.path.join(RAW, f'snap_counts_{season}.csv')
    if not os.path.exists(f): return {}
    s = pd.read_csv(f, low_memory=False)
    s = s[(s.game_type == 'REG') & (s.week < week)].copy()
    if s.empty: return {}
    s['team'] = _team(s.team)
    games = s.groupby('team').week.nunique()
    s['share'] = s[['offense_pct', 'defense_pct']].max(axis=1)
    tot = s.groupby(['team', 'player']).share.sum()
    return {(t, _norm(p)): v / games[t] for (t, p), v in tot.items()}


def official(season, week):
    f = os.path.join(RAW, f'injuries_{season}.csv')
    if not os.path.exists(f): return pd.DataFrame()
    d = pd.read_csv(f, low_memory=False)
    d = d[(d.week == week) & (d.game_type == 'REG')].copy()
    if d.empty: return d
    d['team'] = _team(d.team)
    inj = d.practice_primary_injury.fillna(d.report_primary_injury)
    sec = d.practice_secondary_injury.fillna(d.report_secondary_injury)
    d['injury'] = np.where(sec.notna(), inj.fillna('') + ' / ' + sec.fillna(''), inj.fillna(''))
    d['practice'] = d.practice_status.map(PRACTICE).fillna(d.practice_status)
    d['game_status'] = d.report_status
    return d.rename(columns={'full_name': 'player', 'position': 'pos'})[['team', 'player', 'pos', 'injury', 'practice', 'game_status']]


def notes(season, week):
    if not os.path.exists(NOTES): return pd.DataFrame()
    n = pd.read_csv(NOTES)
    n = n[(n.season == season) & (n.week_from <= week) & (n.week_to.fillna(99) >= week)].copy()
    n['team'] = _team(n.team)
    return n[['team', 'player', 'pos', 'injury', 'status', 'detail', 'source']]


def table(season, week, games):
    """games: list of (away, home, kickoff text). Returns one DataFrame, grouped by game, most important players first."""
    off, nt, share = official(season, week), notes(season, week), _snap_share(season, week)
    rows = []
    for away, home, ko in games:
        for t in (away, home):
            seen = set()
            if not nt.empty:
                for r in nt[nt.team == t].itertuples():
                    seen.add(r.player)
                    rows.append(dict(Game=f'{away} @ {home}', Kickoff=ko, Team=t, Player=r.player, Pos=r.pos, Injury=r.injury,
                                     Practice='', Status=r.status, Detail=r.detail if isinstance(r.detail, str) else '',
                                     Snaps=share.get((t, _norm(r.player)), np.nan), Source=r.source if isinstance(r.source, str) else 'news'))
            if not off.empty:
                for r in off[off.team == t].itertuples():
                    if r.player in seen: continue
                    rows.append(dict(Game=f'{away} @ {home}', Kickoff=ko, Team=t, Player=r.player, Pos=r.pos, Injury=r.injury,
                                     Practice=r.practice if isinstance(r.practice, str) else '',
                                     Status=r.game_status if isinstance(r.game_status, str) else 'Not yet given',
                                     Detail='', Snaps=share.get((t, _norm(r.player)), np.nan), Source='official report'))
    T = pd.DataFrame(rows, columns=['Game', 'Kickoff', 'Team', 'Player', 'Pos', 'Injury', 'Practice', 'Status', 'Detail', 'Snaps', 'Source'])
    if T.empty: return T
    order = {g: i for i, g in enumerate(dict.fromkeys(T.Game))}
    sev = {'Out for season': 0, 'Injured reserve': 1, 'Out': 2, 'Doubtful': 3, 'Questionable': 4}
    T['_g'] = T.Game.map(order); T['_s'] = T.Status.map(sev).fillna(5); T['_n'] = -T.Snaps.fillna(0)
    T = T.sort_values(['_g', 'Team', '_s', '_n']).drop(columns=['_g', '_s', '_n']).reset_index(drop=True)
    return T


def importance(x):
    if x is None or (isinstance(x, float) and np.isnan(x)): return 'No snaps yet'
    return 'Starter' if x >= 0.6 else 'Rotation' if x >= 0.25 else 'Depth'
