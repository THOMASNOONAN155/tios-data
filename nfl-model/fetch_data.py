"""Download real NFL data from nflverse and build compact per-game tables.

Sources (all public, no login):
  games / closing lines / rest / roof / weather / starting QBs:
      https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv
  play-by-play with EPA (nflfastR model):
      https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet
  official injury reports:
      https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv
  snap counts (Pro-Football-Reference via nflverse):
      https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv
  player id map (gsis <-> pfr):
      https://github.com/nflverse/nflverse-data/releases/download/players/players.csv

Usage:
  python3 fetch_data.py                 # all seasons (2006..current), skips files already present
  python3 fetch_data.py --current 2026  # re-download only the current season's files + games.csv
Raw files go to data/raw/ (not committed). Outputs (committed):
  data/games.csv, data/team_games.csv, data/qb_games.csv, data/injury_out.csv, data/manifest.json
"""
import argparse, hashlib, json, os, sys, time, urllib.request
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'data', 'raw'); OUT = os.path.join(HERE, 'data')
GAMES_URL = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
REL = 'https://github.com/nflverse/nflverse-data/releases/download'
FIRST = 2006
PBP_COLS = ['game_id', 'season', 'week', 'season_type', 'posteam', 'defteam', 'play_type', 'epa', 'success', 'wp',
            'pass', 'rush', 'qb_dropback', 'id', 'qb_epa', 'fumble', 'fumble_lost', 'interception', 'weather']


def get(url, dest, force=False):
    if os.path.exists(dest) and not force:
        return dest
    for attempt in range(4):
        try:
            tmp = dest + '.part'
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, 'wb') as f:
                f.write(r.read())
            os.replace(tmp, dest); print('  got', os.path.basename(dest)); return dest
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print('  NOT AVAILABLE (404):', url); return None
            err = e
        except Exception as e:  # network hiccup
            err = e
        time.sleep(2 ** (attempt + 1))
    sys.exit(f'Could not download {url}: {err}\nDownload it by hand into {dest} and re-run.')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()[:16]


def team_game_table(pbp):
    """Offensive aggregates per (game, team). wp filter 5-95% = 'garbage time removed' (as in the original model)."""
    p = pbp[pbp.play_type.isin(['pass', 'run']) & pbp.epa.notna() & pbp.posteam.notna()].copy()
    p['ngt'] = ((p.wp >= 0.05) & (p.wp <= 0.95)).astype(int)
    p['is_pass'] = (p.qb_dropback == 1).astype(int)
    p['pass_epa'] = p.epa * p.is_pass; p['rush_epa'] = p.epa * (1 - p.is_pass)
    p['epa_gt'] = p.epa * p.ngt; p['succ_gt'] = p.success * p.ngt
    p['pass_epa_gt'] = p.pass_epa * p.ngt; p['pass_gt'] = p.is_pass * p.ngt
    k = ['game_id', 'season', 'week', 'posteam', 'defteam']
    a = p.groupby(k).agg(plays=('epa', 'size'), epa=('epa', 'sum'), succ=('success', 'sum'),
                         pass_plays=('is_pass', 'sum'), pass_epa=('pass_epa', 'sum'), rush_epa=('rush_epa', 'sum'),
                         plays_gt=('ngt', 'sum'), epa_gt=('epa_gt', 'sum'), succ_gt=('succ_gt', 'sum'),
                         pass_gt=('pass_gt', 'sum'), pass_epa_gt=('pass_epa_gt', 'sum')).reset_index()
    f = pbp[pbp.posteam.notna()].groupby(k).agg(fumbles=('fumble', 'sum'), fumbles_lost=('fumble_lost', 'sum'),
                                                ints=('interception', 'sum')).reset_index()
    return a.merge(f, on=k, how='left').rename(columns={'posteam': 'team', 'defteam': 'opp'})


def weather_table(pbp):
    """Temperature / wind parsed from the NFL gamebook weather string carried in play-by-play (fills gaps in games.csv)."""
    w = pbp.groupby('game_id').weather.first().dropna().reset_index()
    w['temp_pbp'] = pd.to_numeric(w.weather.str.extract(r'Temp:\s*(-?\d+)')[0], errors='coerce')
    w['wind_pbp'] = pd.to_numeric(w.weather.str.extract(r'Wind:[^\d]*(\d+)\s*mph', flags=2)[0], errors='coerce')
    w.loc[w.weather.str.contains('calm', case=False), 'wind_pbp'] = w.wind_pbp.fillna(0)
    return w[['game_id', 'temp_pbp', 'wind_pbp']]


def qb_game_table(pbp):
    d = pbp[(pbp.qb_dropback == 1) & pbp.qb_epa.notna() & pbp.id.notna()]
    return d.groupby(['game_id', 'season', 'week', 'posteam', 'id']).agg(dropbacks=('qb_epa', 'size'), qb_epa=('qb_epa', 'sum')) \
            .reset_index().rename(columns={'posteam': 'team', 'id': 'player_id'})


def injury_table(season, players):
    """Players listed Out/Doubtful on the final official report, with their snap share in that team's PREVIOUS games."""
    inj = get(f'{REL}/injuries/injuries_{season}.csv', f'{RAW}/injuries_{season}.csv')
    snp = get(f'{REL}/snap_counts/snap_counts_{season}.csv', f'{RAW}/snap_counts_{season}.csv')
    if not inj or not snp: return None
    i = pd.read_csv(inj, low_memory=False); s = pd.read_csv(snp, low_memory=False)
    i = i[i.report_status.isin(['Out', 'Doubtful']) & (i.game_type == 'REG')]
    s = s[s.game_type == 'REG'].merge(players, left_on='pfr_player_id', right_on='pfr_id', how='left')
    s = s.sort_values('week')
    rows = []
    for (team, wk), grp in i.groupby(['team', 'week']):
        prior = s[(s.team == team) & (s.week < wk)]
        if prior.empty: continue
        ngames = prior.week.nunique()
        share = prior.groupby('gsis_id').agg(off=('offense_pct', 'sum'), de=('defense_pct', 'sum'), pos=('position', 'last'))
        share[['off', 'de']] /= ngames   # average share of team snaps over the team's previous games (0 if absent)
        for _, r in grp.iterrows():
            if r.gsis_id in share.index:
                x = share.loc[r.gsis_id]
                rows.append(dict(season=season, week=wk, team=team, gsis_id=r.gsis_id, name=r.full_name, pos=r.position,
                                 status=r.report_status, off_share=round(float(x.off), 3), def_share=round(float(x.de), 3)))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--current', type=int); ap.add_argument('--first', type=int, default=FIRST)
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    g = pd.read_csv(get(GAMES_URL, f'{RAW}/games.csv', force=True))
    last = int(g.season.max()) if not a.current else a.current
    seasons = [a.current] if a.current else list(range(a.first, last + 1))
    g[g.season >= a.first].to_csv(f'{OUT}/games.csv', index=False)
    man = {'games.csv': {'url': GAMES_URL, 'sha': sha(f'{RAW}/games.csv'), 'fetched': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}}
    tg_path, qb_path, ij_path = f'{OUT}/team_games.csv', f'{OUT}/qb_games.csv', f'{OUT}/injury_out.csv'
    TG = [pd.read_csv(tg_path)] if a.current and os.path.exists(tg_path) else []
    QB = [pd.read_csv(qb_path)] if a.current and os.path.exists(qb_path) else []
    IJ = [pd.read_csv(ij_path)] if a.current and os.path.exists(ij_path) else []
    if a.current:
        TG = [x[x.season != a.current] for x in TG]; QB = [x[x.season != a.current] for x in QB]; IJ = [x[x.season != a.current] for x in IJ]
    wx_path = f'{OUT}/weather_pbp.csv'
    WX = [pd.read_csv(wx_path)] if a.current and os.path.exists(wx_path) else []
    if a.current: WX = [x[~x.game_id.str.startswith(str(a.current))] for x in WX]
    pl = get(f'{REL}/players/players.csv', f'{RAW}/players.csv', force=bool(a.current))
    players = pd.read_csv(pl, low_memory=False, usecols=['gsis_id', 'pfr_id']).dropna().drop_duplicates('pfr_id')
    for s in seasons:
        print('season', s)
        f = get(f'{REL}/pbp/play_by_play_{s}.parquet', f'{RAW}/pbp_{s}.parquet', force=bool(a.current))
        if not f: continue
        pbp = pd.read_parquet(f, columns=PBP_COLS)
        TG.append(team_game_table(pbp)); QB.append(qb_game_table(pbp)); WX.append(weather_table(pbp))
        man[f'pbp_{s}'] = {'url': f'{REL}/pbp/play_by_play_{s}.parquet', 'sha': sha(f), 'plays': int(len(pbp))}
        if s >= 2012:
            if a.current:
                for nm in (f'injuries_{s}.csv', f'snap_counts_{s}.csv'):
                    if os.path.exists(f'{RAW}/{nm}'): os.remove(f'{RAW}/{nm}')
            t = injury_table(s, players)
            if t is not None: IJ.append(t); man[f'injuries_{s}'] = {'url': f'{REL}/injuries/injuries_{s}.csv', 'rows_out_doubtful': int(len(t))}
    pd.concat(TG).sort_values(['season', 'week', 'game_id']).to_csv(tg_path, index=False)
    pd.concat(QB).sort_values(['season', 'week', 'game_id']).to_csv(qb_path, index=False)
    pd.concat(WX).to_csv(wx_path, index=False)
    if IJ: pd.concat(IJ).sort_values(['season', 'week']).to_csv(ij_path, index=False)
    mpath = f'{OUT}/manifest.json'
    old = json.load(open(mpath)) if os.path.exists(mpath) else {}
    old.update(man); json.dump(old, open(mpath, 'w'), indent=1)
    print('done')


if __name__ == '__main__':
    main()
