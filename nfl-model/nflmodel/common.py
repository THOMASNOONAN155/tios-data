"""Shared data loading and situational features (rest, travel, time zones, weather, divisions)."""
import math, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # nfl-model/
CACHE = os.path.join(ROOT, 'cache')          # downloaded + rebuilt data (git-ignored; weekly.py recreates it)
RAW = os.path.join(CACHE, 'raw')             # raw nflverse files
DATA = CACHE                                 # derived per-game tables live in the cache too
INPUTS = os.path.join(ROOT, 'data')          # hand-edited inputs (committed): qb_overrides.csv
RESULTS = os.path.join(ROOT, 'results')      # research outputs (committed)
OUTPUT = os.path.join(ROOT, 'output')        # weekly reports
CONFIG_PATH = os.path.join(ROOT, 'config', 'model.json')


def config():
    import json
    return json.load(open(CONFIG_PATH))

# Relocated franchises keep one rating history.
FRANCHISE = {'OAK': 'LV', 'SD': 'LAC', 'STL': 'LA'}
DISPLAY = {'LA': 'LAR', 'WAS': 'WSH'}           # how the original workbook writes them
DIVISIONS = {'AFC East': 'BUF MIA NE NYJ', 'AFC North': 'BAL CIN CLE PIT', 'AFC South': 'HOU IND JAX TEN',
             'AFC West': 'DEN KC LV LAC', 'NFC East': 'DAL NYG PHI WAS', 'NFC North': 'CHI DET GB MIN',
             'NFC South': 'ATL CAR NO TB', 'NFC West': 'ARI LA SF SEA'}
TEAMS = sorted(t for v in DIVISIONS.values() for t in v.split())
TIDX = {t: i for i, t in enumerate(TEAMS)}

# Stadium location and standard-time UTC offset, keyed by nflverse stadium_id.
# Hand-entered from public stadium locations (accurate to roughly 0.05 deg); 'nodst' = no daylight saving there.
STADIUMS = {
 'ATL00': (33.758, -84.401, -5), 'ATL97': (33.755, -84.401, -5), 'BAL00': (39.278, -76.623, -5), 'BOS00': (42.091, -71.264, -5),
 'BUF00': (42.774, -78.787, -5), 'BUF01': (43.641, -79.389, -5), 'CAR00': (35.226, -80.853, -5), 'CHI98': (41.862, -87.617, -6),
 'CIN00': (39.095, -84.516, -5), 'CLE00': (41.506, -81.700, -5), 'DAL00': (32.748, -97.093, -6), 'DAL99': (32.840, -96.911, -6),
 'DEN00': (39.744, -105.020, -7), 'DET00': (42.340, -83.046, -5), 'FRA00': (50.069, 8.645, 1), 'GER00': (48.219, 11.625, 1),
 'GNB00': (44.501, -88.062, -6), 'HOU00': (29.685, -95.411, -6), 'IND00': (39.760, -86.164, -5), 'IND99': (39.763, -86.163, -5),
 'JAX00': (30.324, -81.637, -5), 'KAN00': (39.049, -94.484, -6), 'LAX01': (33.953, -118.339, -8), 'LAX97': (33.864, -118.261, -8),
 'LAX99': (34.014, -118.288, -8), 'LON00': (51.556, -0.280, 0), 'LON01': (51.456, -0.341, 0), 'LON02': (51.604, -0.066, 0),
 'MAD01': (40.453, -3.688, 1), 'MEL00': (-37.820, 144.983, 10), 'MEX00': (19.303, -99.150, -6), 'MIA00': (25.958, -80.239, -5),
 'MIN00': (44.974, -93.258, -6), 'MIN01': (44.974, -93.258, -6), 'MIN98': (44.977, -93.225, -6), 'MUN01': (48.219, 11.625, 1),
 'NAS00': (36.166, -86.771, -6), 'NOR00': (29.951, -90.081, -6), 'NYC00': (40.812, -74.077, -5), 'NYC01': (40.814, -74.074, -5),
 'OAK00': (37.752, -122.201, -8), 'PAR00': (48.924, 2.360, 1), 'PHI00': (39.901, -75.168, -5), 'PHO00': (33.528, -112.263, -7),
 'PIT00': (40.447, -80.016, -5), 'RIO00': (-22.912, -43.230, -3), 'SAO00': (-23.545, -46.474, -3), 'SDG00': (32.783, -117.120, -8),
 'SEA00': (47.595, -122.332, -8), 'SFO00': (37.714, -122.386, -8), 'SFO01': (37.403, -121.970, -8), 'STL00': (38.633, -90.189, -6),
 'TAM00': (27.976, -82.503, -5), 'VEG00': (36.091, -115.184, -8), 'WAS00': (38.908, -76.864, -5), 'BRG00': (30.412, -91.184, -6),
 'SAN00': (29.417, -98.479, -6), 'PHO99': (33.426, -111.933, -7)}
# nflverse lists these international games under the designated home team's US stadium; real venues:
VENUE_FIX = {'2025_01_KC_LAC': 'SAO00', '2025_04_MIN_PIT': 'DUB00', '2025_05_MIN_CLE': 'LON02', '2025_06_DEN_NYJ': 'LON02',
             '2025_07_LA_JAX': 'LON00', '2025_10_ATL_IND': 'BER00', '2025_11_WAS_MIA': 'MAD01', '2026_05_PHI_JAX': 'LON02'}
STADIUMS.update({'DUB00': (53.361, -6.251, 0), 'BER00': (52.515, 13.239, 1)})
NO_DST = {'PHO00', 'PHO99', 'RIO00', 'SAO00', 'MEX00'}   # Arizona, Brazil, Mexico (2022+) do not shift with US DST
SOUTH = {'MEL00'}


def miles(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3959 * 2 * math.asin(math.sqrt(h))


def _us_dst(d):
    """US daylight saving: 2nd Sunday of March to 1st Sunday of November."""
    y = d.year
    mar = pd.Timestamp(y, 3, 8); start = mar + pd.Timedelta(days=(6 - mar.weekday()) % 7)
    nov = pd.Timestamp(y, 11, 1); end = nov + pd.Timedelta(days=(6 - nov.weekday()) % 7)
    return start <= d < end


def _offset(sid, d):
    lat, lon, off = STADIUMS[sid]
    if off <= -5 and off >= -8:          # US time zones
        return off + (1 if (sid not in NO_DST and _us_dst(d)) else 0)
    if off in (0, 1):                    # Europe: BST/CEST until last Sunday of October
        octl = pd.Timestamp(d.year, 10, 31); last = octl - pd.Timedelta(days=(octl.weekday() + 1) % 7)
        return off + (1 if d < last else 0)
    if sid in SOUTH:                     # Melbourne: AEDT from first Sunday of October
        o = pd.Timestamp(d.year, 10, 1); first = o + pd.Timedelta(days=(6 - o.weekday()) % 7)
        return off + (1 if d >= first else 0)
    return off


def load_games():
    g = pd.read_csv(os.path.join(DATA, 'games.csv'), low_memory=False)
    for c in ('home_team', 'away_team'):
        g[c] = g[c].replace(FRANCHISE)
    g['date'] = pd.to_datetime(g.gameday)
    g['neutral'] = (g.location == 'Neutral').astype(int)
    g['post'] = (g.game_type != 'REG').astype(int)
    g['div'] = g.div_game.fillna(0).astype(int)
    g = g.sort_values(['season', 'week', 'date', 'gametime', 'game_id']).reset_index(drop=True)
    # each team's home stadium in a season = where it played most 'Home' games
    hs = g[g.location == 'Home'].groupby(['season', 'home_team']).stadium_id.agg(lambda s: s.value_counts().index[0])
    home_sid = hs.to_dict()
    # fall back to previous / next season for future seasons with no home games yet
    def hsid(season, team):
        for s in [season, season - 1, season + 1, season - 2]:
            if (s, team) in home_sid: return home_sid[(s, team)]
        return None
    g['stadium_id'] = [VENUE_FIX.get(i, s) for i, s in zip(g.game_id, g.stadium_id)]
    rows = []
    for r in g.itertuples():
        ven = r.stadium_id if r.stadium_id in STADIUMS else hsid(r.season, r.home_team)
        hh, ha = hsid(r.season, r.home_team), hsid(r.season, r.away_team)
        dh = 0.0 if not r.neutral else miles(STADIUMS[hh], STADIUMS[ven])
        da = miles(STADIUMS[ha], STADIUMS[ven])
        d = r.date
        try:
            hr, mn = map(int, str(r.gametime).split(':')); et = hr + mn / 60
        except ValueError:
            et = 13.0
        # gametime is US Eastern; convert to UTC, then to each body clock
        utc = et - (-4 if _us_dst(d) else -5)
        ven_local = (utc + _offset(ven, d)) % 24
        a_clock = (utc + _offset(ha, d)) % 24; h_clock = (utc + _offset(hh, d)) % 24
        tzshift_a = _offset(ven, d) - _offset(ha, d); tzshift_h = _offset(ven, d) - _offset(hh, d)
        rows.append((dh, da, ven_local, a_clock, h_clock, tzshift_a, tzshift_h))
    x = pd.DataFrame(rows, columns=['miles_h', 'miles_a', 'ko_local', 'ko_clock_a', 'ko_clock_h', 'tz_a', 'tz_h'])
    g = pd.concat([g, x], axis=1)
    # weather: games.csv first, then the gamebook string from play-by-play
    wp = os.path.join(DATA, 'weather_pbp.csv')
    if os.path.exists(wp):
        w = pd.read_csv(wp)
        g = g.merge(w, on='game_id', how='left')
        g['temp'] = g.temp.fillna(g.temp_pbp); g['wind'] = g.wind.fillna(g.wind_pbp)
    g['indoor'] = g.roof.isin(['dome', 'closed']).astype(int)
    g.loc[g.indoor == 1, ['temp', 'wind']] = np.nan
    g['played'] = g.result.notna().astype(int)
    return g


def season_weeks(season):
    return 18 if season >= 2021 else 17
