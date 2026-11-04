"""Download and assemble every data source into tidy tables.

All raw files live in cache/ (git-ignored) and are re-downloaded by weekly.py. Nothing here invents
data: if a source cannot be fetched we raise DataUnavailable with the exact file and URL to get.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import urllib.request
from datetime import datetime

import numpy as np
import pandas as pd

from .config import CACHE, CONFIG, CURRENT, SEASONS, label

FD_DIRECT = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"
FD_MIRROR = "https://raw.githubusercontent.com/ValentinMartine/football_predictions/main/data/raw/{code}_E0.csv"
FD_MIRROR2 = "https://raw.githubusercontent.com/Mentat-Uran/ScoutFootball_for_World_Cup/main/data/raw/football_data/{code}/E0.csv"
XGABORA = "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv"
FPL_REPO = "https://github.com/vaastav/Fantasy-Premier-League"
OPENFOOTBALL_EN = "https://github.com/openfootball/england"
OPENFOOTBALL_CL = "https://github.com/openfootball/champions-league"
MANAGERS = "https://raw.githubusercontent.com/rohanhs568/next_manager_sacked/main/data/processed/labelled_spells.csv"

FPL_SPARSE = [
    "/data/*/fixtures.csv", "/data/*/teams.csv", "/data/*/players_raw.csv", "/data/*/gws/merged_gw.csv",
    "/data/2019-20/understat/understat_*", "/data/2020-21/understat/understat_*",
    "/data/2021-22/understat/understat_*",
    "/data/2022-23/understat/*", "/data/2023-24/understat/*", "/data/2024-25/understat/*",
]


class DataUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------------------------------------
# Downloading
# --------------------------------------------------------------------------------------------
def _http_get(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "epl-model/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _download(urls: list[str], dest, min_bytes: int = 1000) -> str:
    """Try each URL in order; return the one that worked."""
    errors = []
    for u in urls:
        try:
            data = _http_get(u)
            if len(data) >= min_bytes:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                return u
            errors.append(f"{u}: only {len(data)} bytes")
        except Exception as e:  # network policy / 404 / timeout
            errors.append(f"{u}: {e}")
    raise DataUnavailable(f"Could not download {dest.name}. Tried:\n  " + "\n  ".join(errors))


def _git_sync(url: str, path, sparse: list[str] | None = None) -> None:
    if (path / ".git").exists():
        subprocess.run(["git", "-C", str(path), "fetch", "-q", "--depth", "1", "origin"], check=True)
        subprocess.run(["git", "-C", str(path), "reset", "-q", "--hard", "FETCH_HEAD"], check=True)
        return
    args = ["git", "clone", "-q", "--depth", "1"]
    if sparse:
        args += ["--filter=blob:none", "--no-checkout"]
    subprocess.run(args + [url, str(path)], check=True)
    if sparse:
        subprocess.run(["git", "-C", str(path), "sparse-checkout", "init", "--no-cone"], check=True)
        (path / ".git" / "info" / "sparse-checkout").write_text("\n".join(sparse) + "\n")
        subprocess.run(["git", "-C", str(path), "checkout", "-q", "HEAD"], check=True)


def fetch_all(refresh: bool = True, log=print) -> dict:
    """Download everything into cache/. Past seasons are fetched once; the current season and the
    git-based sources are refreshed when refresh=True. Returns {source: url_used}."""
    used = {}
    for code in SEASONS:
        dest = CACHE / "fd" / f"{code}_E0.csv"
        # completed seasons are downloaded once; the current season is refreshed on every run
        if dest.exists() and dest.stat().st_size > 1000 and (code != CURRENT or not refresh):
            continue
        used[f"fd_{code}"] = _download([FD_DIRECT.format(code=code), FD_MIRROR.format(code=code)], dest)
        log(f"  football-data {label(code)} <- {used[f'fd_{code}']}")
    # independent second mirror of football-data (integrity check of the primary mirror)
    for code in SEASONS[4:-1]:
        dest = CACHE / "fd_mirror2" / f"{code}_E0.csv"
        if not dest.exists():
            try:
                _download([FD_MIRROR2.format(code=code)], dest)
            except DataUnavailable as e:
                log(f"  (optional) {e}")
    dest = CACHE / "xgabora_matches.csv"
    if not dest.exists() or refresh:
        used["xgabora"] = _download([XGABORA], dest, min_bytes=10_000_000)
        log("  xgabora/ClubElo match file refreshed")
    dest = CACHE / "managers.csv"
    if not dest.exists() or refresh:
        used["managers"] = _download([MANAGERS], dest)
    for name, url, sparse in [("fpl", FPL_REPO, FPL_SPARSE), ("of_england", OPENFOOTBALL_EN, None),
                              ("of_cl", OPENFOOTBALL_CL, None)]:
        path = CACHE / name
        if path.exists() and not refresh:
            continue
        try:
            _git_sync(url, path, sparse)
        except subprocess.CalledProcessError as e:
            raise DataUnavailable(f"git clone/fetch of {url} failed: {e}") from e
        log(f"  {name} synced from {url}")
    return used


# --------------------------------------------------------------------------------------------
# Name handling
# --------------------------------------------------------------------------------------------
_ALIASES = None


def team(name: str) -> str:
    global _ALIASES
    if _ALIASES is None:
        _ALIASES = dict(pd.read_csv(CONFIG / "team_names.csv").values)
    name = str(name).strip().replace("_", " ")
    return _ALIASES.get(name, name)


def season_of(date: pd.Timestamp) -> str:
    y = date.year if date.month >= 7 else date.year - 1
    return f"{y}-{str(y + 1)[2:]}"


# --------------------------------------------------------------------------------------------
# football-data.co.uk (results, closing odds, cards, shots, 2026-27 xG)
# --------------------------------------------------------------------------------------------
def _first(df, cols):
    """Row-wise first non-null among candidate columns (sharpest bookmaker first)."""
    out = pd.Series(np.nan, index=df.index)
    src = pd.Series("", index=df.index, dtype=object)
    for c in cols:
        if c in df:
            v = pd.to_numeric(df[c], errors="coerce")
            m = out.isna() & v.notna()
            out[m] = v[m]
            src[m] = c
    return out, src


def load_football_data(folder="fd") -> pd.DataFrame:
    rows = []
    for code in SEASONS:
        f = CACHE / folder / f"{code}_E0.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f, encoding="utf-8-sig", encoding_errors="replace")
        d = d.dropna(subset=["HomeTeam", "AwayTeam", "FTHG"])
        out = pd.DataFrame({
            "season": label(code),
            "date": pd.to_datetime(d["Date"], dayfirst=True, format="mixed"),
            "time": d.get("Time", pd.Series("", index=d.index)).fillna(""),
            "home": d["HomeTeam"].map(team), "away": d["AwayTeam"].map(team),
            "hg": d["FTHG"].astype(int), "ag": d["FTAG"].astype(int),
            "hthg": d["HTHG"], "htag": d["HTAG"],
            "hs": d["HS"], "as_": d["AS"], "hst": d["HST"], "ast": d["AST"],
            "hc": d["HC"], "ac": d["AC"], "hy": d["HY"], "ay": d["AY"], "hr": d["HR"], "ar": d["AR"],
            "referee": d.get("Referee"),
        })
        for k in ["H", "D", "A"]:
            # sharp closing price: Pinnacle, else Betfair exchange, else market average
            out[f"c_{k}"], src = _first(d, [f"PSC{k}", f"BFEC{k}", f"AvgC{k}"])
            out[f"avgc_{k}"], _ = _first(d, [f"AvgC{k}"])
            out[f"b365_{k}"], _ = _first(d, [f"B365{k}"])  # pre-closing Bet365 (cross-check only)
            if k == "H":
                out["c_src"] = src.str.replace("H", "", regex=False)
        out["c_over"], _ = _first(d, ["PC>2.5", "BFEC>2.5", "AvgC>2.5"])
        out["c_under"], _ = _first(d, ["PC<2.5", "BFEC<2.5", "AvgC<2.5"])
        out["pre_over"], _ = _first(d, ["P>2.5", "Avg>2.5", "BbAv>2.5", "B365>2.5"])
        out["pre_under"], _ = _first(d, ["P<2.5", "Avg<2.5", "BbAv<2.5", "B365<2.5"])
        out["c_ahline"], _ = _first(d, ["AHCh"])
        out["c_ahh"], _ = _first(d, ["PCAHH", "BFECAHH", "AvgCAHH"])
        out["c_aha"], _ = _first(d, ["PCAHA", "BFECAHA", "AvgCAHA"])
        out["fd_hxg"], _ = _first(d, ["HxG"])
        out["fd_axg"], _ = _first(d, ["AxG"])
        rows.append(out)
    df = pd.concat(rows, ignore_index=True)
    return df.sort_values(["date", "home"]).reset_index(drop=True)


# --------------------------------------------------------------------------------------------
# FPL (official Premier League fantasy data, mirrored by vaastav): fixtures, minutes, Opta xG
# --------------------------------------------------------------------------------------------
def _fpl_teams(season):
    f = CACHE / "fpl" / "data" / season / "teams.csv"
    if not f.exists():
        return None
    t = pd.read_csv(f)
    return dict(zip(t["id"], t["name"].map(team)))


def load_fpl_fixtures() -> pd.DataFrame:
    out = []
    for f in sorted(glob.glob(str(CACHE / "fpl" / "data" / "*" / "fixtures.csv"))):
        season = f.split(os.sep)[-2]
        names = _fpl_teams(season)
        if names is None:
            continue
        d = pd.read_csv(f)
        ko = pd.to_datetime(d["kickoff_time"], utc=True)
        out.append(pd.DataFrame({
            "season": season, "fixture": d["id"], "gw": d["event"],
            "kickoff": ko, "date": ko.dt.tz_convert("Europe/London").dt.tz_localize(None).dt.normalize(),
            "home": d["team_h"].map(names), "away": d["team_a"].map(names),
            "hg": d["team_h_score"], "ag": d["team_a_score"], "finished": d["finished"].astype(bool),
        }))
    return pd.concat(out, ignore_index=True)


def load_fpl_players() -> pd.DataFrame:
    """One row per player per match (2016-17 onwards): minutes, starts, Opta xG, cards, pens."""
    out = []
    for f in sorted(glob.glob(str(CACHE / "fpl" / "data" / "*" / "gws" / "merged_gw.csv"))):
        season = f.split(os.sep)[-3]
        d = pd.read_csv(f, encoding_errors="replace", low_memory=False)
        names = _fpl_teams(season)
        if "team" in d and names is not None:
            tm = d["team"].map(team)
        else:
            continue  # seasons without a team column cannot be attributed reliably
        ko = pd.to_datetime(d["kickoff_time"], utc=True)
        g = pd.DataFrame({
            "season": season, "fixture": d["fixture"], "gw": d.get("GW", d.get("round")),
            "date": ko.dt.tz_convert("Europe/London").dt.tz_localize(None).dt.normalize(),
            "player": d["name"].astype(str).str.replace(r"_\d+$", "", regex=True).str.replace("_", " "),
            "element": d["element"], "position": d.get("position"), "team": tm, "was_home": d["was_home"],
            "minutes": d["minutes"], "starts": d.get("starts"),
            "xg": d.get("expected_goals"), "xa": d.get("expected_assists"),
            "goals": d["goals_scored"], "assists": d["assists"], "own_goals": d["own_goals"],
            "pen_missed": d["penalties_missed"], "red": d["red_cards"],
        })
        out.append(g)
    p = pd.concat(out, ignore_index=True)
    return p.drop_duplicates(["season", "fixture", "element"])


# --------------------------------------------------------------------------------------------
# Understat xG (mirrored by vaastav): team match files 2019-22, player match logs 2022-25
# --------------------------------------------------------------------------------------------
def load_understat_team() -> pd.DataFrame:
    out = []
    for season in ["2019-20", "2020-21", "2021-22"]:
        for f in glob.glob(str(CACHE / "fpl" / "data" / season / "understat" / "understat_*.csv")):
            tname = os.path.basename(f)[len("understat_"):-4]
            if tname in ("player", "team"):
                continue
            d = pd.read_csv(f)
            out.append(pd.DataFrame({
                "season": season, "team": team(tname),
                "date": pd.to_datetime(d["date"]).dt.normalize(), "h_a": d["h_a"],
                "xg": d["xG"], "xga": d["xGA"], "npxg": d["npxG"], "npxga": d["npxGA"],
                "gf": d["scored"], "ga": d["missed"]}))
    return pd.concat(out, ignore_index=True)


def load_understat_players() -> pd.DataFrame:
    """Player match logs -> team-match xG totals for EPL matches 2021-22..2024-25."""
    recs = []
    for season in ["2021-22", "2022-23", "2023-24", "2024-25"]:
        folder = CACHE / "fpl" / "data" / season / "understat"
        roster = pd.read_csv(folder / "understat_player.csv") if (folder / "understat_player.csv").exists() else None
        if roster is None:
            continue
        teams_of = {int(r.id): [team(t) for t in str(r.team_title).split(",")] for r in roster.itertuples()}
        start_year = int(season[:4])
        for f in glob.glob(str(folder / "*_[0-9]*.csv")):
            m = re.search(r"_(\d+)\.csv$", f)
            if not m or int(m.group(1)) not in teams_of:
                continue
            d = pd.read_csv(f)
            d = d[d["season"] == start_year]
            if d.empty:
                continue
            ts = teams_of[int(m.group(1))]
            d = d.assign(h_team=d["h_team"].map(team), a_team=d["a_team"].map(team))
            side = np.where(d["h_team"].isin(ts), "h", np.where(d["a_team"].isin(ts), "a", ""))
            d = d.assign(side=side, uid=int(m.group(1)))
            recs.append(d[d["side"] != ""][["id", "date", "h_team", "a_team", "side", "uid", "xG", "npxG",
                                            "goals", "npg", "shots"]])
    p = pd.concat(recs, ignore_index=True).drop_duplicates(["id", "uid"])
    agg = p.groupby(["id", "date", "h_team", "a_team", "side"])[["xG", "npxG", "goals", "npg", "shots"]].sum()
    agg = agg.unstack("side").fillna(0)
    agg.columns = [f"{side}_{c}" for c, side in agg.columns]
    agg = agg.reset_index()
    agg["date"] = pd.to_datetime(agg["date"]).dt.normalize()
    return agg


# --------------------------------------------------------------------------------------------
# European fixtures (openfootball) and managers
# --------------------------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                                       "Nov", "Dec"], 1)}


_DATE_RE = re.compile(r"\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3}) (\d{1,2})(?: (\d{4}))?\s*$")
_VFIRST_RE = re.compile(r"\s+(?:\d{1,2}[.:]\d{2}\s+)?(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)")
_SFIRST_RE = re.compile(r"\s+(?:\d{1,2}[.:]\d{2}\s+)?(\S.*?)\s+(\d+)-(\d+)(?:\s+\(\d+-\d+\))?\s+(\S.*?)\s*$")


def load_european() -> pd.DataFrame:
    """Dates on which English clubs played UEFA matches (CL/EL/UECL; coverage as openfootball has it)."""
    recs = []
    for f in glob.glob(str(CACHE / "of_cl" / "*" / "*.txt")):
        comp = os.path.basename(f)[:-4]
        if comp.endswith("q"):
            continue
        season = f.split(os.sep)[-2]
        y0 = int(season[:4])
        cur = None
        for line in open(f, encoding="utf-8").read().splitlines():
            m = _DATE_RE.match(line)
            if m:
                mon, day = _MONTHS[m.group(1)], int(m.group(2))
                yr = int(m.group(3)) if m.group(3) else (y0 if mon >= 7 else y0 + 1)
                cur = datetime(yr, mon, day)
                continue
            if cur is None or "(ENG)" not in line:
                continue
            for name in re.findall(r"([A-Z][^()]*?) \(ENG\)", line):
                name = re.sub(r"^\s*\d{1,2}[.:]\d{2}\s+", "", name).strip()
                name = re.sub(r"^v\s+", "", name)
                recs.append({"date": pd.Timestamp(cur), "team": team(name), "comp": comp})
    return pd.DataFrame(recs).drop_duplicates()


def load_managers() -> pd.DataFrame:
    d = pd.read_csv(CACHE / "managers.csv")
    return pd.DataFrame({"team": d["team_name"].map(team), "manager": d["manager_name"],
                         "start": pd.to_datetime(d["start_date"]).dt.normalize(),
                         "end": pd.to_datetime(d["end_date"]).dt.normalize(),
                         "departure": d["departure_reason"]})


def load_openfootball_results() -> pd.DataFrame:
    recs = []
    for f in glob.glob(str(CACHE / "of_england" / "20*" / "1-premierleague.txt")):
        season = f.split(os.sep)[-2]
        y0 = int(season[:4])
        cur = None
        for line in open(f, encoding="utf-8").read().splitlines():
            m = _DATE_RE.match(line)
            if m:
                mon, day = _MONTHS[m.group(1)], int(m.group(2))
                yr = int(m.group(3)) if m.group(3) else (y0 if mon >= 7 else y0 + 1)
                cur = pd.Timestamp(datetime(yr, mon, day))
                continue
            if cur is None:
                continue
            m = _VFIRST_RE.match(line)  # "Home v Away 1-0 (0-0)"
            if m:
                h, a, hg, ag = m.group(1), m.group(2), m.group(3), m.group(4)
            else:
                m = _SFIRST_RE.match(line)  # "Home 1-0 (0-0) Away"
                if not m:
                    continue
                h, hg, ag, a = m.group(1), m.group(2), m.group(3), m.group(4)
            recs.append({"season": season, "date": cur, "home": team(h.strip()), "away": team(a.strip()),
                         "hg": int(hg), "ag": int(ag)})
    return pd.DataFrame(recs)


# --------------------------------------------------------------------------------------------
# Unified match table
# --------------------------------------------------------------------------------------------
def _attach_by_teams(m, other, cols, max_days=3):
    """Join `other` (with season-free home/away/date) onto matches by (home, away) nearest date."""
    o = other.copy()
    key = m[["home", "away", "date"]].reset_index()
    j = key.merge(o, on=["home", "away"], suffixes=("", "_o"))
    j["gap"] = (j["date"] - j["date_o"]).abs().dt.days
    j = j[j["gap"] <= max_days].sort_values("gap").drop_duplicates("index")
    return j.set_index("index")[cols]


def build_matches() -> pd.DataFrame:
    m = load_football_data()
    # --- xG -----------------------------------------------------------------------------
    m["us_hxg"] = m["us_axg"] = m["us_hnpxg"] = m["us_anpxg"] = np.nan
    ut = load_understat_team()
    uh = ut[ut["h_a"] == "h"].rename(columns={"team": "home", "date": "date_o"})
    ua = ut[ut["h_a"] == "a"][["team", "date", "xg", "npxg"]].rename(
        columns={"team": "away", "date": "date_o", "xg": "axg2", "npxg": "anpxg2"})
    uh = uh.merge(ua, left_on=["date_o"], right_on=["date_o"])
    # pair the home row with the away row of the same match: away team's xGA == home xG
    uh = uh[np.isclose(uh["xga"], uh["axg2"])]
    uh = uh.drop_duplicates(["home", "date_o"])
    j = _attach_by_teams(m, uh, ["xg", "xga", "npxg", "npxga"])
    m.loc[j.index, ["us_hxg", "us_axg", "us_hnpxg", "us_anpxg"]] = j.values
    up = load_understat_players().rename(columns={"h_team": "home", "a_team": "away", "date": "date_o"})
    j = _attach_by_teams(m, up, ["h_xG", "a_xG", "h_npxG", "a_npxG"])
    fill = m.loc[j.index, "us_hxg"].isna()
    idx = fill[fill].index
    m.loc[idx, ["us_hxg", "us_axg", "us_hnpxg", "us_anpxg"]] = j.loc[idx].values
    m["us_player_sum"] = False
    m.loc[idx, "us_player_sum"] = True

    # Opta xG from FPL player rows (sum per team per fixture)
    p = load_fpl_players()
    fx = load_fpl_fixtures()
    px = p.dropna(subset=["xg"]).groupby(["season", "fixture", "was_home"])["xg"].sum().unstack("was_home")
    px.columns = ["axg_o" if not c else "hxg_o" for c in px.columns]
    fx2 = fx.merge(px.reset_index(), on=["season", "fixture"], how="inner").rename(columns={"date": "date_o"})
    # FPL publishes expected_goals only from 2022-23; zero-sum fixtures before that are not data
    fx2 = fx2[(fx2["hxg_o"] + fx2["axg_o"]) > 0]
    j = _attach_by_teams(m, fx2, ["hxg_o", "axg_o"])
    m["opta_hxg"] = m["opta_axg"] = np.nan
    m.loc[j.index, ["opta_hxg", "opta_axg"]] = j.values

    # Unified xG: Understat where available, else Opta (FPL), else football-data's published xG
    m["hxg"], m["axg"], m["xg_src"] = m["us_hxg"], m["us_axg"], np.where(m["us_hxg"].notna(), "understat", "")
    for h, a, s in [("opta_hxg", "opta_axg", "opta"), ("fd_hxg", "fd_axg", "football-data")]:
        mm = m["hxg"].isna() & m[h].notna()
        m.loc[mm, "hxg"], m.loc[mm, "axg"], m.loc[mm, "xg_src"] = m.loc[mm, h], m.loc[mm, a], s
    # penalty attempts (Understat gives each penalty 0.76 xG)
    m["hpen"] = ((m["us_hxg"] - m["us_hnpxg"]) / 0.76).round()
    m["apen"] = ((m["us_axg"] - m["us_anpxg"]) / 0.76).round()

    # --- FPL fixture ids / gameweeks --------------------------------------------------------
    j = _attach_by_teams(m, fx.rename(columns={"date": "date_o"}), ["fixture", "gw"])
    m["fixture"] = m["gw"] = np.nan
    m.loc[j.index, ["fixture", "gw"]] = j.values
    m["fpl_gw"] = m["gw"]
    m["gw"] = season_round(m)
    m["match_id"] = m["season"] + "_" + m["home"] + "_" + m["away"]
    return m


def season_round(m: pd.DataFrame) -> pd.Series:
    """Round number 1-38 from games already played by the two sides (FPL gameweek numbers are not
    consistent across seasons, e.g. 2019-20 ran to GW47 after the COVID restart)."""
    played = {}
    out = []
    for s, h, a in zip(m["season"], m["home"], m["away"]):
        ph, pa = played.get((s, h), 0), played.get((s, a), 0)
        out.append(int(round((ph + pa) / 2)) + 1)
        played[(s, h)], played[(s, a)] = ph + 1, pa + 1
    return pd.Series(out, index=m.index)


def promoted_teams(m: pd.DataFrame) -> dict:
    """{season: set(teams that were not in the previous Premier League season)}."""
    seasons = sorted(m["season"].unique())
    teams = {s: set(m.loc[m["season"] == s, "home"]) for s in seasons}
    return {s: teams[s] - teams[seasons[i - 1]] for i, s in enumerate(seasons) if i > 0}
